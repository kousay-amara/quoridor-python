import math
import random
import time

from quoridor.application.ai_logic import get_all_legal_moves, clone_state, apply_move
from quoridor.rules.win_rules import has_player_won

class MCTSNode :
    def __init__(self, state, parent = None, move = None):
        self.state = state
        self.parent = parent
        self.move = move
        self.children = []
        self.wins = 0
        self.visits = 0
        self.untried_moves = get_all_legal_moves(state)

    def uct_select_child(self, exploration_weight = 1.41):
        """Choose a child using UCT Formula"""
        return max(self.children, key=lambda c: (c.wins / c.visits) + exploration_weight * math.sqrt(math.log(self.visits) / c.visits))

def check_any_winner(state):
    """
    Check if any player won.
    """
    for p_id in state.active_player_ids():
        pos = state.player_positions.get(p_id)
        if pos is not None and has_player_won(p_id, pos, state.board_size):
            return p_id
    return None 


def mcts_search(root_state, time_limit = 5.0):
    """Perform MCTS search"""
    root_node = MCTSNode(root_state)
    ai_player_id = root_state.current_player
    start_time = time.time()

    while time.time() - start_time < time_limit:
        node = root_node

        #Selection
        while not node.untried_moves and node.children :
            node = node.uct_select_child()

        #Expansion
        if node.untried_moves:
            move = random.choice(node.untried_moves)
            node.untried_moves.remove(move)
            new_state = clone_state(node.state)
            apply_move(new_state, move)   
            child_node = MCTSNode(state=new_state, parent=node, move=move)
            node.children.append(child_node)
            node = child_node

        #Simulation
        rollout_state = clone_state(node.state)
        max_moves = 300 #Security against infinites games
        winner = None

        while max_moves > 0:
            winner = check_any_winner(rollout_state)
            if winner is not None:
                break
            
            moves = get_all_legal_moves(rollout_state)
            if not moves:
                break
            
            apply_move(rollout_state, random.choice(moves))
            max_moves -= 1

        #Backpropagation
        result = 1 if winner == ai_player_id else 0
        temp_node = node
        while temp_node is not None:
            temp_node.visits += 1
            temp_node.wins += result
            temp_node = temp_node.parent

    if not root_node.children:
        legal_moves = get_all_legal_moves(root_state)
        return random.choice(legal_moves) if legal_moves else None
        
    return max(root_node.children, key=lambda c: c.visits).move
        