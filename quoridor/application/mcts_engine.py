import math
import random
import time

from quoridor.application.ai_logic import (
    get_all_legal_moves,
    clone_state,
    apply_move,
)
from quoridor.rules.win_rules import has_player_won
from quoridor.utils.graph import get_shortest_path_length
from quoridor.rules.wall_rules import get_all_legal_wall_placements


def get_blocking_walls(state, opponent_id):
    """Return best walls for block opponent"""

    opp_pos = state.player_positions[opponent_id]
    b_size = state.board_size

    if opponent_id == 1:
        is_target = lambda node: node // b_size == b_size - 1
    else:
        is_target = lambda node: node // b_size == 0

    current_path_len = get_shortest_path_length(state.graph, opp_pos, is_target)

    blocking = []
    for wall_move in get_all_legal_wall_placements(state):
        new_state = clone_state(state)
        apply_move(new_state, wall_move)
        new_path_len = get_shortest_path_length(new_state.graph, opp_pos, is_target)
        if new_path_len > current_path_len:
            blocking.append(wall_move)

    return blocking


def get_tree_moves(state):
    current_id = state.current_player
    if not state.is_player_active(current_id):
        return []
    current_pos = state.player_positions[current_id]
    all_pos = list(state.player_positions.values())

    from quoridor.rules.pawn_rules import get_all_legal_pawn_moves
    pawn_targets = get_all_legal_pawn_moves(state.graph, current_pos, all_pos)
    moves = [('pawn', t) for t in pawn_targets]

    if state.remaining_walls.get(current_id, 0) > 0:
        opponent_ids = [p for p in state.active_player_ids() if p != current_id]
        for opp_id in opponent_ids:
            opp_dist = get_dist_to_goal(opp_id, state.player_positions[opp_id], state.board_size)
            if opp_dist <= 5:
                blocking = get_blocking_walls(state, opp_id)
                moves += random.sample(blocking, min(3, len(blocking)))

    return moves


class MCTSNode:
    def __init__(self, state, parent=None, move=None):
        self.state = state
        self.parent = parent
        self.move = move
        self.childrens = []
        self.wins = 0
        self.visits = 0
        self.untried_moves = get_tree_moves(state)

    def uct_select_child(self, exploration_weight):
        return max(
            self.childrens,
            key=lambda c: (c.wins / c.visits)
            + exploration_weight * math.sqrt(math.log(self.visits) / c.visits),
        )


def get_dist_to_goal(player_id, pos_index, board_size):
    y = pos_index // board_size
    target_y = board_size - 1 if player_id == 1 else 0
    return abs(y - target_y)


def check_any_winner(state):
    for p_id in state.active_player_ids():
        pos = state.player_positions.get(p_id)
        if pos is not None and has_player_won(p_id, pos, state.board_size):
            return p_id
    return None


def mcts_search(root_state, time_limit=5.0, exploration_weight=1.41):
    root_node = MCTSNode(root_state)
    start_time = time.time()
    iterations = 0

    while time.time() - start_time < time_limit:
        iterations += 1
        node = root_node

        # Selection
        while not node.untried_moves and node.childrens:
            node = node.uct_select_child(exploration_weight=exploration_weight)

        # Expansion
        if node.untried_moves:
            move = random.choice(node.untried_moves)
            node.untried_moves.remove(move)
            new_state = clone_state(node.state)
            apply_move(new_state, move)
            child_node = MCTSNode(state=new_state, parent=node, move=move)
            node.childrens.append(child_node)
            node = child_node

        # Simulation
        rollout_state = clone_state(node.state)
        max_moves = 300
        winner = None

        while max_moves > 0:
            p_id = rollout_state.current_player
            b_size = rollout_state.board_size
            current_pos = rollout_state.player_positions[p_id]
            all_pos = list(rollout_state.player_positions.values())

            from quoridor.rules.pawn_rules import get_all_legal_pawn_moves
            pawn_targets = get_all_legal_pawn_moves(rollout_state.graph, current_pos, all_pos)

            if not pawn_targets:
                break

            from quoridor.utils.graph import get_shortest_path_length

            if random.random() < 0.85:
                if p_id == 1:
                    is_target = lambda node: node // b_size == b_size - 1
                else:
                    is_target = lambda node: node // b_size == 0

                best_dist = min(
                    get_shortest_path_length(rollout_state.graph, t, is_target)
                    for t in pawn_targets
                )
                best_targets = [
                    t for t in pawn_targets
                    if get_shortest_path_length(rollout_state.graph, t, is_target) == best_dist
                ]
                target = random.choice(best_targets)
            
            
            else:
                target = random.choice(pawn_targets)

            rollout_state.player_positions[p_id] = target
            max_moves -= 1

            if has_player_won(p_id, target, b_size):
                winner = p_id
                break

            pids = sorted(rollout_state.player_positions.keys())
            idx = pids.index(p_id)
            active = rollout_state.active_player_ids()
            for offset in range(1, len(pids) + 1):
                next_p = pids[(idx + offset) % len(pids)]
                if next_p in active:
                    rollout_state.current_player = next_p
                    break
        
        # Backpropagation
        temp_node = node
        while temp_node is not None:
            temp_node.visits += 1
            active = temp_node.state.active_player_ids()
            player_who_moved = next(p for p in active if p != temp_node.state.current_player)
            temp_node.wins += 1 if winner == player_who_moved else 0
            temp_node = temp_node.parent
        

    if not root_node.childrens:
        legal_moves = get_all_legal_moves(root_state)
        return random.choice(legal_moves) if legal_moves else None

    best = max(root_node.childrens, key=lambda c: c.visits)
    return best.move