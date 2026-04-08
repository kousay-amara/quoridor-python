from __future__ import annotations

import threading

import pytest

import quoridor.interfaces.cli_network as cli_net
from quoridor.interfaces.cli_network import (
    command_accept,
    command_cancel,
    command_decline,
    command_join,
    command_move,
    command_new_player,
    command_ping,
    command_players,
    command_scoreboard,
    command_server,
    command_shorthand_move,
    command_shorthand_wall,
    disconnect_client,
)
from quoridor.interfaces.shell import network_handlers as nh


class _State:
    def __init__(self):
        self.network_server = None
        self.network_client = None
        self.network_restore_callback = None
        self.network_discovery_initial_wait_done = True


class _Client:
    host = "127.0.0.1"
    port = 19999
    client_id = 1

    def ping(self): return 10.0
    def quit(self): pass
    def close(self): pass
    def players(self): return [(1, "alice", "idle")]
    def player_details(self, cid):
        if cid == 999: raise ValueError("Player not found.")
        return (cid, "alice", "idle", 0, 0, 0)
    def scoreboard(self): return [(1, "alice", 1, 0, 1)]
    def send_command(self, cmd):
        if cmd.startswith("NEW "): return "INVITATION_SENT PLAYER=bob TIMEOUT=300s"
        return "OK"
    def accept(self): return "GAME_START OPPONENT=bob"
    def decline(self): return "DECLINE_OK PLAYER=alice"
    def cancel(self): return "CANCEL_OK PLAYER=bob"
    def move(self, _notation): return "MOVE_OK"
    def drain_opponent_moves(self): return ["e1-e2"]


def test_cli_network_core_flow(capsys, monkeypatch):
    state = _State()

    class _FailingClient:
        def __init__(self, **_): pass
        def connect(self): raise OSError("refused")

    monkeypatch.setattr(cli_net, "NetworkClient", _FailingClient)
    command_join(state, "join 127.0.0.1:1")
    assert "Cannot connect" in capsys.readouterr().out

    class _OkClient(_Client):
        def __init__(self, **_): pass
        def connect(self): pass

    monkeypatch.setattr(cli_net, "NetworkClient", _OkClient)
    command_join(state, "join 127.0.0.1:19999")
    out = capsys.readouterr().out
    assert "Connected to server" in out
    assert state.network_client is not None

    command_players(state, "players")
    command_players(state, "players 1")
    command_players(state, "players 999")
    out = capsys.readouterr().out
    assert "Connected players" in out and "Player 1" in out
    assert "not found" in out.lower()

    command_scoreboard(state, "scoreboard")
    assert "Scoreboard" in capsys.readouterr().out
    command_new_player(state, "new 2")
    assert "INVITATION_SENT" in capsys.readouterr().out
    with pytest.raises(ValueError):
        command_new_player(state, "new")

    command_accept(state, "accept")
    command_decline(state, "decline")
    command_cancel(state, "cancel")
    out = capsys.readouterr().out
    assert "GAME_START" in out and "DECLINE_OK" in out and "CANCEL_OK" in out

    command_move(state, "move e1-e2")
    cli_net.command_wall(state, "wall e1v")
    command_shorthand_move(state, "e1-e2")
    command_shorthand_wall(state, "e1v")
    out = capsys.readouterr().out
    assert out.count("Move sent") == 4
    assert "OPPONENT_MOVE e1-e2" in out

    assert disconnect_client(state) is True
    out = capsys.readouterr().out
    assert "Disconnected" in out and state.network_client is None

    class _LostClient(_Client):
        def ping(self): raise OSError("lost")

    state.network_client = _LostClient()
    command_ping(state, "ping")
    out = capsys.readouterr().out
    assert "Connection lost" in out and state.network_client is None


def test_server_list_and_status_without_server(capsys, monkeypatch):
    state = _State()
    monkeypatch.setattr(cli_net, "get_discovered_servers", lambda: [])
    command_server(state, "server list")
    out = capsys.readouterr().out
    assert "No network servers found" in out
    command_server(state, "server status")
    out = capsys.readouterr().out
    assert "not running" in out


def test_network_handlers_join_and_apply_state(capsys):
    state = _State()
    wired = {}

    class _MockClient:
        def set_opponent_move_callback(self, cb): wired["move"] = cb
        def set_game_state_callback(self, cb): wired["state"] = cb
        def set_notification_callback(self, cb): wired["notif"] = cb
        def set_connection_lost_callback(self, cb): wired["lost"] = cb
        def drain_opponent_moves(self): return ["e1-e2"]
        def drain_game_state_updates(self): return []
        def drain_notifications(self): return []

    def _join_fn(s, _line):
        s.network_client = _MockClient()
        return False

    nh.command_join(
        state,
        "join",
        command_join_fn=_join_fn,
        save_local_state_before_network=lambda _s: None,
        apply_game_state_to_local_session=lambda _s, _u: None,
    )
    out = capsys.readouterr().out
    assert "OPPONENT_MOVE e1-e2" in out
    assert "move" in wired and "state" in wired

    class _FakeSession:
        class state:
            player_positions = {1: 0, 2: 80}
            board_size = 9
            remaining_walls = {1: 10, 2: 10}

    state.network_sync_lock = threading.Lock()
    state.session = None
    state.players = 0
    state.board_size = 0
    state.walls_per_player = 0
    state.ai_players = []
    state.network_player_id = None
    state.has_unsaved_changes = False
    state.event_bus = None

    nh.apply_network_game_state_to_local_session(
        state,
        {"state": {"board_size": 9}, "winner_id": 1, "player_id": 2},
        create_network_session=lambda _snap: _FakeSession(),
        print_state=lambda *_a, **_k: None,
    )
    assert "Player 1 wins" in capsys.readouterr().out


def test_network_handlers_wrappers_and_save_local_state():
    state = _State()
    called = []

    def _fn(_s, line):
        called.append(line)
        return False

    nh.command_ping(state, "ping", command_ping_fn=_fn)
    nh.command_players(state, "players", command_players_fn=_fn)
    nh.command_scoreboard(state, "scoreboard", command_scoreboard_fn=_fn)
    nh.command_new_player(state, "new 2", command_new_player_fn=_fn)
    assert called == ["ping", "players", "scoreboard", "new 2"]

    state.saved_local_state = None
    for attr, val in [
        ("session", None), ("has_unsaved_changes", False),
        ("ai_minimax_scoring", 1), ("ai_mcts_selection", "UCT"),
        ("current_ai_mode", "minimax"), ("current_ai_time", 5),
        ("current_ai_minimax_depth", None),
        ("current_ai_minimax_scoring", 1),
        ("current_ai_mcts_selection", "UCT"),
        ("players", 2), ("walls_per_player", 10), ("board_size", 9),
        ("ai_players", []), ("blitz_enabled", False),
        ("time_limit", 5.0), ("blitz", None),
    ]:
        setattr(state, attr, val)
    saves = []
    nh.save_local_shell_state_before_network(
        state, saved_state_factory=lambda **_k: saves.append(1) or object()
    )
    nh.save_local_shell_state_before_network(
        state, saved_state_factory=lambda **_k: saves.append(1) or object()
    )
    assert saves == [1]
