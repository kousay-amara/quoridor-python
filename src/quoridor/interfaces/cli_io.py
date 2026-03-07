"""Persistence helpers for the Quoridor CLI."""

from __future__ import annotations

import gettext

from ..application.game_session import GameSession
from ..core.game_state import GameState
from .cli_constants import WALLS_DEFAULT
from .cli_render import _node

_ = gettext.gettext


def _load_session_from_file(
    path: str,
    *,
    fallback_player_types: dict[int, str],
    fallback_walls_per_player: dict[int, int],
) -> GameSession:
    from . import cli as cli_mod

    position = cli_mod.parse_contest_file(path)
    players = sorted(position.positions.keys())
    remaining_walls = {
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
    content = _serialize_game_section(session.state)
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
