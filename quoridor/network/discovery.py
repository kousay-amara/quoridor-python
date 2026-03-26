from __future__ import annotations

import socket
import threading
from time import time as _current_time

from .basic_network import (
    DEFAULT_SERVER_PORT,
    DISCOVERY_BROADCAST_INTERVAL_SEC,
    DISCOVERY_ENTRY_TTL_SEC,
    DISCOVERY_PORT,
    DISCOVERY_TIMEOUT_SEC,
    _DISCOVERY_BUFFER_SIZE,
    _DISCOVERY_PREFIX,
    _SOCKET_TIMEOUT_SEC,
    _validate_port,
)

_discovery_cache = {}
_discovery_cache_lock = threading.Lock()


class DiscoveredServer:
    def __init__(self, name: str, host: str, port: int) -> None:
        self.name = name
        self.host = host
        self.port = port


def _prune_discovery_cache_locked(now: float | None = None) -> None:
    if now is None:
        now = _current_time()

    expired_keys = [
        key
        for key, (_server, last_seen_time) in _discovery_cache.items()
        if now - last_seen_time > DISCOVERY_ENTRY_TTL_SEC
    ]
    for key in expired_keys:
        del _discovery_cache[key]


def _snapshot_discovered_servers_locked() -> list[DiscoveredServer]:
    servers = [server for server, _last_seen in _discovery_cache.values()]
    return sorted(
        servers,
        key=lambda item: (item.name.lower(), item.host, item.port),
    )


def remember_server(name: str, host: str, port: int) -> None:
    server = DiscoveredServer(name, host, _validate_port(port))
    with _discovery_cache_lock:
        _discovery_cache[(server.host, server.port)] = (
            server,
            _current_time(),
        )


def get_discovered_servers() -> list[DiscoveredServer]:
    with _discovery_cache_lock:
        _prune_discovery_cache_locked()
        return _snapshot_discovered_servers_locked()


def format_discovery_message(name: str, port: int) -> str:
    """Build a UDP discovery announcement."""
    port = _validate_port(port)
    server_name = name.strip()
    if not server_name:
        raise ValueError("server name must not be empty")
    return f"{_DISCOVERY_PREFIX} {server_name} {port}"


def parse_discovery_message(message: str) -> tuple[str, int] | None:
    """Parse a UDP discovery announcement."""
    parts = message.strip().split()
    if len(parts) != 3 or parts[0] != _DISCOVERY_PREFIX:
        return None
    try:
        port = _validate_port(int(parts[2]))
    except ValueError:
        return None
    return parts[1], port


class DiscoveryBroadcaster:
    def __init__(
        self,
        *,
        port: int = DEFAULT_SERVER_PORT,
        name: str = "quoridor-server",
        discovery_port: int = DISCOVERY_PORT,
        interval_sec: float = DISCOVERY_BROADCAST_INTERVAL_SEC,
    ) -> None:
        self.port = _validate_port(port)
        self.name = name.strip() or "quoridor-server"
        self.discovery_port = _validate_port(discovery_port)
        self.interval_sec = interval_sec
        self._stop_requested = threading.Event()
        self._thread = None

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running():
            return
        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._broadcast_loop,
            name="quoridor-discovery-broadcast",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=0.5)
        self._thread = None

    def _broadcast_loop(self) -> None:
        message = format_discovery_message(self.name, self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while not self._stop_requested.is_set():
                for target in ("255.255.255.255", "127.0.0.1"):
                    try:
                        sock.sendto(
                            message.encode("ascii", errors="strict"),
                            (target, self.discovery_port),
                        )
                    except OSError:
                        continue
                if self._stop_requested.wait(self.interval_sec):
                    break
        finally:
            sock.close()


class DiscoveryListener:
    def __init__(
        self,
        *,
        listen_port: int = DISCOVERY_PORT,
        socket_timeout_sec: float = _SOCKET_TIMEOUT_SEC,
    ) -> None:
        self.listen_port = _validate_port(listen_port)
        self.socket_timeout_sec = socket_timeout_sec
        self._stop_requested = threading.Event()
        self._thread = None

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running():
            return
        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="quoridor-discovery-listener",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=0.5)
        self._thread = None

    def _listen_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.listen_port))
            sock.settimeout(self.socket_timeout_sec)
            while not self._stop_requested.is_set():
                try:
                    message, address = sock.recvfrom(_DISCOVERY_BUFFER_SIZE)
                except socket.timeout:
                    with _discovery_cache_lock:
                        _prune_discovery_cache_locked()
                    continue
                except OSError:
                    break

                parsed = parse_discovery_message(
                    message.decode("ascii", errors="ignore")
                )
                if parsed is None:
                    continue

                name, port = parsed
                remember_server(name, address[0], port)
                with _discovery_cache_lock:
                    _prune_discovery_cache_locked()
        finally:
            sock.close()


def discover_servers(
    *,
    timeout_sec: float = DISCOVERY_TIMEOUT_SEC,
    listen_port: int = DISCOVERY_PORT,
) -> list[DiscoveredServer]:
    """Listen once for UDP discovery announcements on the local network."""
    listen_port = _validate_port(listen_port)

    if timeout_sec > 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", listen_port))
            deadline = _current_time() + timeout_sec
            while True:
                remaining = deadline - _current_time()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    message, address = sock.recvfrom(_DISCOVERY_BUFFER_SIZE)
                except socket.timeout:
                    break

                parsed = parse_discovery_message(
                    message.decode("ascii", errors="ignore")
                )
                if parsed is None:
                    continue

                name, port = parsed
                remember_server(name, address[0], port)
        finally:
            sock.close()

    return get_discovered_servers()


__all__ = [
    "DiscoveredServer",
    "DiscoveryBroadcaster",
    "DiscoveryListener",
    "discover_servers",
    "format_discovery_message",
    "get_discovered_servers",
    "parse_discovery_message",
    "remember_server",
]
