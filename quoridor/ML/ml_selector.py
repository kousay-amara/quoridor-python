"""Runtime ML move scoring for MCTS selection."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from ..core.game_state import GameState
from .ml_features import ML_FEATURE_COLUMNS, build_ml_feature_row

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent / "data" / "ml_selector.pkl"
)


@lru_cache(maxsize=4)
def _load_model_cached(resolved_path: str):
    return joblib.load(resolved_path)


def load_model(model_path: str | Path | None = None):
    path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
    return _load_model_cached(str(path.resolve()))


def _win_probability(model, feature_frame: pd.DataFrame) -> float:
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(feature_frame)[0]
        classes = list(model.classes_)
        return float(proba[classes.index(1)])
    return 1.0 if model.predict(feature_frame)[0] == 1 else 0.0


def score_move(
    before_state: GameState,
    move: tuple,
    after_state: GameState,
    *,
    player_id: int,
    turn: int,
    model_path: str | Path | None = None,
) -> float:
    """Score a move from `player_id` perspective.

    Returns a win probability in [0, 1].
    """
    features = build_ml_feature_row(
        before_state,
        move,
        after_state,
        player_id=player_id,
        turn=turn,
    )
    ordered = {col: features[col] for col in ML_FEATURE_COLUMNS}
    frame = pd.DataFrame([ordered], columns=ML_FEATURE_COLUMNS)
    model = load_model(model_path)
    return _win_probability(model, frame)


def ml_select_child(parent_node, *, model_path: str | Path | None = None):
    """Select the best child of parent_node using ML win probability.

    Expects MCTSNode objects with .state, .move, .childrens attributes.
    The player who moved is derived from the parent state's current_player
    (before apply_move advanced it).
    """
    if not parent_node.childrens:
        raise ValueError("No children to select from")

    parent_state = parent_node.state
    # The player who made the move to reach each child is the parent's
    # current_player.
    move_player_id = parent_state.current_player
    turn = getattr(parent_node, "_turn", 1)

    best_child = None
    best_score = -1.0

    for child in parent_node.childrens:
        try:
            prob = score_move(
                parent_state,
                child.move,
                child.state,
                player_id=move_player_id,
                turn=turn,
                model_path=model_path,
            )
        except (ValueError, Exception):
            prob = 0.5

        if prob > best_score:
            best_score = prob
            best_child = child

    return best_child
