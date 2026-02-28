import pytest
from src.quoridor.core.game_state import GameState
from src.quoridor.application.ai_logic import evaluate_state

def test_evaluation_start_is_neutral():
    pos = {1: 4, 2: 76}
    state = GameState(9, 1, pos, {1: 10, 2: 10})
    
    score = evaluate_state(state, ai_player_id=1)
    assert score == 0.0

def test_evaluation_advancement():
    pos_initial = {1: 4, 2: 76}
    state_start = GameState(9, 1, pos_initial, {1: 10, 2: 10})
    
    pos_advanced = {1: 13, 2: 76}
    state_adv = GameState(9, 1, pos_advanced, {1: 10, 2: 10})
    
    assert evaluate_state(state_adv, 1) > evaluate_state(state_start, 1)

def test_wall_advantage():
    pos = {1: 4, 2: 76}
    state = GameState(9, 1, pos, {1: 10, 2: 5})
    
    assert evaluate_state(state, 1) > 0