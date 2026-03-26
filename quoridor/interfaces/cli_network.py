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
        raise ValueError("Invalid format. Use: server list|start [PORT]|stop")

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

    raise ValueError("Invalid format. Use: server list|start [PORT]|stop")


def command_join(state: NetworkState, line: str) -> bool:
    parts = line.split(maxsplit=1)
    if state.network_client is not None:
        print(
            f"Already connected to server "
            f"{state.network_client.host}:{state.network_client.port}."
        )
        return False

    endpoint = parts[1] if len(parts) == 2 else None
    try:
        host, port = parse_endpoint(endpoint)
    except ValueError as exc:
        raise ValueError(
            "Invalid format. Use: join [HOST[:PORT]]"
        ) from exc
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
