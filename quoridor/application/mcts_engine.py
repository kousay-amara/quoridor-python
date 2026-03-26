import math
import random
import time

from quoridor.application.ai_logic import (
    apply_move,
    clone_state,
    get_all_legal_moves,
)
from quoridor.rules.wall_rules import get_all_legal_wall_placements
from quoridor.rules.win_rules import has_player_won
from quoridor.utils.graph import get_shortest_path_length


def _make_goal_checker(player_id, board_size):
    if player_id == 1:

        def is_target(node):
            return node // board_size == board_size - 1

    else:

        def is_target(node):
            return node // board_size == 0

    return is_target


def get_blocking_walls(state, opponent_id):
    """Return best walls for block opponent."""
    opp_pos = state.player_positions[opponent_id]
    board_size = state.board_size
    is_target = _make_goal_checker(opponent_id, board_size)
    current_path_len = get_shortest_path_length(
        state.graph,
        opp_pos,
        is_target,
    )

    blocking = []
    for wall_move in get_all_legal_wall_placements(state):
        new_state = clone_state(state)
        apply_move(new_state, wall_move)
        new_path_len = get_shortest_path_length(
            new_state.graph,
            opp_pos,
            is_target,
        )
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

    pawn_targets = get_all_legal_pawn_moves(
        state.graph,
        current_pos,
        all_pos,
    )
    moves = [("pawn", target) for target in pawn_targets]

    if state.remaining_walls.get(current_id, 0) > 0:
        opponent_ids = [
            player_id
            for player_id in state.active_player_ids()
            if player_id != current_id
        ]
        for opponent_id in opponent_ids:
            opp_dist = get_dist_to_goal(
                opponent_id,
                state.player_positions[opponent_id],
                state.board_size,
            )
            if opp_dist <= 5:
                blocking = get_blocking_walls(state, opponent_id)
                moves.extend(
                    random.sample(blocking, min(3, len(blocking)))
                )

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
            key=lambda child: (child.wins / child.visits)
            + exploration_weight
            * math.sqrt(math.log(self.visits) / child.visits),
        )


def get_dist_to_goal(player_id, pos_index, board_size):
    y = pos_index // board_size
    target_y = board_size - 1 if player_id == 1 else 0
    return abs(y - target_y)


def check_any_winner(state):
    for player_id in state.active_player_ids():
        position = state.player_positions.get(player_id)
        if position is not None and has_player_won(
            player_id,
            position,
            state.board_size,
        ):
            return player_id
    return None


def mcts_search(root_state, time_limit=5.0, exploration_weight=1.41):
    root_node = MCTSNode(root_state)
    start_time = time.time()
    iterations = 0

    while time.time() - start_time < time_limit:
        iterations += 1
        node = root_node

        while not node.untried_moves and node.childrens:
            node = node.uct_select_child(
                exploration_weight=exploration_weight
            )

        if node.untried_moves:
            move = random.choice(node.untried_moves)
            node.untried_moves.remove(move)
            new_state = clone_state(node.state)
            apply_move(new_state, move)
            child_node = MCTSNode(state=new_state, parent=node, move=move)
            node.childrens.append(child_node)
            node = child_node

        rollout_state = clone_state(node.state)
        max_moves = 300
        winner = None

        while max_moves > 0:
            player_id = rollout_state.current_player
            board_size = rollout_state.board_size
            current_pos = rollout_state.player_positions[player_id]
            all_pos = list(rollout_state.player_positions.values())

            from quoridor.rules.pawn_rules import get_all_legal_pawn_moves

            pawn_targets = get_all_legal_pawn_moves(
                rollout_state.graph,
                current_pos,
                all_pos,
            )
            if not pawn_targets:
                break

            if random.random() < 0.85:
                is_target = _make_goal_checker(player_id, board_size)
                best_dist = min(
                    get_shortest_path_length(
                        rollout_state.graph,
                        target,
                        is_target,
                    )
                    for target in pawn_targets
                )
                best_targets = [
                    target
                    for target in pawn_targets
                    if get_shortest_path_length(
                        rollout_state.graph,
                        target,
                        is_target,
                    )
                    == best_dist
                ]
                target = random.choice(best_targets)
            else:
                target = random.choice(pawn_targets)

            rollout_state.player_positions[player_id] = target
            max_moves -= 1

            if has_player_won(player_id, target, board_size):
                winner = player_id
                break

            player_ids = sorted(rollout_state.player_positions.keys())
            index = player_ids.index(player_id)
            active_players = rollout_state.active_player_ids()
            for offset in range(1, len(player_ids) + 1):
                next_player = player_ids[(index + offset) % len(player_ids)]
                if next_player in active_players:
                    rollout_state.current_player = next_player
                    break

        temp_node = node
        while temp_node is not None:
            temp_node.visits += 1
            active_players = temp_node.state.active_player_ids()
            player_who_moved = next(
                player_id
                for player_id in active_players
                if player_id != temp_node.state.current_player
            )
            temp_node.wins += 1 if winner == player_who_moved else 0
            temp_node = temp_node.parent

    if not root_node.childrens:
        legal_moves = get_all_legal_moves(root_state)
        return random.choice(legal_moves) if legal_moves else None

    best = max(root_node.childrens, key=lambda child: child.visits)
    return best.move
