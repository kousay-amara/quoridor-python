from __future__ import annotations

from quoridor.core.player import Player


def test_player_initialization_with_defaults():
    player = Player(player_id=1, pos=4)
    assert player.player_id == 1
    assert player.pos == 4
    assert player.target_row is None
    assert player.target_col is None
    assert player.wall_count == 10


def test_player_initialization_with_explicit_targets_and_walls():
    player = Player(player_id=3, pos=40, target_row=None, target_col=8, wall_count=7)
    assert player.player_id == 3
    assert player.pos == 40
    assert player.target_col == 8
    assert player.wall_count == 7


def test_player_move_updates_position():
    player = Player(player_id=2, pos=76)
    player.move(67)
    assert player.pos == 67


def test_player_use_wall_decrements_until_zero_without_going_negative():
    player = Player(player_id=1, pos=4, wall_count=2)
    player.use_wall()
    assert player.wall_count == 1
    player.use_wall()
    assert player.wall_count == 0
    player.use_wall()
    assert player.wall_count == 0
