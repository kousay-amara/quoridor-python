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
        self._client_thread = None
        self._client_sock = None
        self._last_client_activity_time = None
        self._lock = threading.Lock()

    def running(self) -> bool:
        return (
            self._accept_thread is not None
            and self._accept_thread.is_alive()
        )

    def start(self) -> None:
        if self.running():
            return

        listener_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener_sock.settimeout(_SOCKET_TIMEOUT_SEC)
        try:
            listener_sock.bind((self.host, self.port))
            listener_sock.listen(1)
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
            if self._client_sock is not None:
                try:
                    _send_line(self._client_sock, "SERVER_STOPPING")
                    _send_line(self._client_sock, "BYE")
                except OSError:
                    pass
                try:
                    self._client_sock.close()
                except OSError:
                    pass
                self._client_sock = None
            self._last_client_activity_time = None

        if self._accept_thread is not None:
            self._accept_thread.join(timeout=0.5)
        self._accept_thread = None

        if self._client_thread is not None:
            self._client_thread.join(timeout=0.5)
        self._client_thread = None

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
                if self._client_sock is not None:
                    try:
                        _send_line(client_sock, "ERROR BUSY")
                    except OSError:
                        pass
                    try:
                        client_sock.close()
                    except OSError:
                        pass
                    continue
                self._client_sock = client_sock
                self._last_client_activity_time = time.time()

            try:
                _send_line(client_sock, f"WELCOME {self.name} {self.port}")
            except OSError:
                self._close_client(client_sock)
                continue

            self._client_thread = threading.Thread(
                target=self._client_loop,
                args=(client_sock,),
                name="quoridor-network-client",
                daemon=True,
            )
            self._client_thread.start()

    def _client_loop(self, client_sock: socket.socket) -> None:
        buffer = ""
        try:
            while not self._stop_requested.is_set():
                with self._lock:
                    last_client_activity_time = self._last_client_activity_time

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
                    self._last_client_activity_time = time.time()

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
            self._close_client(client_sock)

    def _close_client(self, client_sock: socket.socket) -> None:
        try:
            client_sock.close()
        except OSError:
            pass

        with self._lock:
            if self._client_sock is client_sock:
                self._client_sock = None
                self._last_client_activity_time = None


__all__ = ["NetworkServer"]
