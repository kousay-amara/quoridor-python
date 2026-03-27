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
        name: str = "player",
    ) -> None:
        self.host = host
        self.port = _validate_port(port)
        self.name = name.strip() or "player"
        self.client_id = None
        self._sock = None
        self._buffer = ""
        self._pending_opponent_moves: list[str] = []

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
                _send_line(sock, f"HELLO {self.name}")
                hello_response, hello_buffer, hello_closed = _recv_line(
                    sock,
                    buffer,
                )
                while hello_response is None and not hello_closed:
                    hello_response, hello_buffer, hello_closed = _recv_line(
                        sock,
                        hello_buffer,
                    )
                if hello_closed:
                    raise OSError("server closed the connection")
                if hello_response is None:
                    raise OSError("server did not answer HELLO")
                if not hello_response.startswith("HELLO_OK "):
                    raise OSError(
                        f"unexpected server response: {hello_response}"
                    )
                try:
                    self.client_id = int(
                        hello_response.split(maxsplit=1)[1]
                    )
                except (IndexError, ValueError) as exc:
                    raise OSError(
                        f"unexpected server response: {hello_response}"
                    ) from exc
                self._sock = sock
                self._buffer = hello_buffer
                return
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            self.client_id = None
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
            if line.startswith("OPPONENT_MOVE "):
                move_notation = line[len("OPPONENT_MOVE "):].strip()
                if move_notation:
                    self._pending_opponent_moves.append(move_notation)
                continue
            return line

    def ping(self) -> float:
        started_at = time.time()
        response = self.send_command("PING")
        round_trip_ms = (time.time() - started_at) * 1000.0
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
        self.client_id = None
        self._buffer = ""
        self._pending_opponent_moves = []

    def players(self) -> list[tuple[int, str, str]]:
        response = self.send_command("PLAYERS")
        if response == "PLAYERS":
            return []
        if not response.startswith("PLAYERS "):
            raise OSError(f"unexpected players response: {response}")

        payload = response[8:]
        players = []
        for entry in payload.split(";"):
            parts = entry.split("|")
            if len(parts) != 3:
                raise OSError(f"unexpected players response: {response}")
            try:
                client_id = int(parts[0])
            except ValueError as exc:
                raise OSError(
                    f"unexpected players response: {response}"
                ) from exc
            players.append((client_id, parts[1], parts[2]))
        return players

    def scoreboard(self) -> list[tuple[int, str, int, int, int]]:
        response = self.send_command("SCOREBOARD")
        if response == "SCOREBOARD":
            return []
        if not response.startswith("SCOREBOARD "):
            raise OSError(f"unexpected scoreboard response: {response}")

        payload = response[11:]
        scores = []
        for entry in payload.split(";"):
            parts = entry.split("|")
            if len(parts) != 5:
                raise OSError(
                    f"unexpected scoreboard response: {response}"
                )
            try:
                client_id = int(parts[0])
                wins = int(parts[2])
                losses = int(parts[3])
                played = int(parts[4])
            except ValueError as exc:
                raise OSError(
                    f"unexpected scoreboard response: {response}"
                ) from exc
            scores.append((client_id, parts[1], wins, losses, played))
        return scores

    def move(self, notation: str) -> str:
        move_notation = notation.strip()
        if not move_notation:
            raise ValueError("move notation must not be empty")
        if " " in move_notation:
            raise ValueError("move notation must not contain spaces")
        return self.send_command(f"MOVE {move_notation}")

    def drain_opponent_moves(self) -> list[str]:
        moves = list(self._pending_opponent_moves)
        self._pending_opponent_moves.clear()
        return moves


__all__ = ["NetworkClient"]
