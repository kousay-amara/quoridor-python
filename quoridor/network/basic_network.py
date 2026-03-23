from __future__ import annotations

import socket
import threading
import time

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


_discovery_cache = {}


def _send_line(sock: socket.socket, message: str) -> None:
    sock.sendall(f"{message}\n".encode("ascii", errors="strict"))


def remember_server(name: str, host: str, port: int) -> None:
    server = DiscoveredServer(name, host, _validate_port(port))
    _discovery_cache[(server.host, server.port)] = (server, time.time())


class DiscoveredServer:
    def __init__(self, name: str, host: str, port: int) -> None:
        self.name = name
        self.host = host
        self.port = port


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
                if self.interval_sec <= 0:
                    break
                if self._stop_requested.wait(self.interval_sec):
                    break
        finally:
            sock.close()


class BasicNetworkServer:
    def __init__(
        self,
        *,
        host: str = "",
        port: int = DEFAULT_SERVER_PORT,
        name: str = "quoridor-server",
        discovery_port: int = DISCOVERY_PORT,
        broadcast_interval_sec: float = DISCOVERY_BROADCAST_INTERVAL_SEC,
        client_timeout_sec: float = CLIENT_TIMEOUT_SEC,
    ) -> None:
        self.host = host
        self.port = _validate_port(port)
        self.name = name.strip() or "quoridor-server"
        self.discovery_port = _validate_port(discovery_port)
        self.broadcast_interval_sec = broadcast_interval_sec
        self.client_timeout_sec = client_timeout_sec
        self._broadcaster = DiscoveryBroadcaster(
            port=self.port,
            name=self.name,
            discovery_port=self.discovery_port,
            interval_sec=self.broadcast_interval_sec,
        )
        self._stop_requested = threading.Event()
        self._listener = None
        self._accept_thread = None
        self._client_monitor_thread = None
        self._client = None
        self._last_client_activity = None
        self._lock = threading.Lock()

    def running(self) -> bool:
        return self._accept_thread is not None and self._accept_thread.is_alive()

    def start(self) -> None:
        if self.running():
            return

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(_SOCKET_TIMEOUT_SEC)
        try:
            listener.bind((self.host, self.port))
            listener.listen(1)
        except OSError:
            listener.close()
            raise

        self._listener = listener
        self._stop_requested.clear()
        remember_server(self.name, "127.0.0.1", self.port)
        self._broadcaster.start()
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="quoridor-network-accept",
            daemon=True,
        )
        self._accept_thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        self._broadcaster.stop()

        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass

        with self._lock:
            client = self._client
            self._client = None
            self._last_client_activity = None

        if client is not None:
            try:
                _send_line(client, "SERVER_STOPPING")
                _send_line(client, "BYE")
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass

        accept_thread = self._accept_thread
        if accept_thread is not None:
            accept_thread.join(timeout=0.5)
        self._accept_thread = None

        monitor_thread = self._client_monitor_thread
        if monitor_thread is not None:
            monitor_thread.join(timeout=0.5)
        self._client_monitor_thread = None

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._stop_requested.is_set():
            try:
                conn, _address = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            conn.settimeout(_SOCKET_TIMEOUT_SEC)
            with self._lock:
                if self._client is not None:
                    try:
                        _send_line(conn, "ERROR BUSY")
                    except OSError:
                        pass
                    try:
                        conn.close()
                    except OSError:
                        pass
                    continue
                self._client = conn
                self._last_client_activity = time.time()

            try:
                _send_line(conn, f"WELCOME {self.name} {self.port}")
            except OSError:
                self._close_client(conn)
                continue

            self._client_monitor_thread = threading.Thread(
                target=self._monitor_client,
                args=(conn,),
                name="quoridor-network-client",
                daemon=True,
            )
            self._client_monitor_thread.start()

    def _monitor_client(self, conn: socket.socket) -> None:
        try:
            while not self._stop_requested.is_set():
                with self._lock:
                    if self._client is not conn:
                        break
                    last_client_activity = self._last_client_activity

                if (
                    last_client_activity is not None
                    and time.time() - last_client_activity
                    > self.client_timeout_sec
                ):
                    try:
                        _send_line(conn, "ERROR TIMEOUT")
                        _send_line(conn, "BYE")
                    except OSError:
                        pass
                    break

                try:
                    data = conn.recv(1, socket.MSG_PEEK)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not data:
                    break

                with self._lock:
                    if self._client is conn:
                        self._last_client_activity = time.time()

                if self._stop_requested.wait(_SOCKET_TIMEOUT_SEC):
                    break
        finally:
            self._close_client(conn)

    def _close_client(self, conn: socket.socket) -> None:
        try:
            conn.close()
        except OSError:
            pass

        with self._lock:
            if self._client is conn:
                self._client = None
                self._last_client_activity = None


def _validate_port(port: int) -> int:
    """Validate a TCP or UDP port."""
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid port: {port}")
    return port


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


def discover_servers(
    *,
    timeout_sec: float = DISCOVERY_TIMEOUT_SEC,
    listen_port: int = DISCOVERY_PORT,
) -> list[DiscoveredServer]:
    """Listen for UDP discovery announcements on the local network."""
    listen_port = _validate_port(listen_port)

    now = time.time()
    expired_keys = [
        key
        for key, (_server, last_seen_time) in _discovery_cache.items()
        if now - last_seen_time > DISCOVERY_ENTRY_TTL_SEC
    ]
    for key in expired_keys:
        del _discovery_cache[key]

    if timeout_sec > 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", listen_port))
            deadline = time.time() + timeout_sec
            while True:
                remaining = deadline - time.time()
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

    now = time.time()
    servers = []
    for key, value in list(_discovery_cache.items()):
        server, last_seen = value
        if now - last_seen > DISCOVERY_ENTRY_TTL_SEC:
            del _discovery_cache[key]
            continue
        servers.append(server)

    return sorted(
        servers,
        key=lambda item: (item.name.lower(), item.host, item.port),
    )
