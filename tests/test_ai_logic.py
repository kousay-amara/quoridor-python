import pytest
from src.quoridor.core.game_state import GameState
from src.quoridor.application.ai_logic import get_all_legal_moves, apply_move, clone_state

def test_clone_state():
    pos = {1: 4, 2: 76}
    walls = {1: 10, 2: 10}
    state = GameState(9, 1, pos, walls)
    
    new_state = clone_state(state)
    
    assert new_state is not state  
    assert new_state.board_size == state.board_size
    assert new_state.player_positions == state.player_positions

    new_state.player_positions[1] = 5
    assert state.player_positions[1] == 4

def test_get_all_legal_moves_count():
    pos = {1: 40, 2: 4} 
    walls = {1: 10, 2: 10}
    state = GameState(9, 1, pos, walls)
    
    moves = get_all_legal_moves(state)
    
    pawn_moves = [m for m in moves if m[0] == 'pawn']
    wall_moves = [m for m in moves if m[0] == 'wall']
    
    assert len(pawn_moves) == 4
    assert len(wall_moves) == 128


import random

def test_state_integrity_after_simulation():
    pos = {1: 4, 2: 76}
    state = GameState(9, 1, pos, {1: 10, 2: 10})
    original_snapshot = state.to_snapshot()
    
    for _ in range(50):
        temp_state = clone_state(state)
        moves = get_all_legal_moves(temp_state)
        if moves:
            move = random.choice(moves)
            apply_move(temp_state, move)
            
    assert state.to_snapshot() == original_snapshot


def test_apply_move_pawn():
    pos = {1: 4, 2: 76}
    state = GameState(9, 1, pos, {1: 10, 2: 10})
    move = ('pawn', 5)
    apply_move(state, move)
    assert state.player_positions[1] == 5
    assert state.current_player == 2

def test_apply_move_wall_vertical():
    pos = {1: 4, 2: 76}
    state = GameState(9, 1, pos, {1: 10, 2: 10})
    edges = [(4, 5), (13, 14)]
    move = ('wall', edges, 'vertical')
    apply_move(state, move)
    assert edges[0] in state.vertical_walls
    assert state.remaining_walls[1] == 9

def test_apply_move_wall_horizontal():
    pos = {1: 4, 2: 76}
    state = GameState(9, 1, pos, {1: 10, 2: 10})
    edges = [(0, 9), (1, 10)]
    move = ('wall', edges, 'horizontal')
    apply_move(state, move)
    assert edges[0] in state.horizontal_walls
    assert edges[1] in state.horizontal_walls
    assert state.remaining_walls[1] == 9
    assert state.current_player == 2