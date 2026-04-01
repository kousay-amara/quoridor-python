"""Simple graph"""

from __future__ import annotations
from collections import deque


class Graph:
    """Graph."""

    def __init__(self, size: int = 9, *, build_grid: bool = True) -> None:
        self.size = size
        self.nodes = size * size
        self.adj: dict[int, list[int]] = {}
        if build_grid:
            for i in range(self.nodes):
                self.adj[i] = self.get_initial_neighbors(i)

    def get_initial_neighbors(self, node: int) -> list[int]:
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

    def add_node(self, node: int) -> None:
        if node not in self.adj:
            self.adj[node] = []

    def remove_edge(self, node1: int, node2: int) -> None:
        """Remove a bidirectional edge between two adjacent cells."""
        if node2 in self.adj[node1]:
            self.adj[node1].remove(node2)

        if node1 in self.adj[node2]:
            self.adj[node2].remove(node1)

    def add_edge(self, node1: int, node2: int, bidirectional: bool = True) -> None:
        """Add a bidirectional or not edge between two cells."""
        self.add_node(node1)
        self.add_node(node2)
        if node2 not in self.adj[node1]:
            self.adj[node1].append(node2)

        if bidirectional and node1 not in self.adj[node2]:
            self.adj[node2].append(node1)


"""Simple generic BFS"""


def bfs_has_path(graph, start_node, is_target_func) -> bool:
    """Return whether a path reaches any node accepted by the predicate."""
    visited = {start_node}
    queue = deque([start_node])
    while queue:
        curr = queue.popleft()
        if is_target_func(curr):
            return True
        for neighbor in graph.adj.get(curr, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return False


def get_shortest_path_length(graph, start_node, is_target_func) -> int:
    """
    Return the the number of move to the shortest path for reach the target.
    Return a large value (999) if there is no path.
    """
    queue = deque([(start_node, 0)])
    visited = {start_node}

    while queue:
        curr, dist = queue.popleft()

        if is_target_func(curr):
            return dist

        for neighbor in graph.adj.get(curr, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))

    return 999


def count_connected_components(self) -> int:
    """Count the number of connected components"""
    visited = set()
    count = 0
    for node in self.adj:
        if node not in visited:
            count += 1
            stack = [node]
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    stack.extend(self.adj[curr])
    return count
