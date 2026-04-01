"""Extract rich ML dataset by replaying raw games turn by turn.

Each row describes one move with 20 features computed from the
before/after GameState. Label = 1 if the player won, -1 otherwise.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ..application.ai_logic import apply_move, clone_state
from ..application.game_session import initial_player_positions
from ..core.game_state_builder import GameStateBuilder
from .ml_features import ML_FEATURE_COLUMNS, build_ml_feature_row

DEFAULT_RAW_GAMES_DIR = Path("quoridor/ML/data/raw_games")
DEFAULT_OUTPUT_PATH = Path("quoridor/ML/data/ml_moves_dataset.csv")
DEFAULT_WALLS_PER_PLAYER = 10


def _deserialize_move(move_data: dict) -> tuple:
    move_type = move_data["type"]
    if move_type == "pawn":
        return ("pawn", int(move_data["to_node"]))
    if move_type == "wall":
        edges = [tuple(e) for e in move_data["edges"]]
        orientation = move_data["orientation"]  # "h" or "v"
        return ("wall", edges, orientation)
    raise ValueError(f"Unknown move type: {move_type}")


def _build_initial_state(game_data: dict):
    board_size = game_data["board_size"]
    players = game_data["players"]
    walls_per_player = game_data.get("walls_per_player", DEFAULT_WALLS_PER_PLAYER)

    positions = initial_player_positions(board_size, players)
    remaining_walls = {pid: walls_per_player for pid in positions}

    return (
        GameStateBuilder(board_size=board_size)
        .with_current_player(1)
        .with_players(positions)
        .with_remaining_walls(remaining_walls)
        .build()
    )


def extract_moves_dataset(
    raw_games_dir: Path = DEFAULT_RAW_GAMES_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> int:
    game_paths = sorted(raw_games_dir.glob("game_*.json"))
    print(f"Found {len(game_paths)} game files")

    rows: list[dict] = []
    skipped = 0

    for game_path in game_paths:
        game_data = json.loads(game_path.read_text(encoding="utf-8"))

        if game_data.get("termination") != "winner":
            skipped += 1
            continue

        winner_id = game_data.get("winner_id")
        if winner_id is None:
            skipped += 1
            continue

        if game_data.get("players", 2) != 2:
            skipped += 1
            continue

        turn_count = game_data.get("turn_count", len(game_data["turns"]))
        state = _build_initial_state(game_data)

        for turn_data in game_data["turns"]:
            player_id = turn_data["player_id"]
            turn_num = turn_data["turn"]
            move = _deserialize_move(turn_data["move"])

            before_state = clone_state(state)
            after_state = clone_state(state)
            apply_move(after_state, move)

            try:
                features = build_ml_feature_row(
                    before_state,
                    move,
                    after_state,
                    player_id=player_id,
                    turn=turn_num,
                    total_turns=turn_count,
                )
            except ValueError:
                # Skip non-2-player turns (shouldn't happen given players check)
                apply_move(state, move)
                continue

            row = {
                "game_id": game_data["game_id"],
                "turn": turn_num,
                **{col: features[col] for col in ML_FEATURE_COLUMNS},
                "label": 1 if player_id == winner_id else -1,
            }
            rows.append(row)

            # Advance the real state
            apply_move(state, move)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["game_id", "turn", *ML_FEATURE_COLUMNS, "label"]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✓ Dataset written: {output_path}")
    print(f"  Rows: {len(rows)}")
    print(f"  Skipped games: {skipped}")
    won = sum(1 for r in rows if r["label"] == 1)
    lost = sum(1 for r in rows if r["label"] == -1)
    print(f"  Won moves: {won} | Lost moves: {lost}")
    return len(rows)


def main() -> None:
    extract_moves_dataset()


if __name__ == "__main__":
    main()
