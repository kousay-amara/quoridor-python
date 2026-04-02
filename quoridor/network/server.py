from __future__ import annotations

import socket
import threading
import time

from ..application.game_application_service import GameApplicationService
from ..application.game_session import GameSession
from .discovery import DiscoveryBroadcaster, remember_server
from .basic_network import (
    CLIENT_TIMEOUT_SEC,
    DEFAULT_SERVER_PORT,
    DISCOVERY_BROADCAST_INTERVAL_SEC,
    DISCOVERY_PORT,
    format_game_state_message,
    _SOCKET_TIMEOUT_SEC,
    _recv_line,
    _send_line,
    _validate_port,
)

_ROOM_BOARD_SIZE = 9
_ROOM_WALLS_PER_PLAYER = 20
_INVITATION_TIMEOUT_SEC = 300.0
_PLAYER_STATUS_IDLE = "idle"
_PLAYER_STATUS_AWAY = "away"
_PLAYER_STATUS_WAITGAME = "waitgame"
_PLAYER_STATUS_INGAME = "ingame"


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
            for client_id, player_id in self.client_to_player_id.items()
        }
        self.session = session


class _Invitation:
    def __init__(
        self,
        *,
        inviter_id: int,
        invitee_id: int,
        created_at: float,
        expires_at: float,
    ) -> None:
        self.inviter_id = inviter_id
        self.invitee_id = invitee_id
        self.created_at = created_at
        self.expires_at = expires_at


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
        invitation_timeout_sec: float = _INVITATION_TIMEOUT_SEC,
    ) -> None:
        self.host = host
        self.port = _validate_port(port)
        self.name = name.strip() or "quoridor-server"
        self.discovery_port = _validate_port(discovery_port)
        self.broadcast_interval_sec = broadcast_interval_sec
        self.client_timeout_sec = client_timeout_sec
        self.invitation_timeout_sec = invitation_timeout_sec
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
        self._pending_invitations_by_inviter: dict[int, _Invitation] = {}
        self._pending_invitations_by_invitee: dict[int, _Invitation] = {}
        self._next_client_id = 1
        self._next_game_id = 1
        self._lock = threading.Lock()

    def running(self) -> bool:
        return (
            self._accept_thread is not None and self._accept_thread.is_alive()
        )

    def server_status_snapshot(self) -> dict[str, int]:
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
            listener_sock.listen(15)
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

        for _, session in sessions:
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
            self._expire_invitations()
            try:
                client_sock, _ = self._listener_sock.accept()
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
                    status=_PLAYER_STATUS_IDLE,
                    game_id=None,
                    buffer="",
                )

            try:
                _send_line(client_sock, f"WELCOME {self.name} {self.port}")
            except OSError:
                self._close_client(client_id, client_sock)
                continue

            if not self._perform_handshake(client_id, client_sock):
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
                    client_status = session.status
                    waiting_invitation = None
                    if client_status == _PLAYER_STATUS_WAITGAME:
                        waiting_invitation = (
                            self._pending_invitations_by_inviter.get(client_id)
                        )
                        if waiting_invitation is None:
                            waiting_invitation = (
                                self._pending_invitations_by_invitee.get(
                                    client_id
                                )
                            )

                if (
                    client_status != _PLAYER_STATUS_WAITGAME
                    or waiting_invitation is None
                ) and (
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

                if command_upper == "PLAYERS" or command_upper.startswith(
                    "PLAYERS "
                ):
                    try:
                        _send_line(
                            client_sock,
                            self._handle_players_command(command),
                        )
                    except OSError:
                        break
                    continue

                if command_upper == "SCOREBOARD":
                    try:
                        _send_line(
                            client_sock,
                            self._scoreboard_response(),
                        )
                    except OSError:
                        break
                    continue

                if command_upper == "NEW" or command_upper.startswith("NEW "):
                    try:
                        response, notifications = self._handle_new_command(
                            client_id, command
                        )
                        _send_line(
                            client_sock,
                            response,
                        )
                    except OSError:
                        break
                    self._send_notifications(notifications)
                    continue

                if command_upper == "ACCEPT":
                    try:
                        (
                            response,
                            notifications,
                            room,
                        ) = self._handle_accept_command(client_id)
                        _send_line(
                            client_sock,
                            response,
                        )
                    except OSError:
                        break
                    self._send_notifications(notifications)
                    if room is not None:
                        self._send_room_state(room)
                    continue

                if command_upper == "DECLINE":
                    try:
                        response, notifications = self._handle_decline_command(
                            client_id
                        )
                        _send_line(
                            client_sock,
                            response,
                        )
                    except OSError:
                        break
                    self._send_notifications(notifications)
                    continue

                if command_upper == "CANCEL":
                    try:
                        response, notifications = self._handle_cancel_command(
                            client_id
                        )
                        _send_line(
                            client_sock,
                            response,
                        )
                    except OSError:
                        break
                    self._send_notifications(notifications)
                    continue

                if command_upper == "AWAY":
                    try:
                        _send_line(
                            client_sock,
                            self._handle_away_command(client_id),
                        )
                    except OSError:
                        break
                    continue

                if command_upper == "BACK":
                    try:
                        _send_line(
                            client_sock,
                            self._handle_back_command(client_id),
                        )
                    except OSError:
                        break
                    continue

                if command_upper == "MOVE" or command_upper.startswith(
                    "MOVE "
                ):
                    try:
                        (
                            response,
                            room,
                            winner_player_id,
                        ) = self._handle_move_command(client_id, command)
                    except OSError:
                        break
                    if room is not None and winner_player_id is not None:
                        winner_client_id = room.player_to_client_id.get(
                            winner_player_id
                        )
                        if winner_client_id is not None:
                            self.record_finished_game(
                                player_ids=list(room.player_ids),
                                winner_client_id=winner_client_id,
                            )
                        with self._lock:
                            self._close_game_room_locked(room.game_id)
                    try:
                        _send_line(
                            client_sock,
                            response,
                        )
                    except OSError:
                        break
                    if room is not None:
                        self._send_room_state(
                            room,
                            winner_player_id=winner_player_id,
                        )
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

    def _close_client_locked(
        self,
        client_id: int,
        client_sock: socket.socket,
    ) -> None:
        session = self._client_sessions.get(client_id)
        if session is not None and session.sock is client_sock:
            game_id = session.game_id
            del self._client_sessions[client_id]
            if game_id is not None:
                self._close_game_room_locked(game_id)
            invitation = self._pending_invitations_by_inviter.get(client_id)
            if invitation is None:
                invitation = self._pending_invitations_by_invitee.get(
                    client_id
                )
            if invitation is not None:
                self._clear_invitation_locked(invitation)

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
            self._close_client_locked(client_id, client_sock)

    def _send_notifications(
        self,
        notifications: list[tuple[int, socket.socket, str]],
    ) -> None:
        for recipient_client_id, recipient_sock, message in notifications:
            try:
                _send_line(recipient_sock, message)
            except OSError:
                self._close_client(recipient_client_id, recipient_sock)

    def _clear_invitation_locked(self, invitation: _Invitation) -> None:
        self._pending_invitations_by_inviter.pop(invitation.inviter_id, None)
        self._pending_invitations_by_invitee.pop(invitation.invitee_id, None)
        now = time.time()

        for client_id in (invitation.inviter_id, invitation.invitee_id):
            session = self._client_sessions.get(client_id)
            if session is None:
                continue
            if (
                session.status == _PLAYER_STATUS_WAITGAME
                and session.game_id is None
            ):
                session.status = _PLAYER_STATUS_IDLE
                session.last_activity_time = now

    def _expire_invitations(self) -> None:
        notifications = []
        with self._lock:
            now = time.time()
            expired_invitations = []
            for invitation in self._pending_invitations_by_inviter.values():
                if invitation.expires_at <= now:
                    expired_invitations.append(invitation)

            for invitation in expired_invitations:
                inviter_session = self._client_sessions.get(
                    invitation.inviter_id
                )
                invitee_session = self._client_sessions.get(
                    invitation.invitee_id
                )
                inviter_name = (
                    inviter_session.name
                    if inviter_session is not None
                    else f"client-{invitation.inviter_id}"
                )
                invitee_name = (
                    invitee_session.name
                    if invitee_session is not None
                    else f"client-{invitation.invitee_id}"
                )
                inviter_sock = (
                    inviter_session.sock
                    if inviter_session is not None
                    else None
                )
                invitee_sock = (
                    invitee_session.sock
                    if invitee_session is not None
                    else None
                )
                self._clear_invitation_locked(invitation)

                if inviter_sock is not None:
                    notifications.append(
                        (
                            invitation.inviter_id,
                            inviter_sock,
                            f"INVITATION_EXPIRED PLAYER={invitee_name}",
                        )
                    )
                if invitee_sock is not None:
                    notifications.append(
                        (
                            invitation.invitee_id,
                            invitee_sock,
                            f"INVITATION_EXPIRED PLAYER={inviter_name}",
                        )
                    )

        self._send_notifications(notifications)

    def _perform_handshake(
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
                session.status = _PLAYER_STATUS_IDLE
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

    def _player_response(self, requested_client_id: int) -> str:
        with self._lock:
            session = self._client_sessions.get(requested_client_id)
            if session is None:
                return "ERROR PLAYER_NOT_FOUND"

            self._ensure_score_entry(requested_client_id, session.name)
            entry = self._scoreboard[requested_client_id]
            player_name = session.name
            player_status = session.status
            wins = entry.wins
            losses = entry.losses
            played = entry.played

        return (
            "PLAYER "
            f"{requested_client_id}|{player_name}|{player_status}|"
            f"{wins}|{losses}|{played}"
        )

    def _handle_players_command(self, command: str) -> str:
        parts = command.split()
        if len(parts) == 1:
            return self._format_players_response()
        if len(parts) != 2:
            return "ERROR INVALID_PLAYERS_FORMAT"

        try:
            requested_client_id = int(parts[1])
        except ValueError:
            return "ERROR INVALID_PLAYERS_FORMAT"

        if requested_client_id <= 0:
            return "ERROR INVALID_PLAYERS_FORMAT"

        return self._player_response(requested_client_id)

    def _scoreboard_response(self) -> str:
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

    def _create_room_locked(
        self,
        participants_client_ids: list[int],
    ) -> _GameRoom:
        participant_count = len(participants_client_ids)
        room_session = GameApplicationService.new_session(
            board_size=_ROOM_BOARD_SIZE,
            players=participant_count,
            walls_per_player=_ROOM_WALLS_PER_PLAYER,
            player_types={
                player_id: "human"
                for player_id in range(1, participant_count + 1)
            },
        )
        game_id = self._next_game_id
        self._next_game_id += 1
        client_to_player_id = {
            participants_client_ids[index]: index + 1
            for index in range(len(participants_client_ids))
        }
        room = _GameRoom(
            game_id=game_id,
            player_ids=tuple(participants_client_ids),
            client_to_player_id=client_to_player_id,
            session=room_session,
        )
        self._game_rooms[game_id] = room

        for participant_client_id in participants_client_ids:
            participant_session = self._client_sessions.get(
                participant_client_id
            )
            if participant_session is None:
                continue
            participant_session.status = _PLAYER_STATUS_INGAME
            participant_session.game_id = game_id

        return room

    def _handle_new_command(
        self,
        client_id: int,
        command: str,
    ) -> tuple[str, list[tuple[int, socket.socket, str]]]:
        parts = command.split()
        if len(parts) != 2:
            return "ERROR INVALID_NEW_FORMAT", []

        try:
            target_client_id = int(parts[1])
        except ValueError:
            return "ERROR INVALID_NEW_FORMAT", []
        if target_client_id <= 0:
            return "ERROR INVALID_NEW_FORMAT", []
        if target_client_id == client_id:
            return "ERROR SELF_INVITE", []

        with self._lock:
            requester = self._client_sessions.get(client_id)
            if requester is None:
                return "ERROR REQUESTER_NOT_FOUND", []
            if requester.status != _PLAYER_STATUS_IDLE:
                return "ERROR REQUESTER_NOT_IDLE", []
            if client_id in self._pending_invitations_by_inviter:
                return "ERROR REQUESTER_NOT_IDLE", []
            if client_id in self._pending_invitations_by_invitee:
                return "ERROR REQUESTER_NOT_IDLE", []

            target = self._client_sessions.get(target_client_id)
            if target is None:
                return "ERROR PLAYER_NOT_FOUND", []
            if target.status != _PLAYER_STATUS_IDLE:
                return "ERROR PLAYER_NOT_AVAILABLE", []
            if target_client_id in self._pending_invitations_by_inviter:
                return "ERROR PLAYER_NOT_AVAILABLE", []
            if target_client_id in self._pending_invitations_by_invitee:
                return "ERROR PLAYER_NOT_AVAILABLE", []

            created_at = time.time()
            invitation = _Invitation(
                inviter_id=client_id,
                invitee_id=target_client_id,
                created_at=created_at,
                expires_at=created_at + self.invitation_timeout_sec,
            )
            self._pending_invitations_by_inviter[client_id] = invitation
            self._pending_invitations_by_invitee[target_client_id] = invitation
            requester.status = _PLAYER_STATUS_WAITGAME
            target.status = _PLAYER_STATUS_WAITGAME

            timeout_sec = round(self.invitation_timeout_sec)
            notifications = [
                (
                    target_client_id,
                    target.sock,
                    (
                        "INVITATION_RECEIVED "
                        f"FROM={requester.name} EXPIRES={timeout_sec}s"
                    ),
                )
            ]

        return (
            "INVITATION_SENT " f"PLAYER={target.name} TIMEOUT={timeout_sec}s",
            notifications,
        )

    def _handle_accept_command(
        self,
        client_id: int,
    ) -> tuple[str, list[tuple[int, socket.socket, str]], _GameRoom | None]:
        with self._lock:
            invitation = self._pending_invitations_by_invitee.get(client_id)
            if invitation is None:
                return "ERROR NO_INVITATION", [], None

            inviter_session = self._client_sessions.get(invitation.inviter_id)
            invitee_session = self._client_sessions.get(invitation.invitee_id)
            if inviter_session is None or invitee_session is None:
                self._clear_invitation_locked(invitation)
                return "ERROR PLAYER_NOT_FOUND", [], None

            inviter_name = inviter_session.name
            invitee_name = invitee_session.name
            inviter_sock = inviter_session.sock
            self._clear_invitation_locked(invitation)
            room = self._create_room_locked(
                [invitation.inviter_id, invitation.invitee_id]
            )

        return (
            f"GAME_START OPPONENT={inviter_name}",
            [
                (
                    invitation.inviter_id,
                    inviter_sock,
                    (
                        "INVITATION_ACCEPTED "
                        f"PLAYER={invitee_name} STARTING_GAME"
                    ),
                )
            ],
            room,
        )

    def _handle_decline_command(
        self,
        client_id: int,
    ) -> tuple[str, list[tuple[int, socket.socket, str]]]:
        with self._lock:
            invitation = self._pending_invitations_by_invitee.get(client_id)
            if invitation is None:
                return "ERROR NO_INVITATION", []

            inviter_session = self._client_sessions.get(invitation.inviter_id)
            invitee_session = self._client_sessions.get(invitation.invitee_id)
            inviter_name = (
                inviter_session.name
                if inviter_session is not None
                else f"client-{invitation.inviter_id}"
            )
            invitee_name = (
                invitee_session.name
                if invitee_session is not None
                else f"client-{invitation.invitee_id}"
            )
            inviter_sock = (
                inviter_session.sock if inviter_session is not None else None
            )
            self._clear_invitation_locked(invitation)

            notifications = []
            if inviter_sock is not None:
                notifications.append(
                    (
                        invitation.inviter_id,
                        inviter_sock,
                        f"INVITATION_DECLINED PLAYER={invitee_name}",
                    )
                )

        return f"DECLINE_OK PLAYER={inviter_name}", notifications

    def _handle_cancel_command(
        self,
        client_id: int,
    ) -> tuple[str, list[tuple[int, socket.socket, str]]]:
        with self._lock:
            invitation = self._pending_invitations_by_inviter.get(client_id)
            if invitation is None:
                return "ERROR NO_INVITATION", []

            inviter_session = self._client_sessions.get(invitation.inviter_id)
            invitee_session = self._client_sessions.get(invitation.invitee_id)
            inviter_name = (
                inviter_session.name
                if inviter_session is not None
                else f"client-{invitation.inviter_id}"
            )
            invitee_name = (
                invitee_session.name
                if invitee_session is not None
                else f"client-{invitation.invitee_id}"
            )
            invitee_sock = (
                invitee_session.sock if invitee_session is not None else None
            )
            self._clear_invitation_locked(invitation)

            notifications = []
            if invitee_sock is not None:
                notifications.append(
                    (
                        invitation.invitee_id,
                        invitee_sock,
                        f"INVITATION_CANCELLED PLAYER={inviter_name}",
                    )
                )

        return f"CANCEL_OK PLAYER={invitee_name}", notifications

    def _handle_away_command(self, client_id: int) -> str:
        with self._lock:
            session = self._client_sessions.get(client_id)
            if session is None:
                return "ERROR PLAYER_NOT_FOUND"
            if session.status == _PLAYER_STATUS_AWAY:
                return "ERROR ALREADY_AWAY"
            if (
                session.status != _PLAYER_STATUS_IDLE
                or session.game_id is not None
            ):
                return "ERROR CANNOT_GO_AWAY"
            session.status = _PLAYER_STATUS_AWAY
            session.last_activity_time = time.time()
        return "AWAY_OK"

    def _handle_back_command(self, client_id: int) -> str:
        with self._lock:
            session = self._client_sessions.get(client_id)
            if session is None:
                return "ERROR PLAYER_NOT_FOUND"
            if session.status != _PLAYER_STATUS_AWAY:
                return "ERROR NOT_AWAY"
            session.status = _PLAYER_STATUS_IDLE
            session.last_activity_time = time.time()
        return "BACK_OK"

    def _handle_move_command(
        self,
        client_id: int,
        command: str,
    ) -> tuple[str, _GameRoom | None, int | None]:
        parts = command.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            return "ERROR INVALID_MOVE_FORMAT", None, None
        move_notation = parts[1].strip()
        if " " in move_notation:
            return "ERROR INVALID_MOVE_FORMAT", None, None

        with self._lock:
            session = self._client_sessions.get(client_id)
            if session is None:
                return "ERROR PLAYER_NOT_FOUND", None, None
            if (
                session.game_id is None
                or session.status != _PLAYER_STATUS_INGAME
            ):
                return "ERROR NOT_IN_GAME", None, None

            room = self._game_rooms.get(session.game_id)
            if room is None:
                session.status = _PLAYER_STATUS_IDLE
                session.game_id = None
                return "ERROR NOT_IN_GAME", None, None

            player_id = room.client_to_player_id.get(client_id)
            if player_id is None:
                return "ERROR NOT_IN_GAME", None, None

            game_session = room.session
            if game_session.state.current_player != player_id:
                return "ERROR NOT_YOUR_TURN", None, None

            try:
                self._apply_room_move(
                    game_session,
                    player_id,
                    move_notation,
                )
            except ValueError:
                return "ERROR ILLEGAL_MOVE", None, None

            for participant_client_id in room.player_ids:
                if participant_client_id == client_id:
                    continue

                opponent_session = self._client_sessions.get(
                    participant_client_id
                )
                if opponent_session is None:
                    self._close_game_room_locked(room.game_id)
                    return "ERROR OPPONENT_DISCONNECTED", None, None

                try:
                    _send_line(
                        opponent_session.sock,
                        f"OPPONENT_MOVE {move_notation}",
                    )
                except OSError:
                    try:
                        opponent_session.sock.close()
                    except OSError:
                        pass
                    self._close_client_locked(
                        participant_client_id,
                        opponent_session.sock,
                    )
                    if room.game_id in self._game_rooms:
                        self._close_game_room_locked(room.game_id)
                    return "ERROR OPPONENT_DISCONNECTED", None, None

            winner_player_id = game_session.winner_id()

        return "MOVE_OK", room, winner_player_id

    def _send_room_state(
        self,
        room: _GameRoom,
        *,
        winner_player_id: int | None = None,
    ) -> None:
        with self._lock:
            snapshot = room.session.state.to_snapshot()
            recipients = []
            for participant_client_id in room.player_ids:
                participant_session = self._client_sessions.get(
                    participant_client_id
                )
                player_id = room.client_to_player_id.get(participant_client_id)
                if participant_session is None or player_id is None:
                    continue
                recipients.append(
                    (
                        participant_client_id,
                        participant_session.sock,
                        player_id,
                    )
                )

        for participant_client_id, participant_sock, player_id in recipients:
            try:
                _send_line(
                    participant_sock,
                    format_game_state_message(
                        game_id=room.game_id,
                        player_id=player_id,
                        winner_id=winner_player_id,
                        snapshot=snapshot,
                    ),
                )
            except OSError:
                self._close_client(participant_client_id, participant_sock)

    def _apply_room_move(
        self,
        game_session: GameSession,
        _player_id: int,
        move_notation: str,
    ) -> None:
        service = GameApplicationService(session=game_session)
        if "-" in move_notation:
            service.play_pawn_move_token(move_notation)
            return

        service.place_wall_token(
            move_notation,
            3,
        )

    def _close_game_room_locked(self, game_id: int) -> None:
        room = self._game_rooms.pop(game_id, None)
        if room is None:
            return

        for room_player_id in room.player_ids:
            session = self._client_sessions.get(room_player_id)
            if session is None:
                continue
            session.status = _PLAYER_STATUS_IDLE
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
