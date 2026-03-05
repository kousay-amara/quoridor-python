"""GTK GUI for Quoridor demo."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..utils.graph import Graph

SIZE = 9
MARGIN = 30
SYMBOLS = ["X", "O"]


class QuoridorWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Quoridor")
        self.graph = Graph(SIZE)
        self.positions = [4, 76]
        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_content_width(SIZE * 52 + 2 * MARGIN)
        self.area.set_content_height(SIZE * 52 + 2 * MARGIN)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

    def _cell_size(self):
        w, h = self.area.get_width(), self.area.get_height()
        return max((min(w, h) - 2 * MARGIN) / SIZE, 1)

    def _cell_xy(self, row, col):
        cs = self._cell_size()
        return MARGIN + col * cs, MARGIN + row * cs

    def _draw(self, _area, cr, _w, _h):
        cs = self._cell_size()
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

        cr.set_source_rgb(0, 0, 0)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(cs * 0.6)

        for i, pos in enumerate(self.positions):
            r, c = divmod(pos, SIZE)
            x, y = self._cell_xy(r, c)
            cr.move_to(x + cs / 4, y + cs / 1.4)
            cr.show_text(SYMBOLS[i])


def main():
    app = Gtk.Application(application_id="fr.ubordeaux.quoridor.demo")
    app.connect("activate", lambda a: QuoridorWindow(a).present())
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
