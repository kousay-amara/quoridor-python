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

    monkeypatch.setattr(
        client_mod.socket,
        "create_connection",
        lambda *_args, **_kwargs: sock,
    )
    recv_calls = iter(
        [
            (None, "partial", False),  # continue loop
            ("WELCOME id-1", "rest", False),
        ]
    )
    monkeypatch.setattr(client_mod, "_recv_line", lambda *_a, **_k: next(recv_calls))

    client.connect()

    assert client._sock is sock
    assert client._buffer == "rest"
    assert sock.timeout == client_mod._SOCKET_TIMEOUT_SEC


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
    monkeypatch.setattr(client_mod, "_recv_line", lambda *_a, **_k: ("ERROR BUSY", "", False))

    with pytest.raises(OSError, match="unexpected server response"):
        client.connect()


def test_send_command_not_connected_raises():
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    with pytest.raises(OSError, match="client is not connected"):
        client.send_command("PING")


def test_send_command_retries_on_none_then_returns_line(monkeypatch):
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    sock = _FakeSock()
    client._sock = sock

    sent: list[str] = []
    monkeypatch.setattr(client_mod, "_send_line", lambda _sock, cmd: sent.append(cmd))
    recv_calls = iter(
        [
            (None, "tmp", False),  # continue
            ("OK", "buf", False),
        ]
    )
    monkeypatch.setattr(client_mod, "_recv_line", lambda *_a, **_k: next(recv_calls))

    response = client.send_command("HELLO")
    assert response == "OK"
    assert sent == ["HELLO"]
    assert client._buffer == "buf"


def test_send_command_closes_on_remote_close(monkeypatch):
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    sock = _FakeSock()
    client._sock = sock

    monkeypatch.setattr(client_mod, "_send_line", lambda *_a, **_k: None)
    monkeypatch.setattr(client_mod, "_recv_line", lambda *_a, **_k: (None, "", True))

    with pytest.raises(OSError, match="server closed the connection"):
        client.send_command("PING")
    assert client._sock is None
    assert client._buffer == ""


def test_ping_accepts_pong_and_timed_pong(monkeypatch):
    client = client_mod.NetworkClient(host="127.0.0.1", port=12345)
    client.send_command = lambda _cmd: "PONG"  # type: ignore[method-assign]
    monkeypatch.setattr(client_mod.time, "time", lambda: 10.0)
    assert client.ping() == 0.0

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
    client.send_command = lambda _cmd: (_ for _ in ()).throw(OSError("x"))  # type: ignore[method-assign]
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
