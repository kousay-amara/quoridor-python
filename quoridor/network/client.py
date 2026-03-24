from __future__ import annotations

import socket
import time

from .basic_network import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    _SOCKET_TIMEOUT_SEC,
    _recv_line,
    _send_line,
    _validate_port,
)


class NetworkClient:
    def __init__(
        self,
        *,
        host: str = DEFAULT_SERVER_HOST,
        port: int = DEFAULT_SERVER_PORT,
    ) -> None:
        self.host = host
        self.port = _validate_port(port)
        self._sock = None
        self._buffer = ""

    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        if self.connected():
            return

        sock = socket.create_connection(
            (self.host, self.port),
            timeout=_SOCKET_TIMEOUT_SEC,
        )
        sock.settimeout(_SOCKET_TIMEOUT_SEC)
        try:
            while True:
                line, buffer, closed = _recv_line(sock, "")
                if closed:
                    raise OSError("server closed the connection")
                if line is None:
                    continue
                if not line.startswith("WELCOME "):
                    raise OSError(f"unexpected server response: {line}")
                self._sock = sock
                self._buffer = buffer
                return
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            raise

    def send_command(self, command: str) -> str:
        if self._sock is None:
            raise OSError("client is not connected")

        _send_line(self._sock, command)
        while True:
            line, self._buffer, closed = _recv_line(
                self._sock,
                self._buffer,
            )
            if closed:
                self.close()
                raise OSError("server closed the connection")
            if line is None:
                continue
            return line

    def ping(self) -> float:
        started_at = time.time()
        response = self.send_command("PING")
        round_trip_ms = (time.time() - started_at) * 1000.0
        if response == "PONG":
            return round_trip_ms
        if response.startswith("PONG TIME=") and response.endswith("ms"):
            return round_trip_ms
        raise OSError(f"unexpected ping response: {response}")

    def quit(self) -> None:
        if self._sock is None:
            return
        try:
            response = self.send_command("QUIT")
        except OSError:
            self.close()
            return
        self.close()
        if response != "BYE":
            raise OSError(f"unexpected quit response: {response}")

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._buffer = ""


__all__ = ["NetworkClient"]
