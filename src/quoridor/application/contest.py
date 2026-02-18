"""Contest application service."""

from __future__ import annotations

from pathlib import Path

from ..core.graph import Graph
from ..interfaces.contest_parser import ContestError, ContestPosition, parse_contest_file
from ..rules.pawn_rules import get_all_legal_pawn_moves


def _node_to_notation(node: int, size: int) -> str:
    row, col = divmod(node, size)
    return f"{chr(ord('a') + col)}{row + 1}"


def run_contest(path: str | Path) -> str:
    position: ContestPosition = parse_contest_file(path)
    graph = Graph(position.size)
    for edge in position.vertical_walls + position.horizontal_walls:
        graph.remove_edge(*edge)

    ordered_players = sorted(position.positions.keys())
    positions_list = [position.positions[p] for p in ordered_players]
    current_pos = position.positions[position.current_player]
    legal_moves = get_all_legal_pawn_moves(graph, current_pos, positions_list)
    if not legal_moves:
        raise ContestError("no legal moves available")

    target = sorted(legal_moves)[0]
    return (
        f"{_node_to_notation(current_pos, position.size)}"
        f"-{_node_to_notation(target, position.size)}"
    )
