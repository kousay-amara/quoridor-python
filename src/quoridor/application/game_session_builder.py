"""Builder for GameSession to avoid error-prone construction."""

from __future__ import annotations

from ..core.game_state import GameState
from ..core.move_record import PlayerType
from .game_session import GameSession


class GameSessionBuilder:
    def __init__(self) -> None:
        self._state: GameState | None = None
        self._player_types: dict[int, PlayerType] = {}

    def with_state(self, state: GameState) -> GameSessionBuilder:
        self._state = state
        return self

    def with_player_types(
        self, player_types: dict[int, PlayerType]
    ) -> GameSessionBuilder:
        self._player_types = dict(player_types)
        return self

    def build(self) -> GameSession:
        if self._state is None:
            raise ValueError("state is required to build GameSession")
        if not self._player_types:
            raise ValueError("player_types are required to build GameSession")
        return GameSession(state=self._state, player_types=self._player_types)
