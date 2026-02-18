"""Player domain model."""

from __future__ import annotations


class Player:
    def __init__(
        self,
        player_id: int,
        pos: int,
        target_row: int | None = None,
        target_col: int | None = None,
        wall_count: int = 10,
    ) -> None:
        self.player_id = player_id
        self.pos = pos
        self.target_row = target_row
        self.target_col = target_col
        self.wall_count = wall_count

    def move(self, new_pos: int) -> None:
        self.pos = new_pos

    def use_wall(self) -> None:
        if self.wall_count > 0:
            self.wall_count -= 1
