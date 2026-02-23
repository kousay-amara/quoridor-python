"""Wall placement legality rules for Quoridor."""

from __future__ import annotations
from typing import Callable, List, Tuple
from src.utils.algorithms import bfs_has_path


def is_wall_legal(graph, 
    player_positions: List[int], 
    wall_edges: List[Tuple[int, int]], 
    player_target_funcs: List[Callable[[int], bool]]
) -> bool:
    """Check whether placing a wall is legal (no player is blocked)."""
    for (n1, n2) in wall_edges:
        graph.remove_edge(n1, n2)

    try:
        for i, pos in enumerate(player_positions):
            is_at_target = player_target_funcs[i]
            
            if not bfs_has_path(graph, pos, is_at_target):
                return False 
        
        return True 
        
    finally:
        for (n1, n2) in wall_edges:
            graph.add_edge(n1, n2)