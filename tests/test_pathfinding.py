from __future__ import annotations

from quoridor.rules.pathfinding import has_path
from quoridor.utils.graph import Graph


def test_has_path_reaches_target_row_on_grid():
    graph = Graph(size=3)
    # Node 0 is at row 0; target row 2 is reachable on a normal grid.
    assert has_path(graph, node=0, target_row=2) is True


def test_has_path_reaches_target_col_on_grid():
    graph = Graph(size=3)
    # Node 0 is at col 0; target col 2 is reachable on a normal grid.
    assert has_path(graph, node=0, target_col=2) is True


def test_has_path_returns_false_when_target_row_unreachable():
    graph = Graph(size=3, build_grid=False)
    # Keep a connected component that cannot reach row 2.
    graph.adj = {
        0: [1],
        1: [0, 4],
        4: [1],
    }
    assert has_path(graph, node=0, target_row=2) is False


def test_has_path_returns_false_when_target_col_unreachable():
    graph = Graph(size=3, build_grid=False)
    # Keep a connected component that cannot reach col 2.
    graph.adj = {
        0: [3],
        3: [0, 6],
        6: [3],
    }
    assert has_path(graph, node=0, target_col=2) is False
