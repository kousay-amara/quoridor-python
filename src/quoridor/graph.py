"""
Board graph for Quoridor: cells as nodes, possible moves as edges.

Walls are represented by the absence of an edge between two adjacent cells.
"""

from collections import deque


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


    def has_path(self, node, target_row = None, target_col = None):
        """
        BFS to find a valid path from a node to a winning row or column.

        Starts from the given node and searches for target_row and/or target_col
        (2 or 4 player mode). At each visited node, checks if the winning row
        or column is reached.

        Args:
            node: Starting node.
            target_row: Row to reach (None to ignore).
            target_col: Column to reach (None to ignore).

        Returns:
            True if a path to the target exists, False otherwise.
        """
        visited = {node}
        queue = deque([node])

        while queue :
            curr = queue.popleft()
            curr_row, curr_col = divmod(curr, self.size)
            if target_row is not None and curr_row == target_row :
                return True
            if target_col is not None and curr_col == target_col :
                return True

            for neighbor in self.adj[curr]:
                if neighbor not in visited :
                    visited.add(neighbor)
                    queue.append(neighbor)
    
        return False

    def is_walk_legal(self, from_node: int, to_node: int) -> bool:
        """
        Check whether a pawn move is legal (no wall between the two cells).

        Args:
            from_node: Starting cell (index 0..nodes-1).
            to_node: Destination cell.

        Returns:
            True if to_node is adjacent to from_node in the current graph (move allowed).
        """
        if from_node < 0 or from_node >= self.nodes or to_node < 0 or to_node >= self.nodes:
            return False
        return to_node in self.adj[from_node]

    def is_wall_legal(
        self,
        player_positions: list[int],
        wall_edges: list[tuple[int, int]],
        player_targets: list[tuple[int | None, int | None]] | None = None,
    ) -> bool:
        """
        Check whether placing a wall is legal (no player must be blocked).

        Simulates removing the wall edges, checks that each player can still
        reach their winning row/column (BFS), then restores the graph. Does not
        modify the graph on success: the caller must call remove_edge for each
        wall edge to apply it.

        Args:
            player_positions: List of current player cell indices [pos0, pos1, ...].
            wall_edges: List of edges to block by the wall, e.g. [(node1, node2)].
            player_targets: For each player, (target_row, target_col) with one None.
                If None: 2 players -> (row 8, row 0), 4 players -> (row 8, row 0, col 8, col 0).

        Returns:
            True if placing the wall is legal (all players keep a path).

        Algorithm:
            1. Determine default targets if needed (2 players: rows 8 and 0;
               4 players: rows 8 and 0, cols 8 and 0).
            2. Check that each wall edge exists (actual link between two cells).
            3. Save the board (copy of adjacency lists).
            4. Temporarily remove the wall edges.
            5. For each player, check that a path to their target exists (BFS).
            6. Restore the board in all cases (finally).
        """
        wall_edges = list(wall_edges)
        if not wall_edges:
            return True

        n = len(player_positions)
        if player_targets is None:
            if n == 2:
                player_targets = [(self.size - 1, None), (0, None)]
            elif n == 4:
                player_targets = [
                    (self.size - 1, None),
                    (0, None),
                    (None, self.size - 1),
                    (None, 0),
                ]
            else:
                player_targets = [(self.size - 1, None)] * n

        for (n1, n2) in wall_edges:
            if n1 not in self.adj or n2 not in self.adj.get(n1, []):
                return False

        backup = {i: list(neighbors) for i, neighbors in self.adj.items()}

        for (n1, n2) in wall_edges:
            self.remove_edge(n1, n2)

        try:
            for i, pos in enumerate(player_positions):
                if i >= len(player_targets):
                    break
                target_row, target_col = player_targets[i]
                if not self.has_path(pos, target_row=target_row, target_col=target_col):
                    return False
            return True
        finally:
            self.adj = backup