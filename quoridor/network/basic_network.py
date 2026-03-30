"""Basic shared helpers for the network package."""

from __future__ import annotations

import json
import socket

from ..core.move_record import GameSnapshot


DEFAULT_SERVER_HOST = "localhost"
DEFAULT_SERVER_PORT = 12345
DISCOVERY_PORT = 12346
DISCOVERY_BROADCAST_INTERVAL_SEC = 10.0
DISCOVERY_ENTRY_TTL_SEC = 30.0
CLIENT_TIMEOUT_SEC = 60.0
_SOCKET_TIMEOUT_SEC = 0.5
_DISCOVERY_BUFFER_SIZE = 1024
_DISCOVERY_PREFIX = "QUORIDOR_SERVER"
_GAME_STATE_PREFIX = "GAME_STATE"


GameStateUpdate = dict


def _validate_port(port: int) -> int:
    """Validate a TCP or UDP port."""
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid port: {port}")
    return port


def _send_line(sock: socket.socket, message: str) -> None:
    sock.sendall(f"{message}\n".encode("ascii", errors="strict"))


def _recv_line(
    sock: socket.socket,
    buffer: str,
) -> tuple[str | None, str, bool]:
    while "\n" not in buffer:
        try:
            data = sock.recv(_DISCOVERY_BUFFER_SIZE)
        except socket.timeout:
            return None, buffer, False
        if not data:
            return None, buffer, True
        buffer += data.decode("ascii", errors="ignore")

    line, buffer = buffer.split("\n", 1)
    return line.rstrip("\r"), buffer, False


def _normalize_snapshot(snapshot_data: object) -> GameSnapshot:
    if not isinstance(snapshot_data, dict):
        raise ValueError("invalid game snapshot")

    def _normalize_int_mapping(raw: object) -> dict[int, int]:
        if not isinstance(raw, dict):
            raise ValueError("invalid game snapshot")
        return {int(key): int(value) for key, value in raw.items()}

    def _normalize_edges(raw: object) -> list[tuple[int, int]]:
        if not isinstance(raw, list):
            raise ValueError("invalid game snapshot")
        edges = []
        for edge in raw:
            if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                raise ValueError("invalid game snapshot")
            edges.append((int(edge[0]), int(edge[1])))
        return edges

    raw_inactive_players = snapshot_data.get("inactive_players", [])
    if not isinstance(raw_inactive_players, list):
        raise ValueError("invalid game snapshot")

    normalized_snapshot: GameSnapshot = {
        "board_size": int(snapshot_data["board_size"]),
        "current_player": int(snapshot_data["current_player"]),
        "player_positions": _normalize_int_mapping(
            snapshot_data["player_positions"]
        ),
        "remaining_walls": _normalize_int_mapping(
            snapshot_data["remaining_walls"]
        ),
        "vertical_walls": _normalize_edges(snapshot_data["vertical_walls"]),
        "horizontal_walls": _normalize_edges(
            snapshot_data["horizontal_walls"]
        ),
    }
    if raw_inactive_players:
        normalized_snapshot["inactive_players"] = [
            int(player_id) for player_id in raw_inactive_players
        ]
    return normalized_snapshot


def format_game_state_message(
    *,
    game_id: int,
    player_id: int,
    winner_id: int | None,
    snapshot: GameSnapshot,
) -> str:
    payload = {
        "game_id": int(game_id),
        "player_id": int(player_id),
        "winner_id": None if winner_id is None else int(winner_id),
        "state": dict(snapshot),
    }
    return (
        f"{_GAME_STATE_PREFIX} "
        f"{json.dumps(payload, separators=(',', ':'), sort_keys=True)}"
    )


def parse_game_state_message(message: str) -> GameStateUpdate | None:
    prefix = f"{_GAME_STATE_PREFIX} "
    if not message.startswith(prefix):
        return None

    try:
        payload = json.loads(message[len(prefix):])
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    try:
        raw_winner_id = payload.get("winner_id")
        winner_id = None if raw_winner_id is None else int(raw_winner_id)
        return {
            "game_id": int(payload["game_id"]),
            "player_id": int(payload["player_id"]),
            "winner_id": winner_id,
            "state": _normalize_snapshot(payload["state"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


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


__all__ = [
    "CLIENT_TIMEOUT_SEC",
    "DEFAULT_SERVER_HOST",
    "DEFAULT_SERVER_PORT",
    "DISCOVERY_BROADCAST_INTERVAL_SEC",
    "DISCOVERY_ENTRY_TTL_SEC",
    "DISCOVERY_PORT",
    "GameStateUpdate",
    "format_game_state_message",
    "parse_endpoint",
    "parse_game_state_message",
]
