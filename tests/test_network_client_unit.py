from __future__ import annotations

import types

import pytest

import quoridor.network.client as client_mod


class _FakeSock:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.timeout = None
        self.closed = False
        self.fail_close = fail_close

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def close(self) -> None:
        if self.fail_close:
            raise OSError("close failed")
        self.closed = True


def test_connect_returns_immediately_when_already_connected():
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    client._sock = _FakeSock()

    # Should not try opening a new connection.
    client.connect()
    assert client.connected() is True


def test_connect_retries_until_welcome_and_stores_buffer(monkeypatch):
    sock = _FakeSock()
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    sent: list[str] = []

    monkeypatch.setattr(
        client_mod.socket,
        "create_connection",
        lambda *_args, **_kwargs: sock,
    )
    monkeypatch.setattr(
        client_mod,
        "_send_line",
        lambda _sock, message: sent.append(message),
    )
    fake_thread = types.SimpleNamespace(
        start=lambda: None,
        is_alive=lambda: False,
    )
    monkeypatch.setattr(
        client_mod.threading,
        "Thread",
        lambda *args, **kwargs: fake_thread,
    )
    recv_calls = iter(
        [
            (None, "partial", False),  # continue loop
            ("WELCOME id-1", "rest", False),
            ("HELLO_OK 7", "after-hello", False),
        ]
    )
    monkeypatch.setattr(client_mod, "_recv_line", lambda *_a, **_k: next(recv_calls))

    client.connect()

    assert client._sock is sock
    assert client._buffer == "after-hello"
    assert client.client_id == 7
    assert sock.timeout == client_mod._SOCKET_TIMEOUT_SEC
    assert sent == ["HELLO player"]


def test_connect_raises_when_server_closes_and_swallow_close_error(monkeypatch):
    sock = _FakeSock(fail_close=True)
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)

    monkeypatch.setattr(
        client_mod.socket,
        "create_connection",
        lambda *_args, **_kwargs: sock,
    )
    monkeypatch.setattr(client_mod, "_recv_line", lambda *_a, **_k: (None, "", True))

    with pytest.raises(OSError, match="server closed the connection"):
        client.connect()


def test_connect_rejects_unexpected_welcome_line(monkeypatch):
    sock = _FakeSock()
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)

    monkeypatch.setattr(
        client_mod.socket,
        "create_connection",
        lambda *_args, **_kwargs: sock,
    )
    monkeypatch.setattr(
        client_mod,
        "_recv_line",
        lambda *_a, **_k: ("ERROR BUSY", "", False),
    )

    with pytest.raises(OSError, match="unexpected server response"):
        client.connect()


def test_send_command_not_connected_raises():
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    with pytest.raises(OSError, match="client is not connected"):
        client.send_command("PING")


def test_send_command_returns_line_from_reader_queue(monkeypatch):
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    sock = _FakeSock()
    client._sock = sock

    sent: list[str] = []

    def fake_send_line(_sock, cmd):
        sent.append(cmd)
        with client._response_condition:
            client._response_queue.append("OK")
            client._response_condition.notify_all()

    monkeypatch.setattr(client_mod, "_send_line", fake_send_line)

    response = client.send_command("HELLO")
    assert response == "OK"
    assert sent == ["HELLO"]


def test_send_command_closes_on_remote_close(monkeypatch):
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    sock = _FakeSock()
    client._sock = sock

    def fake_send_line(*_a, **_k):
        with client._response_condition:
            client._reader_error = OSError("server closed the connection")
            client._response_condition.notify_all()

    monkeypatch.setattr(client_mod, "_send_line", fake_send_line)

    with pytest.raises(OSError, match="server closed the connection"):
        client.send_command("PING")
    assert client._sock is None
    assert client._buffer == ""


def test_ping_accepts_timed_pong(monkeypatch):
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    times = iter([10.0, 10.050])
    monkeypatch.setattr(client_mod.time, "time", lambda: next(times))
    client.send_command = lambda _cmd: "PONG TIME=50.0ms"  # type: ignore[method-assign]
    assert client.ping() == pytest.approx(50.0, rel=0.05)


def test_ping_rejects_unexpected_response():
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    client.send_command = lambda _cmd: "NOPE"  # type: ignore[method-assign]
    with pytest.raises(OSError, match="unexpected ping response"):
        client.ping()


def test_quit_branches(monkeypatch):
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)

    # Not connected branch.
    client.quit()

    # Connected + send_command OSError: should close and return.
    client._sock = _FakeSock()
    client.send_command = (  # type: ignore[method-assign]
        lambda _cmd: (_ for _ in ()).throw(OSError("x"))
    )
    client.quit()
    assert client._sock is None

    # Connected + unexpected response branch.
    client._sock = _FakeSock()
    client.send_command = lambda _cmd: "NOT-BYE"  # type: ignore[method-assign]
    with pytest.raises(OSError, match="unexpected quit response"):
        client.quit()

    # Connected + BYE branch.
    client._sock = _FakeSock()
    client.send_command = lambda _cmd: "BYE"  # type: ignore[method-assign]
    client.quit()
    assert client._sock is None


def test_close_swallow_socket_close_oserror():
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    client._sock = _FakeSock(fail_close=True)
    client._buffer = "abc"
    client.close()
    assert client._sock is None
    assert client._buffer == ""
