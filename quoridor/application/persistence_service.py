"""Persistence service shared by CLI and GUI."""

from __future__ import annotations

import re
from pathlib import Path

from .game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.move_record import BlitzSnapshot
from ..core.notation import (
    get_edges_for_wall,
    get_node_from_notation,
    get_notation_from_node,
)
from ..interfaces.cli_constants import WALLS_DEFAULT
from ..interfaces.contest_parser import ContestError, parse_contest_file

_SECTION_RE = re.compile(r"^\[(.+)\]$")
_BLOCK_COMMENT_RE = re.compile(r"\{.*?\}", re.DOTALL)


def record_to_notation(record) -> str:
    size = record.after_state["board_size"]
    if record.action == "move_pawn":
        from_node = record.before_state["player_positions"][record.player_id]
        to_node = record.after_state["player_positions"][record.player_id]
        return (
            f"{get_notation_from_node(from_node, size)}-"
            f"{get_notation_from_node(to_node, size)}"
        )
    if record.action == "timeout_loss":
        return "timeout"

    before_vertical = set(record.before_state["vertical_walls"])
    after_vertical = set(record.after_state["vertical_walls"])
    if len(after_vertical) > len(before_vertical):
        added_edges = list(after_vertical - before_vertical)
        orientation = "v"
    else:
        before_horizontal = set(record.before_state["horizontal_walls"])
        after_horizontal = set(record.after_state["horizontal_walls"])
        added_edges = list(after_horizontal - before_horizontal)
        orientation = "h"

    if not added_edges:
        raise ValueError("cannot infer wall notation from move record")

    anchor = min(node for edge in added_edges for node in edge)
    return f"{get_notation_from_node(anchor, size)}{orientation}"


def serialize_history(session: GameSession) -> str:
    player_count = len(session.state.player_positions)
    active_records = session.history.records[: session.history.cursor + 1]
    lines = ["[history]"]

    for idx in range(0, len(active_records), player_count):
        turn = active_records[idx : idx + player_count]
        turn_text = " ".join(
            f"{record.player_id} {record_to_notation(record)};"
            for record in turn
        )
        lines.append(turn_text)

    return "\n".join(lines) + "\n"


def split_sections(raw_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    text = _BLOCK_COMMENT_RE.sub("", raw_text)
    for raw_line in text.splitlines():
        if "#" in raw_line:
            raw_line = raw_line.split("#", 1)[0]
        line = raw_line.strip()
        if not line:
            continue
        match = _SECTION_RE.match(line)
        if match:
            current_section = match.group(1).lower()
            sections.setdefault(current_section, [])
            continue
        if current_section is not None:
            sections[current_section].append(line)

    return sections


def parse_history(raw_text: str) -> list[tuple[int, str]]:
    sections = split_sections(raw_text)
    entries: list[tuple[int, str]] = []

    for line in sections.get("history", []):
        for chunk in line.split(";"):
            item = chunk.strip()
            if not item:
                continue
            parts = item.split(maxsplit=1)
            if len(parts) != 2:
                raise ValueError(f"invalid history entry: {item}")
            try:
                player_id = int(parts[0])
            except ValueError as exc:
                raise ValueError(
                    f"invalid history player id: {parts[0]}"
                ) from exc
            entries.append((player_id, parts[1].strip().lower()))

    return entries


def serialize_settings(session: GameSession) -> str:
    players = sorted(session.state.player_positions)
    lines = ["[settings]"]
    lines.append(f"players: {len(players)}")
    lines.append(f"board_size: {session.state.board_size}")
    parts = [
        f"{player_id}={session.player_types.get(player_id, 'human')}"
        for player_id in players
    ]
    lines.append("player_types: " + " ".join(parts))
    return "\n".join(lines) + "\n"


def parse_player_types(raw_text: str) -> dict[int, str]:
    sections = split_sections(raw_text)
    lines = sections.get("settings", [])
    values: dict[str, str] = {}

    for line in lines:
        if ":" not in line:
            raise ValueError(f"invalid settings line: {line}")
        key, raw_value = line.split(":", 1)
        values[key.strip().lower()] = raw_value.strip()

    player_types_raw = values.get("player_types", "")
    if not player_types_raw:
        return {}

    parsed: dict[int, str] = {}
    for token in player_types_raw.split():
        if "=" not in token:
            raise ValueError(f"invalid player_types token: {token}")
        player_id_raw, player_type_raw = token.split("=", 1)
        try:
            player_id = int(player_id_raw)
        except ValueError as exc:
            raise ValueError(
                f"invalid player id in settings: {player_id_raw}"
            ) from exc

        player_type = player_type_raw.strip().lower()
        if player_type not in {"human", "ai"}:
            raise ValueError(f"invalid player type in settings: {player_type_raw}")
        parsed[player_id] = player_type

    return parsed


def serialize_blitz(snapshot: BlitzSnapshot | None) -> str:
    if snapshot is None:
        return ""

    enabled = bool(snapshot.get("enabled", False))
    time_limit = int(snapshot.get("time_limit_minutes", 0))
    paused = bool(snapshot.get("paused", False))
    remaining_raw = snapshot.get("remaining_times", {})
    remaining = {
        int(player_id): float(seconds)
        for player_id, seconds in remaining_raw.items()
    }

    lines = ["[blitz]"]
    lines.append(f"enabled: {'true' if enabled else 'false'}")
    lines.append(f"time_limit_minutes: {time_limit}")
    lines.append(f"paused: {'true' if paused else 'false'}")

    if remaining:
        parts = [
            f"{player_id}={remaining[player_id]:.6f}"
            for player_id in sorted(remaining)
        ]
        lines.append("remaining: " + " ".join(parts))
    else:
        lines.append("remaining:")

    return "\n".join(lines) + "\n"


def parse_blitz(raw_text: str) -> BlitzSnapshot | None:
    sections = split_sections(raw_text)
    lines = sections.get("blitz", [])
    if not lines:
        return None

    values: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            raise ValueError(f"invalid blitz line: {line}")
        key, raw_value = line.split(":", 1)
        values[key.strip().lower()] = raw_value.strip()

    enabled_raw = values.get("enabled", "false").lower()
    if enabled_raw not in {"true", "false"}:
        raise ValueError("invalid blitz enabled value")
    enabled = enabled_raw == "true"

    try:
        time_limit = int(values.get("time_limit_minutes", "0"))
    except ValueError as exc:
        raise ValueError("invalid blitz time_limit_minutes") from exc

    paused_raw = values.get("paused", "false").lower()
    if paused_raw not in {"true", "false"}:
        raise ValueError("invalid blitz paused value")
    paused = paused_raw == "true"

    remaining_times: dict[int, float] = {}
    remaining_raw = values.get("remaining", "")
    if remaining_raw:
        for token in remaining_raw.split():
            if "=" not in token:
                raise ValueError(f"invalid blitz remaining token: {token}")
            pid_text, seconds_text = token.split("=", 1)
            try:
                player_id = int(pid_text)
                seconds = float(seconds_text)
            except ValueError as exc:
                raise ValueError(
                    f"invalid blitz remaining token: {token}"
                ) from exc
            remaining_times[player_id] = seconds

    return {
        "enabled": enabled,
        "time_limit_minutes": time_limit,
        "paused": paused,
        "remaining_times": remaining_times,
    }


def replay_history(
    path: str,
    *,
    position,
    history_entries: list[tuple[int, str]],
    player_types: dict[int, str],
    fallback_walls_per_player: dict[int, int],
) -> GameSession:
    players = sorted(position.positions)
    wall_counts = {pid: 0 for pid in players}
    for player_id, token in history_entries:
        if token.endswith(("h", "v")):
            wall_counts[player_id] = wall_counts.get(player_id, 0) + 1

    remaining_walls = position.remaining_walls or {
        pid: fallback_walls_per_player.get(pid, WALLS_DEFAULT)
        for pid in players
    }
    initial_walls = {
        pid: remaining_walls.get(pid, WALLS_DEFAULT) + wall_counts.get(pid, 0)
        for pid in players
    }

    state = GameState(
        board_size=position.size,
        current_player=players[0],
        player_positions=initial_player_positions(position.size, len(players)),
        remaining_walls=initial_walls,
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types=player_types)

    for player_id, token in history_entries:
        if token == "timeout":
            session.timeout_player(player_id)
        elif "-" in token:
            from_txt, to_txt = token.split("-", 1)
            from_node = get_node_from_notation(from_txt, position.size)
            to_node = get_node_from_notation(to_txt, position.size)
            session.play_pawn_move_from_to(player_id, from_node, to_node)
        else:
            orientation = "horizontal" if token.endswith("h") else "vertical"
            wall_edges = get_edges_for_wall(token, position.size)
            session.place_wall(player_id, wall_edges, orientation)

    final_state = session.state
    if (
        final_state.current_player != position.current_player
        or final_state.player_positions != position.positions
        or final_state.remaining_walls != remaining_walls
        or sorted(final_state.vertical_walls) != sorted(position.vertical_walls)
        or sorted(final_state.horizontal_walls)
        != sorted(position.horizontal_walls)
    ):
        raise ContestError(
            f"history does not match saved game state in {path}"
        )

    return session


def load_session(
    path: str,
    *,
    fallback_player_types: dict[int, str],
    fallback_walls_per_player: dict[int, int],
) -> GameSession:
    raw_text = Path(path).read_text(encoding="utf-8")
    position = parse_contest_file(path)
    history_entries = parse_history(raw_text)

    players = sorted(position.positions.keys())
    saved_player_types = parse_player_types(raw_text)
    player_types = {
        pid: saved_player_types.get(
            pid, fallback_player_types.get(pid, "human")
        )
        for pid in players
    }

    if history_entries:
        return replay_history(
            path,
            position=position,
            history_entries=history_entries,
            player_types=player_types,
            fallback_walls_per_player=fallback_walls_per_player,
        )

    remaining_walls = position.remaining_walls or {
        pid: fallback_walls_per_player.get(pid, WALLS_DEFAULT)
        for pid in players
    }
    state = GameState(
        board_size=position.size,
        current_player=position.current_player,
        player_positions=position.positions,
        remaining_walls=remaining_walls,
        vertical_walls=position.vertical_walls,
        horizontal_walls=position.horizontal_walls,
    )
    return GameSession(state=state, player_types=player_types)


def load_blitz_snapshot(path: str) -> BlitzSnapshot | None:
    raw_text = Path(path).read_text(encoding="utf-8")
    return parse_blitz(raw_text)


def serialize_game(state: GameState) -> str:
    size = state.board_size
    vwalls = set(tuple(edge) for edge in state.vertical_walls)
    hwalls = set(tuple(edge) for edge in state.horizontal_walls)
    player_at = {node: pid for pid, node in state.player_positions.items()}

    lines: list[str] = []
    lines.append("[game]")
    lines.append(str(state.current_player))

    for row in range(size):
        cell_tokens: list[str] = []
        for col in range(size):
            node = row * size + col
            cell = str(player_at[node]) if node in player_at else "_"

            prefix = ""
            if col > 0:
                left = row * size + (col - 1)
                has_vwall = (left, node) in vwalls or (node, left) in vwalls
                if has_vwall:
                    prefix = "X"
            cell_tokens.append(f"{prefix}{cell}")
        lines.append(" ".join(cell_tokens))

        if row < size - 1:
            sep_tokens: list[str] = []
            for col in range(size):
                top = row * size + col
                bottom = (row + 1) * size + col
                has_hwall = (top, bottom) in hwalls or (bottom, top) in hwalls
                sep_tokens.append("X" if has_hwall else ".")
            lines.append(" ".join(sep_tokens))

    ordered_players = sorted(state.remaining_walls.keys())
    walls_part = " ".join(
        str(state.remaining_walls[pid]) for pid in ordered_players
    )
    lines.append(f"walls: {walls_part}")
    return "\n".join(lines) + "\n"


def save_session(
    path: str,
    session: GameSession,
    blitz_snapshot: BlitzSnapshot | None = None,
) -> None:
    content = (
        serialize_game(session.state)
        + "\n"
        + serialize_settings(session)
        + "\n"
        + serialize_history(session)
    )
    blitz_text = serialize_blitz(blitz_snapshot)
    if blitz_text:
        content += "\n" + blitz_text
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(content)
