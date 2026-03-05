"""Board graph for Quoridor: cells as nodes, possible moves as edges."""

from ..utils.graph import Graph


class QuoridorBoard:
    """Game board modelled as a 4-connected grid graph."""

    def __init__(self, size: int = 9):
        self.size = size
        self.graph = Graph()
        self.adj = self.graph.adj
        self._build_grid()

    def _build_grid(self):
        for r in range(self.size):
            for c in range(self.size):
                node = r * self.size + c
                if c < self.size - 1:
                    self.graph.add_edge(node, node + 1)
                if r < self.size - 1:
                    self.graph.add_edge(node, node + self.size)
