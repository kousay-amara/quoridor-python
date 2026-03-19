"""GTK GUI for Quoridor demo."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from quoridor.core.game_state import GameState  # noqa: E402
    from quoridor.application.game_session import (  # noqa: E402
        GameSession,
        initial_player_positions,
    )
else:
    from ..core.game_state import GameState  # noqa: E402
    from ..application.game_session import (  # noqa: E402
        GameSession,
        initial_player_positions,
    )

SIZE = 9
MARGIN = 30
GAP = 6
CELL = 46
PLAYER_COLORS = {1: (0.2, 0.4, 0.8), 2: (0.8, 0.2, 0.2)}


class QuoridorWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Quoridor")
        positions = initial_player_positions(SIZE, 2)
        state = GameState(
            board_size=SIZE,
            current_player=1,
            player_positions=positions,
            remaining_walls={p: 10 for p in positions},
            vertical_walls=[],
            horizontal_walls=[],
        )
        self.session = GameSession(
            state=state, player_types={p: "human" for p in positions}
        )

        total = SIZE * CELL + (SIZE - 1) * GAP + 2 * MARGIN
        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_content_width(total)
        self.area.set_content_height(total)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.area.add_controller(click)
        self._ox = self._oy = MARGIN

    def _cell_size(self):
        available = (
            min(self.area.get_width(), self.area.get_height()) - 2 * MARGIN
        )
        return max((available - (SIZE - 1) * GAP) / SIZE, 1)

    def _cell_xy(self, row, col):
        cs = self._cell_size()
        return self._ox + col * (cs + GAP), self._oy + row * (cs + GAP)

    def _xy_to_cell(self, x, y):
        """Convert pixel coordinates to a board cell, if any."""
        cs = self._cell_size()
        col = int((x - self._ox) / (cs + GAP))
        row = int((y - self._oy) / (cs + GAP))
        if 0 <= row < SIZE and 0 <= col < SIZE:
            return row, col
        return None

    def _on_click(self, _gesture, _n, x, y):
        cell = self._xy_to_cell(x, y)
        if cell:
            row, col = cell
            print(f"Clic sur case ({row}, {col}) = node {row * SIZE + col}")

    def _draw(self, _area, cr, _w, _h):
        cs = self._cell_size()
        board = SIZE * cs + (SIZE - 1) * GAP
        self._ox = (self.area.get_width() - board) / 2
        self._oy = (self.area.get_height() - board) / 2

        cr.set_source_rgb(0.86, 0.82, 0.73)
        cr.paint()

        for r in range(SIZE):
            for c in range(SIZE):
                x, y = self._cell_xy(r, c)
                cr.set_source_rgb(0.96, 0.93, 0.91)
                cr.rectangle(x, y, cs, cs)
                cr.fill()
                cr.set_source_rgb(0, 0, 0)
                cr.set_line_width(0.5)
                cr.rectangle(x, y, cs, cs)
                cr.stroke()

        cr.set_source_rgb(0.55, 0.27, 0.07)
        for walls, vertical in [
            (self.session.state.vertical_walls, True),
            (self.session.state.horizontal_walls, False),
        ]:
            for n1, n2 in walls:
                r1, c1 = divmod(n1, SIZE)
                r2, c2 = divmod(n2, SIZE)
                row, col = min(r1, r2), min(c1, c2)
                if vertical:
                    cr.rectangle(
                        self._ox + col * (cs + GAP) + cs,
                        self._oy + row * (cs + GAP),
                        GAP,
                        cs,
                    )
                else:
                    cr.rectangle(
                        self._ox + col * (cs + GAP),
                        self._oy + row * (cs + GAP) + cs,
                        cs,
                        GAP,
                    )
                cr.fill()

        for pid, pos in self.session.state.player_positions.items():
            x, y = self._cell_xy(*divmod(pos, SIZE))
            cr.set_source_rgb(*PLAYER_COLORS[pid])
            cr.arc(x + cs / 2, y + cs / 2, cs * 0.35, 0, math.pi * 2)
            cr.fill()


def main():
    app = Gtk.Application(application_id="fr.ubordeaux.quoridor.demo")
    app.connect("activate", lambda a: QuoridorWindow(a).present())
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
