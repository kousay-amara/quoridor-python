from ..core.game_state import GameState
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..rules.wall_rules import get_all_legal_wall_placements
from ..rules.wall_rules import get_player_target_funcs
from ..utils.graph import get_shortest_path_length

SCORING_DEFAULT = 1
SCORING_MATERIAL = 2
SCORING_HYBRID = 3


def get_all_legal_moves(state: GameState):
    moves = []
    current_id = state.current_player
    if not state.is_player_active(current_id):
        return moves
    current_pos = state.player_positions[current_id]
    all_pos = list(state.player_positions.values())

    pawn_moves = get_all_legal_pawn_moves(state.graph, current_pos, all_pos)

    for target in pawn_moves:
        moves.append(("pawn", target))

    if state.remaining_walls.get(current_id, 0) > 0:
        moves.extend(get_all_legal_wall_placements(state))

    return moves


def clone_state(state: GameState) -> GameState:
    """Create an independant copy of the current state"""
    return GameState.from_snapshot(state.to_snapshot())


def apply_move(state: GameState, move: tuple) -> None:
    move_type = move[0]

    if move_type == "pawn":
        state.player_positions[state.current_player] = move[1]

    elif move_type == "wall":
        edges, orientation = move[1], move[2]

        if orientation == "horizontal":
            state.horizontal_walls.extend(edges)
        else:
            state.vertical_walls.extend(edges)

        #for edge in edges:
            #state.graph.remove_edge(*edge)

        state.remaining_walls[state.current_player] -= 1

    state._rebuild_graph()

    # Passer au joueur suivant
    active_players = state.active_player_ids()
    if not active_players:
        return
    if len(active_players) == 1:
        state.current_player = active_players[0]
        return

    pids = sorted(state.player_positions.keys())
    idx = pids.index(state.current_player)
    for offset in range(1, len(pids) + 1):
        next_player = pids[(idx + offset) % len(pids)]
        if next_player in active_players:
            state.current_player = next_player
            return

    state.current_player = active_players[0]


def evaluate_state(
    state: GameState, ai_player_id: int, scoring_type: int = SCORING_DEFAULT
) -> float:
    """
    Évalue l'état selon le mode choisi via --ai-minimax-scoring.
    """

    if scoring_type == SCORING_MATERIAL:
        return evaluate_state_material(state, ai_player_id)

    elif scoring_type == SCORING_HYBRID:
        return evaluate_state_hybrid(state, ai_player_id)

    return evaluate_state_default(state, ai_player_id)


"""
The three next fonctions are heuristics for AI.
They return a note for a state for AI POV.
Highest is the score, better is the position
"""


def evaluate_state_default(state: GameState, ai_player_id: int) -> float:
    """
    First heuristic, based on the distance from players to their target and the number of remaining wall
    """
    player_ids = state.active_player_ids()
    if ai_player_id not in player_ids:
        return -1000.0
    if len(player_ids) == 1:
        return 1000.0
    targets = get_player_target_funcs(state.board_size, player_ids)

    my_dist = get_shortest_path_length(state.graph, state.player_positions[ai_player_id], targets[player_ids.index(ai_player_id)])
    opp_distances = [get_shortest_path_length(state.graph, state.player_positions[p], targets[i]) 
                     for i, p in enumerate(player_ids) if p != ai_player_id]
    min_opp_dist = min(opp_distances)

    if my_dist == 0: return 1000.0
    if min_opp_dist == 0: return -1000.0   
    if my_dist >= 999: return -1000.0

    score = min_opp_dist - my_dist

    wall_weight = 0.5 if len(player_ids) == 2 else 0.3
    my_walls = state.remaining_walls[ai_player_id]
    average_opp_walls = sum(
        state.remaining_walls[p] for p in player_ids if p != ai_player_id
    ) / (len(player_ids) - 1)
    wall_diff = my_walls - average_opp_walls

    score += wall_diff * wall_weight

    return float(score)


def evaluate_state_material(state: GameState, ai_player_id: int) -> float:
    """
    Second heurisrtic, focused on maintaining the walls and blocking the opposing team.
    """
    player_ids = state.active_player_ids()
    if ai_player_id not in player_ids:
        return -1000.0
    if len(player_ids) == 1:
        return 1000.0
    targets = get_player_target_funcs(state.board_size, player_ids)
    
    my_dist = get_shortest_path_length(state.graph, state.player_positions[ai_player_id], targets[player_ids.index(ai_player_id)])
    opponents_dist = [get_shortest_path_length(state.graph, state.player_positions[p], targets[i]) 
                      for i, p in enumerate(player_ids) if p != ai_player_id]
    min_opp_dist = min(opponents_dist)

    if my_dist == 0: return 1000.0
    if min_opp_dist == 0: return -1000.0
    if my_dist >= 999: return -1000.0

    score = (min_opp_dist * 2.0) - my_dist

    wall_weight = 2.0 if len(player_ids) == 2 else 1.2
    
    my_walls = state.remaining_walls[ai_player_id]
    max_opp_walls = max(state.remaining_walls[p] for p in player_ids if p != ai_player_id)
    wall_diff = my_walls - max_opp_walls

    score += wall_diff * wall_weight

    return float(score)


def evaluate_state_hybrid(state: GameState, ai_player_id: int) -> float:
    """
    Third heuristic, a balanced mix of distance, remaining walls, and center control.
    Reduce the risk to being blocked by one oponent's wall. Try to control the center and maximise oportunities.
    """
    player_ids = state.active_player_ids()
    if ai_player_id not in player_ids:
        return -1000.0
    if len(player_ids) == 1:
        return 1000.0
    targets = get_player_target_funcs(state.board_size, player_ids)

    my_dist = get_shortest_path_length(state.graph, state.player_positions[ai_player_id], targets[player_ids.index(ai_player_id)])
    opp_distances = [get_shortest_path_length(state.graph, state.player_positions[p], targets[i]) 
                     for i, p in enumerate(player_ids) if p != ai_player_id]
    min_opp_dist = min(opp_distances)

    if my_dist == 0: return 1000.0
    if min_opp_dist == 0: return -1000.0
    if my_dist >= 999: return -1000.0

    center = state.board_size // 2
    my_pos = state.player_positions[ai_player_id]
    my_row, my_col = divmod(my_pos, state.board_size)
    dist_to_center = abs(my_row - center) + abs(my_col - center)
    
    centrality_bonus = -dist_to_center * 0.15
    my_walls = state.remaining_walls[ai_player_id]
    opp_walls_avg = sum(state.remaining_walls[p] for p in player_ids if p != ai_player_id) / (len(player_ids) - 1)

    current_wall_weight = 0.4 if my_walls > 2 else 0.8
    
    score = (min_opp_dist * 2.5) - (my_dist * 1.5) + centrality_bonus + ((my_walls - opp_walls_avg) * current_wall_weight)
    return float(score)
