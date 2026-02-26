"""Board graph for Quoridor: cells as nodes, possible moves as edges."""

from __future__ import annotations


class Graph:
    """Game board modeled as a 4-connected grid graph."""

    def __init__(self, size: int = 9) -> None:
        self.size = size
        self.nodes = size * size
        self.adj: dict[int, list[int]] = {}
        for node in range(self.nodes):
            self.adj[node] = self._initial_neighbors(node)

    def _initial_neighbors(self, node: int) -> list[int]:
        neighbors: list[int] = []
        row, col = divmod(node, self.size)

        if row > 0:
            neighbors.append(node - self.size)
        if row < self.size - 1:
            neighbors.append(node + self.size)
        if col > 0:
            neighbors.append(node - 1)
        if col < self.size - 1:
            neighbors.append(node + 1)

        return neighbors

    def remove_edge(self, node1: int, node2: int) -> None:
        """Remove a bidirectional edge between two adjacent nodes."""
        if node1 in self.adj and node2 in self.adj[node1]:
            self.adj[node1].remove(node2)
        if node2 in self.adj and node1 in self.adj[node2]:
            self.adj[node2].remove(node1)

    def add_edge(self, node1: int, node2: int) -> None:
        """Add a bidirectional edge between two adjacent nodes."""
        if node1 not in self.adj:
            self.adj[node1] = []
        if node2 not in self.adj:
            self.adj[node2] = []

        if node2 not in self.adj[node1]:
            self.adj[node1].append(node2)
        if node1 not in self.adj[node2]:
            self.adj[node2].append(node1)
