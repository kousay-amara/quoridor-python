"""Shared ML feature definitions and extraction for training and runtime."""

from __future__ import annotations

from ..core.game_state import GameState
from ..rules.wall_rules import get_player_target_funcs
from ..utils.graph import get_shortest_path_length

ESTIMATED_TOTAL_TURNS = 80

ML_FEATURE_COLUMNS = [
    # Before-state context (13)
    "game_phase",
    "my_dist_before",
    "opp_dist_before",
    "dist_advantage_before",
    "my_walls_before",
    "opp_walls_before",
    "wall_advantage_before",
    "my_row_before",
    "my_col_before",
    "opp_row_before",
    "opp_col_before",
    "my_center_distance_before",
    "opp_center_distance_before",
    # Move description (5)
    "is_pawn_move",
    "is_wall_move",
    "wall_is_horizontal",
    "wall_is_vertical",
    "pawn_move_distance",
    # Move effect deltas (2)
    "my_progress",
    "opp_slowdown",
]


def _distance_to_goal(state: GameState, player_id: int) -> int:
    player_ids = state.active_player_ids()
    targets = get_player_target_funcs(state.board_size, player_ids)
    target_index = player_ids.index(player_id)
    return get_shortest_path_length(
        state.graph,
        state.player_positions[player_id],
        targets[target_index],
    )


def _position_features(
    state: GameState, player_id: int
) -> tuple[int, int, int]:
    node = state.player_positions[player_id]
    row, col = divmod(node, state.board_size)
    center = state.board_size // 2
    center_dist = abs(row - center) + abs(col - center)
    return row, col, center_dist


def _game_phase(turn: int, total_turns: int | None) -> float:
    if total_turns is None or total_turns <= 0:
        total_turns = ESTIMATED_TOTAL_TURNS
    phase = turn / float(total_turns)
    return max(0.0, min(1.0, phase))


def build_ml_feature_row(
    before_state: GameState,
    move: tuple,
    after_state: GameState,
    *,
    player_id: int,
    turn: int,
    total_turns: int | None = None,
) -> dict[str, int | float]:
    """Build one feature row (20 features) for a single move.

    Used both during dataset extraction (training) and at runtime
    (MCTS selection scoring).
    """
    opponent_ids = [
        pid for pid in before_state.active_player_ids() if pid != player_id
    ]
    if len(opponent_ids) != 1:
        raise ValueError("ML features support 2-player games only")
    opponent_id = opponent_ids[0]

    # --- Before-state ---
    my_dist_before = _distance_to_goal(before_state, player_id)
    opp_dist_before = _distance_to_goal(before_state, opponent_id)

    my_row_b, my_col_b, my_center_b = _position_features(
        before_state, player_id
    )
    opp_row_b, opp_col_b, opp_center_b = _position_features(
        before_state, opponent_id
    )

    my_walls_before = before_state.remaining_walls[player_id]
    opp_walls_before = before_state.remaining_walls[opponent_id]

    # --- Move description ---
    move_type = move[0]
    is_pawn = int(move_type == "pawn")
    is_wall = int(move_type == "wall")

    wall_h = 0
    wall_v = 0
    if move_type == "wall":
        orientation = move[2]
        wall_h = int(orientation in ("h", "horizontal"))
        wall_v = int(orientation in ("v", "vertical"))

    pawn_distance = 0
    if move_type == "pawn":
        after_node = move[1]
        before_node = before_state.player_positions[player_id]
        r_b, c_b = divmod(before_node, before_state.board_size)
        r_a, c_a = divmod(after_node, before_state.board_size)
        pawn_distance = abs(r_a - r_b) + abs(c_a - c_b)

    # --- After-state (only for deltas) ---
    my_dist_after = _distance_to_goal(after_state, player_id)
    opp_dist_after = _distance_to_goal(after_state, opponent_id)

    return {
        "game_phase": _game_phase(turn, total_turns),
        "my_dist_before": my_dist_before,
        "opp_dist_before": opp_dist_before,
        "dist_advantage_before": opp_dist_before - my_dist_before,
        "my_walls_before": my_walls_before,
        "opp_walls_before": opp_walls_before,
        "wall_advantage_before": my_walls_before - opp_walls_before,
        "my_row_before": my_row_b,
        "my_col_before": my_col_b,
        "opp_row_before": opp_row_b,
        "opp_col_before": opp_col_b,
        "my_center_distance_before": my_center_b,
        "opp_center_distance_before": opp_center_b,
        "is_pawn_move": is_pawn,
        "is_wall_move": is_wall,
        "wall_is_horizontal": wall_h,
        "wall_is_vertical": wall_v,
        "pawn_move_distance": pawn_distance,
        "my_progress": my_dist_before - my_dist_after,
        "opp_slowdown": opp_dist_after - opp_dist_before,
    }
