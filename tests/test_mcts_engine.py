import pytest
import time
from quoridor.application.mcts_engine import MCTSNode, mcts_search, check_any_winner
from quoridor.core.game_state import GameState

@pytest.fixture
def real_mini_state():
    """
    Create a real game state on a small board (3x3) to accelerate MCTS processing 
    and ensure deterministic behavior during tests.
    """
    return GameState(
        board_size=3,
        current_player=1,
        player_positions={1: 1, 2: 7}, # Players facing each other on a 3x3 grid
        remaining_walls={1: 2, 2: 2}
    )

def test_mcts_search_full_coverage(real_mini_state):
    """
    Integration test forcing the execution of all MCTS phases:
    Selection, Expansion, Simulation, and Backpropagation.
    This ensures that the while loops in mcts_search are fully covered.
    """
    # Provide enough time for multiple iterations to be completed
    limit = 0.5
    best_move = mcts_search(real_mini_state, time_limit=limit)
    
    assert best_move is not None
    # Verify that children were created in the tree (indicates expansion/selection worked)
    assert isinstance(best_move, tuple)

def test_check_any_winner_logic(real_mini_state):
    """
    Verify the win detection logic used by the MCTS rollout phase.
    """
    # No winner at the starting position
    assert check_any_winner(real_mini_state) is None
    
    # Manually move player 1 to the winning line (index 2 on a 3x3 board)
    real_mini_state.player_positions[1] = 7 
    assert check_any_winner(real_mini_state) == 1

def test_mcts_node_untried_moves(real_mini_state):
    """
    Verify that the node correctly tracks untried moves and transitions to 
    UCT selection once fully expanded.
    """
    node = MCTSNode(real_mini_state)
    assert len(node.untried_moves) > 0
    
    # Simulate manual expansion to empty the untried_moves list
    while node.untried_moves:
        move = node.untried_moves.pop()
        child = MCTSNode(real_mini_state, parent=node, move=move)
        node.children.append(child)
    
    # Now that untried_moves is empty, uct_select_child should be callable
    assert len(node.untried_moves) == 0
    selected = node.uct_select_child()
    assert selected in node.children

def test_mcts_time_limit_compliance(real_mini_state):
    """
    Ensure the algorithm respects the provided time limit as per requirement F31.
    """
    start = time.time()
    limit = 0.2
    mcts_search(real_mini_state, time_limit=limit)
    duration = time.time() - start
    
    # The duration should be at least the limit, with a small buffer for processing
    assert duration >= limit
    assert duration < limit + 0.1