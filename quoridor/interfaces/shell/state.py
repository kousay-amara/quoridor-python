"""State containers for the interactive CLI shell."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from ...application.blitz import Blitz
from ...application.game_session import GameSession


@dataclass
class _ShellConfig:
    verbose: bool
    debug: bool
    blitz_enabled: bool
    time_limit: float
    players: int
    walls_per_player: int
    board_size: int
    ai_players: list[int]
    ai_mode: str
    ai_time: int
    ai_minimax_depth: int | None
    ai_minimax_scoring: int
    ai_mcts_selection: str = "UCT"


class _SavedLocalShellState:
    def __init__(
        self,
        *,
        session: GameSession,
        has_unsaved_changes: bool,
        ai_minimax_scoring: int,
        ai_mcts_selection: str,
        current_ai_mode: str,
        current_ai_time: int,
        current_ai_minimax_depth: int | None,
        current_ai_minimax_scoring: int,
        current_ai_mcts_selection: str,
        players: int,
        walls_per_player: int,
        board_size: int,
        ai_players: list[int],
        blitz_enabled: bool,
        time_limit: float,
        blitz: Blitz,
    ) -> None:
        self.session = session
        self.has_unsaved_changes = has_unsaved_changes
        self.ai_minimax_scoring = ai_minimax_scoring
        self.ai_mcts_selection = ai_mcts_selection
        self.current_ai_mode = current_ai_mode
        self.current_ai_time = current_ai_time
        self.current_ai_minimax_depth = current_ai_minimax_depth
        self.current_ai_minimax_scoring = current_ai_minimax_scoring
        self.current_ai_mcts_selection = current_ai_mcts_selection
        self.players = players
        self.walls_per_player = walls_per_player
        self.board_size = board_size
        self.ai_players = list(ai_players)
        self.blitz_enabled = blitz_enabled
        self.time_limit = time_limit
        self.blitz = blitz


@dataclass
class _ShellState:
    session: GameSession
    has_unsaved_changes: bool
    verbose: bool
    debug: bool
    ai_mode: str
    ai_time: int
    ai_minimax_depth: int | None
    ai_minimax_scoring: int
    ai_mcts_selection: str
    current_ai_mode: str
    current_ai_time: int
    current_ai_minimax_depth: int | None
    current_ai_minimax_scoring: int
    current_ai_mcts_selection: str
    players: int
    walls_per_player: int
    board_size: int
    ai_players: list[int]
    blitz_enabled: bool
    time_limit: float
    blitz: Blitz
    network_server: Any | None = None
    network_client: Any | None = None
    network_restore_callback: Callable[[], None] | None = None
    network_player_id: int | None = None
    saved_local_state: _SavedLocalShellState | None = None
    network_sync_lock: threading.Lock = field(default_factory=threading.Lock)
    event_bus: Any | None = None
