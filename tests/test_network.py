from __future__ import annotations

import socket
import time

import pytest

import quoridor.network.discovery as discovery_mod
from quoridor.interfaces import cli as cli_mod
from quoridor.network import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DiscoveryBroadcaster,
    DiscoveryListener,
    NetworkClient,
    NetworkServer,
    discover_servers,
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


def _run_shell(monkeypatch, commands: list[str], **kwargs) -> None:
    iterator = iter(commands)

    def fake_input(_prompt: str = "") -> str:
        if _prompt:
            print(_prompt, end="")
        try:
            return next(iterator)
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


def test_parse_endpoint_supports_defaults_and_explicit_values():
    assert parse_endpoint(None) == (DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
    assert parse_endpoint("   ") == (DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
    assert parse_endpoint("127.0.0.1") == ("127.0.0.1", DEFAULT_SERVER_PORT)
    assert parse_endpoint("127.0.0.1:23456") == ("127.0.0.1", 23456)


def test_discovery_message_round_trip_and_invalid_prefix():
    message = format_discovery_message("alpha", 23456)

    assert parse_discovery_message(message) == ("alpha", 23456)
    assert parse_discovery_message("WRONG alpha 23456") is None


def test_discover_servers_finds_udp_broadcast():
    server_port = _unused_port()
    discovery_port = _unused_port()
    broadcaster = DiscoveryBroadcaster(
        port=server_port,
        discovery_port=discovery_port,
        interval_sec=0.05,
    )

    try:
        broadcaster.start()
        servers = discover_servers(
            timeout_sec=0.2,
            listen_port=discovery_port,
        )
    finally:
        broadcaster.stop()

    assert any(
        server.name == "quoridor-server" and server.port == server_port
        for server in servers
    )


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


def test_network_server_rejects_second_client():
    port = _unused_port()
    server = NetworkServer(port=port)
    first_client = NetworkClient(host="127.0.0.1", port=port)
    second_client = NetworkClient(host="127.0.0.1", port=port)

    try:
        server.start()
        first_client.connect()

        with pytest.raises(OSError, match="ERROR BUSY"):
            second_client.connect()
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
            "ping",
            "quit",
            "server stop",
            "quit",
        ],
    )

    out = capsys.readouterr().out
    assert f"Server started on port {port}." in out
    assert f"Connected to server 127.0.0.1:{port}." in out
    assert "PONG TIME=" in out
    assert "Disconnected from server." in out
    assert "Server stopped." in out
    assert "Bye." in out
