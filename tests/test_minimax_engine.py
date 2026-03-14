"""Tests for the minimax engine."""

from __future__ import annotations

from src.quoridor.application import minimax_engine as engine
from src.quoridor.application.ai_logic import get_all_legal_moves
from src.quoridor.core.game_state import GameState


def _build_state() -> GameState:
    return GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 10, 2: 10},
        vertical_walls=[],
        horizontal_walls=[],
    )


def test_minimax_returns_legal_move():
    state = _build_state()

    move = engine.find_best_move_minimax(state, ai_player_id=1, depth=1)

    assert move in get_all_legal_moves(state)


def test_alpha_beta_returns_float_without_error():
    state = _build_state()

    score = engine.minimax_alpha_beta(
        state=state,
        depth=1,
        alpha=float("-inf"),
        beta=float("inf"),
        maximizing=True,
        ai_player_id=1,
        eval_fn=engine.evaluate_state,
    )

    assert isinstance(score, float)


def test_find_best_move_minimax_returns_current_best_on_timeout(monkeypatch):
    state = _build_state()
    legal_moves = get_all_legal_moves(state)
    calls = {"count": 0}

    def fake_check_deadline(deadline_ts):
        del deadline_ts
        calls["count"] += 1
        if calls["count"] > 1:
            raise engine.SearchTimeout("stop search")

    monkeypatch.setattr(engine, "_check_deadline", fake_check_deadline)

    move = engine.find_best_move_minimax(
        state=state,
        ai_player_id=1,
        depth=1,
        eval_fn=lambda *_args: 0.0,
        deadline_ts=123.0,
    )

    assert move == legal_moves[0]


def test_iterative_deepening_keeps_last_completed_result(monkeypatch):
    state = _build_state()
    depth_calls: list[int] = []

    def fake_find_best_move_minimax(
        state,
        ai_player_id,
        depth,
        eval_fn,
        deadline_ts=None,
    ):
        del state, ai_player_id, eval_fn, deadline_ts
        depth_calls.append(depth)
        if depth == 4:
            raise engine.SearchTimeout("deadline")
        return ("pawn", depth)

    monkeypatch.setattr(engine, "find_best_move_minimax", fake_find_best_move_minimax)

    move = engine.find_best_move_iterative(
        state=state,
        ai_player_id=1,
        eval_fn=lambda *_args: 0.0,
        time_limit_sec=1.0,
    )

    assert depth_calls == [1, 2, 3, 4]
    assert move == ("pawn", 3)


def test_iterative_deepening_respects_max_depth(monkeypatch):
    state = _build_state()
    depth_calls: list[int] = []

    def fake_find_best_move_minimax(
        state,
        ai_player_id,
        depth,
        eval_fn,
        deadline_ts=None,
    ):
        del state, ai_player_id, eval_fn, deadline_ts
        depth_calls.append(depth)
        return ("pawn", depth)

    monkeypatch.setattr(engine, "find_best_move_minimax", fake_find_best_move_minimax)

    move = engine.find_best_move_iterative(
        state=state,
        ai_player_id=1,
        eval_fn=lambda *_args: 0.0,
        time_limit_sec=1.0,
        max_depth=2,
    )

    assert depth_calls == [1, 2]
    assert move == ("pawn", 2)
