from __future__ import annotations

from quoridor.interfaces import cli as cli_mod


def test_resolve_ai_ids_supports_all_default_and_dedup():
    assert cli_mod._resolve_ai_ids([], 4) == []
    assert cli_mod._resolve_ai_ids(["ALL"], 3) == [1, 2, 3]
    assert cli_mod._resolve_ai_ids(["DEFAULT"], 4) == [2]
    assert cli_mod._resolve_ai_ids(["DEFAULT"], 1) == [1]
    assert cli_mod._resolve_ai_ids([3, "DEFAULT", 3], 4) == [2, 3]


def test_run_server_daemon_start_error(monkeypatch, capsys):
    class FailingServer:
        def __init__(self, port):
            self.port = port

        def start(self):
            raise OSError("bind failed")

    monkeypatch.setattr(cli_mod, "NetworkServer", FailingServer)
    code = cli_mod._run_server_daemon(25000)
    assert code == 1
    assert "Cannot start server on port 25000: bind failed" in capsys.readouterr().err


def test_run_server_daemon_lifecycle(monkeypatch, capsys):
    class FakeServer:
        def __init__(self, port):
            self.port = port
            self._running = False
            self.stopped = False

        def start(self):
            self._running = True

        def running(self):
            return self._running

        def stop(self):
            self._running = False
            self.stopped = True

    monkeypatch.setattr(cli_mod, "NetworkServer", FakeServer)
    monkeypatch.setattr(
        cli_mod.time,
        "sleep",
        lambda _s: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    code = cli_mod._run_server_daemon(26000)
    out = capsys.readouterr().out
    assert code == 0
    assert "Server started on port 26000. Press Ctrl+C to stop." in out
    assert "Server stopped." in out
