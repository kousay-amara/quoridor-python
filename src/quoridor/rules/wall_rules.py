"""Wall placement legality rules for Quoridor."""

from __future__ import annotations

from .pathfinding import has_path


def is_wall_legal(
    graph,
    player_positions: list[int],
    wall_edges: list[tuple[int, int]],
    player_targets: list[tuple[int | None, int | None]] | None = None,
) -> bool:
    """Check whether placing a wall is legal (no player is blocked)."""
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
            if not has_path(graph, pos, target_row=target_row, target_col=target_col):
                return False
        return True
    finally:
        graph.adj = backup
