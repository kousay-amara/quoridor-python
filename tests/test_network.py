from __future__ import annotations

import socket
import time

import pytest

import quoridor.network.discovery as discovery_mod
from quoridor.interfaces import cli as cli_mod
from quoridor.interfaces import cli_network as cli_network_mod
from quoridor.interfaces import cli_shell as cli_shell_mod
from quoridor.network import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DiscoveryBroadcaster,
    DiscoveryListener,
    NetworkClient,
    NetworkServer,
    format_discovery_message,
    get_discovered_servers,
    parse_discovery_message,
    parse_endpoint,
    remember_server,
)


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    discovery_mod._discovery_cache.clear()
    yield
    discovery_mod._discovery_cache.clear()


def _run_shell(monkeypatch, commands: list[object], **kwargs) -> None:
    iterator = iter(commands)

    def fake_input(_prompt: str = "") -> str:
        if _prompt:
            print(_prompt, end="")
        try:
            value = next(iterator)
            if callable(value):
                value = value()
            return value
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr("builtins.input", fake_input)
    shell_kwargs = {
        "blitz": False,
        "time_limit": 30,
        "save_file": None,
        "players": 2,
        "walls_per_player": 20,
        "board_size": 9,
        "ai_players": [],
        "ai_mode": "minimax",
        "ai_time": 5,
        "ai_minimax_depth": 2,
        "verbose": False,
        "debug": False,
    }
    shell_kwargs.update(kwargs)
    cli_mod._run_interactive_shell(**shell_kwargs)


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_connected_clients(
    server: NetworkServer,
    expected_count: int,
) -> bool:
    deadline = time.time() + 1.0
    while time.time() < deadline:
        status = server.server_status_snapshot()
        if status["connected_clients"] == expected_count:
            return True
        time.sleep(0.01)
    return False


def _wait_for_game_state_update(
    client: NetworkClient,
):
    deadline = time.time() + 1.0
    while time.time() < deadline:
        updates = client.drain_game_state_updates()
        if updates:
            return updates[-1]
        time.sleep(0.01)
    return None


def _wait_for_client_id(server: NetworkServer, name: str) -> int | None:
    deadline = time.time() + 1.0
    while time.time() < deadline:
        with server._lock:
            for client_id, session in server._client_sessions.items():
                if session.name == name:
                    return client_id
        time.sleep(0.01)
    return None


def _start_room_for_clients(
    server: NetworkServer,
    *clients: NetworkClient,
):
    participant_ids = []
    for client in clients:
        assert client.client_id is not None
        participant_ids.append(client.client_id)

    with server._lock:
        room = server._create_room_locked(participant_ids)
    server._send_room_state(room)
    return room


def _start_room_for_names(
    server: NetworkServer,
    *names: str,
):
    participant_ids = []
    for name in names:
        client_id = _wait_for_client_id(server, name)
        assert client_id is not None
        participant_ids.append(client_id)

    with server._lock:
        room = server._create_room_locked(participant_ids)
    server._send_room_state(room)
    return room


class _FakeNetworkState:
    def __init__(self) -> None:
        self.network_server = None
        self.network_client = None
        self.network_restore_callback = None


def test_parse_endpoint_supports_defaults_and_explicit_values():
    assert parse_endpoint(None) == (DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
    assert parse_endpoint("   ") == (DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
    assert parse_endpoint("127.0.0.1") == ("127.0.0.1", DEFAULT_SERVER_PORT)
    assert parse_endpoint("127.0.0.1:23456") == ("127.0.0.1", 23456)


def test_discovery_message_round_trip_and_invalid_prefix():
    message = format_discovery_message("alpha", 23456)

    assert parse_discovery_message(message) == ("alpha", 23456)
    assert parse_discovery_message("WRONG alpha 23456") is None

def test_discovery_listener_updates_cache_in_background():
    server_port = _unused_port()
    discovery_port = _unused_port()
    broadcaster = DiscoveryBroadcaster(
        port=server_port,
        discovery_port=discovery_port,
        interval_sec=0.05,
    )
    listener = DiscoveryListener(
        listen_port=discovery_port,
        socket_timeout_sec=0.05,
    )

    try:
        listener.start()
        broadcaster.start()

        deadline = time.time() + 1.0
        while time.time() < deadline:
            servers = get_discovered_servers()
            if any(server.port == server_port for server in servers):
                break
            time.sleep(0.05)
    finally:
        broadcaster.stop()
        listener.stop()

    assert any(server.port == server_port for server in servers)


def test_get_discovered_servers_prunes_expired_entries(monkeypatch):
    remember_server("alpha", "127.0.0.1", 23456)
    monkeypatch.setattr(discovery_mod, "DISCOVERY_ENTRY_TTL_SEC", 0.0)

    assert get_discovered_servers() == []


def test_cli_server_list_waits_only_on_first_lookup(
    monkeypatch,
    capsys,
):
    state = _FakeNetworkState()
    clock = {"value": 0.0}
    sleep_calls = []
    discovered_server = cli_network_mod.DiscoveredServer(
        "alpha",
        "127.0.0.1",
        23456,
    )
    responses = [
        [],
        [],
        [discovered_server],
        [],
    ]
    response_index = {"value": 0}

    def fake_get_discovered_servers():
        index = min(response_index["value"], len(responses) - 1)
        response_index["value"] += 1
        return responses[index]

    def fake_monotonic():
        return clock["value"]

    def fake_sleep(duration: float):
        sleep_calls.append(duration)
        clock["value"] += duration

    monkeypatch.setattr(
        cli_network_mod,
        "get_discovered_servers",
        fake_get_discovered_servers,
    )
    monkeypatch.setattr(cli_network_mod.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(cli_network_mod.time, "sleep", fake_sleep)

    assert cli_network_mod.command_server(state, "server list") is False
    first_output = capsys.readouterr().out
    assert "Discovered servers:" in first_output
    assert "- alpha (127.0.0.1:23456)" in first_output
    assert sleep_calls

    sleep_calls.clear()

    assert cli_network_mod.command_server(state, "server list") is False
    second_output = capsys.readouterr().out
    assert "No network servers found." in second_output
    assert sleep_calls == []


def test_network_server_and_client_support_ping_and_quit():
    port = _unused_port()
    server = NetworkServer(port=port)
    client = NetworkClient(host="127.0.0.1", port=port)

    try:
        server.start()
        client.connect()

        assert client.connected()
        assert client.ping() >= 0

        client.quit()
        assert not client.connected()
    finally:
        client.close()
        if server.running():
            server.stop()


def test_network_server_accepts_multiple_clients():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        first_client.connect()
        second_client.connect()

        assert first_client.connected()
        assert second_client.connected()
        assert first_client.ping() >= 0
        assert second_client.ping() >= 0

        first_client.quit()
        second_client.quit()

        assert not first_client.connected()
        assert not second_client.connected()
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_network_server_status_snapshot_updates_with_connections():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        status = server.server_status_snapshot()
        assert status["port"] == port
        assert status["connected_clients"] == 0
        assert status["active_games"] == 0

        first_client.connect()
        assert _wait_connected_clients(server, 1)

        second_client.connect()
        assert _wait_connected_clients(server, 2)
        assert first_client.players() == [
            (1, "alice", "idle"),
            (2, "bob", "idle"),
        ]

        first_client.quit()
        assert _wait_connected_clients(server, 1)

        second_client.quit()
        assert _wait_connected_clients(server, 0)
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_network_players_supports_detailed_lookup_by_id():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        first_client.connect()
        second_client.connect()

        assert first_client.player_details(2) == (
            2,
            "bob",
            "idle",
            0,
            0,
            0,
        )

        _start_room_for_clients(server, first_client, second_client)
        assert _wait_for_game_state_update(first_client) is not None
        assert _wait_for_game_state_update(second_client) is not None

        assert first_client.player_details(2) == (
            2,
            "bob",
            "ingame",
            0,
            0,
            0,
        )
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_network_scoreboard_tracks_runtime_stats():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        first_client.connect()
        second_client.connect()

        scores = first_client.scoreboard()
        assert scores == [
            (1, "alice", 0, 0, 0),
            (2, "bob", 0, 0, 0),
        ]

        server.record_finished_game(
            player_ids=[1, 2],
            winner_client_id=1,
        )
        scores = first_client.scoreboard()
        assert scores == [
            (1, "alice", 1, 0, 1),
            (2, "bob", 0, 1, 1),
        ]
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_network_new_creates_room_and_sets_players_ingame():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        first_client.connect()
        second_client.connect()

        _start_room_for_clients(server, first_client, second_client)
        assert _wait_for_game_state_update(first_client) is not None
        assert _wait_for_game_state_update(second_client) is not None

        status = server.server_status_snapshot()
        assert status["active_games"] == 1

        players = first_client.players()
        assert players == [
            (1, "alice", "ingame"),
            (2, "bob", "ingame"),
        ]
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_network_new_rejects_absent_or_unavailable_player():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")
    third_client = NetworkClient(
        host="127.0.0.1",
        port=port,
        name="charlie",
    )

    try:
        server.start()
        first_client.connect()
        second_client.connect()
        third_client.connect()

        assert first_client.send_command("NEW 999") == "ERROR PLAYER_NOT_FOUND"

        assert (
            first_client.send_command("NEW 2")
            == "INVITATION_SENT PLAYER=bob TIMEOUT=300s"
        )
        assert (
            third_client.send_command("NEW 2")
            == "ERROR PLAYER_NOT_AVAILABLE"
        )
    finally:
        first_client.close()
        second_client.close()
        third_client.close()
        if server.running():
            server.stop()


def test_network_new_supports_multiple_target_players():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")
    third_client = NetworkClient(host="127.0.0.1", port=port, name="charlie")

    try:
        server.start()
        first_client.connect()
        second_client.connect()
        third_client.connect()

        response = first_client.send_command("NEW 2 3")
        assert response == "ERROR INVALID_NEW_FORMAT"

        status = server.server_status_snapshot()
        assert status["active_games"] == 0

        players = first_client.players()
        assert players == [
            (1, "alice", "idle"),
            (2, "bob", "idle"),
            (3, "charlie", "idle"),
        ]
    finally:
        first_client.close()
        second_client.close()
        third_client.close()
        if server.running():
            server.stop()


def test_network_new_rejects_unsupported_player_count():
    port = _unused_port()
    server = NetworkServer(port=port)
    clients = [
        NetworkClient(host="127.0.0.1", port=port, name="alice"),
        NetworkClient(host="127.0.0.1", port=port, name="bob"),
        NetworkClient(host="127.0.0.1", port=port, name="charlie"),
        NetworkClient(host="127.0.0.1", port=port, name="dave"),
        NetworkClient(host="127.0.0.1", port=port, name="eve"),
    ]

    try:
        server.start()
        for client in clients:
            client.connect()

        assert (
            clients[0].send_command("NEW 2 3 4 5")
            == "ERROR INVALID_NEW_FORMAT"
        )
    finally:
        for client in clients:
            client.close()
        if server.running():
            server.stop()


def test_network_move_routes_to_opponent_and_enforces_turn_order():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        first_client.connect()
        second_client.connect()
        _start_room_for_clients(server, first_client, second_client)

        first_update = _wait_for_game_state_update(first_client)
        second_update = _wait_for_game_state_update(second_client)
        assert first_update is not None
        assert second_update is not None
        assert first_update["game_id"] == 1
        assert first_update["player_id"] == 1
        assert second_update["player_id"] == 2
        assert first_update["state"]["current_player"] == 1
        assert first_update["state"]["player_positions"] == {1: 4, 2: 76}

        assert first_client.move("e1-e2") == "MOVE_OK"
        first_update = _wait_for_game_state_update(first_client)
        second_update = _wait_for_game_state_update(second_client)
        assert first_update is not None
        assert second_update is not None
        assert first_update["state"]["current_player"] == 2
        assert first_update["state"]["player_positions"] == {
            1: 13,
            2: 76,
        }
        assert first_client.move("e2-e3") == "ERROR NOT_YOUR_TURN"

        assert second_client.ping() >= 0
        assert second_client.drain_opponent_moves() == ["e1-e2"]

        assert second_client.move("e9-e8") == "MOVE_OK"
        assert first_client.ping() >= 0
        assert first_client.drain_opponent_moves() == ["e9-e8"]
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_network_moves_are_isolated_between_parallel_games():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")
    third_client = NetworkClient(host="127.0.0.1", port=port, name="charlie")
    fourth_client = NetworkClient(host="127.0.0.1", port=port, name="dave")

    try:
        server.start()
        first_client.connect()
        second_client.connect()
        third_client.connect()
        fourth_client.connect()

        _start_room_for_clients(server, first_client, second_client)
        _start_room_for_clients(server, third_client, fourth_client)
        assert _wait_for_game_state_update(first_client) is not None
        assert _wait_for_game_state_update(second_client) is not None
        assert _wait_for_game_state_update(third_client) is not None
        assert _wait_for_game_state_update(fourth_client) is not None

        assert first_client.move("e1-e2") == "MOVE_OK"
        assert second_client.ping() >= 0
        assert second_client.drain_opponent_moves() == ["e1-e2"]

        assert third_client.ping() >= 0
        assert third_client.drain_opponent_moves() == []
        assert fourth_client.ping() >= 0
        assert fourth_client.drain_opponent_moves() == []

        assert third_client.move("e1-e2") == "MOVE_OK"
        assert fourth_client.ping() >= 0
        assert fourth_client.drain_opponent_moves() == ["e1-e2"]

        assert first_client.ping() >= 0
        assert first_client.drain_opponent_moves() == []
        assert second_client.ping() >= 0
        assert second_client.drain_opponent_moves() == []
    finally:
        first_client.close()
        second_client.close()
        third_client.close()
        fourth_client.close()
        if server.running():
            server.stop()


def test_network_move_rejects_invalid_format_and_not_in_game():
    port = _unused_port()
    server = NetworkServer(port=port)
    client = NetworkClient(host="127.0.0.1", port=port, name="alice")

    try:
        server.start()
        client.connect()
        assert client.send_command("MOVE") == "ERROR INVALID_MOVE_FORMAT"
        assert client.send_command("MOVE ") == "ERROR INVALID_MOVE_FORMAT"
        assert client.move("e1-e2") == "ERROR NOT_IN_GAME"
    finally:
        client.close()
        if server.running():
            server.stop()


def test_network_move_rejects_illegal_move():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        first_client.connect()
        second_client.connect()
        _start_room_for_clients(server, first_client, second_client)
        assert _wait_for_game_state_update(first_client) is not None
        assert _wait_for_game_state_update(second_client) is not None

        assert first_client.move("e1-e3") == "ERROR ILLEGAL_MOVE"
        assert second_client.ping() >= 0
        assert second_client.drain_opponent_moves() == []
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_network_game_end_closes_room_and_updates_scoreboard():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port, name="alice")
    second_client = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        first_client.connect()
        second_client.connect()
        _start_room_for_clients(server, first_client, second_client)
        assert _wait_for_game_state_update(first_client) is not None
        assert _wait_for_game_state_update(second_client) is not None

        assert first_client.move("e1-e2") == "MOVE_OK"
        assert second_client.move("e9-d9") == "MOVE_OK"
        assert first_client.move("e2-e3") == "MOVE_OK"
        assert second_client.move("d9-d8") == "MOVE_OK"
        assert first_client.move("e3-e4") == "MOVE_OK"
        assert second_client.move("d8-d7") == "MOVE_OK"
        assert first_client.move("e4-e5") == "MOVE_OK"
        assert second_client.move("d7-d6") == "MOVE_OK"
        assert first_client.move("e5-e6") == "MOVE_OK"
        assert second_client.move("d6-d5") == "MOVE_OK"
        assert first_client.move("e6-e7") == "MOVE_OK"
        assert second_client.move("d5-d4") == "MOVE_OK"
        assert first_client.move("e7-e8") == "MOVE_OK"
        assert second_client.move("d4-d3") == "MOVE_OK"
        assert first_client.move("e8-e9") == "MOVE_OK"

        status = server.server_status_snapshot()
        assert status["active_games"] == 0

        players = first_client.players()
        assert players == [
            (1, "alice", "idle"),
            (2, "bob", "idle"),
        ]

        scores = first_client.scoreboard()
        assert scores == [
            (1, "alice", 1, 0, 1),
            (2, "bob", 0, 1, 1),
        ]

        assert first_client.move("e9-e8") == "ERROR NOT_IN_GAME"
    finally:
        first_client.close()
        second_client.close()
        if server.running():
            server.stop()


def test_cli_server_join_ping_and_quit_cycle(
    monkeypatch,
    capsys,
):
    port = _unused_port()

    _run_shell(
        monkeypatch,
        [
            f"server start {port}",
            f"join 127.0.0.1:{port}",
            "players",
            "ping",
            "quit",
            "server stop",
            "quit",
        ],
    )

    out = capsys.readouterr().out
    assert f"Server started on port {port}." in out
    assert f"Connected to server 127.0.0.1:{port}." in out
    assert "Connected players:" in out
    assert "PONG TIME=" in out
    assert "Disconnected from server." in out
    assert "Server stopped." in out
    assert "Bye." in out


def test_cli_new_player_creates_game_with_explicit_errors(
    monkeypatch,
    capsys,
):
    port = _unused_port()
    server = NetworkServer(port=port)
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        bob.connect()
        _run_shell(
            monkeypatch,
            [
                f"join 127.0.0.1:{port} alice",
                "new 999",
                "new 1",
                "new 999",
                "players",
                "quit",
                "quit",
            ],
        )
    finally:
        bob.close()
        if server.running():
            server.stop()

    out = capsys.readouterr().out
    assert "Cannot send invitation: player not found." in out
    assert "INVITATION_SENT PLAYER=bob TIMEOUT=300s" in out
    assert "Cannot send invitation: you are not idle." in out
    assert "- 1: bob (waitgame)" in out
    assert "- 2: alice (waitgame)" in out


def test_cli_network_move_routes_and_enforces_turn(monkeypatch, capsys):
    port = _unused_port()
    server = NetworkServer(port=port)
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        bob.connect()
        _run_shell(
            monkeypatch,
            [
                f"join 127.0.0.1:{port} alice",
                lambda: (
                    _start_room_for_names(server, "alice", "bob"),
                    "move e1-e2",
                )[1],
                "move e2-e3",
                "quit",
                "quit",
            ],
        )
        assert bob.ping() >= 0
        assert bob.drain_opponent_moves() == ["e1-e2"]
    finally:
        bob.close()
        if server.running():
            server.stop()

    out = capsys.readouterr().out
    assert "Move sent: e1-e2" in out
    assert "Cannot play move: not your turn." in out
    assert "Current player: 2" in out
    assert "You are player 1. Position: e2. Goal: reach row 9." in out
    assert "Player 1: e2, Player 2: e9" in out


def test_cli_quit_from_network_restores_previous_local_game(
    monkeypatch,
    capsys,
):
    port = _unused_port()
    server = NetworkServer(port=port)
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        bob.connect()
        _run_shell(
            monkeypatch,
            [
                f"join 127.0.0.1:{port} alice",
                lambda: (
                    _start_room_for_names(server, "alice", "bob"),
                    "quit",
                )[1],
                "e1-e2",
                "quit",
                "n",
            ],
        )
    finally:
        bob.close()
        if server.running():
            server.stop()

    out = capsys.readouterr().out
    assert "Disconnected from server." in out
    assert "Returned to local game." in out
    assert "Player 1: e2, Player 2: e9" in out


def test_cli_network_shorthand_wall_routes_to_server(monkeypatch, capsys):
    port = _unused_port()
    server = NetworkServer(port=port)
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        bob.connect()
        _run_shell(
            monkeypatch,
            [
                f"join 127.0.0.1:{port} alice",
                lambda: (
                    _start_room_for_names(server, "alice", "bob"),
                    "e2h",
                )[1],
                "quit",
                "quit",
            ],
        )
        assert bob.ping() >= 0
        assert bob.drain_opponent_moves() == ["e2h"]
    finally:
        bob.close()
        if server.running():
            server.stop()

    out = capsys.readouterr().out
    assert "Move sent: e2h" in out


def test_cli_new_player_accepts_multiple_ids(monkeypatch, capsys):
    port = _unused_port()
    server = NetworkServer(port=port)
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")
    charlie = NetworkClient(host="127.0.0.1", port=port, name="charlie")

    try:
        server.start()
        bob.connect()
        charlie.connect()
        _run_shell(
            monkeypatch,
            [
                f"join 127.0.0.1:{port} alice",
                "new 1 2",
                "players",
                "quit",
                "quit",
            ],
        )
    finally:
        bob.close()
        charlie.close()
        if server.running():
            server.stop()

    out = capsys.readouterr().out
    assert "Invalid command: Invalid format. Use: new PLAYER_ID" in out
    assert "- 1: bob (idle)" in out
    assert "- 2: charlie (idle)" in out
    assert "- 3: alice (idle)" in out


def test_cli_join_accepts_custom_name(monkeypatch, capsys):
    port = _unused_port()

    _run_shell(
        monkeypatch,
        [
            f"server start {port}",
            f"join 127.0.0.1:{port} alice",
            "players",
            "quit",
            "server stop",
            "quit",
        ],
    )

    out = capsys.readouterr().out
    assert f"Connected to server 127.0.0.1:{port}." in out
    assert "Connected players:" in out
    assert "- 1: alice (idle)" in out


def test_cli_players_with_id_displays_detailed_player_info(
    monkeypatch,
    capsys,
):
    port = _unused_port()

    _run_shell(
        monkeypatch,
        [
            f"server start {port}",
            f"join 127.0.0.1:{port} alice",
            "players 1",
            "quit",
            "server stop",
            "quit",
        ],
    )

    out = capsys.readouterr().out
    assert "Player 1: alice" in out
    assert "- status: idle" in out
    assert "- played: 0" in out
    assert "- wins: 0" in out
    assert "- losses: 0" in out


def test_cli_scoreboard_displays_server_stats(monkeypatch, capsys):
    port = _unused_port()
    server = NetworkServer(port=port)
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        bob.connect()
        server.record_finished_game(
            player_ids=[1, 2],
            winner_client_id=2,
        )

        _run_shell(
            monkeypatch,
            [
                f"join 127.0.0.1:{port}",
                "scoreboard",
                "quit",
                "quit",
            ],
        )
    finally:
        bob.close()
        if server.running():
            server.stop()

    out = capsys.readouterr().out
    assert "Scoreboard:" in out
    assert "- 1: bob (played=1 wins=0 losses=1)" in out
    assert "- 2: player (played=1 wins=1 losses=0)" in out


def test_cli_server_status_reports_counts(monkeypatch, capsys):
    port = _unused_port()

    _run_shell(
        monkeypatch,
        [
            f"server start {port}",
            "server status",
            f"join 127.0.0.1:{port}",
            "server status",
            "quit",
            "server status",
            "server stop",
            "quit",
        ],
    )

    out = capsys.readouterr().out
    assert out.count("Server status:") == 3
    assert f"- port: {port}" in out
    assert "- connected clients: 0" in out
    assert "- connected clients: 1" in out
    assert "- active games: 0" in out


def test_cli_invalid_network_commands_do_not_crash_shell(monkeypatch, capsys):
    monkeypatch.setattr(
        cli_shell_mod.cli_network,
        "start_discovery_listener",
        lambda: None,
    )
    monkeypatch.setattr(
        cli_shell_mod.cli_network,
        "stop_discovery_listener",
        lambda _listener: None,
    )

    _run_shell(
        monkeypatch,
        [
            "server foo",
            "join 127.0.0.1:abc",
            "ping",
            "quit",
        ],
    )

    out = capsys.readouterr().out
    assert (
        "Invalid command: Invalid format. Use: "
        "server list|start [PORT]|status|stop"
    ) in out
    assert (
        "Invalid command: Invalid format. Use: "
        "join [HOST[:PORT]] [NAME]"
    ) in out
    assert "Invalid command:" in out
    assert "Not connected to any server." in out
    assert "Bye." in out
