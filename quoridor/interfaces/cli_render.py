"""Rendering helpers for the Quoridor CLI."""

from __future__ import annotations

from ..application.game_session import GameSession
from ..core.notation import get_notation_from_node
from ..rules.pawn_rules import get_all_legal_pawn_moves


def _node(row: int, col: int, size: int) -> int:
    return row * size + col


def _render_ascii_board(state) -> str:
    """
    Render proche du format contest/spec:
    - cellules: '_', '1','2','3','4'
    - mur vertical: préfixe 'X' devant la cellule de droite (col > 0)
    - ligne séparatrice: 'X' si mur horizontal, sinon '.'
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


def _print_state(session: GameSession) -> None:
    state = session.state
    size = state.board_size

    ordered_ids = sorted(state.player_positions.keys())
    players_line = ", ".join(
        f"Player {pid}: {get_notation_from_node(state.player_positions[pid], size)}"
        for pid in ordered_ids
    )
    walls_line = ", ".join(
        f"Player {pid}: "
        f"{'unlimited' if state.remaining_walls.get(pid, 0) < 0 else state.remaining_walls.get(pid, 0)}"
        for pid in ordered_ids
    )
    print(_render_ascii_board(state))
    print()
    print(f"Current player: {state.current_player}")
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
        get_notation_from_node(n, session.state.board_size) for n in sorted(legal_nodes)
    ]
    print(f"Legal pawn moves for player {current}: {legal_notation}")


def _format_hint_move(move: tuple, *, from_node: int, size: int) -> str:
    move_type = move[0]
    if move_type == "pawn":
        to_node = int(move[1])
        return f"{get_notation_from_node(from_node, size)}-{get_notation_from_node(to_node, size)}"
    if move_type == "wall":
        edges = move[1]
        orientation = move[2]
        anchor = min(min(a, b) for a, b in edges)
        ori = "h" if orientation in {"h", "horizontal"} else "v"
        return f"{get_notation_from_node(anchor, size)}{ori}"
    return str(move)
