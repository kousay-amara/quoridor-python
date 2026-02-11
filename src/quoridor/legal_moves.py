def is_walk_legal(graph, from_node: int, to_node: int) -> bool:
        """
        Check whether a pawn move is legal (no wall between the two cells).

        Args:
            from_node: Starting cell (index 0..nodes-1).
            to_node: Destination cell.

        Returns:
            True if to_node is adjacent to from_node in the current graph (move allowed).
        """
        if from_node < 0 or from_node >= graph.nodes or to_node < 0 or to_node >= graph.nodes:
            return False
        return to_node in graph.adj[from_node]


def is_wall_legal(
    graph,
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
            player_targets = [(graph.size - 1, None), (0, None)]
        elif n == 4:
            player_targets = [
                (graph.size - 1, None),
                (0, None),
                (None, graph.size - 1),
                (None, 0),
            ]
        else:
            player_targets = [(graph.size - 1, None)] * n

    for (n1, n2) in wall_edges:
        if n1 not in graph.adj or n2 not in graph.adj.get(n1, []):
            return False

    backup = {i: list(neighbors) for i, neighbors in graph.adj.items()}

    for (n1, n2) in wall_edges:
        graph.remove_edge(n1, n2)

    try:
        for i, pos in enumerate(player_positions):
            if i >= len(player_targets):
                break
            target_row, target_col = player_targets[i]
            if not graph.has_path(pos, target_row=target_row, target_col=target_col):
                return False
        return True
    finally:
        graph.adj = backup


    

def get_all_legal_pawn_moves(graph, player_pos : int, all_players_pos : list[int]) -> list[int]:
    """
    Return every legal moves for un pawn
    simple moves, jumps and diagonal jumps
    """

    legal_moves = []
    opponents_pos = [p for p in all_players_pos if p != player_pos]

    for neighbor in graph.adj.get(player_pos, []):
        if neighbor not in opponents_pos:
            legal_moves.append(neighbor)
        else :
            diff = neighbor - player_pos
            jump_target = neighbor + diff

            row_n, col_n = divmod(neighbor, graph.size)
            row_t, col_t = divmod(jump_target, graph.size)

            is_same_axis = (row_n == row_t or col_n == col_t)
            in_bounds = 0 <= jump_target < graph.nodes

            if in_bounds and is_same_axis and jump_target in graph.adj.get(neighbor, []):
                if jump_target not in opponents_pos:
                    legal_moves.append(jump_target)

            else :
                for lateral in graph.adj.get(neighbor, []):
                    if lateral != player_pos and lateral not in opponents_pos:
                        legal_moves.append(lateral)
    
    return list(set(legal_moves))