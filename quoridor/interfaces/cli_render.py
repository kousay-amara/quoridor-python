"""Rendering helpers for the Quoridor CLI."""

from __future__ import annotations

from ..application.game_session import GameSession
from ..core.notation import get_notation_from_node
from ..rules.pawn_rules import get_all_legal_pawn_moves


def _node(row: int, col: int, size: int) -> int:
    return row * size + col


def _goal_for_player(player_id: int, size: int) -> str:
    if player_id == 1:
        return f"reach row {size}"
    if player_id == 2:
        return "reach row 1"
    if player_id == 3:
        return f"reach column {chr(ord('a') + size - 1)}"
    if player_id == 4:
        return "reach column a"
    return "reach your goal edge"


def _render_ascii_board(state) -> str:
    """
    Rendering close to the contest/spec format:
    - cells: '_', '1', '2', '3', '4'
    - vertical wall: 'X' prefix before the right cell (col > 0)
    - separator row: 'X' for a horizontal wall, '.' otherwise
    """
    size = state.board_size

    vwalls = set(tuple(edge) for edge in state.vertical_walls)
    hwalls = set(tuple(edge) for edge in state.horizontal_walls)

    player_at = {node: pid for pid, node in state.player_positions.items()}

    lines = []
    lines.append("    " + "   ".join(chr(ord("a") + c) for c in range(size)))
    lines.append("")

    for r in range(size):
        row_tokens = []
        for c in range(size):
            n = _node(r, c, size)
            cell = str(player_at[n]) if n in player_at else "_"
            row_tokens.append(cell)

            if c < size - 1:
                right = _node(r, c + 1, size)
                has_vwall = (n, right) in vwalls or (right, n) in vwalls
                row_tokens.append("X" if has_vwall else " ")

        lines.append(f"{r + 1:>2}  " + " ".join(row_tokens))

        if r < size - 1:
            sep_tokens = []
            for c in range(size):
                top = _node(r, c, size)
                bottom = _node(r + 1, c, size)
                has_hwall = (top, bottom) in hwalls or (bottom, top) in hwalls
                sep_tokens.append("X" if has_hwall else " ")
                if c < size - 1:
                    sep_tokens.append(" ")
            lines.append("    " + " ".join(sep_tokens))

    return "\n".join(lines)


def _print_state(
    session: GameSession,
    *,
    perspective_player_id: int | None = None,
) -> None:
    state = session.state
    size = state.board_size

    ordered_ids = sorted(state.player_positions.keys())
    player_positions = state.player_positions
    players_line = ", ".join(
        f"Player {pid}: {get_notation_from_node(player_positions[pid], size)}"
        for pid in ordered_ids
    )
    wall_counts = (
        (
            "unlimited"
            if state.remaining_walls.get(pid, 0) < 0
            else str(state.remaining_walls.get(pid, 0))
        )
        for pid in ordered_ids
    )
    walls_line = ", ".join(
        f"Player {pid}: {count}"
        for pid, count in zip(ordered_ids, wall_counts)
    )
    print(_render_ascii_board(state))
    print()
    current_line = f"Current player: {state.current_player}"
    if perspective_player_id == state.current_player:
        current_line += " (your turn)"
    print(current_line)
    if perspective_player_id in player_positions:
        position = get_notation_from_node(
            player_positions[perspective_player_id], size
        )
        print(
            f"You are player {perspective_player_id}. "
            f"Position: {position}. "
            f"Goal: {_goal_for_player(perspective_player_id, size)}."
        )
    print(players_line)
    print(f"Walls -> {walls_line}")


def _print_moves(session: GameSession) -> None:
    """Shows the legal moves for the current player"""
    current = session.state.current_player

    from_node = session.state.player_positions[current]
    all_positions = list(session.state.player_positions.values())
    legal_nodes = get_all_legal_pawn_moves(
        session.state.graph, from_node, all_positions
    )
    legal_notation = [
        get_notation_from_node(n, session.state.board_size)
        for n in sorted(legal_nodes)
    ]
    print(f"Legal pawn moves for player {current}: {legal_notation}")


def _format_hint_move(move: tuple, *, from_node: int, size: int) -> str:
    move_type = move[0]
    if move_type == "pawn":
        to_node = int(move[1])
        return (
            f"{get_notation_from_node(from_node, size)}-"
            f"{get_notation_from_node(to_node, size)}"
        )
    if move_type == "wall":
        edges = move[1]
        orientation = move[2]
        anchor = min(min(a, b) for a, b in edges)
        ori = "h" if orientation in {"h", "horizontal"} else "v"
        return f"{get_notation_from_node(anchor, size)}{ori}"
    return str(move)
