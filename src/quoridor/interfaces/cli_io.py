"""Persistence helpers for the Quoridor CLI."""

from __future__ import annotations

import gettext
import re
from pathlib import Path

from ..application.game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.notation import (
    get_edges_for_wall,
    get_node_from_notation,
    get_notation_from_node,
)
from .cli_constants import WALLS_DEFAULT
from .cli_render import _node

_ = gettext.gettext
_SECTION_RE = re.compile(r"^\[(.+)\]$")


def _record_to_notation(session: GameSession, record) -> str:
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


def _serialize_history_section(session: GameSession) -> str:
    player_count = len(session.state.player_positions)
    active_records = session.history.records[: session.history.cursor + 1]
    lines = ["[history]"]

    for idx in range(0, len(active_records), player_count):
        turn = active_records[idx : idx + player_count]
        turn_text = " ".join(
            f"{record.player_id} {_record_to_notation(session, record)};"
            for record in turn
        )
        lines.append(turn_text)

    return "\n".join(lines) + "\n"


def _split_sections(raw_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for raw_line in raw_text.splitlines():
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


def _parse_history_section(raw_text: str) -> list[tuple[int, str]]:
    sections = _split_sections(raw_text)
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
                raise ValueError(f"invalid history player id: {parts[0]}") from exc
            entries.append((player_id, parts[1].strip().lower()))

    return entries


def _replay_history(
    path: str,
    *,
    position,
    history_entries: list[tuple[int, str]],
    fallback_player_types: dict[int, str],
    fallback_walls_per_player: dict[int, int],
) -> GameSession:
    from .contest_parser import ContestError

    players = sorted(position.positions)
    wall_counts = {pid: 0 for pid in players}
    for player_id, token in history_entries:
        if token.endswith(("h", "v")):
            wall_counts[player_id] = wall_counts.get(player_id, 0) + 1

    remaining_walls = position.remaining_walls or {
        pid: fallback_walls_per_player.get(pid, WALLS_DEFAULT) for pid in players
    }
    initial_walls = {
        pid: remaining_walls.get(pid, WALLS_DEFAULT) + wall_counts.get(pid, 0)
        for pid in players
    }
    player_types = {pid: fallback_player_types.get(pid, "human") for pid in players}

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
        or sorted(final_state.horizontal_walls) != sorted(position.horizontal_walls)
    ):
        raise ContestError(f"history does not match saved game state in {path}")

    return session


def _load_session_from_file(
    path: str,
    *,
    fallback_player_types: dict[int, str],
    fallback_walls_per_player: dict[int, int],
) -> GameSession:
    from . import cli as cli_mod

    raw_text = Path(path).read_text(encoding="utf-8")
    position = cli_mod.parse_contest_file(path)
    history_entries = _parse_history_section(raw_text)
    if history_entries:
        return _replay_history(
            path,
            position=position,
            history_entries=history_entries,
            fallback_player_types=fallback_player_types,
            fallback_walls_per_player=fallback_walls_per_player,
        )

    players = sorted(position.positions.keys())
    remaining_walls = position.remaining_walls or {
        pid: fallback_walls_per_player.get(pid, WALLS_DEFAULT) for pid in players
    }
    player_types = {pid: fallback_player_types.get(pid, "human") for pid in players}
    state = GameState(
        board_size=position.size,
        current_player=position.current_player,
        player_positions=position.positions,
        remaining_walls=remaining_walls,
        vertical_walls=position.vertical_walls,
        horizontal_walls=position.horizontal_walls,
    )
    return GameSession(state=state, player_types=player_types)


def _serialize_game_section(state: GameState) -> str:
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
            node = _node(row, col, size)
            cell = str(player_at[node]) if node in player_at else "_"

            prefix = ""
            if col > 0:
                left = _node(row, col - 1, size)
                has_vwall = (left, node) in vwalls or (node, left) in vwalls
                if has_vwall:
                    prefix = "X"
            cell_tokens.append(f"{prefix}{cell}")
        lines.append(" ".join(cell_tokens))

        if row < size - 1:
            sep_tokens: list[str] = []
            for col in range(size):
                top = _node(row, col, size)
                bottom = _node(row + 1, col, size)
                has_hwall = (top, bottom) in hwalls or (bottom, top) in hwalls
                sep_tokens.append("X" if has_hwall else ".")
            lines.append(" ".join(sep_tokens))

    ordered_players = sorted(state.remaining_walls.keys())
    walls_part = " ".join(str(state.remaining_walls[pid]) for pid in ordered_players)
    lines.append(f"walls: {walls_part}")
    return "\n".join(lines) + "\n"


def _save_session_to_file(path: str, session: GameSession) -> None:
    content = _serialize_game_section(session.state) + "\n" + _serialize_history_section(
        session
    )
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(content)


def _prompt_save_before_quit(session: GameSession) -> bool:
    """Return True when the caller should quit."""
    try:
        choice = input("Save the game before quitting? [Y/N] ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return True

    if choice.lower() not in {"y", "yes"}:
        return True

    while True:
        try:
            path = input("Save file path: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return True

        if not path:
            print("Invalid path.")
        else:
            try:
                from . import cli as cli_mod

                cli_mod._save_session_to_file(path, session)
                print(_("Game saved to {path}").format(path=path))
                return True
            except OSError as exc:
                print(f"Cannot save file: {exc}")
            except Exception as exc:
                print(f"Cannot save game: {exc}")

        try:
            retry = input("Saving failed. Try again? [Y/N] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return True
        if retry.lower() not in {"y", "yes"}:
            return True
