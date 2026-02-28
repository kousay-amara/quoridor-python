"""Pathfinding algorithms for Quoridor rules."""

from __future__ import annotations

from collections import deque


def has_path(
    graph,
    node: int,
    target_row: int | None = None,
    target_col: int | None = None,
) -> bool:
    """BFS to find a valid path from a node to a target row or column."""
    visited = {node}
    queue = deque([node])

    while queue:
        curr = queue.popleft()
        curr_row, curr_col = divmod(curr, graph.size)
        if target_row is not None and curr_row == target_row:
            return True
        if target_col is not None and curr_col == target_col:
            return True

        for neighbor in graph.adj[curr]:
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
