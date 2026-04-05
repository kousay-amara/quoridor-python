"""Application facade for shared game operations used by CLI and GUI."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.notation import get_edges_for_wall, get_node_from_notation
from ..core.validators import validate_pawn_move, validate_wall
from ..rules.win_rules import has_player_won
from .blitz import Blitz
from .game_session import GameOutcome, GameSession, initial_player_positions
from .mcts_engine import mcts_search
from .minimax_engine import (
    find_best_move_iterative,
    find_best_move_minimax,
)
from .persistence_service import (
    load_blitz_snapshot,
    load_session,
    save_session,
)
from ..core.game_state import GameState


@dataclass
class GameApplicationService:
    """Facade to expose core game use-cases to interfaces."""

    session: GameSession
    blitz: Blitz | None = None

    def __post_init__(self) -> None:
        self.session.attach_blitz(self.blitz)

    def set_context(
        self, *, session: GameSession, blitz: Blitz | None
    ) -> None:
        self.session = session
        self.blitz = blitz
        self.session.attach_blitz(self.blitz)

    def load(
        self,
        path: str,
        *,
        fallback_player_types: dict[int, str],
        fallback_walls_per_player: dict[int, int],
    ) -> tuple[GameSession, Blitz]:
        session = load_session(
            path,
            fallback_player_types=fallback_player_types,
            fallback_walls_per_player=fallback_walls_per_player,
        )
        snapshot = load_blitz_snapshot(path)
        blitz = (
            Blitz.from_snapshot(snapshot)
            if snapshot is not None
            else Blitz(time_limit_minutes=0)
        )
        session.attach_blitz(blitz)
        self.set_context(session=session, blitz=blitz)
        return session, blitz

    def save(self, path: str) -> None:
        snapshot = None if self.blitz is None else self.blitz.snapshot()
        save_session(path, self.session, blitz_snapshot=snapshot)

    def hint(
        self,
        *,
        ai_mode: str,
        ai_time: int,
        ai_minimax_depth: int | None,
        mcts_fn=None,
        iterative_fn=None,
        minimax_fn=None,
    ):
        current = self.session.state.current_player
        if mcts_fn is None:
            mcts_fn = mcts_search
        if iterative_fn is None:
            iterative_fn = find_best_move_iterative
        if minimax_fn is None:
            minimax_fn = find_best_move_minimax
        if ai_mode == "mcts":
            move = mcts_fn(self.session.state, time_limit=ai_time)
            if move is None:
                raise ValueError("no legal moves available for hint")
            return move

        if ai_mode == "iterative":
            return iterative_fn(
                self.session.state,
                ai_player_id=current,
                time_limit_sec=ai_time,
                max_depth=ai_minimax_depth,
            )

        if ai_mode == "minimax":
            if ai_minimax_depth is None:
                raise ValueError("minimax mode requires ai_minimax_depth")
            return minimax_fn(
                self.session.state,
                ai_player_id=current,
                depth=ai_minimax_depth,
            )

        raise ValueError(f"unsupported AI mode: {ai_mode}")

    def scores(self) -> dict[int, int]:
        return self.session.compute_scores()

    def game_outcome(self) -> GameOutcome:
        return self.session.game_outcome()

    def undo_groups(self, *, requester_id: int, count: int) -> tuple[int, int]:
        if count <= 0:
            raise ValueError("N must be > 0")

        total_undone = 0
        groups_done = 0
        for _ in range(count):
            undone = self.session.undo(requester_id=requester_id)
            if not undone:
                break
            groups_done += 1
            total_undone += len(undone)
        return groups_done, total_undone

    def redo_groups(self, *, requester_id: int, count: int) -> tuple[int, int]:
        if count <= 0:
            raise ValueError("N must be > 0")

        total_redone = 0
        groups_done = 0
        for _ in range(count):
            redone = self.session.redo(requester_id=requester_id)
            if not redone:
                break
            groups_done += 1
            total_redone += len(redone)
        return groups_done, total_redone

    def play_pawn_move_token(self, move_token: str) -> tuple[bool, int]:
        token = move_token.strip().lower()
        if "-" not in token:
            raise ValueError("Invalid format. Use: e2-e3")

        from_txt, to_txt = token.split("-", 1)
        from_node = get_node_from_notation(
            from_txt, self.session.state.board_size
        )
        to_node = get_node_from_notation(to_txt, self.session.state.board_size)

        current = self.session.state.current_player
        all_positions = list(self.session.state.player_positions.values())
        ok, error_msg = validate_pawn_move(
            self.session.state.graph,
            from_node,
            to_node,
            all_positions,
            self.session.state.board_size,
        )
        if not ok:
            raise ValueError(error_msg)

        self.session.play_pawn_move_from_to(current, from_node, to_node)
        new_pos = self.session.state.player_positions[current]
        return (
            has_player_won(current, new_pos, self.session.state.board_size),
            current,
        )

    def place_wall_token(
        self, wall_token: str, wall_token_min_length: int
    ) -> None:
        token = wall_token.strip().lower()
        if len(token) < wall_token_min_length:
            raise ValueError("Invalid format. Use: e2h or e2v")

        ori_char = token[-1]
        if ori_char not in {"h", "v"}:
            raise ValueError("Invalid wall orientation. Use h or v")

        wall_edges = get_edges_for_wall(token, self.session.state.board_size)
        orientation = "horizontal" if ori_char == "h" else "vertical"

        current = self.session.state.current_player
        active_players = self.session.active_player_ids()
        positions = [
            self.session.state.player_positions[player_id]
            for player_id in active_players
        ]
        target_funcs = self.session._build_player_target_funcs()
        ok, error_msg = validate_wall(
            self.session.state.graph,
            positions,
            wall_edges,
            target_funcs,
            self.session.state.remaining_walls,
            current,
        )
        if not ok:
            raise ValueError(error_msg)

        self.session.place_wall(current, wall_edges, orientation)

    @staticmethod
    def new_session(
        *,
        board_size: int,
        players: int,
        walls_per_player: int,
        player_types: dict[int, str],
    ) -> GameSession:
        state = GameState(
            board_size=board_size,
            current_player=1,
            player_positions=initial_player_positions(board_size, players),
            remaining_walls={
                pid: walls_per_player for pid in range(1, players + 1)
            },
            vertical_walls=[],
            horizontal_walls=[],
        )
        return GameSession(state=state, player_types=player_types)
