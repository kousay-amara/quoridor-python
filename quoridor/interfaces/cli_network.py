"""Network command handlers extracted from CLI shell."""

from __future__ import annotations

import time
from typing import Protocol

from ..network import (
    DEFAULT_SERVER_PORT,
    DISCOVERY_BROADCAST_INTERVAL_SEC,
    DiscoveredServer,
    DiscoveryListener,
    NetworkClient,
    NetworkServer,
    get_discovered_servers,
    parse_endpoint,
)


class NetworkState(Protocol):
    network_server: NetworkServer | None
    network_client: NetworkClient | None
    network_restore_callback: object | None


_NEW_GAME_ERRORS = {
    "ERROR PLAYER_NOT_FOUND": ("Cannot send invitation: player not found."),
    "ERROR PLAYER_NOT_AVAILABLE": (
        "Cannot send invitation: player is not available."
    ),
    "ERROR REQUESTER_NOT_IDLE": ("Cannot send invitation: you are not idle."),
    "ERROR SELF_INVITE": (
        "Cannot send invitation: choose a player ID different from yours."
    ),
}

_INVITATION_ACTION_ERRORS = {
    "ERROR NO_INVITATION": "No pending invitation.",
    "ERROR PLAYER_NOT_FOUND": "Invitation is no longer available.",
}

_STATUS_CHANGE_ERRORS = {
    "ERROR ALREADY_AWAY": "You are already away.",
    "ERROR CANNOT_GO_AWAY": "Cannot go away right now.",
    "ERROR NOT_AWAY": "You are not away.",
}

_MOVE_ERRORS = {
    "ERROR NOT_IN_GAME": "Cannot play move: you are not in a network game.",
    "ERROR NOT_YOUR_TURN": "Cannot play move: not your turn.",
    "ERROR INVALID_MOVE_FORMAT": "Cannot play move: invalid move format.",
    "ERROR ILLEGAL_MOVE": "Cannot play move: illegal move.",
    "ERROR OPPONENT_DISCONNECTED": (
        "Cannot play move: opponent disconnected."
    ),
}

_DISCOVERY_WARMUP_POLL_SEC = 0.05


def parse_server_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError(f"invalid port: {value}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid port: {value}")
    return port


def start_discovery_listener() -> DiscoveryListener:
    listener = DiscoveryListener()
    listener.start()
    return listener


def stop_discovery_listener(listener: DiscoveryListener | None) -> None:
    if listener is None:
        return
    listener.stop()


def _restore_local_mode(state: NetworkState) -> None:
    callback = getattr(state, "network_restore_callback", None)
    if callback is None:
        return
    try:
        callback()
    except Exception:
        return


def _handle_connection_lost(
    state: NetworkState,
    exc: OSError,
) -> None:
    if state.network_client is not None:
        state.network_client.close()
    state.network_client = None
    if hasattr(state, "network_player_id"):
        setattr(state, "network_player_id", None)
    print(f"Connection lost: {exc}")
    _restore_local_mode(state)


def _load_discovered_servers_for_listing(
    state: NetworkState,
) -> list[DiscoveredServer]:
    if state.network_server is not None:
        return get_discovered_servers()

    if getattr(state, "network_discovery_initial_wait_done", False):
        return get_discovered_servers()

    setattr(state, "network_discovery_initial_wait_done", True)
    deadline = time.monotonic() + DISCOVERY_BROADCAST_INTERVAL_SEC
    while time.monotonic() < deadline:
        servers = get_discovered_servers()
        if servers:
            return servers
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(_DISCOVERY_WARMUP_POLL_SEC, remaining))
    return get_discovered_servers()


def command_server(state: NetworkState, line: str) -> bool:
    parts = line.split()
    if len(parts) < 2:
        raise ValueError(
            "Invalid format. Use: server list|start [PORT]|status|stop"
        )

    action = parts[1].lower()
    if action == "list":
        if len(parts) != 2:
            raise ValueError("Invalid format. Use: server list")
        servers = _load_discovered_servers_for_listing(state)
        unique_servers = []
        seen_server_keys = set()
        for server in servers:
            server_key = (server.name, server.port)
            if server_key in seen_server_keys:
                continue
            seen_server_keys.add(server_key)
            unique_servers.append(server)
        servers = unique_servers
        if state.network_server is not None:
            local_server = DiscoveredServer(
                state.network_server.name,
                "127.0.0.1",
                state.network_server.port,
            )
            servers = [
                server
                for server in servers
                if (server.name, server.port)
                != (local_server.name, local_server.port)
            ]
            servers = [local_server, *servers]
        if not servers:
            print("No network servers found.")
            return False
        print("Discovered servers:")
        for server in servers:
            print(f"- {server.name} ({server.host}:{server.port})")
        return False

    if action == "start":
        if len(parts) > 3:
            raise ValueError("Invalid format. Use: server start [PORT]")
        if state.network_server is not None:
            print(
                f"Server already running on port {state.network_server.port}."
            )
            return False
        port = DEFAULT_SERVER_PORT
        if len(parts) == 3:
            port = parse_server_port(parts[2])
        server = NetworkServer(port=port)
        try:
            server.start()
        except OSError as exc:
            print(f"Cannot start server on port {port}: {exc}")
            return False
        state.network_server = server
        print(f"Server started on port {server.port}.")
        return False

    if action == "status":
        if len(parts) != 2:
            raise ValueError("Invalid format. Use: server status")
        if state.network_server is None:
            print("Server is not running.")
            return False
        status = state.network_server.server_status_snapshot()
        print("Server status:")
        print(f"- port: {status['port']}")
        print(f"- connected clients: {status['connected_clients']}")
        print(f"- active games: {status['active_games']}")
        return False

    if action == "stop":
        if len(parts) != 2:
            raise ValueError("Invalid format. Use: server stop")
        if state.network_server is None:
            print("Server is not running.")
            return False
        state.network_server.stop()
        state.network_server = None
        print("Server stopped.")
        return False

    raise ValueError(
        "Invalid format. Use: server list|start [PORT]|status|stop"
    )


def command_join(state: NetworkState, line: str) -> bool:
    parts = line.split(maxsplit=2)
    if state.network_client is not None:
        print(
            f"Already connected to server "
            f"{state.network_client.host}:{state.network_client.port}."
        )
        return False

    if len(parts) > 3:
        raise ValueError("Invalid format. Use: join [HOST[:PORT]] [NAME]")

    endpoint = parts[1] if len(parts) >= 2 else None
    name = parts[2].strip() if len(parts) == 3 else ""
    if len(parts) == 3 and not name:
        raise ValueError("Invalid format. Use: join [HOST[:PORT]] [NAME]")

    try:
        host, port = parse_endpoint(endpoint)
    except ValueError as exc:
        raise ValueError(
            "Invalid format. Use: join [HOST[:PORT]] [NAME]"
        ) from exc

    client = NetworkClient(host=host, port=port, name=name or "player")
    try:
        client.connect()
    except OSError as exc:
        print(f"Cannot connect to server {host}:{port}: {exc}")
        return False

    state.network_client = client
    print(f"Connected to server {host}:{port}.")
    return False


def command_ping(state: NetworkState, _line: str) -> bool:
    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        round_trip_ms = state.network_client.ping()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    print(f"PONG TIME={round(round_trip_ms)}ms")
    return False


def command_players(state: NetworkState, line: str) -> bool:
    parts = line.split()
    if len(parts) > 2 or not parts or parts[0].lower() != "players":
        raise ValueError("Invalid format. Use: players [PLAYER_ID]")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    if len(parts) == 2:
        try:
            requested_player_id = int(parts[1])
        except ValueError as exc:
            raise ValueError(
                "Invalid format. Use: players [PLAYER_ID]"
            ) from exc
        if requested_player_id <= 0:
            raise ValueError("Invalid format. Use: players [PLAYER_ID]")

        try:
            (
                client_id,
                name,
                status,
                wins,
                losses,
                played,
            ) = state.network_client.player_details(requested_player_id)
        except ValueError as exc:
            print(str(exc))
            return False
        except OSError as exc:
            _handle_connection_lost(state, exc)
            return False

        print(f"Player {client_id}: {name}")
        print(f"- status: {status}")
        print(f"- played: {played}")
        print(f"- wins: {wins}")
        print(f"- losses: {losses}")
        return False

    try:
        players = state.network_client.players()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if not players:
        print("No connected players.")
        return False

    print("Connected players:")
    for client_id, name, status in players:
        print(f"- {client_id}: {name} ({status})")
    return False


def command_scoreboard(state: NetworkState, line: str) -> bool:
    if line.strip().lower() != "scoreboard":
        raise ValueError("Invalid format. Use: scoreboard")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        scores = state.network_client.scoreboard()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if not scores:
        print("Scoreboard is empty.")
        return False

    print("Scoreboard:")
    for client_id, name, wins, losses, played in scores:
        print(
            f"- {client_id}: {name} "
            f"(played={played} wins={wins} losses={losses})"
        )
    return False


def command_new_player(state: NetworkState, line: str) -> bool:
    parts = line.split()
    if len(parts) < 2:
        raise ValueError("Invalid format. Use: new PLAYER_ID [PLAYER_ID ...]")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    target_player_ids = []
    seen_target_ids = set()
    for value in parts[1:]:
        try:
            target_player_id = int(value)
        except ValueError as exc:
            raise ValueError(
                "Invalid format. Use: new PLAYER_ID [PLAYER_ID ...]"
            ) from exc
        if target_player_id <= 0 or target_player_id in seen_target_ids:
            raise ValueError(
                "Invalid format. Use: new PLAYER_ID [PLAYER_ID ...]"
            )
        seen_target_ids.add(target_player_id)
        target_player_ids.append(target_player_id)

    try:
        response = state.network_client.send_command(
            "NEW " + " ".join(str(player_id) for player_id in target_player_ids)
        )
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if response.startswith("INVITATION_SENT "):
        print(response)
        return False

    if response == "ERROR INVALID_NEW_FORMAT":
        raise ValueError("Invalid format. Use: new PLAYER_ID [PLAYER_ID ...]")
    if response in _NEW_GAME_ERRORS:
        print(_NEW_GAME_ERRORS[response])
        return False

    print(f"Cannot send invitation: unexpected response ({response}).")
    return False


def command_accept(state: NetworkState, line: str) -> bool:
    if line.strip().lower() != "accept":
        raise ValueError("Invalid format. Use: accept")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        response = state.network_client.accept()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if response.startswith("GAME_START ") or response.startswith("ACCEPT_OK "):
        print(response)
        return False

    print(
        _INVITATION_ACTION_ERRORS.get(
            response,
            f"Cannot accept invitation: unexpected response ({response}).",
        )
    )
    return False


def command_decline(state: NetworkState, line: str) -> bool:
    if line.strip().lower() != "decline":
        raise ValueError("Invalid format. Use: decline")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        response = state.network_client.decline()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if response.startswith("DECLINE_OK"):
        print(response)
        return False

    print(
        _INVITATION_ACTION_ERRORS.get(
            response,
            f"Cannot decline invitation: unexpected response ({response}).",
        )
    )
    return False


def command_cancel(state: NetworkState, line: str) -> bool:
    if line.strip().lower() != "cancel":
        raise ValueError("Invalid format. Use: cancel")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        response = state.network_client.cancel()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if response.startswith("CANCEL_OK"):
        print(response)
        return False

    print(
        _INVITATION_ACTION_ERRORS.get(
            response,
            f"Cannot cancel invitation: unexpected response ({response}).",
        )
    )
    return False


def command_away(state: NetworkState, line: str) -> bool:
    if line.strip().lower() != "away":
        raise ValueError("Invalid format. Use: away")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        response = state.network_client.away()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if response == "AWAY_OK":
        print("Status changed to away.")
        return False

    print(
        _STATUS_CHANGE_ERRORS.get(
            response,
            f"Cannot change status: unexpected response ({response}).",
        )
    )
    return False


def command_back(state: NetworkState, line: str) -> bool:
    if line.strip().lower() != "back":
        raise ValueError("Invalid format. Use: back")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        response = state.network_client.back()
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    if response == "BACK_OK":
        print("Status changed to idle.")
        return False

    print(
        _STATUS_CHANGE_ERRORS.get(
            response,
            f"Cannot change status: unexpected response ({response}).",
        )
    )
    return False


def _print_opponent_moves(client: NetworkClient) -> None:
    for move_notation in client.drain_opponent_moves():
        print(f"OPPONENT_MOVE {move_notation}")


def _command_move_with_notation(
    state: NetworkState,
    move_notation: str,
) -> bool:
    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        response = state.network_client.move(move_notation)
    except ValueError as exc:
        print(f"Cannot play move: {exc}")
        return False
    except OSError as exc:
        _handle_connection_lost(state, exc)
        return False

    client = state.network_client
    if response == "MOVE_OK":
        print(f"Move sent: {move_notation}")
    else:
        print(
            _MOVE_ERRORS.get(
                response,
                f"Cannot play move: unexpected response ({response}).",
            )
        )
    _print_opponent_moves(client)
    return False


def command_move(state: NetworkState, line: str) -> bool:
    if not line.lower().startswith("move "):
        raise ValueError("Invalid format. Use: move <FROM-TO>")
    move_notation = line[5:].strip()
    if not move_notation:
        raise ValueError("Invalid format. Use: move <FROM-TO>")
    return _command_move_with_notation(state, move_notation)


def command_shorthand_move(state: NetworkState, line: str) -> bool:
    move_notation = line.strip()
    if not move_notation:
        raise ValueError("Invalid format. Use: move <FROM-TO>")
    return _command_move_with_notation(state, move_notation)


def command_wall(state: NetworkState, line: str) -> bool:
    if not line.lower().startswith("wall "):
        raise ValueError("Invalid format. Use: wall <POSh|POSv>")
    move_notation = line[5:].strip()
    if not move_notation:
        raise ValueError("Invalid format. Use: wall <POSh|POSv>")
    return _command_move_with_notation(state, move_notation)


def command_shorthand_wall(state: NetworkState, line: str) -> bool:
    move_notation = line.strip()
    if not move_notation:
        raise ValueError("Invalid format. Use: wall <POSh|POSv>")
    return _command_move_with_notation(state, move_notation)


def disconnect_client(state: NetworkState) -> bool:
    if state.network_client is None:
        return False

    client = state.network_client
    state.network_client = None
    try:
        client.quit()
        print("Disconnected from server.")
    except OSError as exc:
        client.close()
        print(f"Disconnected from server: {exc}")
    if hasattr(state, "network_player_id"):
        setattr(state, "network_player_id", None)
    _restore_local_mode(state)
    return True


def stop_server(state: NetworkState) -> None:
    if state.network_server is None:
        return
    state.network_server.stop()
    state.network_server = None
