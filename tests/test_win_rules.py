from __future__ import annotations

from quoridor.rules.win_rules import has_player_won


def test_has_player_won_player_1_reaches_last_row():
    size = 9
    assert has_player_won(1, (size - 1) * size + 4, size) is True
    assert has_player_won(1, 4, size) is False


def test_has_player_won_player_2_reaches_first_row():
    size = 9
    assert has_player_won(2, 4, size) is True
    assert has_player_won(2, (size - 1) * size + 4, size) is False


def test_has_player_won_player_3_reaches_last_column():
    size = 9
    assert has_player_won(3, 4 * size + (size - 1), size) is True
    assert has_player_won(3, 4 * size + 0, size) is False


def test_has_player_won_player_4_reaches_first_column():
    size = 9
    assert has_player_won(4, 4 * size + 0, size) is True
    assert has_player_won(4, 4 * size + (size - 1), size) is False


def test_has_player_won_unknown_player_id_is_false():
    assert has_player_won(99, 0, 9) is False
