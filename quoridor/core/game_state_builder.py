"""Builder for GameState to avoid error-prone construction."""

from __future__ import annotations

from .game_state import GameState


class GameStateBuilder:
    def __init__(self, *, board_size: int = 9) -> None:
        self._board_size = board_size
        self._current_player = 1
        self._player_positions: dict[int, int] = {}
        self._remaining_walls: dict[int, int] = {}
        self._vertical_walls: list[tuple[int, int]] = []
        self._horizontal_walls: list[tuple[int, int]] = []

    def with_board_size(self, size: int) -> GameStateBuilder:
        self._board_size = size
        return self

    def with_current_player(self, player_id: int) -> GameStateBuilder:
        self._current_player = player_id
        return self

    def with_players(self, positions: dict[int, int]) -> GameStateBuilder:
        self._player_positions = dict(positions)
        return self

    def with_remaining_walls(
        self, remaining: dict[int, int]
    ) -> GameStateBuilder:
        self._remaining_walls = dict(remaining)
        return self

    def with_walls(
        self,
        *,
        vertical: list[tuple[int, int]] | None = None,
        horizontal: list[tuple[int, int]] | None = None,
    ) -> GameStateBuilder:
        if vertical is not None:
            self._vertical_walls = list(vertical)
        if horizontal is not None:
            self._horizontal_walls = list(horizontal)
        return self

    def build(self) -> GameState:
        return GameState(
            board_size=self._board_size,
            current_player=self._current_player,
            player_positions=self._player_positions,
            remaining_walls=self._remaining_walls,
            vertical_walls=self._vertical_walls,
            horizontal_walls=self._horizontal_walls,
        )
