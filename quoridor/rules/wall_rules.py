"""Wall placement legality rules for Quoridor."""

from __future__ import annotations
from typing import Callable, List, Tuple
from ..utils.graph import bfs_has_path
from ..core.game_state import GameState
from ..core.notation import get_edges_for_wall_at


def is_wall_legal(
    graph,
    player_positions: List[int],
    wall_edges: List[Tuple[int, int]],
    player_target_funcs: List[Callable[[int], bool]],
) -> bool:
    """Check whether placing a wall is legal (no player is blocked)."""
    # A wall cannot be placed on already removed edges.
    for n1, n2 in wall_edges:
        if n1 not in graph.adj or n2 not in graph.adj[n1]:
            return False

    for n1, n2 in wall_edges:
        graph.remove_edge(n1, n2)

    try:
        for i, pos in enumerate(player_positions):
            is_at_target = player_target_funcs[i]

            if not bfs_has_path(graph, pos, is_at_target):
                return False

        return True

    finally:
        for n1, n2 in wall_edges:
            graph.add_edge(n1, n2)


def get_player_target_funcs(
    board_size: int, player_ids: list[int]
) -> list[Callable[[int], bool]]:
    """
    Return all targets for all players
    """
    targets = []
    for pid in player_ids:
        if pid == 1:
            targets.append(lambda n, s=board_size: (n // s) == s - 1)
        elif pid == 2:
            targets.append(lambda n, s=board_size: (n // s) == 0)
        elif pid == 3:
            targets.append(lambda n, s=board_size: (n % s) == s - 1)
        elif pid == 4:
            targets.append(lambda n, s=board_size: (n % s) == 0)
    return targets


def get_all_legal_wall_placements(state: GameState):
    legal_walls = []
    size = state.board_size
    player_ids = state.active_player_ids()

    targets = get_player_target_funcs(size, player_ids)
    positions = [state.player_positions[pid] for pid in player_ids]

    for r in range(size - 1):
        for c in range(size - 1):
            for orientation in ["h", "v"]:
                edges = get_edges_for_wall_at(r, c, orientation, size)

                if is_wall_legal(state.graph, positions, edges, targets):
                    legal_walls.append(("wall", edges, orientation))
    return legal_walls
