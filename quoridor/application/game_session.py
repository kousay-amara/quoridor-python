"""Simple game session service with history integration."""

from __future__ import annotations

from typing import Any, Literal

from ..core.game_state import GameState
from ..core.move_record import MoveRecord, PlayerType
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..rules.wall_rules import get_player_target_funcs, is_wall_legal
from ..rules.win_rules import has_player_won
from .blitz import Blitz
from .history_manager import HistoryManager
from .mcts_engine import mcts_search
from .minimax_engine import (
    find_best_move_iterative,
    find_best_move_minimax,
)

WallOrientation = Literal["vertical", "horizontal"]
AIMove = tuple[Any, ...]


def initial_player_positions(board_size: int, players: int) -> dict[int, int]:
    """Return canonical starting positions for 2 to 4 players."""
    mid = board_size // 2
    all_positions = {
        1: 0 * board_size + mid,
        2: (board_size - 1) * board_size + mid,
        3: mid * board_size + 0,
        4: mid * board_size + (board_size - 1),
    }
    return {pid: all_positions[pid] for pid in range(1, players + 1)}


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
        self._blitz: Blitz | None = None

    def attach_blitz(self, blitz: Blitz | None) -> None:
        self._blitz = blitz

    def active_player_ids(self) -> list[int]:
        return self.state.active_player_ids()

    def winner_id(self) -> int | None:
        active_players = self.active_player_ids()
        if len(active_players) == 1:
            return active_players[0]

        for player_id in active_players:
            player_node = self.state.player_positions[player_id]
            if has_player_won(player_id, player_node, self.state.board_size):
                return player_id
        return None

    def play_pawn_move(self, player_id: int, to_node: int) -> MoveRecord:
        self._ensure_current_player(player_id)

        from_node = self.state.player_positions[player_id]
        all_positions = list(self.state.player_positions.values())
        legal = get_all_legal_pawn_moves(self.state.graph, from_node, all_positions)
        if to_node not in legal:
            raise ValueError(f"illegal pawn move: {from_node} -> {to_node}")

        before = self.state.to_snapshot()
        before_blitz = self._capture_blitz_snapshot()
        self.state.player_positions[player_id] = to_node
        self._advance_turn()
        after = self.state.to_snapshot()
        after_blitz = self._capture_blitz_snapshot()

        record = MoveRecord(
            player_id=player_id,
            player_type=self._player_type(player_id),
            action="move_pawn",
            before_state=before,
            after_state=after,
            before_blitz=before_blitz,
            after_blitz=after_blitz,
        )
        self.history.record_move(record)
        return record

    def play_pawn_move_from_to(
        self, player_id: int, from_node: int, to_node: int
    ) -> MoveRecord:
        """Play a pawn move while enforcing the provided source node."""
        self._ensure_current_player(player_id)
        current_node = self.state.player_positions[player_id]
        if current_node != from_node:
            raise ValueError(f"player {player_id} pawn is not on node {from_node}")
        return self.play_pawn_move(player_id, to_node)

    # Needed by is_wall_legal to know each player's target rows/columns.
    def _build_player_target_funcs(self):
        return get_player_target_funcs(self.state.board_size, self.active_player_ids())

    def place_wall(
        self,
        player_id: int,
        wall_edges: list[tuple[int, int]],
        orientation: WallOrientation,
    ) -> MoveRecord:
        self._ensure_current_player(player_id)
        walls_left = self.state.remaining_walls.get(player_id, 0)
        if walls_left == 0:
            raise ValueError(f"player {player_id} has no walls left")
        if not wall_edges:
            raise ValueError("wall_edges must not be empty")

        active_players = self.active_player_ids()
        positions = [
            self.state.player_positions[player_id] for player_id in active_players
        ]
        target_funcs = self._build_player_target_funcs()
        if not is_wall_legal(self.state.graph, positions, wall_edges, target_funcs):
            raise ValueError(f"illegal wall placement: {wall_edges}")

        before = self.state.to_snapshot()
        before_blitz = self._capture_blitz_snapshot()
        for edge in wall_edges:
            self.state.graph.remove_edge(*edge)
        if orientation == "vertical":
            self.state.vertical_walls.extend(wall_edges)
        else:
            self.state.horizontal_walls.extend(wall_edges)
        if walls_left > 0:
            self.state.remaining_walls[player_id] = walls_left - 1
        self._advance_turn()
        after = self.state.to_snapshot()
        after_blitz = self._capture_blitz_snapshot()

        record = MoveRecord(
            player_id=player_id,
            player_type=self._player_type(player_id),
            action="place_wall",
            before_state=before,
            after_state=after,
            before_blitz=before_blitz,
            after_blitz=after_blitz,
        )
        self.history.record_move(record)
        return record

    def timeout_player(
        self,
        player_id: int,
        *,
        before_blitz_snapshot=None,
    ) -> tuple[MoveRecord, int | None]:
        self._ensure_current_player(player_id)
        if not self.state.is_player_active(player_id):
            raise ValueError(f"player {player_id} is already inactive")

        before = self.state.to_snapshot()
        before_blitz = (
            self._capture_blitz_snapshot()
            if before_blitz_snapshot is None
            else before_blitz_snapshot
        )
        self.state.inactive_players.add(player_id)
        self._advance_turn()
        after = self.state.to_snapshot()
        after_blitz = self._capture_blitz_snapshot()

        record = MoveRecord(
            player_id=player_id,
            player_type=self._player_type(player_id),
            action="timeout_loss",
            before_state=before,
            after_state=after,
            before_blitz=before_blitz,
            after_blitz=after_blitz,
        )
        self.history.record_move(record)
        return record, self.winner_id()

    def undo(self, requester_id: int) -> list[MoveRecord]:
        requester_type = self._player_type(requester_id)
        return self.history.undo_until_human_boundary(
            self.state.restore,
            requester_type=requester_type,
            apply_blitz_snapshot=self._restore_blitz_snapshot,
        )

    def redo(self, requester_id: int) -> list[MoveRecord]:
        requester_type = self._player_type(requester_id)
        return self.history.redo_until_human_boundary(
            self.state.restore,
            requester_type=requester_type,
            apply_blitz_snapshot=self._restore_blitz_snapshot,
        )

    def compute_ai_move(
        self,
        *,
        mode: str = "iterative",
        depth: int | None = None,
        time_limit_sec: float = 5.0,
    ) -> AIMove:
        """Compute the current AI player's move without applying it."""
        player_id = self.state.current_player
        if self._player_type(player_id) != "ai":
            raise ValueError(f"player {player_id} is not an AI player")

        if mode == "mcts":
            move = mcts_search(
                self.state,
                time_limit=time_limit_sec,
            )
        elif mode == "iterative":
            move = find_best_move_iterative(
                self.state,
                ai_player_id=player_id,
                time_limit_sec=time_limit_sec,
                max_depth=depth,
            )
        elif mode == "minimax":
            if depth is None:
                raise ValueError("minimax mode requires a fixed depth")
            move = find_best_move_minimax(
                self.state,
                ai_player_id=player_id,
                depth=depth,
            )
        else:
            raise ValueError(f"unsupported AI mode: {mode}")

        return move

    def apply_ai_move(
        self,
        move: AIMove,
        *,
        player_id: int | None = None,
    ) -> MoveRecord:
        """Apply a previously computed move for the current AI player."""
        if player_id is None:
            player_id = self.state.current_player
        self._ensure_current_player(player_id)
        if self._player_type(player_id) != "ai":
            raise ValueError(f"player {player_id} is not an AI player")

        move_type = move[0]

        if move_type == "pawn":
            return self.play_pawn_move(player_id, move[1])

        if move_type == "wall":
            edges = move[1]
            orientation_token = move[2]
            orientation: WallOrientation = (
                "horizontal" if orientation_token in {"h", "horizontal"} else "vertical"
            )
            return self.place_wall(player_id, edges, orientation)

        raise ValueError(f"unsupported AI move type: {move_type}")

    def play_ai_turn(
        self,
        *,
        mode: str = "iterative",
        depth: int | None = None,
        time_limit_sec: float = 5.0,
    ) -> MoveRecord:
        """Compute and play the current AI player's move."""
        move = self.compute_ai_move(
            mode=mode,
            depth=depth,
            time_limit_sec=time_limit_sec,
        )
        return self.apply_ai_move(move)

    def _ensure_current_player(self, player_id: int) -> None:
        if not self.state.is_player_active(player_id):
            raise ValueError(f"player {player_id} is inactive")
        if player_id != self.state.current_player:
            raise ValueError(
                f"not player {player_id}'s turn "
                f"(current={self.state.current_player})"
            )

    def _advance_turn(self) -> None:
        active_players = self.active_player_ids()
        if not active_players:
            return
        if len(active_players) == 1:
            self.state.current_player = active_players[0]
            return

        idx = self._turn_order.index(self.state.current_player)
        for offset in range(1, len(self._turn_order) + 1):
            next_player = self._turn_order[(idx + offset) % len(self._turn_order)]
            if next_player in active_players:
                self.state.current_player = next_player
                return

    def _capture_blitz_snapshot(self):
        if self._blitz is None:
            return None
        return self._blitz.snapshot()

    def _restore_blitz_snapshot(self, snapshot) -> None:
        if self._blitz is None:
            return
        self._blitz.restore_snapshot(snapshot)

    def _player_type(self, player_id: int) -> PlayerType:
        if player_id not in self.player_types:
            raise ValueError(f"missing player type for player {player_id}")
        return self.player_types[player_id]
