from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quoridor.ML import ml_features, ml_selector
from quoridor.core.game_state import GameState


def _state(
    *,
    p1: int = 4,
    p2: int = 76,
    current: int = 1,
    walls1: int = 20,
    walls2: int = 20,
) -> GameState:
    return GameState(
        board_size=9,
        current_player=current,
        player_positions={1: p1, 2: p2},
        remaining_walls={1: walls1, 2: walls2},
        vertical_walls=[],
        horizontal_walls=[],
    )


def test_game_phase_clamps_and_default_total_turns():
    assert ml_features._game_phase(10, 20) == 0.5
    assert ml_features._game_phase(-1, 20) == 0.0
    assert ml_features._game_phase(200, 20) == 1.0
    assert ml_features._game_phase(40, None) == 0.5
    assert ml_features._game_phase(40, 0) == 0.5


def test_build_ml_feature_row_for_pawn_move():
    before = _state(p1=4, p2=76, current=1, walls1=19, walls2=20)
    after = _state(p1=13, p2=76, current=2, walls1=19, walls2=20)
    move = ("pawn", 13)

    row = ml_features.build_ml_feature_row(
        before,
        move,
        after,
        player_id=1,
        turn=4,
        total_turns=20,
    )

    assert set(row) == set(ml_features.ML_FEATURE_COLUMNS)
    assert row["is_pawn_move"] == 1
    assert row["is_wall_move"] == 0
    assert row["pawn_move_distance"] == 1
    assert row["wall_is_horizontal"] == 0
    assert row["wall_is_vertical"] == 0
    assert row["my_walls_before"] == 19
    assert row["opp_walls_before"] == 20
    assert row["game_phase"] == 0.2


def test_build_ml_feature_row_for_wall_move_and_two_player_guard():
    before = _state()
    after = _state()
    wall_move_h = ("wall", [(4, 13), (5, 14)], "horizontal")
    row_h = ml_features.build_ml_feature_row(
        before,
        wall_move_h,
        after,
        player_id=1,
        turn=1,
        total_turns=10,
    )
    assert row_h["is_wall_move"] == 1
    assert row_h["wall_is_horizontal"] == 1
    assert row_h["wall_is_vertical"] == 0
    assert row_h["pawn_move_distance"] == 0

    wall_move_v = ("wall", [(4, 5), (13, 14)], "v")
    row_v = ml_features.build_ml_feature_row(
        before,
        wall_move_v,
        after,
        player_id=1,
        turn=1,
        total_turns=10,
    )
    assert row_v["wall_is_horizontal"] == 0
    assert row_v["wall_is_vertical"] == 1

    three_players = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76, 3: 36},
        remaining_walls={1: 20, 2: 20, 3: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    with pytest.raises(ValueError, match="2-player games only"):
        ml_features.build_ml_feature_row(
            three_players,
            ("pawn", 13),
            three_players,
            player_id=1,
            turn=1,
        )


class _ModelWithProba:
    classes_ = [0, 1]

    def predict_proba(self, _frame):
        return [[0.25, 0.75]]


class _ModelWithPredict:
    def __init__(self, y):
        self._y = y

    def predict(self, _frame):
        return [self._y]


def test_win_probability_prefers_predict_proba_then_predict():
    frame = pd.DataFrame([{"x": 1}])
    assert ml_selector._win_probability(_ModelWithProba(), frame) == 0.75
    assert ml_selector._win_probability(_ModelWithPredict(1), frame) == 1.0
    assert ml_selector._win_probability(_ModelWithPredict(0), frame) == 0.0


def test_load_model_uses_cache_and_resolves_path(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def fake_load(path: str):
        calls.append(path)
        return {"loaded": path}

    ml_selector._load_model_cached.cache_clear()
    monkeypatch.setattr(ml_selector.joblib, "load", fake_load)

    model_path = tmp_path / "model.pkl"
    model_path.write_text("x", encoding="utf-8")

    first = ml_selector.load_model(model_path)
    second = ml_selector.load_model(str(model_path))

    assert first == second
    assert len(calls) == 1


def test_score_move_builds_ordered_frame_and_returns_probability(monkeypatch):
    before = _state()
    after = _state(p1=13, current=2)
    move = ("pawn", 13)

    monkeypatch.setattr(
        ml_selector,
        "load_model",
        lambda _model_path=None: _ModelWithProba(),
    )

    score = ml_selector.score_move(
        before,
        move,
        after,
        player_id=1,
        turn=2,
    )
    assert score == 0.75


def test_ml_select_child_chooses_best_and_fallback_on_error(monkeypatch):
    parent_state = _state(current=1)
    child_a = SimpleNamespace(move=("pawn", 13), state=_state(p1=13, current=2))
    child_b = SimpleNamespace(move=("pawn", 5), state=_state(p1=5, current=2))
    parent = SimpleNamespace(state=parent_state, childrens=[child_a, child_b], _turn=3)

    def fake_score(_before, move, _after, **_kwargs):
        if move[1] == 13:
            return 0.9
        return 0.1

    monkeypatch.setattr(ml_selector, "score_move", fake_score)
    assert ml_selector.ml_select_child(parent) is child_a

    def raising_score(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ml_selector, "score_move", raising_score)
    picked = ml_selector.ml_select_child(parent)
    assert picked is child_a

    with pytest.raises(ValueError, match="No children"):
        ml_selector.ml_select_child(
            SimpleNamespace(state=parent_state, childrens=[])
        )
