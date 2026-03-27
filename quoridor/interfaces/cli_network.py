"""Network command handlers extracted from CLI shell."""

from __future__ import annotations

from typing import Protocol

from ..network import (
    DEFAULT_SERVER_PORT,
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
        servers = get_discovered_servers()
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
        status = state.network_server.status_snapshot()
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

    if len(parts) == 3:
        client = NetworkClient(host=host, port=port, name=name)
    else:
        client = NetworkClient(host=host, port=port)
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
        state.network_client.close()
        state.network_client = None
        print(f"Connection lost: {exc}")
        return False

    print(f"PONG TIME={round(round_trip_ms)}ms")
    return False


def command_players(state: NetworkState, line: str) -> bool:
    if line.strip().lower() != "players":
        raise ValueError("Invalid format. Use: players")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        players = state.network_client.players()
    except OSError as exc:
        state.network_client.close()
        state.network_client = None
        print(f"Connection lost: {exc}")
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
        state.network_client.close()
        state.network_client = None
        print(f"Connection lost: {exc}")
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
    if len(parts) != 2:
        raise ValueError("Invalid format. Use: new PLAYER_ID")

    if state.network_client is None:
        print("Not connected to any server.")
        return False

    try:
        target_player_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Invalid format. Use: new PLAYER_ID") from exc
    if target_player_id <= 0:
        raise ValueError("Invalid format. Use: new PLAYER_ID")

    try:
        response = state.network_client.send_command(
            f"NEW {target_player_id}"
        )
    except OSError as exc:
        state.network_client.close()
        state.network_client = None
        print(f"Connection lost: {exc}")
        return False

    if response.startswith("NEW_OK "):
        parts = response.split()
        if len(parts) != 2:
            print(f"Cannot create game: unexpected response ({response}).")
            return False
        try:
            game_id = int(parts[1])
        except ValueError:
            print(f"Cannot create game: unexpected response ({response}).")
            return False
        print(f"Game {game_id} started with player {target_player_id}.")
        return False

    if response == "ERROR PLAYER_NOT_FOUND":
        print(f"Cannot create game: player {target_player_id} not found.")
        return False
    if response == "ERROR PLAYER_NOT_AVAILABLE":
        print(f"Cannot create game: player {target_player_id} is busy.")
        return False
    if response == "ERROR REQUESTER_NOT_IDLE":
        print("Cannot create game: you are already in game.")
        return False
    if response == "ERROR SELF_INVITE":
        print("Cannot create game: choose another player.")
        return False
    if response == "ERROR INVALID_NEW_FORMAT":
        raise ValueError("Invalid format. Use: new PLAYER_ID")

    print(f"Cannot create game: unexpected response ({response}).")
    return False


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
    return True


def stop_server(state: NetworkState) -> None:
    if state.network_server is None:
        return
    state.network_server.stop()
    state.network_server = None
