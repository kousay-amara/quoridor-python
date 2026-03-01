"""Core domain structures for Quoridor."""

from .game_state import GameState
from .move_record import ActionType, GameSnapshot, MoveRecord, PlayerType
from .player import Player

__all__ = [
    "GameState",
    "Player",
    "MoveRecord",
    "GameSnapshot",
    "PlayerType",
    "ActionType",
]
