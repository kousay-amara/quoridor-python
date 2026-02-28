from ..core.game_state import GameState
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..rules.wall_rules import get_all_legal_wall_placements

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