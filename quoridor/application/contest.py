"""Contest application service."""

from __future__ import annotations

from math import inf
from pathlib import Path

from .ai_logic import (
    apply_move,
    clone_state,
    evaluate_state,
    get_all_legal_moves,
)
from .constants import WALLS_DEFAULT
from .minimax_engine import minimax_alpha_beta
from ..core.game_state import GameState
from ..core.notation import get_notation_from_node
from ..interfaces.contest_parser import (
    ContestError,
    ContestPosition,
    parse_contest_file,
)

CONTEST_SEARCH_DEPTH = 2


def _move_to_notation(
    move: tuple,
    *,
    from_node: int,
    size: int,
) -> str:
    move_type = move[0]
    if move_type == "pawn":
        return (
            f"{get_notation_from_node(from_node, size)}"
            f"-{get_notation_from_node(move[1], size)}"
        )
    if move_type == "wall":
        edges = move[1]
        orientation = str(move[2]).lower()
        anchor = min(node for edge in edges for node in edge)
        suffix = "h" if orientation.startswith("h") else "v"
        return f"{get_notation_from_node(anchor, size)}{suffix}"
    raise ContestError(f"unsupported move type in contest mode: {move_type}")


def _build_state(position: ContestPosition) -> GameState:
    player_ids = sorted(position.positions.keys())
    remaining_walls = {
        pid: position.remaining_walls.get(pid, WALLS_DEFAULT) for pid in player_ids
    }
    return GameState(
        board_size=position.size,
        current_player=position.current_player,
        player_positions=position.positions,
        remaining_walls=remaining_walls,
        vertical_walls=position.vertical_walls,
        horizontal_walls=position.horizontal_walls,
    )


def _choose_best_move(state: GameState, *, depth: int) -> tuple:
    legal_moves = get_all_legal_moves(state)
    if not legal_moves:
        raise ContestError("no legal moves available")

    from_node = state.player_positions[state.current_player]
    size = state.board_size
    ai_player_id = state.current_player

    best_move = None
    best_score = -inf
    best_notation = ""

    for move in sorted(
        legal_moves,
        key=lambda candidate: _move_to_notation(
            candidate,
            from_node=from_node,
            size=size,
        ),
    ):
        child = clone_state(state)
        apply_move(child, move)
        score = minimax_alpha_beta(
            child,
            depth - 1,
            -inf,
            inf,
            child.current_player == ai_player_id,
            ai_player_id,
            evaluate_state,
        )
        notation = _move_to_notation(move, from_node=from_node, size=size)
        if (
            best_move is None
            or score > best_score
            or (score == best_score and notation < best_notation)
        ):
            best_move = move
            best_score = score
            best_notation = notation

    return best_move


def run_contest(path: str | Path) -> str:
    position: ContestPosition = parse_contest_file(path)
    state = _build_state(position)
    from_node = state.player_positions[state.current_player]
    best_move = _choose_best_move(state, depth=CONTEST_SEARCH_DEPTH)
    return _move_to_notation(
        best_move,
        from_node=from_node,
        size=state.board_size,
    )
