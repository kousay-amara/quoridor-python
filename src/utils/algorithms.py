"""Simple generic BFS"""
from collections import deque

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