"""Minimax engine (with alpha-beta pruning) for Quoridor AI."""

from __future__ import annotations

from math import inf
from time import monotonic
from typing import Any, Callable

from ..core.game_state import GameState
from ..rules.wall_rules import get_player_target_funcs
from .ai_logic import (
    apply_move,
    clone_state,
    evaluate_state,
    get_all_legal_moves,
)

Move = tuple[Any, ...]
EvalFn = Callable[[GameState, int], float]


class SearchTimeout(RuntimeError):
    """Raised when a timed search reaches its deadline."""


def winner_id(state: GameState) -> int | None:
    """Return winner player id if any player reached their target edge."""
    player_ids = state.active_player_ids()
    if len(player_ids) == 1:
        return player_ids[0]
    targets = get_player_target_funcs(state.board_size, player_ids)

    for index, player_id in enumerate(player_ids):
        if targets[index](state.player_positions[player_id]):
            return player_id
    return None


def is_terminal(state: GameState) -> bool:
    """A state is terminal when a winner exists."""
    return winner_id(state) is not None


def _check_deadline(deadline_ts: float | None) -> None:
    if deadline_ts is not None and monotonic() >= deadline_ts:
        raise SearchTimeout("minimax search reached its deadline")


def _deadline_checker(deadline_ts: float | None) -> Callable[[], None] | None:
    if deadline_ts is None:
        return None

    def _check() -> None:
        _check_deadline(deadline_ts)

    return _check


def minimax_alpha_beta(
    state: GameState,
    depth: int,
    alpha: float,
    beta: float,
    maximizing: bool,
    ai_player_id: int,
    eval_fn: EvalFn,
    deadline_ts: float | None = None,
) -> float:
    """Return minimax score for state from ai_player_id perspective."""
    _check_deadline(deadline_ts)

    winner = winner_id(state)
    if winner is not None:
        return 1_000_000.0 if winner == ai_player_id else -1_000_000.0

    if depth <= 0:
        return float(eval_fn(state, ai_player_id))

    legal_moves = get_all_legal_moves(
        state,
        deadline_check=_deadline_checker(deadline_ts),
    )
    if not legal_moves:
        return float(eval_fn(state, ai_player_id))

    if maximizing:
        value = -inf
        for move in legal_moves:
            child = clone_state(state)
            apply_move(child, move)
            value = max(
                value,
                minimax_alpha_beta(
                    child,
                    depth - 1,
                    alpha,
                    beta,
                    child.current_player == ai_player_id,
                    ai_player_id,
                    eval_fn,
                    deadline_ts,
                ),
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
            value,
            minimax_alpha_beta(
                child,
                depth - 1,
                alpha,
                beta,
                child.current_player == ai_player_id,
                ai_player_id,
                eval_fn,
                deadline_ts,
            ),
        )
        beta = min(beta, value)
        if beta <= alpha:
            break
    return value


def find_best_move_minimax(
    state: GameState,
    ai_player_id: int,
    depth: int,
    eval_fn: EvalFn = evaluate_state,
    deadline_ts: float | None = None,
) -> Move:
    """Choose the best legal move for ai_player_id with fixed-depth minimax."""
    try:
        legal_moves = get_all_legal_moves(
            state,
            deadline_check=_deadline_checker(deadline_ts),
        )
    except SearchTimeout:
        legal_moves = get_all_legal_moves(state, deadline_check=None)

    if not legal_moves:
        raise ValueError("no legal moves available for AI")

    best_move = legal_moves[0]
    best_score = -inf

    for move in legal_moves:
        try:
            _check_deadline(deadline_ts)
            child = clone_state(state)
            apply_move(child, move)
            score = minimax_alpha_beta(
                child,
                depth - 1,
                -inf,
                inf,
                child.current_player == ai_player_id,
                ai_player_id,
                eval_fn,
                deadline_ts,
            )
        except SearchTimeout:
            break
        if score > best_score:
            best_score = score
            best_move = move

    return best_move


def find_best_move_iterative(
    state: GameState,
    ai_player_id: int,
    eval_fn: EvalFn = evaluate_state,
    time_limit_sec: float = 5.0,
    max_depth: int | None = None,
) -> Move:
    """Iteratively deepen fixed-depth minimax while time remains."""
    if time_limit_sec <= 0:
        raise ValueError("time_limit_sec must be > 0")

    legal_moves = get_all_legal_moves(state)
    if not legal_moves:
        raise ValueError("no legal moves available for AI")

    best_move = legal_moves[0]
    deadline_ts = monotonic() + time_limit_sec
    depth = 1

    while max_depth is None or depth <= max_depth:
        try:
            _check_deadline(deadline_ts)
            best_move = find_best_move_minimax(
                state=state,
                ai_player_id=ai_player_id,
                depth=depth,
                eval_fn=eval_fn,
                deadline_ts=deadline_ts,
            )
        except SearchTimeout:
            break
        depth += 1

    return best_move
