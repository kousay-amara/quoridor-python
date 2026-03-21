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

    from quoridor.application.game_session import (  # noqa: E402
        GameSession,
        initial_player_positions,
    )
    from quoridor.application.persistence_service import (  # noqa: E402
        load_session,
        save_session,
    )
    from quoridor.core.game_state import GameState  # noqa: E402
else:
    from ..application.game_session import GameSession, initial_player_positions
    from ..application.persistence_service import load_session, save_session
    from ..core.game_state import GameState

SIZE = 9
MARGIN = 30
GAP = 6
CELL = 46
PLAYER_COLORS = {
    1: (0.2, 0.4, 0.8),
    2: (0.8, 0.2, 0.2),
    3: (0.2, 0.65, 0.3),
    4: (0.75, 0.58, 0.2),
}


class QuoridorWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Quoridor")
        self.set_default_size(680, 760)

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

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        load_button = Gtk.Button(label="Load")
        save_button = Gtk.Button(label="Save")
        load_button.connect("clicked", self._on_load_clicked)
        save_button.connect("clicked", self._on_save_clicked)
        controls.append(load_button)
        controls.append(save_button)

        self.status = Gtk.Label(label="Ready.")
        self.status.set_xalign(0.0)

        total = SIZE * CELL + (SIZE - 1) * GAP + 2 * MARGIN
        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_content_width(total)
        self.area.set_content_height(total)
        self.area.set_draw_func(self._draw)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(10)
        root.set_margin_bottom(10)
        root.set_margin_start(10)
        root.set_margin_end(10)
        root.append(controls)
        root.append(self.area)
        root.append(self.status)
        self.set_child(root)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.area.add_controller(click)
        self._ox = self._oy = MARGIN

    def _board_size(self) -> int:
        return self.session.state.board_size

    def _set_status(self, message: str) -> None:
        self.status.set_text(message)

    def _cell_size(self):
        size = self._board_size()
        available = (
            min(self.area.get_width(), self.area.get_height()) - 2 * MARGIN
        )
        return max((available - (size - 1) * GAP) / size, 1)

    def _cell_xy(self, row, col):
        cs = self._cell_size()
        return self._ox + col * (cs + GAP), self._oy + row * (cs + GAP)

    def _xy_to_cell(self, x, y):
        """Convert pixel coordinates to a board cell, if any."""
        size = self._board_size()
        cs = self._cell_size()
        col = int((x - self._ox) / (cs + GAP))
        row = int((y - self._oy) / (cs + GAP))
        if 0 <= row < size and 0 <= col < size:
            return row, col
        return None

    def _on_click(self, _gesture, _n, x, y):
        cell = self._xy_to_cell(x, y)
        if cell:
            row, col = cell
            size = self._board_size()
            print(f"Clic sur case ({row}, {col}) = node {row * size + col}")

    def _on_save_clicked(self, _button) -> None:
        dialog = Gtk.FileChooserNative(
            title="Save Quoridor game",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
            accept_label="Save",
            cancel_label="Cancel",
        )
        dialog.connect("response", self._on_save_response)
        dialog.show()

    def _on_save_response(self, dialog, response_id) -> None:
        if response_id != Gtk.ResponseType.ACCEPT:
            self._set_status("Save cancelled.")
            dialog.destroy()
            return

        selected = dialog.get_file()
        path = selected.get_path() if selected is not None else None
        dialog.destroy()
        if not path:
            self._set_status("Save failed: invalid file path.")
            return

        try:
            save_session(path, self.session)
            self._set_status(f"Saved to: {path}")
        except OSError as exc:
            self._set_status(f"Save failed: {exc}")

    def _on_load_clicked(self, _button) -> None:
        dialog = Gtk.FileChooserNative(
            title="Load Quoridor game",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="Load",
            cancel_label="Cancel",
        )
        dialog.connect("response", self._on_load_response)
        dialog.show()

    def _on_load_response(self, dialog, response_id) -> None:
        if response_id != Gtk.ResponseType.ACCEPT:
            self._set_status("Load cancelled.")
            dialog.destroy()
            return

        selected = dialog.get_file()
        path = selected.get_path() if selected is not None else None
        dialog.destroy()
        if not path:
            self._set_status("Load failed: invalid file path.")
            return

        try:
            self.session = load_session(
                path,
                fallback_player_types=self.session.player_types,
                fallback_walls_per_player=self.session.state.remaining_walls,
            )
            self.area.queue_draw()
            self._set_status(f"Loaded from: {path}")
        except Exception as exc:
            self._set_status(f"Load failed: {exc}")

    def _draw(self, _area, cr, _w, _h):
        size = self._board_size()
        cs = self._cell_size()
        board = size * cs + (size - 1) * GAP
        self._ox = (self.area.get_width() - board) / 2
        self._oy = (self.area.get_height() - board) / 2

        cr.set_source_rgb(0.86, 0.82, 0.73)
        cr.paint()

        for r in range(size):
            for c in range(size):
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
                r1, c1 = divmod(n1, size)
                r2, c2 = divmod(n2, size)
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
            x, y = self._cell_xy(*divmod(pos, size))
            color = PLAYER_COLORS.get(pid, (0.25, 0.25, 0.25))
            cr.set_source_rgb(*color)
            cr.arc(x + cs / 2, y + cs / 2, cs * 0.35, 0, math.pi * 2)
            cr.fill()


def main():
    app = Gtk.Application(application_id="fr.ubordeaux.quoridor.demo")
    app.connect("activate", lambda a: QuoridorWindow(a).present())
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
