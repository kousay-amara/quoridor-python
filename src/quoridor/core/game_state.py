"""Central game state for Quoridor."""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import Graph
from .move_record import GameSnapshot


@dataclass
class GameState:
    """Single source of truth for the current game state."""

    board_size: int
    current_player: int
    player_positions: dict[int, int]
    remaining_walls: dict[int, int]
    vertical_walls: list[tuple[int, int]] = field(default_factory=list)
    horizontal_walls: list[tuple[int, int]] = field(default_factory=list)
    graph: Graph = field(init=False)

    def __post_init__(self) -> None:
        self.player_positions = dict(self.player_positions)
        self.remaining_walls = dict(self.remaining_walls)
        self.vertical_walls = list(self.vertical_walls)
        self.horizontal_walls = list(self.horizontal_walls)
        self._rebuild_graph()

    def _rebuild_graph(self) -> None:
        graph = Graph(self.board_size)
        for edge in self.vertical_walls:
            graph.remove_edge(*edge)
        for edge in self.horizontal_walls:
            graph.remove_edge(*edge)
        self.graph = graph

    def to_snapshot(self) -> GameSnapshot:
        """Return a serializable snapshot of the current state."""
        return {
            "board_size": self.board_size,
            "current_player": self.current_player,
            "player_positions": dict(self.player_positions),
            "remaining_walls": dict(self.remaining_walls),
            "vertical_walls": list(self.vertical_walls),
            "horizontal_walls": list(self.horizontal_walls),
        }

    def restore(self, snapshot: GameSnapshot) -> None:
        """Restore state from a previously captured snapshot."""
        self.board_size = int(snapshot["board_size"])
        self.current_player = int(snapshot["current_player"])
        self.player_positions = dict(snapshot["player_positions"])
        self.remaining_walls = dict(snapshot["remaining_walls"])
        self.vertical_walls = list(snapshot["vertical_walls"])
        self.horizontal_walls = list(snapshot["horizontal_walls"])
        self._rebuild_graph()

    @classmethod
    def from_snapshot(cls, snapshot: GameSnapshot) -> GameState:
        """Create a new state instance from a snapshot."""
        return cls(
            board_size=int(snapshot["board_size"]),
            current_player=int(snapshot["current_player"]),
            player_positions=dict(snapshot["player_positions"]),
            remaining_walls=dict(snapshot["remaining_walls"]),
            vertical_walls=list(snapshot["vertical_walls"]),
            horizontal_walls=list(snapshot["horizontal_walls"]),
        )
