import math
import random
import time

from quoridor.application.ai_logic import (
    apply_move,
    clone_state,
    get_all_legal_moves,
)
from quoridor.rules.win_rules import has_player_won


class MCTSNode:
    def __init__(self, state, parent=None, move=None):
        self.state = state
        self.parent = parent
        self.move = move
        self.children = []
        self.wins = 0
        self.visits = 0

        all_moves = get_all_legal_moves(state)
        self.untried_moves = sorted(
            all_moves,
<<<<<<< HEAD
            key=lambda m: 0 if getattr(m, 'action', '') == 'move_pawn' else 1
=======
            key=lambda move: 0 if move[0] == "pawn" else 1,
>>>>>>> 3c4ae1366b9e9c3bff00e91d68540497a8f2e371
        )

    def uct_select_child(self, exploration_weight):
        """Choose a child using UCT Formula"""
        return max(
            self.children,
            key=lambda c: (c.wins / c.visits)
            + exploration_weight * math.sqrt(math.log(self.visits) / c.visits),
        )


def _pawn_goal_distance(player_id, node_index, board_size):
    """Return a simple row distance from a pawn to its goal side."""
    row = node_index // board_size
    if player_id == 1:
        target_row = board_size - 1
    else:
        target_row = 0
    return abs(target_row - row)


def check_any_winner(state):
    """
    Check if any player won.
    """
    for p_id in state.active_player_ids():
        pos = state.player_positions.get(p_id)
        if pos is not None and has_player_won(p_id, pos, state.board_size):
            return p_id
    return None


def mcts_search(root_state, time_limit=5.0, exploration_weight=1.41):
    """Perform MCTS search"""
    root_node = MCTSNode(root_state)
    start_time = time.time()

    while time.time() - start_time < time_limit:
        node = root_node

        # Selection
        while not node.untried_moves and node.children:
            node = node.uct_select_child(exploration_weight=exploration_weight)

        # Expansion
        if node.untried_moves:
            move = random.choice(node.untried_moves)
            node.untried_moves.remove(move)
            new_state = clone_state(node.state)
            apply_move(new_state, move)
            child_node = MCTSNode(state=new_state, parent=node, move=move)
            node.children.append(child_node)
            node = child_node

        # Simulation
        rollout_state = clone_state(node.state)
        max_moves = 300  # Security against infinite games
        winner = None

        while max_moves > 0:
            moves = get_all_legal_moves(rollout_state)
            if not moves:
                break

            p_id = rollout_state.current_player
            b_size = rollout_state.board_size

            pawn_moves = [move for move in moves if move[0] == "pawn"]

            if pawn_moves and random.random() < 0.7:
<<<<<<< HEAD
                best_dist = min(get_dist_to_goal(p_id, m.to_pos, b_size) for m in pawn_moves)
                best_moves = [m for m in pawn_moves if get_dist_to_goal(p_id, m.to_pos, b_size) == best_dist]
                move_to_apply = random.choice(best_moves)
            else:
                move_to_apply = random.choice(moves)

=======
                move_to_apply = min(
                    pawn_moves,
                    key=lambda move: _pawn_goal_distance(
                        p_id,
                        move[1],
                        b_size,
                    ),
                )
            else:
                move_to_apply = random.choice(moves)
            
>>>>>>> 3c4ae1366b9e9c3bff00e91d68540497a8f2e371
            apply_move(rollout_state, move_to_apply)
            max_moves -= 1

            winner = check_any_winner(rollout_state)
            if winner is not None:
                break

        # Backpropagation
        temp_node = node
        while temp_node is not None:
            temp_node.visits += 1
            node_player = temp_node.state.current_player
            temp_node.wins += 1 if winner == node_player else 0
            temp_node = temp_node.parent

    if not root_node.children:
        legal_moves = get_all_legal_moves(root_state)
        return random.choice(legal_moves) if legal_moves else None

<<<<<<< HEAD
    return max(root_node.childrens, key=lambda c: c.visits).move
=======
    return max(root_node.children, key=lambda c: c.visits).move
>>>>>>> 3c4ae1366b9e9c3bff00e91d68540497a8f2e371
