"""Simple game session service with history integration."""

from __future__ import annotations

from typing import Literal

from ..core.game_state import GameState
from ..core.move_record import MoveRecord, PlayerType
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..rules.wall_rules import is_wall_legal
from .history_manager import HistoryManager


WallOrientation = Literal["vertical", "horizontal"]


class GameSession:
    """Apply moves on GameState and keep undo/redo history."""

    def __init__(
        self,
        state: GameState,
        player_types: dict[int, PlayerType],
    ) -> None:
        self.state = state
        self.player_types = dict(player_types)
        self.history = HistoryManager()
        self._turn_order = sorted(self.state.player_positions.keys())

    def play_pawn_move(self, player_id: int, to_node: int) -> MoveRecord:
        self._ensure_current_player(player_id)

        from_node = self.state.player_positions[player_id]
        all_positions = list(self.state.player_positions.values())
        legal = get_all_legal_pawn_moves(self.state.graph, from_node, all_positions)
        if to_node not in legal:
            raise ValueError(f"illegal pawn move: {from_node} -> {to_node}")

        before = self.state.to_snapshot()
        self.state.player_positions[player_id] = to_node
        self._advance_turn()
        after = self.state.to_snapshot()

        record = MoveRecord(
            player_id=player_id,
            player_type=self._player_type(player_id),
            action="move_pawn",
            before_state=before,
            after_state=after,
        )
        self.history.record_move(record)
        return record

    def place_wall(
        self,
        player_id: int,
        wall_edges: list[tuple[int, int]],
        orientation: WallOrientation,
    ) -> MoveRecord:
        self._ensure_current_player(player_id)
        if self.state.remaining_walls.get(player_id, 0) <= 0:
            raise ValueError(f"player {player_id} has no walls left")
        if not wall_edges:
            raise ValueError("wall_edges must not be empty")

        positions = [self.state.player_positions[p] for p in sorted(self.state.player_positions)]
        if not is_wall_legal(self.state.graph, positions, wall_edges):
            raise ValueError(f"illegal wall placement: {wall_edges}")

        before = self.state.to_snapshot()
        for edge in wall_edges:
            self.state.graph.remove_edge(*edge)
        if orientation == "vertical":
            self.state.vertical_walls.extend(wall_edges)
        else:
            self.state.horizontal_walls.extend(wall_edges)
        self.state.remaining_walls[player_id] = self.state.remaining_walls[player_id] - 1
        self._advance_turn()
        after = self.state.to_snapshot()

        record = MoveRecord(
            player_id=player_id,
            player_type=self._player_type(player_id),
            action="place_wall",
            before_state=before,
            after_state=after,
        )
        self.history.record_move(record)
        return record

    def undo(self, requester_id: int) -> list[MoveRecord]:
        requester_type = self._player_type(requester_id)
        return self.history.undo_until_human_boundary(
            self.state.restore,
            requester_type=requester_type,
        )

    def redo(self, requester_id: int) -> list[MoveRecord]:
        requester_type = self._player_type(requester_id)
        return self.history.redo_until_human_boundary(
            self.state.restore,
            requester_type=requester_type,
        )

    def _ensure_current_player(self, player_id: int) -> None:
        if player_id != self.state.current_player:
            raise ValueError(
                f"not player {player_id}'s turn (current={self.state.current_player})"
            )

    def _advance_turn(self) -> None:
        idx = self._turn_order.index(self.state.current_player)
        self.state.current_player = self._turn_order[(idx + 1) % len(self._turn_order)]

    def _player_type(self, player_id: int) -> PlayerType:
        if player_id not in self.player_types:
            raise ValueError(f"missing player type for player {player_id}")
        return self.player_types[player_id]
