"""Simple graph"""

from __future__ import annotations
from collections import deque


class Graph:
    """Graph."""

    def __init__(self, size: int = 9) -> None:
        self.adj: dict[int, list[int]] = {}

    def add_node(self, node: int) -> None :
        if node not in self.adj :
            self.adj[node] = []

    def remove_edge(self, node1: int, node2: int) -> None:
        """Remove a bidirectional edge between two adjacent cells."""
        if node2 in self.adj[node1]:
            self.adj[node1].remove(node2)

        if node1 in self.adj[node2]:
            self.adj[node2].remove(node1)

    def add_edge(self, node1: int, node2: int, bidirectional : bool = True) -> None:
        """Add a bidirectional or not edge between two cells."""
        self.add_node(node1)
        self.add_node(node2)
        if node2 not in self.adj[node1]:
            self.adj[node1].append(node2)

        if bidirectional and node1 not in self.adj[node2]:
            self.adj[node2].append(node1)




"""Simple generic BFS"""
def bfs_has_path(graph, start_node, is_target_func) -> bool:
    """Give a graph, a start node and a function (ex : check_victoire_j1 = lambda node: (node // 9) == 8)"""
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