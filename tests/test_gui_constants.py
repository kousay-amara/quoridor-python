from __future__ import annotations

from quoridor.interfaces import gui_constants as c


def test_gui_constants_are_coherent():
    assert c.SIZE > 0
    assert c.CELL > 0
    assert c.GAP >= 0
    assert c.MARGIN >= 0
    assert c.DEFAULT_WALLS > 0
    assert set(c.PLAYER_COLORS.keys()) >= {1, 2}
    assert len(c.COLOR_BACKGROUND) == 3
    assert len(c.COLOR_CELL) == 3
    assert len(c.COLOR_WALL) == 3
