"""
Board graph for Quoridor: cells as nodes, possible moves as edges.

Walls are represented by the absence of an edge between two adjacent cells.
"""

from collections import deque
from legal_moves import get_all_legal_pawn_moves
from player import Player
import pathfiding


class Graph:
    """
    Game board modelled as a graph (4-connected grid).

    Attributes:
        size: Board side length (size x size grid).
        nodes: Number of cells (size * size).
        adj: Dictionary mapping each node (int) to the list of its reachable
            neighbors (no wall between them).
    """

    def __init__(self, size=9):
        """
        Initialize the board as a graph.

        Args:
            size: Board side length (default 9, 9x9 grid).
        """
        self.size = size
        self.nodes = size * size
        self.adj = {}
        for i in range(self.nodes):
            self.adj[i] = self.get_initial_neighbors(i)

    def get_initial_neighbors(self, node):
        """
        Compute the neighbors of a cell with no walls (4-connected grid).

        Args:
            node: Node index (0..nodes-1).

        Returns:
            List of neighboring nodes (up, down, left, right depending on bounds).
        """
        neighbors = []
        row, col = divmod(node, self.size)

        if row > 0 : neighbors.append(node - self.size)
        if row < self.size - 1 : neighbors.append(node + self.size)
        if col > 0 : neighbors.append(node - 1)
        if col < self.size - 1 : neighbors.append(node + 1)

        return neighbors
    
    def remove_edge(self, node1, node2):
        """
        Remove the link between two cells (place a wall between them).

        Args:
            node1: First cell.
            node2: Second cell (must be adjacent to node1).
        """
        if node2 in self.adj[node1] :
            self.adj[node1].remove(node2)
        
        if node1 in self.adj[node2] :
            self.adj[node2].remove(node1)

    def add_edge(self, node1, node2):
        """
        Add a link between two cells
        
        Args:
            node1 : First cell.
            node2 : Second cell.
        """
        if node2 not in self.adj[node1]:
            self.adj[node1].append(node2)

        if node1 not in self.adj[node2] :
            self.adj[node2].append(node1)


"""Quelques tests temporaires"""
player = Player(1, 5, 8, None, 10)
graph = Graph()
graph.remove_edge(9, 0)
graph.remove_edge(1,10)
graph.remove_edge(9, 18)
graph.remove_edge(10, 11)
print(get_all_legal_pawn_moves(graph, 9, [10]))