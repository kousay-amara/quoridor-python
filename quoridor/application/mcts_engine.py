import math
import random
import time

class MCTSNode :
    def __init__(self, state, parent = None, move = None):
        self.state = state
        self.parent = parent
        self.move = move
        self.children = []
        self.wins = 0
        self.visits = 0
        self.untried_moves = state.get_legal_moves()

    def uct_select_child(self, exploration_weight = 1.41):
        """Choose a child using UCT Formula"""
        return max(self.children, key=lambda c: (c.wins / c.visits) + exploration_weight * math.sqrt(math.log(self.visits) / c.visits))
    

def mcts_search(root_state, time_limit = 5.0):
    """Perform MCTS search"""
    root_node = MCTSNode(root_state)
    start_time = time.time()

    while time.time() - start_time < time_limit:
        node = root_node

        #Sélection
        while not node.untried_moves and node.children :
            node = node.uct_select_child()

        #Expansion
        if node.untried_moves:
            move = random.choice(node.untried_moves)
            node.untried_moves.remove(move)
            new_state = node.state.apply_move(move)
            child_node = MCTSNode(state=new_state, parent=node, move=move)
            node.children.append(child_node)
            node = child_node

        #Simulation
        current_rollout_state = node.state
        while not current_rollout_state.is_terminal() :
            possible_moves = current_rollout_state.get_legal_moves()
            current_rollout_state = current_rollout_state.apply_move(random.choice(possible_moves))

        #Backpropagation
        result = current_rollout_state.get_winner_result()
        while node is not None :
            node.visits += 1
            node.wins += result
            node = node.parent

    return max(root_node.children, key=lambda c: c.visits).move
        