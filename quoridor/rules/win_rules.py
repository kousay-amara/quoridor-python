"""Win condition rules for Quoridor players."""

from __future__ import annotations


def has_player_won(player_id: int, node: int, board_size: int) -> bool:
    """Return True when the player reached their target side."""
    row = node // board_size
    col = node % board_size
    if player_id == 1:
        return row == board_size - 1
    if player_id == 2:
        return row == 0
    if player_id == 3:
        return col == board_size - 1
    if player_id == 4:
        return col == 0
    return False
