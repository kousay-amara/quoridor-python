from ..utils.graph import Graph
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..rules.wall_rules import is_wall_legal


def validate_pawn_move(
    graph: Graph, from_node, to_node, all_positions, board_size
):
    legal = get_all_legal_pawn_moves(graph, from_node, all_positions)
    if to_node in legal:
        return True, None
    if to_node not in graph.adj:
        return False, "This cell does not exist on the board."
    if to_node in all_positions:
        return False, "This cell is occupied by another player."

    # Distinguish a direct wall collision from a generally unreachable
    # move to provide a clearer CLI error message.
    diff = abs(from_node - to_node)
    same_row = from_node // board_size == to_node // board_size
    naturally_adjacent = (diff == 1 and same_row) or diff == board_size

    if naturally_adjacent:
        return False, "A wall is blocking that move."
    return False, "This move is not reachable from your position."


def _has_crossing_wall(graph, wall_edges):
    (a, b), (c, d) = wall_edges
    cross1_missing = c not in graph.adj.get(a, [])
    cross2_missing = d not in graph.adj.get(b, [])
    return cross1_missing and cross2_missing


def validate_wall(
    graph: Graph,
    player_positions,
    wall_edges,
    target_funcs,
    remaining_walls,
    current_player,
):
    walls_left = remaining_walls.get(current_player, 0)
    if walls_left == 0:
        return False, "You have no walls left."
    for n1, n2 in wall_edges:
        if n2 not in graph.adj.get(n1, []):
            return False, "A wall already exists there."
    if _has_crossing_wall(graph, wall_edges):
        return False, "A wall already crosses this position."    
    if not is_wall_legal(graph, player_positions, wall_edges, target_funcs):
        return False, "This wall would completely block a player's path."
    return True, None
