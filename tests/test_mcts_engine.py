import time

import pytest

from quoridor.application.mcts_engine import (
    MCTSNode,
    check_any_winner,
    mcts_search,
)
from quoridor.core.game_state import GameState


@pytest.fixture
def real_mini_state():
    """Create a small state to keep MCTS tests fast and deterministic."""
    return GameState(
        board_size=3,
        current_player=1,
        # Players facing each other on a 3x3 grid.
        player_positions={1: 1, 2: 7},
        remaining_walls={1: 2, 2: 2},
    )


def test_mcts_search_full_coverage(real_mini_state):
    """Execute selection/expansion/simulation/backpropagation paths."""
    limit = 0.5
    best_move = mcts_search(real_mini_state, time_limit=limit)

    assert best_move is not None
    assert isinstance(best_move, tuple)


def test_check_any_winner_logic(real_mini_state):
    """Verify winner detection used in rollout."""
    assert check_any_winner(real_mini_state) is None

    # Move player 1 to the winning row on a 3x3 board.
    real_mini_state.player_positions[1] = 7
    assert check_any_winner(real_mini_state) == 1


def test_mcts_node_untried_moves(real_mini_state):
    """Verify untried move tracking and UCT selection once expanded."""
    node = MCTSNode(real_mini_state)
    assert len(node.untried_moves) > 0

    while node.untried_moves:
        move = node.untried_moves.pop()
        child = MCTSNode(real_mini_state, parent=node, move=move)
        child.visits = 1
        node.childrens.append(child)

    node.visits = len(node.childrens) + 1

    assert len(node.untried_moves) == 0
    selected = node.uct_select_child(exploration_weight=1.414)
    assert selected in node.childrens


def test_mcts_time_limit_compliance(real_mini_state):
    """Ensure MCTS respects the provided time limit."""
    start = time.time()
    limit = 0.2
    mcts_search(real_mini_state, time_limit=limit)
    duration = time.time() - start

    assert duration >= limit
    assert duration < limit + 0.1
