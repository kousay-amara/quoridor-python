from __future__ import annotations

import socket
import threading
import time

from .discovery import DiscoveryBroadcaster, remember_server
from .basic_network import (
    CLIENT_TIMEOUT_SEC,
    DEFAULT_SERVER_PORT,
    DISCOVERY_BROADCAST_INTERVAL_SEC,
    DISCOVERY_PORT,
    _SOCKET_TIMEOUT_SEC,
    _recv_line,
    _send_line,
    _validate_port,
)


class _ClientSession:
    def __init__(
        self,
        *,
        sock: socket.socket,
        thread: threading.Thread,
        last_activity_time: float,
        name: str,
        status: str,
        buffer: str,
    ) -> None:
        self.sock = sock
        self.thread = thread
        self.last_activity_time = last_activity_time
        self.name = name
        self.status = status
        self.buffer = buffer


class NetworkServer:
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
        self._listener_sock = None
        self._accept_thread = None
        self._client_sessions: dict[int, _ClientSession] = {}
        self._next_client_id = 1
        self._lock = threading.RLock()

    def running(self) -> bool:
        return (
            self._accept_thread is not None
            and self._accept_thread.is_alive()
        )

    def status_snapshot(self) -> dict[str, int]:
        with self._lock:
            connected_clients = len(self._client_sessions)
        return {
            "port": self.port,
            "connected_clients": connected_clients,
            "active_games": 0,
        }

    def start(self) -> None:
        if self.running():
            return

        listener_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener_sock.settimeout(_SOCKET_TIMEOUT_SEC)
        try:
            listener_sock.bind((self.host, self.port))
            listener_sock.listen(16)
        except OSError:
            listener_sock.close()
            raise

        self._listener_sock = listener_sock
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

        if self._listener_sock is not None:
            try:
                self._listener_sock.close()
            except OSError:
                pass
            self._listener_sock = None

        with self._lock:
            sessions = list(self._client_sessions.items())
            self._client_sessions = {}

        for _client_id, session in sessions:
            try:
                _send_line(session.sock, "SERVER_STOPPING")
                _send_line(session.sock, "BYE")
            except OSError:
                pass
            try:
                session.sock.close()
            except OSError:
                pass

        current_thread = threading.current_thread()
        with self._lock:
            client_threads = [session.thread for _, session in sessions]

        if self._accept_thread is not None:
            self._accept_thread.join(timeout=0.5)
        self._accept_thread = None

        for client_thread in client_threads:
            if (
                client_thread is not current_thread
                and client_thread.is_alive()
            ):
                client_thread.join(timeout=0.5)

    def _accept_loop(self) -> None:
        assert self._listener_sock is not None
        while not self._stop_requested.is_set():
            try:
                client_sock, _address = self._listener_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_sock.settimeout(_SOCKET_TIMEOUT_SEC)
            with self._lock:
                client_id = self._next_client_id
                self._next_client_id += 1

            client_thread = threading.Thread(
                target=self._client_loop,
                args=(client_id, client_sock),
                name=f"quoridor-network-client-{client_id}",
                daemon=True,
            )
            with self._lock:
                self._client_sessions[client_id] = _ClientSession(
                    sock=client_sock,
                    thread=client_thread,
                    last_activity_time=time.time(),
                    name=f"client-{client_id}",
                    status="idle",
                    buffer="",
                )

            try:
                _send_line(client_sock, f"WELCOME {self.name} {self.port}")
            except OSError:
                self._close_client(client_id, client_sock)
                continue

            if not self._perform_hello(client_id, client_sock):
                self._close_client(client_id, client_sock)
                continue

            client_thread.start()

    def _client_loop(
        self,
        client_id: int,
        client_sock: socket.socket,
    ) -> None:
        with self._lock:
            session = self._client_sessions.get(client_id)
            if session is None:
                return
            buffer = session.buffer
        try:
            while not self._stop_requested.is_set():
                with self._lock:
                    session = self._client_sessions.get(client_id)
                    if session is None:
                        break
                    last_client_activity_time = session.last_activity_time

                if (
                    last_client_activity_time is not None
                    and time.time() - last_client_activity_time
                    > self.client_timeout_sec
                ):
                    try:
                        _send_line(client_sock, "ERROR TIMEOUT")
                        _send_line(client_sock, "BYE")
                    except OSError:
                        pass
                    break

                try:
                    line, buffer, closed = _recv_line(client_sock, buffer)
                except OSError:
                    break
                if closed:
                    break
                if line is None:
                    continue

                with self._lock:
                    session = self._client_sessions.get(client_id)
                    if session is None:
                        break
                    session.last_activity_time = time.time()

                command = line.strip()
                if not command:
                    continue

                command_upper = command.upper()
                if command_upper == "PING":
                    started_at = time.time()
                    response_ms = round((time.time() - started_at) * 1000.0)
                    try:
                        _send_line(client_sock, f"PONG TIME={response_ms}ms")
                    except OSError:
                        break
                    continue

                if command_upper == "PLAYERS":
                    try:
                        _send_line(
                            client_sock,
                            self._format_players_response(),
                        )
                    except OSError:
                        break
                    continue

                if command_upper == "QUIT":
                    try:
                        _send_line(client_sock, "BYE")
                    except OSError:
                        pass
                    break

                try:
                    _send_line(client_sock, "ERROR UNKNOWN_COMMAND")
                except OSError:
                    break
        finally:
            self._close_client(client_id, client_sock)

    def _close_client(
        self,
        client_id: int,
        client_sock: socket.socket,
    ) -> None:
        try:
            client_sock.close()
        except OSError:
            pass

        with self._lock:
            session = self._client_sessions.get(client_id)
            if session is not None and session.sock is client_sock:
                del self._client_sessions[client_id]

    def _perform_hello(
        self,
        client_id: int,
        client_sock: socket.socket,
    ) -> bool:
        buffer = ""
        deadline = time.time() + 5.0
        while not self._stop_requested.is_set():
            if time.time() > deadline:
                try:
                    _send_line(client_sock, "ERROR HELLO_TIMEOUT")
                    _send_line(client_sock, "BYE")
                except OSError:
                    pass
                return False

            try:
                line, buffer, closed = _recv_line(client_sock, buffer)
            except OSError:
                return False

            if closed:
                return False
            if line is None:
                continue

            if not line.upper().startswith("HELLO "):
                try:
                    _send_line(client_sock, "ERROR HELLO_REQUIRED")
                    _send_line(client_sock, "BYE")
                except OSError:
                    pass
                return False

            raw_name = line[6:].strip()
            client_name = self._parse_client_name(raw_name)
            if client_name is None:
                try:
                    _send_line(client_sock, "ERROR INVALID_NAME")
                    _send_line(client_sock, "BYE")
                except OSError:
                    pass
                return False

            with self._lock:
                session = self._client_sessions.get(client_id)
                if session is None:
                    return False
                session.name = client_name
                session.status = "idle"
                session.buffer = buffer

            try:
                _send_line(client_sock, f"HELLO_OK {client_id}")
            except OSError:
                return False
            return True
        return False

    def _parse_client_name(self, raw_name: str) -> str | None:
        name = raw_name.strip()
        if not name or len(name) > 32:
            return None
        if any(not (char.isalnum() or char in {"-", "_"}) for char in name):
            return None
        return name

    def _format_players_response(self) -> str:
        with self._lock:
            players = [
                (client_id, session.name, session.status)
                for client_id, session in self._client_sessions.items()
            ]

        players.sort(key=lambda item: item[0])
        if not players:
            return "PLAYERS"

        payload = ";".join(
            f"{client_id}|{name}|{status}"
            for client_id, name, status in players
        )
        return f"PLAYERS {payload}"


__all__ = ["NetworkServer"]
