"""Compatibility helpers and lazy exports for the network package."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import NetworkClient
    from .discovery import (
        DiscoveredServer,
        DiscoveryBroadcaster,
        discover_servers,
        format_discovery_message,
        parse_discovery_message,
        remember_server,
    )
    from .server import NetworkServer


DEFAULT_SERVER_HOST = "localhost"
DEFAULT_SERVER_PORT = 12345
DISCOVERY_PORT = 12346
DISCOVERY_BROADCAST_INTERVAL_SEC = 10.0
DISCOVERY_TIMEOUT_SEC = DISCOVERY_BROADCAST_INTERVAL_SEC + 0.5
DISCOVERY_ENTRY_TTL_SEC = 30.0
CLIENT_TIMEOUT_SEC = 60.0
_SOCKET_TIMEOUT_SEC = 0.5
_DISCOVERY_BUFFER_SIZE = 1024
_DISCOVERY_PREFIX = "QUORIDOR_SERVER"


def _validate_port(port: int) -> int:
    """Validate a TCP or UDP port."""
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid port: {port}")
    return port


def _send_line(sock: socket.socket, message: str) -> None:
    sock.sendall(f"{message}\n".encode("ascii", errors="strict"))


def _recv_line(
    sock: socket.socket,
    buffer: str,
) -> tuple[str | None, str, bool]:
    while "\n" not in buffer:
        try:
            data = sock.recv(_DISCOVERY_BUFFER_SIZE)
        except socket.timeout:
            return None, buffer, False
        if not data:
            return None, buffer, True
        buffer += data.decode("ascii", errors="ignore")

    line, buffer = buffer.split("\n", 1)
    return line.rstrip("\r"), buffer, False


def parse_endpoint(
    raw: str | None,
    *,
    default_host: str = DEFAULT_SERVER_HOST,
    default_port: int = DEFAULT_SERVER_PORT,
) -> tuple[str, int]:
    """Parse a HOST[:PORT] endpoint."""
    default_port = _validate_port(default_port)
    if not raw:
        return default_host, default_port

    text = raw.strip()
    if not text:
        return default_host, default_port

    if ":" not in text:
        return text, default_port

    host, port_text = text.rsplit(":", 1)
    host = host.strip() or default_host
    if not port_text.strip():
        return host, default_port
    return host, _validate_port(int(port_text))


__all__ = [
    "CLIENT_TIMEOUT_SEC",
    "DEFAULT_SERVER_HOST",
    "DEFAULT_SERVER_PORT",
    "DISCOVERY_BROADCAST_INTERVAL_SEC",
    "DISCOVERY_ENTRY_TTL_SEC",
    "DISCOVERY_PORT",
    "DISCOVERY_TIMEOUT_SEC",
    "DiscoveredServer",
    "DiscoveryBroadcaster",
    "NetworkClient",
    "NetworkServer",
    "discover_servers",
    "format_discovery_message",
    "parse_discovery_message",
    "parse_endpoint",
    "remember_server",
]


def __getattr__(name: str):
    if name == "NetworkClient":
        from .client import NetworkClient

        return NetworkClient
    if name == "NetworkServer":
        from .server import NetworkServer

        return NetworkServer
    if name in {
        "DiscoveredServer",
        "DiscoveryBroadcaster",
        "discover_servers",
        "format_discovery_message",
        "parse_discovery_message",
        "remember_server",
    }:
        from . import discovery

        return getattr(discovery, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
