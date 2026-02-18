"""History model for undo/redo support."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, TypedDict


PlayerType = Literal["human", "ai"]
ActionType = Literal["move_pawn", "place_wall"]


class GameSnapshot(TypedDict):
    """Serializable game snapshot used by history records.

    Expected structure:
    - board_size: int
    - current_player: int
    - player_positions: dict[int, int]
    - remaining_walls: dict[int, int]
    - vertical_walls: list[tuple[int, int]]
    - horizontal_walls: list[tuple[int, int]]
    """

    board_size: int
    current_player: int
    player_positions: dict[int, int]
    remaining_walls: dict[int, int]
    vertical_walls: list[tuple[int, int]]
    horizontal_walls: list[tuple[int, int]]


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class MoveRecord:
    """One recorded move with state before/after execution."""

    player_id: int
    player_type: PlayerType
    action: ActionType
    before_state: GameSnapshot
    after_state: GameSnapshot
    timestamp: datetime = field(default_factory=_utcnow)
