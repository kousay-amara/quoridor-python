from __future__ import annotations

import socket
import threading
import time

from .basic_network import (
    CLIENT_TIMEOUT_SEC,
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
        keepalive_interval_sec: float | None = CLIENT_TIMEOUT_SEC / 4.0,
    ) -> None:
        self.host = host
        self.port = _validate_port(port)
        self.name = name.strip() or "player"
        self.keepalive_interval_sec = keepalive_interval_sec
        self.client_id = None
        self._sock = None
        self._buffer = ""
        self._pending_opponent_moves = []
        self._pending_game_state_updates = []
        self._pending_notifications = []
        self._response_queue = []
        self._response_condition = threading.Condition()
        self._send_lock = threading.Lock()
        self._reader_thread = None
        self._reader_stop_requested = threading.Event()
        self._keepalive_thread = None
        self._keepalive_stop_requested = threading.Event()
        self._reader_error = None
        self._opponent_move_callback = None
        self._game_state_callback = None
        self._notification_callback = None
        self._connection_lost_callback = None

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
                    self.client_id = int(hello_response.split(maxsplit=1)[1])
                except (IndexError, ValueError) as exc:
                    raise OSError(
                        f"unexpected server response: {hello_response}"
                    ) from exc
                self._sock = sock
                self._buffer = hello_buffer
                self._response_queue.clear()
                self._pending_opponent_moves.clear()
                self._pending_game_state_updates.clear()
                self._pending_notifications.clear()
                self._reader_error = None
                self._reader_stop_requested.clear()
                self._keepalive_stop_requested.clear()
                self._reader_thread = threading.Thread(
                    target=self._reader_loop,
                    name="quoridor-network-client-reader",
                    daemon=True,
                )
                self._reader_thread.start()
                if (
                    self.keepalive_interval_sec is not None
                    and self.keepalive_interval_sec > 0
                ):
                    self._keepalive_thread = threading.Thread(
                        target=self._keepalive_loop,
                        name="quoridor-network-client-keepalive",
                        daemon=True,
                    )
                    self._keepalive_thread.start()
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
                if self._reader_stop_requested.is_set():
                    break
                self._set_reader_error(exc)
                break
            if closed:
                if self._reader_stop_requested.is_set():
                    break
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
                    except Exception:  # pylint: disable=broad-exception-caught
                        # Callback errors must not break the reader thread.
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
                    except Exception:  # pylint: disable=broad-exception-caught
                        # Callback errors must not break the reader thread.
                        with self._response_condition:
                            self._pending_game_state_updates.append(
                                game_state_update
                            )
                    continue

                with self._response_condition:
                    self._pending_game_state_updates.append(game_state_update)
                continue

            if line.startswith(
                (
                    "INVITATION_RECEIVED ",
                    "INVITATION_ACCEPTED ",
                    "INVITATION_DECLINED ",
                    "INVITATION_CANCELLED ",
                    "INVITATION_EXPIRED ",
                    "OPPONENT_DISCONNECTED ",
                    "PLAYER_STATUS ",
                )
            ):
                callback = self._notification_callback
                if callback is not None:
                    try:
                        callback(line)
                    except Exception:  # pylint: disable=broad-exception-caught
                        # Callback errors must not break the reader thread.
                        with self._response_condition:
                            self._pending_notifications.append(line)
                    continue

                with self._response_condition:
                    self._pending_notifications.append(line)
                continue

            if line == "ERROR TIMEOUT":
                self._set_reader_error(
                    OSError("server timed out the connection")
                )
                break

            with self._response_condition:
                self._response_queue.append(line)
                self._response_condition.notify_all()

    def _keepalive_loop(self) -> None:
        interval = self.keepalive_interval_sec
        if interval is None or interval <= 0:
            return

        while not self._keepalive_stop_requested.wait(timeout=interval):
            if self._sock is None or self._reader_stop_requested.is_set():
                break
            try:
                response = self.send_command("PING")
            except OSError as exc:
                if not self._keepalive_stop_requested.is_set():
                    self._set_reader_error(OSError(str(exc)))
                    self.close()
                break

            if not (
                response.startswith("PONG TIME=")
                and response.endswith("ms")
            ):
                self._set_reader_error(
                    OSError(f"unexpected keepalive response: {response}")
                )
                self.close()
                break

    def _set_reader_error(self, exc: OSError) -> None:
        callback = None
        reader_error = None
        with self._response_condition:
            if self._reader_error is None:
                self._reader_error = OSError(str(exc))
                reader_error = self._reader_error
                callback = self._connection_lost_callback
            self._response_condition.notify_all()
        if callback is not None and reader_error is not None:
            try:
                callback(reader_error)
            except Exception:  # pylint: disable=broad-exception-caught
                # The connection-lost hook is user-provided and best-effort.
                pass

    def set_opponent_move_callback(
        self,
        callback,
    ) -> None:
        self._opponent_move_callback = callback

    def set_game_state_callback(
        self,
        callback,
    ) -> None:
        self._game_state_callback = callback

    def set_notification_callback(
        self,
        callback,
    ) -> None:
        self._notification_callback = callback

    def set_connection_lost_callback(
        self,
        callback,
    ) -> None:
        self._connection_lost_callback = callback

    def send_command(self, command: str) -> str:
        if self._sock is None:
            raise OSError("client is not connected")

        with self._send_lock:
            with self._response_condition:
                if self._reader_error is not None:
                    error = self._reader_error
                    self.close()
                    raise OSError(str(error))
            _send_line(self._sock, command)
            with self._response_condition:
                while True:
                    if self._response_queue:
                        return self._response_queue.pop(0)
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
        self._keepalive_stop_requested.set()
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
        self._keepalive_stop_requested.set()
        self._connection_lost_callback = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        current_thread = threading.current_thread()
        reader_thread = self._reader_thread
        keepalive_thread = self._keepalive_thread
        if (
            reader_thread is not None
            and reader_thread is not current_thread
            and reader_thread.is_alive()
        ):
            reader_thread.join(timeout=0.5)
        if (
            keepalive_thread is not None
            and keepalive_thread is not current_thread
            and keepalive_thread.is_alive()
        ):
            keepalive_thread.join(timeout=0.5)
        self._sock = None
        self.client_id = None
        self._buffer = ""
        with self._response_condition:
            self._pending_opponent_moves.clear()
            self._pending_game_state_updates.clear()
            self._pending_notifications.clear()
            self._response_queue.clear()
            self._reader_error = None
            self._response_condition.notify_all()
        self._opponent_move_callback = None
        self._game_state_callback = None
        self._notification_callback = None
        self._connection_lost_callback = None
        self._reader_thread = None
        self._keepalive_thread = None

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
                raise OSError(f"unexpected players response: {response}") from exc
            players.append((client_id, parts[1], parts[2]))
        return players

    def player_details(
        self,
        client_id: int,
    ) -> tuple[int, str, str, int, int, int]:
        if client_id <= 0:
            raise ValueError("player id must be positive")

        response = self.send_command(f"PLAYERS {client_id}")
        if response == "ERROR PLAYER_NOT_FOUND":
            raise ValueError("Player not found.")
        if response == "ERROR INVALID_PLAYERS_FORMAT":
            raise OSError(f"unexpected players response: {response}")
        if not response.startswith("PLAYER "):
            raise OSError(f"unexpected players response: {response}")

        parts = response[7:].split("|")
        if len(parts) != 6:
            raise OSError(f"unexpected players response: {response}")

        try:
            detail_client_id = int(parts[0])
            wins = int(parts[3])
            losses = int(parts[4])
            played = int(parts[5])
        except ValueError as exc:
            raise OSError(f"unexpected players response: {response}") from exc

        return (
            detail_client_id,
            parts[1],
            parts[2],
            wins,
            losses,
            played,
        )

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
                raise OSError(f"unexpected scoreboard response: {response}")
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

    def accept(self) -> str:
        return self.send_command("ACCEPT")

    def decline(self) -> str:
        return self.send_command("DECLINE")

    def cancel(self) -> str:
        return self.send_command("CANCEL")

    def away(self) -> str:
        return self.send_command("AWAY")

    def back(self) -> str:
        return self.send_command("BACK")

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

    def drain_notifications(self) -> list[str]:
        with self._response_condition:
            notifications = list(self._pending_notifications)
            self._pending_notifications.clear()
            return notifications


__all__ = ["NetworkClient"]
