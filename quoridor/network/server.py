from __future__ import annotations

import socket
import threading
import time

from ..application.game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.notation import get_edges_for_wall, get_node_from_notation
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


_ROOM_BOARD_SIZE = 9
_ROOM_WALLS_PER_PLAYER = 20


class _ClientSession:
    def __init__(
        self,
        *,
        sock: socket.socket,
        thread: threading.Thread,
        last_activity_time: float,
        name: str,
        status: str,
        game_id: int | None,
        buffer: str,
    ) -> None:
        self.sock = sock
        self.thread = thread
        self.last_activity_time = last_activity_time
        self.name = name
        self.status = status
        self.game_id = game_id
        self.buffer = buffer


class _ScoreEntry:
    def __init__(
        self,
        *,
        name: str,
        wins: int = 0,
        losses: int = 0,
        played: int = 0,
    ) -> None:
        self.name = name
        self.wins = wins
        self.losses = losses
        self.played = played


class _GameRoom:
    def __init__(
        self,
        *,
        game_id: int,
        player_ids: tuple[int, ...],
        client_to_player_id: dict[int, int],
        session: GameSession,
    ) -> None:
        self.game_id = game_id
        self.player_ids = player_ids
        self.client_to_player_id = dict(client_to_player_id)
        self.player_to_client_id = {
            player_id: client_id
            for client_id, player_id in client_to_player_id.items()
        }
        self.session = session


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
        self._scoreboard: dict[int, _ScoreEntry] = {}
        self._game_rooms: dict[int, _GameRoom] = {}
        self._next_client_id = 1
        self._next_game_id = 1
        self._lock = threading.RLock()

    def running(self) -> bool:
        return (
            self._accept_thread is not None
            and self._accept_thread.is_alive()
        )

    def status_snapshot(self) -> dict[str, int]:
        with self._lock:
            connected_clients = len(self._client_sessions)
            active_games = len(self._game_rooms)
        return {
            "port": self.port,
            "connected_clients": connected_clients,
            "active_games": active_games,
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
            self._game_rooms = {}

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
                    game_id=None,
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

                if command_upper == "SCOREBOARD":
                    try:
                        _send_line(
                            client_sock,
                            self._format_scoreboard_response(),
                        )
                    except OSError:
                        break
                    continue

                if command_upper == "NEW" or command_upper.startswith("NEW "):
                    try:
                        _send_line(
                            client_sock,
                            self._handle_new_command(client_id, command),
                        )
                    except OSError:
                        break
                    continue

                if (
                    command_upper == "MOVE"
                    or command_upper.startswith("MOVE ")
                ):
                    try:
                        _send_line(
                            client_sock,
                            self._handle_move_command(client_id, command),
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
                game_id = session.game_id
                del self._client_sessions[client_id]
                if game_id is not None:
                    self._close_game_room_locked(game_id)

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
                session.game_id = None
                session.buffer = buffer
                self._ensure_score_entry(client_id, client_name)

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

    def _format_scoreboard_response(self) -> str:
        with self._lock:
            items = [
                (
                    client_id,
                    entry.name,
                    entry.wins,
                    entry.losses,
                    entry.played,
                )
                for client_id, entry in self._scoreboard.items()
            ]

        items.sort(key=lambda item: item[0])
        if not items:
            return "SCOREBOARD"

        payload = ";".join(
            f"{client_id}|{name}|{wins}|{losses}|{played}"
            for client_id, name, wins, losses, played in items
        )
        return f"SCOREBOARD {payload}"

    def _ensure_score_entry(self, client_id: int, client_name: str) -> None:
        entry = self._scoreboard.get(client_id)
        if entry is None:
            self._scoreboard[client_id] = _ScoreEntry(name=client_name)
            return
        entry.name = client_name

    def _handle_new_command(self, client_id: int, command: str) -> str:
        parts = command.split()
        if len(parts) < 2:
            return "ERROR INVALID_NEW_FORMAT"

        target_client_ids = []
        seen_targets = set()
        for raw_target_id in parts[1:]:
            try:
                target_client_id = int(raw_target_id)
            except ValueError:
                return "ERROR INVALID_NEW_FORMAT"
            if target_client_id <= 0:
                return "ERROR INVALID_NEW_FORMAT"
            if target_client_id == client_id:
                return "ERROR SELF_INVITE"
            if target_client_id in seen_targets:
                return "ERROR INVALID_NEW_FORMAT"
            seen_targets.add(target_client_id)
            target_client_ids.append(target_client_id)

        with self._lock:
            requester = self._client_sessions.get(client_id)
            if requester is None:
                return "ERROR REQUESTER_NOT_FOUND"
            if requester.status != "idle":
                return "ERROR REQUESTER_NOT_IDLE"

            participants_client_ids = [client_id]
            for target_client_id in target_client_ids:
                target = self._client_sessions.get(target_client_id)
                if target is None:
                    return "ERROR PLAYER_NOT_FOUND"
                if target.status != "idle":
                    return "ERROR PLAYER_NOT_AVAILABLE"
                participants_client_ids.append(target_client_id)

            participant_count = len(participants_client_ids)
            if participant_count < 2 or participant_count > 4:
                return "ERROR UNSUPPORTED_PLAYER_COUNT"

            room_state = GameState(
                board_size=_ROOM_BOARD_SIZE,
                current_player=1,
                player_positions=initial_player_positions(
                    _ROOM_BOARD_SIZE, participant_count
                ),
                remaining_walls={
                    player_id: _ROOM_WALLS_PER_PLAYER
                    for player_id in range(1, participant_count + 1)
                },
                vertical_walls=[],
                horizontal_walls=[],
            )
            room_session = GameSession(
                state=room_state,
                player_types={
                    player_id: "human"
                    for player_id in range(1, participant_count + 1)
                },
            )
            game_id = self._next_game_id
            self._next_game_id += 1
            client_to_player_id = {
                participant_client_id: player_id
                for player_id, participant_client_id in enumerate(
                    participants_client_ids,
                    start=1,
                )
            }
            self._game_rooms[game_id] = _GameRoom(
                game_id=game_id,
                player_ids=tuple(participants_client_ids),
                client_to_player_id=client_to_player_id,
                session=room_session,
            )
            for participant_client_id in participants_client_ids:
                participant_session = self._client_sessions.get(
                    participant_client_id
                )
                if participant_session is not None:
                    participant_session.status = "ingame"
                    participant_session.game_id = game_id

        return f"NEW_OK {game_id}"

    def _handle_move_command(self, client_id: int, command: str) -> str:
        parts = command.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return "ERROR INVALID_MOVE_FORMAT"
        move_notation = parts[1].strip()
        if " " in move_notation:
            return "ERROR INVALID_MOVE_FORMAT"

        with self._lock:
            session = self._client_sessions.get(client_id)
            if session is None:
                return "ERROR PLAYER_NOT_FOUND"
            if session.game_id is None or session.status != "ingame":
                return "ERROR NOT_IN_GAME"

            room = self._game_rooms.get(session.game_id)
            if room is None:
                session.status = "idle"
                session.game_id = None
                return "ERROR NOT_IN_GAME"

            player_id = room.client_to_player_id.get(client_id)
            if player_id is None:
                return "ERROR NOT_IN_GAME"

            game_session = room.session
            if game_session.state.current_player != player_id:
                return "ERROR NOT_YOUR_TURN"

            try:
                self._apply_room_move(
                    game_session,
                    player_id,
                    move_notation,
                )
            except ValueError:
                return "ERROR ILLEGAL_MOVE"

            for participant_client_id in room.player_ids:
                if participant_client_id == client_id:
                    continue

                opponent_session = self._client_sessions.get(
                    participant_client_id
                )
                if opponent_session is None:
                    self._close_game_room_locked(room.game_id)
                    return "ERROR OPPONENT_DISCONNECTED"

                try:
                    _send_line(
                        opponent_session.sock,
                        f"OPPONENT_MOVE {move_notation}",
                    )
                except OSError:
                    self._close_client(
                        participant_client_id,
                        opponent_session.sock,
                    )
                    if room.game_id in self._game_rooms:
                        self._close_game_room_locked(room.game_id)
                    return "ERROR OPPONENT_DISCONNECTED"

            winner_player_id = game_session.winner_id()
            if winner_player_id is not None:
                winner_client_id = room.player_to_client_id.get(
                    winner_player_id
                )
                if winner_client_id is not None:
                    self.record_finished_game(
                        player_ids=list(room.player_ids),
                        winner_client_id=winner_client_id,
                    )
                self._close_game_room_locked(room.game_id)

        return "MOVE_OK"

    def _apply_room_move(
        self,
        game_session: GameSession,
        player_id: int,
        move_notation: str,
    ) -> None:
        if "-" in move_notation:
            from_notation, to_notation = move_notation.split("-", 1)
            from_node = get_node_from_notation(
                from_notation,
                game_session.state.board_size,
            )
            to_node = get_node_from_notation(
                to_notation,
                game_session.state.board_size,
            )
            game_session.play_pawn_move_from_to(
                player_id,
                from_node,
                to_node,
            )
            return

        if len(move_notation) < 3:
            raise ValueError("invalid notation")
        orientation_char = move_notation[-1].lower()
        if orientation_char not in {"h", "v"}:
            raise ValueError("invalid notation")

        wall_edges = get_edges_for_wall(
            move_notation,
            game_session.state.board_size,
        )
        orientation = "horizontal" if orientation_char == "h" else "vertical"
        game_session.place_wall(
            player_id,
            wall_edges,
            orientation,
        )

    def _close_game_room_locked(self, game_id: int) -> None:
        room = self._game_rooms.pop(game_id, None)
        if room is None:
            return

        for room_player_id in room.player_ids:
            session = self._client_sessions.get(room_player_id)
            if session is None:
                continue
            session.status = "idle"
            session.game_id = None

    def record_finished_game(
        self,
        *,
        player_ids: list[int],
        winner_client_id: int | None = None,
    ) -> None:
        with self._lock:
            for client_id in player_ids:
                session = self._client_sessions.get(client_id)
                if session is not None:
                    self._ensure_score_entry(client_id, session.name)
                else:
                    self._ensure_score_entry(
                        client_id,
                        f"client-{client_id}",
                    )

            for client_id in player_ids:
                entry = self._scoreboard[client_id]
                entry.played += 1

            if winner_client_id is None:
                return

            for client_id in player_ids:
                entry = self._scoreboard[client_id]
                if client_id == winner_client_id:
                    entry.wins += 1
                else:
                    entry.losses += 1


__all__ = ["NetworkServer"]
