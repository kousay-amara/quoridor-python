"""History model for undo/redo support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

PlayerType = Literal["human", "ai"]
ActionType = Literal["move_pawn", "place_wall", "timeout_loss"]


class GameSnapshot(TypedDict):
    """Serializable game snapshot used by history records.

    Expected structure:
    - board_size: int
    - current_player: int
    - player_positions: dict[int, int]
    - remaining_walls: dict[int, int]
    - vertical_walls: list[tuple[int, int]]
    - horizontal_walls: list[tuple[int, int]]
    - inactive_players: list[int]
    """

    board_size: int
    current_player: int
    player_positions: dict[int, int]
    remaining_walls: dict[int, int]
    vertical_walls: list[tuple[int, int]]
    horizontal_walls: list[tuple[int, int]]
    inactive_players: list[int]


class BlitzSnapshot(TypedDict):
    """Serializable blitz timer snapshot."""

    enabled: bool
    time_limit_minutes: float
    paused: bool
    remaining_times: dict[int, float]


@dataclass
class MoveRecord:
    """One recorded move with state before/after execution."""

    player_id: int
    player_type: PlayerType
    action: ActionType
    before_state: GameSnapshot
    after_state: GameSnapshot
    before_blitz: BlitzSnapshot | None = None
    after_blitz: BlitzSnapshot | None = None
