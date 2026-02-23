"""Pawn movement rules for Quoridor."""

from __future__ import annotations


def is_walk_legal(graph, from_node: int, to_node: int) -> bool:
    """Check whether a pawn move is legal in the current graph."""
    if from_node not in graph.adj or to_node not in graph.adj:
        return False
    return to_node in graph.adj[from_node]


def get_all_legal_pawn_moves(
    graph,
    player_pos: int,
    all_players_pos: list[int],
) -> list[int]:
    """Return all legal pawn moves: simple, jump, diagonal jump."""
    legal_moves: list[int] = []
    opponents_pos = [p for p in all_players_pos if p != player_pos]

    for neighbor in graph.adj.get(player_pos, []):
        if neighbor not in opponents_pos:
            legal_moves.append(neighbor)
        else:
            diff = neighbor - player_pos
            jump_target = neighbor + diff

            if jump_target in graph.adj.get(neighbor, []):
                if jump_target not in opponents_pos:
                    legal_moves.append(jump_target)
                else:
                    # Cas très rare : deux adversaires à la suite, on ne peut pas sauter
                    pass
            else:
                # 3. Saut diagonal (si le saut direct est bloqué par un mur ou bord)
                for lateral in graph.adj.get(neighbor, []):
                    if lateral != player_pos and lateral not in opponents_pos:
                        legal_moves.append(lateral)

    return list(set(legal_moves))
