"""Tests for quoridor.core.validators."""

from __future__ import annotations

from quoridor.utils.graph import Graph
from quoridor.core.validators import validate_pawn_move, validate_wall

SIZE = 9


def _graph(size: int = SIZE) -> Graph:
    return Graph(size)


class TestValidatePawnMove:
    """One test per possible outcome (True + 4 error messages)."""

    def test_legal_move_returns_true(self):
        graph = _graph()
        ok, msg = validate_pawn_move(graph, 4, 13, [4, 76], SIZE)
        assert ok is True
        assert msg is None

    def test_nonexistent_cell(self):
        graph = _graph()
        ok, msg = validate_pawn_move(graph, 4, 999, [4, 76], SIZE)
        assert ok is False
        assert msg == "This cell does not exist on the board."

    def test_occupied_cell(self):
        graph = _graph()
        ok, msg = validate_pawn_move(graph, 4, 13, [4, 13], SIZE)
        assert ok is False
        assert msg == "This cell is occupied by another player."

    def test_wall_blocking(self):
        graph = _graph()
        graph.remove_edge(4, 13)
        ok, msg = validate_pawn_move(graph, 4, 13, [4, 76], SIZE)
        assert ok is False
        assert msg == "A wall is blocking that move."

    def test_not_reachable_non_adjacent(self):
        graph = _graph()
        ok, msg = validate_pawn_move(graph, 4, 14, [4, 76], SIZE)
        assert ok is False
        assert msg == "This move is not reachable from your position."


def _target_funcs_9x9():
    """Standard targets for a 9×9 board: player 1 → row 8, player 2 → row 0."""
    return [
        lambda node: node // SIZE == SIZE - 1,
        lambda node: node // SIZE == 0,
    ]


class TestValidateWall:
    def test_legal_wall_returns_true(self):
        graph = _graph()
        wall_edges = [(4, 13), (5, 14)]
        ok, msg = validate_wall(
            graph, [4, 76], wall_edges, _target_funcs_9x9(), {1: 10, 2: 10}, 1
        )
        assert ok is True
        assert msg is None

    def test_no_walls_left(self):
        graph = _graph()
        wall_edges = [(4, 13), (5, 14)]
        ok, msg = validate_wall(
            graph, [4, 76], wall_edges, _target_funcs_9x9(), {1: 0, 2: 10}, 1
        )
        assert ok is False
        assert msg == "You have no walls left."

    def test_wall_already_exists(self):
        graph = _graph()
        graph.remove_edge(4, 13)
        wall_edges = [(4, 13), (5, 14)]
        ok, msg = validate_wall(
            graph, [4, 76], wall_edges, _target_funcs_9x9(), {1: 10, 2: 10}, 1
        )
        assert ok is False
        assert msg == "A wall already exists there."

    def test_wall_blocks_player_path(self):
        size = 3
        graph = _graph(size)
        graph.remove_edge(0, 1)

        target_funcs = [
            lambda node, s=size: node // s == s - 1,
            lambda node, s=size: node // s == 0,
        ]
        wall_edges = [(0, 3), (1, 4)]
        ok, msg = validate_wall(
            graph, [0, 8], wall_edges, target_funcs, {1: 5, 2: 5}, 1
        )
        assert ok is False
        assert msg == "This wall would completely block a player's path."

    def test_crossing_wall_rejected(self):
        graph = _graph()
        # Simulate a placed horizontal wall (removes vertical edges 4-13 and 5-14),
        # then try placing a vertical wall (4-5),(13-14) which would cross it.
        graph.remove_edge(4, 13)
        graph.remove_edge(5, 14)
        wall_edges = [(4, 5), (13, 14)]
        ok, msg = validate_wall(
            graph, [4, 76], wall_edges, _target_funcs_9x9(), {1: 10, 2: 10}, 1
        )
        assert ok is False
        assert msg == "A wall already crosses this position."
