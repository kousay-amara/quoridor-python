from __future__ import annotations

import socket
import threading
import time
from collections import deque
from typing import Callable

from .basic_network import (
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    GameStateUpdate,
    _SOCKET_TIMEOUT_SEC,
    _recv_line,
    _send_line,
    _validate_port,
    parse_game_state_message,
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
        self._pending_opponent_moves = deque()
        self._pending_game_state_updates = deque()
        self._response_queue = deque()
        self._response_condition = threading.Condition()
        self._send_lock = threading.Lock()
        self._reader_thread = None
        self._reader_stop_requested = threading.Event()
        self._reader_error = None
        self._opponent_move_callback = None
        self._game_state_callback = None

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
                self._response_queue.clear()
                self._pending_opponent_moves.clear()
                self._pending_game_state_updates.clear()
                self._reader_error = None
                self._reader_stop_requested.clear()
                self._reader_thread = threading.Thread(
                    target=self._reader_loop,
                    name="quoridor-network-client-reader",
                    daemon=True,
                )
                self._reader_thread.start()
                return
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            self.client_id = None
            raise

    def _reader_loop(self) -> None:
        if self._sock is None:
            return

        sock = self._sock
        buffer = self._buffer
        while not self._reader_stop_requested.is_set():
            try:
                line, buffer, closed = _recv_line(sock, buffer)
            except OSError as exc:
                self._set_reader_error(exc)
                break
            if closed:
                self._set_reader_error(OSError("server closed the connection"))
                break
            if line is None:
                continue
            if line.startswith("OPPONENT_MOVE "):
                move_notation = line[len("OPPONENT_MOVE "):].strip()
                if not move_notation:
                    continue
                callback = self._opponent_move_callback
                if callback is not None:
                    try:
                        callback(move_notation)
                    except Exception:
                        with self._response_condition:
                            self._pending_opponent_moves.append(move_notation)
                    continue
                with self._response_condition:
                    self._pending_opponent_moves.append(move_notation)
                continue

            if line.startswith("GAME_STATE "):
                game_state_update = parse_game_state_message(line)
                if game_state_update is None:
                    self._set_reader_error(
                        OSError(f"unexpected game state response: {line}")
                    )
                    break

                callback = self._game_state_callback
                if callback is not None:
                    try:
                        callback(game_state_update)
                    except Exception:
                        with self._response_condition:
                            self._pending_game_state_updates.append(
                                game_state_update
                            )
                    continue

                with self._response_condition:
                    self._pending_game_state_updates.append(
                        game_state_update
                    )
                continue

            with self._response_condition:
                self._response_queue.append(line)
                self._response_condition.notify_all()

    def _set_reader_error(self, exc: OSError) -> None:
        with self._response_condition:
            if self._reader_error is None:
                self._reader_error = OSError(str(exc))
            self._response_condition.notify_all()

    def set_opponent_move_callback(
        self,
        callback: Callable[[str], None] | None,
    ) -> None:
        self._opponent_move_callback = callback

    def set_game_state_callback(
        self,
        callback: Callable[[GameStateUpdate], None] | None,
    ) -> None:
        self._game_state_callback = callback

    def send_command(self, command: str) -> str:
        if self._sock is None:
            raise OSError("client is not connected")

        with self._send_lock:
            _send_line(self._sock, command)
            with self._response_condition:
                while True:
                    if self._response_queue:
                        return self._response_queue.popleft()
                    if self._reader_error is not None:
                        error = self._reader_error
                        self.close()
                        raise OSError(str(error))
                    self._response_condition.wait(timeout=_SOCKET_TIMEOUT_SEC)

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
        self._reader_stop_requested.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        current_thread = threading.current_thread()
        reader_thread = self._reader_thread
        if (
            reader_thread is not None
            and reader_thread is not current_thread
            and reader_thread.is_alive()
        ):
            reader_thread.join(timeout=0.5)
        self._sock = None
        self.client_id = None
        self._buffer = ""
        with self._response_condition:
            self._pending_opponent_moves.clear()
            self._pending_game_state_updates.clear()
            self._response_queue.clear()
            self._reader_error = None
            self._response_condition.notify_all()
        self._opponent_move_callback = None
        self._game_state_callback = None
        self._reader_thread = None

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
        with self._response_condition:
            moves = list(self._pending_opponent_moves)
            self._pending_opponent_moves.clear()
            return moves

    def drain_game_state_updates(self) -> list[GameStateUpdate]:
        with self._response_condition:
            updates = list(self._pending_game_state_updates)
            self._pending_game_state_updates.clear()
            return updates


__all__ = ["NetworkClient"]
