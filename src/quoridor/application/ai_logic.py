from ..core.game_state import GameState
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..rules.wall_rules import get_all_legal_wall_placements
from ..rules.wall_rules import get_player_target_funcs
from utils.graph import get_shortest_path_length

SCORING_DEFAULT = 1
SCORING_MATERIAL = 2
SCORING_HYBRID = 3

def get_all_legal_moves(state : GameState) : 
    moves = []
    current_id = state.current_player
    current_pos = state.player_positions[current_id]
    all_pos = list(state.player_positions.values())

    pawn_moves = get_all_legal_pawn_moves(
        state.graph, 
        current_pos,
        all_pos
    )

    for target in pawn_moves :
        moves.append(('pawn', target))

    if state.remaining_walls.get(current_id, 0) > 0 :
        moves.extend(get_all_legal_wall_placements(state))
    
    return moves


def clone_state(state : GameState) -> GameState :
    """Create an independant copy of the current state"""
    return GameState.from_snapshot(state.to_snapshot())

def apply_move(state: GameState, move: tuple) -> None:
    move_type = move[0]
    
    if move_type == 'pawn':
        state.player_positions[state.current_player] = move[1]
    
    elif move_type == 'wall':
        edges, orientation = move[1], move[2]
        
        if orientation == 'horizontal':
            state.horizontal_walls.extend(edges)
        else:
            state.vertical_walls.extend(edges)
        
        state.remaining_walls[state.current_player] -= 1
    
    state._rebuild_graph()
    
    #Passer au joueur suivant
    pids = sorted(state.player_positions.keys())
    idx = pids.index(state.current_player)
    state.current_player = pids[(idx + 1) % len(pids)]


def evaluate_state(state: GameState, ai_player_id: int, scoring_type: int = SCORING_DEFAULT) -> float :
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
    player_ids = sorted(state.player_positions.keys())
    targets = get_player_target_funcs(state.board_size, player_ids)
    
    distances = {}
    for i, pid in enumerate(player_ids):
        pos = state.player_positions[pid]
        dist = get_shortest_path_length(state.graph, pos, targets[i])
        distances[pid] = dist

    opponent_id = [pid for pid in player_ids if pid != ai_player_id][0]
    
    score = distances[opponent_id] - distances[ai_player_id]
    
    score += (state.remaining_walls[ai_player_id] - state.remaining_walls[opponent_id]) * 0.5
    
    return float(score)


def evaluate_state_material(state: GameState, ai_player_id: id) -> float:
    """
    Second heurisrtic, focused on maintaining the walls and blocking the opposing team.
    """
    player_ids = sorted(state.player_positions.keys())
    targets = get_player_target_funcs(state.board_size, player_ids)
    opponent_id = [pid for pid in player_ids if pid != ai_player_id[0]]

    my_pos = state.player_positions[ai_player_id]
    opp_pos = state.player_positions[opponent_id]

    my_dist = get_shortest_path_length(state.graph, my_pos, targets[player_ids.index(ai_player_id)])
    opp_dist = get_shortest_path_length(state.graph, opp_pos, targets[player_ids.index(opponent_id)])

    my_walls = state.remaining_walls[ai_player_id]
    opp_walls = state.remaining_walls[opponent_id]
    wall_diff = my_walls - opp_walls

    if my_dist >= 999: return -1000.0
    if opp_dist >= 999: return 1000.0

    score = (opp_dist * 1.5) - (my_dist * 0.5) + (wall_diff * 2.0)
    
    return float(score)


def evaluate_state_hybrid(state: GameState, ai_player_id: id) -> float:
    """
    Third heuristic, a balanced mix of distance, remaining walls, and center control.
    Reduce the risk to being blocked by one oponent's wall. Try to control the center and maximise oportunities.
    """
    player_ids = sorted(state.player_positions.keys())
    targets = get_player_target_funcs(state.board_size, player_ids)
    opponent_id = [pid for pid in player_ids if pid != ai_player_id][0]

    my_dist = get_shortest_path_length(state.graph, state.player_positions[ai_player_id], targets[player_ids.index(ai_player_id)])
    opp_dist = get_shortest_path_length(state.graph, state.player_positions[opponent_id], targets[player_ids.index(opponent_id)])
    
    if my_dist >= 999: return -1000.0
    if opp_dist >= 999: return 1000.0

    center = state.board_size // 2
    my_col = state.player_positions[ai_player_id] % state.board_size

    centrality_bonus = -abs(my_col - center) * 0.2

    wall_bonus = (state.remaining_walls[ai_player_id] - state.remaining_walls[opponent_id]) * 0.3

    score = (opp_dist * 2.0) - (my_dist * 1.0) + centrality_bonus + wall_bonus

    return float(score)
