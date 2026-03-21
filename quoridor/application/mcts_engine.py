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
            key=lambda move: 0 if move[0] == "pawn" else 1,
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


def mcts_search(root_state, time_limit=5.0, exploration_weight = 1.41):
    """Perform MCTS search"""
    root_node = MCTSNode(root_state)
    ai_player_id = root_state.current_player
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
        max_moves = 300  # Security against infinites games
        winner = None

        while max_moves > 0:
            winner = check_any_winner(rollout_state)
            if winner is not None:
                break

            moves = get_all_legal_moves(rollout_state)
            if not moves:
                break

            p_id = rollout_state.current_player
            b_size = rollout_state.board_size

            pawn_moves = [move for move in moves if move[0] == "pawn"]

            if pawn_moves and random.random() < 0.7:
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
            
            apply_move(rollout_state, move_to_apply)
            max_moves -= 1

        # Backpropagation
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
