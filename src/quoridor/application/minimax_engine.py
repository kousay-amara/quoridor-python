"""Minimax engine (with alpha-beta pruning) for Quoridor AI."""

from __future__ import annotations

from math import inf
from typing import Any

from ..core.game_state import GameState
from ..rules.wall_rules import get_player_target_funcs
from .ai_logic import apply_move, clone_state, evaluate_state, get_all_legal_moves

Move = tuple[Any, ...]


def get_winner_id(state: GameState) -> int | None:
    """Return winner player id if any player reached their target edge."""
    player_ids = sorted(state.player_positions.keys())
    targets = get_player_target_funcs(state.board_size, player_ids)

    for i, pid in enumerate(player_ids):
        if targets[i](state.player_positions[pid]):
            return pid
    return None


def is_terminal_state(state: GameState) -> bool:
    """A state is terminal when a winner exists."""
    return get_winner_id(state) is not None


def minimax_alpha_beta(
    state: GameState,
    depth: int,
    alpha: float,
    beta: float,
    ai_player_id: int,
) -> float:
    """Return minimax score for state from ai_player_id perspective."""
    winner = get_winner_id(state)
    if winner is not None:
        return 1_000_000.0 if winner == ai_player_id else -1_000_000.0

    if depth <= 0:
        return evaluate_state(state, ai_player_id)

    legal_moves = get_all_legal_moves(state)
    if not legal_moves:
        return evaluate_state(state, ai_player_id)

    maximizing = state.current_player == ai_player_id

    if maximizing:
        value = -inf
        for move in legal_moves:
            child = clone_state(state)
            apply_move(child, move)
            value = max(
                value, minimax_alpha_beta(child, depth - 1, alpha, beta, ai_player_id)
            )
            alpha = max(alpha, value)
            if beta <= alpha:
                break
        return value

    value = inf
    for move in legal_moves:
        child = clone_state(state)
        apply_move(child, move)
        value = min(
            value, minimax_alpha_beta(child, depth - 1, alpha, beta, ai_player_id)
        )
        beta = min(beta, value)
        if beta <= alpha:
            break
    return value


def choose_best_move_minimax(
    state: GameState, ai_player_id: int, depth: int = 2
) -> Move:
    """Choose the best legal move for ai_player_id with minimax alpha-beta."""
    legal_moves = get_all_legal_moves(state)
    if not legal_moves:
        raise ValueError("no legal moves available for AI")

    best_move = legal_moves[0]
    best_score = -inf

    for move in legal_moves:
        child = clone_state(state)
        apply_move(child, move)
        score = minimax_alpha_beta(child, depth - 1, -inf, inf, ai_player_id)
        if score > best_score:
            best_score = score
            best_move = move

    return best_move
