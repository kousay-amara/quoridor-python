"""Board graph for Quoridor: cells as nodes, possible moves as edges."""

from .graph import Graph

class QuoridorBoard:
    """Game board modelled as a 4-connected grid graph."""
    def __init__(self, size: int = 9):
        self.size = size
        self.graph = Graph(size)
