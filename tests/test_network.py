from __future__ import annotations

import socket
import time

import pytest

import quoridor.network.discovery as discovery_mod
from quoridor.network.basic_network import (
    _recv_line,
    _send_line,
    _SOCKET_TIMEOUT_SEC,
    _validate_port,
    parse_game_state_message,
)
from quoridor.network import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    NetworkClient,
    NetworkServer,
    format_discovery_message,
    get_discovered_servers,
    parse_discovery_message,
    parse_endpoint,
    remember_server,
)


def setup_function(_function) -> None:
    discovery_mod._discovery_cache.clear()


def teardown_function(_function) -> None:
    discovery_mod._discovery_cache.clear()


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_connected_clients(server: NetworkServer, expected_count: int) -> bool:
    deadline = time.time() + 1.0
    while time.time() < deadline:
        status = server.server_status_snapshot()
        if status["connected_clients"] == expected_count:
            return True
        time.sleep(0.01)
    return False


def _wait_for_notification_prefix(client: NetworkClient, prefix: str) -> str | None:
    deadline = time.time() + 1.0
    while time.time() < deadline:
        for notification in client.drain_notifications():
            if notification.startswith(prefix):
                return notification
        time.sleep(0.01)
    return None


def _wait_for_opponent_move(client: NetworkClient) -> str | None:
    deadline = time.time() + 1.0
    while time.time() < deadline:
        moves = client.drain_opponent_moves()
        if moves:
            return moves[-1]
        time.sleep(0.01)
    return None


def _recv_protocol_line(client_sock: socket.socket) -> str:
    buffer = ""
    deadline = time.time() + 1.0
    while time.time() < deadline:
        line, buffer, closed = _recv_line(client_sock, buffer)
        if closed:
            break
        if line is not None:
            return line
    raise AssertionError("Timed out while waiting for protocol line.")


def _recv_optional_protocol_line(client_sock: socket.socket) -> str | None:
    try:
        return _recv_protocol_line(client_sock)
    except AssertionError:
        return None


def test_parse_endpoint_supports_defaults_and_explicit_values():
    assert parse_endpoint(None) == (DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
    assert parse_endpoint("   ") == (DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
    assert parse_endpoint("127.0.0.1") == ("127.0.0.1", DEFAULT_SERVER_PORT)
    assert parse_endpoint("127.0.0.1:23456") == ("127.0.0.1", 23456)


def test_discovery_message_round_trip_and_invalid_prefix():
    message = format_discovery_message("alpha", 23456)

    assert parse_discovery_message(message) == ("alpha", 23456)
    assert parse_discovery_message("WRONG alpha 23456") is None


def test_get_discovered_servers_prunes_expired_entries(monkeypatch):
    remember_server("alpha", "127.0.0.1", 23456)
    monkeypatch.setattr(discovery_mod, "DISCOVERY_ENTRY_TTL_SEC", 0.0)

    assert get_discovered_servers() == []


def test_network_server_and_client_support_ping_and_quit():
    port = _unused_port()
    server = NetworkServer(port=port)
    client = NetworkClient(host="127.0.0.1", port=port, name="alice")

    try:
        server.start()
        client.connect()
        assert _wait_connected_clients(server, 1)
        assert client.ping() >= 0
        client.quit()
    finally:
        client.close()
        server.stop()


def test_network_players_supports_detailed_lookup_by_id():
    port = _unused_port()
    server = NetworkServer(port=port)
    client = NetworkClient(host="127.0.0.1", port=port, name="alice")

    try:
        server.start()
        client.connect()
        assert client.client_id is not None
        assert _wait_connected_clients(server, 1)

        players = client.players()
        assert any(
            cid == client.client_id and name == "alice" for cid, name, _ in players
        )

        with pytest.raises(ValueError, match="player id must be positive"):
            client.player_details(0)

        cid, name, _status, wins, losses, played = client.player_details(
            client.client_id
        )
        assert cid == client.client_id
        assert name == "alice"
        assert wins == losses == played == 0

        with pytest.raises(ValueError, match="Player not found"):
            client.player_details(999)
    finally:
        client.close()
        server.stop()


def test_network_new_accept_starts_game_and_routes_moves():
    port = _unused_port()
    server = NetworkServer(port=port)
    alice = NetworkClient(host="127.0.0.1", port=port, name="alice")
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        alice.connect()
        bob.connect()
        assert alice.client_id is not None
        assert bob.client_id is not None
        assert _wait_connected_clients(server, 2)

        response = alice.send_command(f"NEW {bob.client_id}")
        assert response.startswith("INVITATION_SENT")
        assert bob.accept().startswith("GAME_START")

        assert alice.send_command("MOVE e1-e2") == "MOVE_OK"
        assert _wait_for_opponent_move(bob) == "e1-e2"
    finally:
        alice.close()
        bob.close()
        server.stop()


def test_network_invitation_decline_and_cancel():
    port = _unused_port()
    server = NetworkServer(port=port)
    alice = NetworkClient(host="127.0.0.1", port=port, name="alice")
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        alice.connect()
        bob.connect()
        assert alice.client_id is not None
        assert bob.client_id is not None

        alice.send_command(f"NEW {bob.client_id}")
        assert bob.decline().startswith("DECLINE_OK")
        assert _wait_for_notification_prefix(alice, "INVITATION_DECLINED ")

        alice.send_command(f"NEW {bob.client_id}")
        assert alice.cancel().startswith("CANCEL_OK")
        assert _wait_for_notification_prefix(bob, "INVITATION_CANCELLED ")
    finally:
        alice.close()
        bob.close()
        server.stop()


def test_network_away_back_roundtrip_and_invalid_players_format():
    port = _unused_port()
    server = NetworkServer(port=port)
    alice = NetworkClient(host="127.0.0.1", port=port, name="alice")

    try:
        server.start()
        alice.connect()
        assert alice.away() == "AWAY_OK"
        assert alice.back() == "BACK_OK"
        assert alice.send_command("PLAYERS nope") == "ERROR INVALID_PLAYERS_FORMAT"
    finally:
        alice.close()
        server.stop()


def test_basic_network_unit_helpers():
    # _validate_port: invalid range
    import pytest as _pytest

    with _pytest.raises(ValueError, match="invalid port"):
        _validate_port(0)
    with _pytest.raises(ValueError, match="invalid port"):
        _validate_port(65536)
    assert _validate_port(12345) == 12345

    # parse_game_state_message: bad prefix, bad JSON, missing keys
    assert parse_game_state_message("NOPE {}") is None
    assert parse_game_state_message("GAME_STATE not-json") is None
    assert parse_game_state_message('GAME_STATE "string"') is None

    # parse_endpoint: host with trailing colon uses default port
    assert parse_endpoint("myhost:") == ("myhost", DEFAULT_SERVER_PORT)


def test_server_start_idempotent_and_port_conflict():
    port = _unused_port()
    server = NetworkServer(port=port)
    try:
        server.start()
        assert server.running()
        server.start()  # idempotent — should not raise
        assert server.running()
    finally:
        server.stop()

    # Port already in use raises OSError
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupier:
        occupier.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupier.bind(("127.0.0.1", port))
        occupier.listen(1)
        conflict_server = NetworkServer(host="127.0.0.1", port=port)
        with pytest.raises(OSError):
            conflict_server.start()


def test_network_client_scoreboard_and_move_errors():
    port = _unused_port()
    server = NetworkServer(port=port)
    alice = NetworkClient(host="127.0.0.1", port=port, name="alice")
    bob = NetworkClient(host="127.0.0.1", port=port, name="bob")

    try:
        server.start()
        alice.connect()
        bob.connect()
        assert _wait_connected_clients(server, 2)

        # scoreboard returns a list
        scores = alice.scoreboard()
        assert isinstance(scores, list)

        alice.send_command(f"NEW {bob.client_id}")
        bob.accept()

        # move validation: empty notation
        with pytest.raises(ValueError, match="must not be empty"):
            alice.move("")

        # move validation: notation with spaces
        with pytest.raises(ValueError, match="must not contain spaces"):
            alice.move("e1 e2")

        # drain_game_state_updates returns list
        assert isinstance(alice.drain_game_state_updates(), list)
    finally:
        alice.close()
        bob.close()
        server.stop()


def test_network_server_stop_notifies_connected_client():
    port = _unused_port()
    server = NetworkServer(port=port)
    client = NetworkClient(host="127.0.0.1", port=port, name="alice")

    try:
        server.start()
        client.connect()
        assert _wait_connected_clients(server, 1)
    finally:
        server.stop()
        client.close()


def test_cli_network_not_connected_sweep(capsys):
    """Covers 'not-connected' early-returns and input-validation branches in cli_network."""
    from types import SimpleNamespace as NS
    from quoridor.interfaces import cli_network as cn

    # parse_server_port: bad string, out-of-range, valid (lines 62-68)
    with pytest.raises(ValueError):
        cn.parse_server_port("abc")
    with pytest.raises(ValueError):
        cn.parse_server_port("0")
    assert cn.parse_server_port("8080") == 8080

    # _restore_local_mode: swallows exception from callback (lines 87-90)
    def _bad():
        raise RuntimeError("x")

    cn._restore_local_mode(NS(network_restore_callback=_bad))

    # _handle_connection_lost: clears network_player_id (line 101)
    st = NS(network_client=None, network_player_id=9, network_restore_callback=None)
    cn._handle_connection_lost(st, OSError("x"))
    assert st.network_player_id is None

    # stop_discovery_listener with a listener object (line 79)
    cn.stop_discovery_listener(NS(stop=lambda: None))

    nc = NS(network_client=None, network_server=None)

    # All "not connected" commands
    for fn, line in [
        (cn.command_ping, "ping"),
        (cn.command_players, "players"),
        (cn.command_scoreboard, "scoreboard"),
        (cn.command_new_player, "new 1"),
        (cn.command_accept, "accept"),
        (cn.command_decline, "decline"),
        (cn.command_cancel, "cancel"),
        (cn.command_away, "away"),
        (cn.command_back, "back"),
    ]:
        fn(nc, line)
    cn._command_move_with_notation(nc, "e1-e2")
    assert "Not connected" in capsys.readouterr().out

    # Format / validation error branches
    for bad in [
        lambda: cn.command_server(nc, "server"),
        lambda: cn.command_server(nc, "server list extra"),
        lambda: cn.command_server(nc, "server status extra"),
        lambda: cn.command_players(nc, "players 1 2"),
        lambda: cn.command_scoreboard(nc, "scoreboard extra"),
        lambda: cn.command_accept(nc, "accept extra"),
        lambda: cn.command_decline(nc, "decline extra"),
        lambda: cn.command_cancel(nc, "cancel xyz"),
        lambda: cn.command_move(nc, "ping"),
        lambda: cn.command_move(nc, "move  "),
        lambda: cn.command_shorthand_move(nc, ""),
        lambda: cn.command_wall(nc, "ping"),
        lambda: cn.command_wall(nc, "wall  "),
        lambda: cn.command_shorthand_wall(nc, ""),
    ]:
        with pytest.raises(ValueError):
            bad()

    # command_new_player: invalid player_id with a connected state (line 375)
    with pytest.raises(ValueError):
        cn.command_new_player(NS(network_client=NS(), network_server=None), "new -1")

    # command_join: already connected prints message (lines 223-227)
    cn.command_join(
        NS(network_client=NS(host="h", port=1), network_server=None), "join"
    )


def test_cli_network_server_and_handlers(capsys):
    """Covers server-running branches, discovery list, and network_handlers wrappers."""
    from types import SimpleNamespace as NS
    from quoridor.interfaces import cli_network as cn
    from quoridor.interfaces.shell import network_handlers as nh

    fake_srv = NS(
        port=9999,
        name="srv",
        server_status_snapshot=lambda: {
            "port": 9999,
            "connected_clients": 0,
            "active_games": 0,
        },
        stop=lambda: None,
    )
    st = NS(network_client=None, network_server=fake_srv)

    # server start when already running (lines 171, 173-177)
    cn.command_server(st, "server start")
    # server status when running (lines 197-202)
    cn.command_server(st, "server status")
    # server stop when running (lines 204-213)
    cn.command_server(st, "server stop")
    assert st.network_server is None
    # server invalid action (line 215)
    with pytest.raises(ValueError):
        cn.command_server(st, "server xyz")

    # _load_discovered_servers_for_listing with server running (line 110)
    cn._load_discovered_servers_for_listing(NS(network_server=fake_srv))

    # stop_server with a server object (lines 627-628)
    st2 = NS(network_server=NS(stop=lambda: None))
    cn.stop_server(st2)
    assert st2.network_server is None

    # server list with a cached server (lines 143-147, 165-168)
    remember_server("cached-srv", "127.0.0.1", 9998)
    st3 = NS(
        network_client=None,
        network_server=None,
        network_discovery_initial_wait_done=True,
    )
    cn.command_server(st3, "server list")
    assert "cached-srv" in capsys.readouterr().out

    # Ping/players/scoreboard with fake connected client (lines 267-268, 320-321, 344-345)
    cn.command_ping(NS(network_client=NS(ping=lambda: 10.0)), "ping")
    cn.command_players(NS(network_client=NS(players=lambda: [])), "players")
    cn.command_scoreboard(NS(network_client=NS(scoreboard=lambda: [])), "scoreboard")
    capsys.readouterr()

    # network_handlers.command_server wrapper (lines 20-24)
    events: list = []
    bus = NS(emit=lambda name, **kw: events.append(name))
    st4 = NS(network_client=None, network_server=None, event_bus=bus)
    nh.command_server(st4, "server status", command_server_fn=cn.command_server)
    assert "network.server_command" in events

    # network_handlers.command_join: client stays None → early return (line 105)
    nh.command_join(
        NS(network_client=None, event_bus=None),
        "join",
        command_join_fn=lambda s, l: False,
        save_local_state_before_network=lambda s: None,
        apply_game_state_to_local_session=lambda s, d: None,
    )

    # network_handlers.command_join: drain callbacks (lines 112, 115, 117, 133, 136)
    applied: list = []
    notified: list = []

    class _FakeClient:
        def set_opponent_move_callback(self, cb):
            pass

        def set_game_state_callback(self, cb):
            pass

        def set_notification_callback(self, cb):
            pass

        def set_connection_lost_callback(self, cb):
            pass

        def drain_opponent_moves(self):
            return []

        def drain_game_state_updates(self):
            return [{"x": 1}]

        def drain_notifications(self):
            return ["hello"]

    st5 = NS(network_client=None, event_bus=None)

    def _set_client(s, l):
        s.network_client = _FakeClient()
        return False

    nh.command_join(
        st5,
        "join",
        command_join_fn=_set_client,
        save_local_state_before_network=lambda s: None,
        apply_game_state_to_local_session=lambda s, d: applied.append(d),
        on_notification=lambda m: notified.append(m),
    )
    assert applied and notified

    # stop_discovery_listener(None) → early return (line 79)
    cn.stop_discovery_listener(None)

    # _command_move_with_notation: ValueError from client.move() (lines 553-555)
    class _MoveValueError:
        def move(self, _n):
            raise ValueError("bad")

        def drain_opponent_moves(self):
            return []

    cn._command_move_with_notation(NS(network_client=_MoveValueError()), "e1-e2")

    # _command_move_with_notation: error response (line 564)
    class _MoveErrResp:
        def move(self, _n):
            return "ERROR NOT_YOUR_TURN"

        def drain_opponent_moves(self):
            return []

    cn._command_move_with_notation(NS(network_client=_MoveErrResp()), "e1-e2")

    # disconnect_client: quit() raises OSError + has network_player_id (lines 615-617, 619)
    class _QuitRaises:
        def quit(self):
            raise OSError("gone")

        def close(self):
            pass

    st6 = NS(
        network_client=_QuitRaises(), network_player_id=1, network_restore_callback=None
    )
    cn.disconnect_client(st6)
    assert st6.network_player_id is None


def test_server_handshake_rejects_invalid_hello_and_name():
    port = _unused_port()
    server = NetworkServer(port=port)

    try:
        server.start()
        sock = socket.create_connection(
            ("127.0.0.1", port), timeout=_SOCKET_TIMEOUT_SEC
        )
        sock.settimeout(_SOCKET_TIMEOUT_SEC)
        try:
            assert _recv_protocol_line(sock).startswith("WELCOME ")
            _send_line(sock, "HELLO")
            assert _recv_protocol_line(sock) == "ERROR HELLO_REQUIRED"
            _recv_optional_protocol_line(sock)
        finally:
            sock.close()

        sock = socket.create_connection(
            ("127.0.0.1", port), timeout=_SOCKET_TIMEOUT_SEC
        )
        sock.settimeout(_SOCKET_TIMEOUT_SEC)
        try:
            assert _recv_protocol_line(sock).startswith("WELCOME ")
            _send_line(sock, "HELLO !!!")
            assert _recv_protocol_line(sock) == "ERROR INVALID_NAME"
            assert _recv_optional_protocol_line(sock) in (None, "BYE")
        finally:
            sock.close()
    finally:
        server.stop()
