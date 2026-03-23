"""GTK GUI for Quoridor demo."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from quoridor.application.game_session import (  # noqa: E402
        GameSession,
        initial_player_positions,
    )
    from quoridor.core.validators import validate_pawn_move, validate_wall

    from quoridor.application.minimax_engine import (  # noqa: E402
        find_best_move_minimax,
    )
    from quoridor.application.persistence_service import (  # noqa: E402
        load_session,
        save_session,
    )
    from quoridor.core.game_state import GameState  # noqa: E402
    from quoridor.interfaces.gui_shortcuts import (  # noqa: E402
        ACTION_LABELS,
        ActionRegistry,
        ActionType,
        ConfigManager,
        ShortcutError,
        ShortcutManager,
    )
else:
    from ..application.game_session import (
        GameSession,
        initial_player_positions,
    )
    from ..application.minimax_engine import find_best_move_minimax
    from ..core.validators import validate_pawn_move, validate_wall
    from ..application.persistence_service import load_session, save_session
    from ..core.game_state import GameState
    from .gui_shortcuts import (
        ACTION_LABELS,
        ActionRegistry,
        ActionType,
        ConfigManager,
        ShortcutError,
        ShortcutManager,
    )

SIZE = 9
DEFAULT_WALLS = 10
MARGIN = 30
GAP = 6
CELL = 46
PLAYER_COLORS = {
    1: (0.2, 0.4, 0.8),
    2: (0.8, 0.2, 0.2),
    3: (0.2, 0.65, 0.3),
    4: (0.75, 0.58, 0.2),
}
COLOR_BACKGROUND = (0.86, 0.82, 0.73)
COLOR_CELL = (0.96, 0.93, 0.91)
COLOR_WALL = (0.55, 0.27, 0.07)


class QuoridorWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Quoridor")
        self.set_default_size(680, 760)

        self._app = app
        self._paused = False
        self._shortcut_window: Gtk.Window | None = None
        self._shortcut_entries: dict[ActionType, Gtk.Entry] = {}

        self.config_manager = ConfigManager.default()
        self.shortcut_manager = self.config_manager.load_shortcuts()
        self.action_registry = ActionRegistry(handlers={})

        self.session = self._build_new_session(size=SIZE, players=2)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        new_button = Gtk.Button(label="New")
        load_button = Gtk.Button(label="Load")
        save_button = Gtk.Button(label="Save")
        undo_button = Gtk.Button(label="Undo")
        redo_button = Gtk.Button(label="Redo")
        hint_button = Gtk.Button(label="Hint")
        pause_button = Gtk.Button(label="Pause")

        new_button.connect("clicked", lambda _b: self._action_new_game())
        load_button.connect("clicked", self._on_load_clicked)
        save_button.connect("clicked", self._on_save_clicked)
        undo_button.connect("clicked", lambda _b: self._action_undo())
        redo_button.connect("clicked", lambda _b: self._action_redo())
        hint_button.connect("clicked", lambda _b: self._action_hint())
        pause_button.connect("clicked", lambda _b: self._action_pause())

        for widget in [
            new_button,
            load_button,
            save_button,
            undo_button,
            redo_button,
            hint_button,
            pause_button,
        ]:
            controls.append(widget)

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

        self._drag_pid = None
        self._drag_start = None
        self._drag_offset = (0, 0)

        self._drag_ctrl = Gtk.GestureDrag()
        self._drag_ctrl.connect("drag-begin", self._on_drag_begin)
        self._drag_ctrl.connect("drag-update", self._on_drag_update)
        self._drag_ctrl.connect("drag-end", self._on_drag_end)
        self.area.add_controller(self._drag_ctrl)
        self._ox = self._oy = MARGIN

        self._install_actions()
        self._bind_shortcuts()

    def _build_new_session(self, *, size: int, players: int) -> GameSession:
        positions = initial_player_positions(size, players)
        state = GameState(
            board_size=size,
            current_player=1,
            player_positions=positions,
            remaining_walls={p: DEFAULT_WALLS for p in positions},
            vertical_walls=[],
            horizontal_walls=[],
        )
        return GameSession(
            state=state, player_types={p: "human" for p in positions}
        )

    def _install_actions(self) -> None:
        handlers = {
            ActionType.NEW_GAME: self._action_new_game,
            ActionType.LOAD_GAME: self._action_load_game,
            ActionType.SAVE_GAME: self._action_save_game,
            ActionType.SHOW_CONFIG: self._action_show_config,
            ActionType.SHOW_INFO: self._action_show_info,
            ActionType.QUIT_APP: self._action_quit,
            ActionType.UNDO: self._action_undo,
            ActionType.REDO: self._action_redo,
            ActionType.PAUSE: self._action_pause,
            ActionType.HINT: self._action_hint,
        }

        for action_type, callback in handlers.items():
            self.action_registry.register(action_type, callback)
            action = Gio.SimpleAction.new(action_type.value, None)
            action.connect("activate", self._on_action_activated, action_type)
            self.add_action(action)

    def _bind_shortcuts(self) -> None:
        for action_type in ActionType:
            action_name = f"win.{action_type.value}"
            self._app.set_accels_for_action(action_name, [])
            self._app.set_accels_for_action(
                action_name, [self.shortcut_manager.get(action_type)]
            )

    def _on_action_activated(
        self, _action: Gio.SimpleAction, _param, action_type: ActionType
    ) -> None:
        try:
            self.action_registry.execute(action_type)
        except Exception as exc:
            self._set_status(f"Action failed: {exc}")

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

    def _on_drag_begin(self, gesture, start_x, start_y):
        cell = self._xy_to_cell(start_x, start_y)
        if cell is not None:
            row, col = cell
            size = self._board_size()
            node = row * size + col
            current = self.session.state.current_player
            if self.session.state.player_positions[current] == node:
                self._drag_pid = current
                self._drag_start = (start_x, start_y)
                self._drag_offset = (0, 0)
                return
        gap = self._xy_to_gap(start_x, start_y)
        if gap is None:
            return
        orientation, row, col = gap
        edges, orient = self._gap_to_wall_edges(orientation, row, col)
        if edges is None:
            return
        current = self.session.state.current_player
        positions = [
            self.session.state.player_positions[p]
            for p in sorted(self.session.state.player_positions)
        ]
        target_funcs = self.session._build_player_target_funcs()
        valid, error = validate_wall(
            self.session.state.graph, positions, edges,
            target_funcs, self.session.state.remaining_walls, current
        )
        if valid:
            self.session.place_wall(current, edges, orient)
            self._set_status(
                f"Player {current} placed {orient} wall "
                f"at ({row}, {col})."
            )
        else:
            self._set_status(error)
        self.area.queue_draw()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        if self._drag_pid is None:
            return
        self._drag_offset = (offset_x, offset_y)
        self.area.queue_draw()

    def _on_drag_end(self, gesture, offset_x, offset_y):
        if self._drag_pid is None:
            return
        sx, sy = self._drag_start
        target = self._xy_to_cell(sx + offset_x, sy + offset_y)
        if target:
            row, col = target
            size = self._board_size()
            to_node = row * size + col
            from_node = self.session.state.player_positions[self._drag_pid]
            all_pos = list(self.session.state.player_positions.values())
            valid, error = validate_pawn_move(
                self.session.state.graph, from_node, to_node, all_pos, size
            )
            if valid:
                self.session.play_pawn_move(self._drag_pid, to_node)
                self._set_status(
                    f"Player {self._drag_pid} moved "
                    f"to ({row}, {col})."
                )
            else:
                self._set_status(error)
        self._drag_pid = None
        self._drag_start = None
        self._drag_offset = (0, 0)
        self.area.queue_draw()

    def _xy_to_gap(self, x, y):
        cs = self._cell_size()
        size = self._board_size()
        rel_x = x - self._ox
        rel_y = y - self._oy
        step = cs + GAP

        col_idx = int(rel_x / step)
        row_idx = int(rel_y / step)
        in_cell_x = rel_x - col_idx * step
        in_cell_y = rel_y - row_idx * step

        in_gap_x = in_cell_x >= cs
        in_gap_y = in_cell_y >= cs

        if in_gap_x and not in_gap_y and col_idx < size - 1:
            return ("vertical", row_idx, col_idx)
        if in_gap_y and not in_gap_x and row_idx < size - 1:
            return ("horizontal", row_idx, col_idx)
        return None

    def _gap_to_wall_edges(self, orientation, row, col):
        size = self._board_size()
        if orientation == "vertical" and row + 1 < size and col + 1 < size:
            n1 = row * size + col
            n2 = row * size + col + 1
            n3 = (row + 1) * size + col
            n4 = (row + 1) * size + col + 1
            return [(n1, n2), (n3, n4)], "vertical"
        if orientation == "horizontal" and row + 1 < size and col + 1 < size:
            n1 = row * size + col
            n2 = (row + 1) * size + col
            n3 = row * size + col + 1
            n4 = (row + 1) * size + col + 1
            return [(n1, n2), (n3, n4)], "horizontal"
        return None, None

    def _action_new_game(self) -> None:
        players = len(self.session.state.player_positions)
        self.session = self._build_new_session(
            size=self._board_size(),
            players=players,
        )
        self._paused = False
        self.area.queue_draw()
        self._set_status("New game started.")

    def _action_load_game(self) -> None:
        self._on_load_clicked(None)

    def _action_save_game(self) -> None:
        self._on_save_clicked(None)

    def _action_show_config(self) -> None:
        self._show_shortcut_configuration()

    def _action_show_info(self) -> None:
        about = Gtk.AboutDialog(
            transient_for=self,
            modal=True,
            program_name="Quoridor",
            version="1.0",
            comments="GTK interface for Quoridor with configurable shortcuts.",
        )
        about.present()

    def _action_quit(self) -> None:
        self.close()

    def _action_undo(self) -> None:
        current = self.session.state.current_player
        try:
            undone = self.session.undo(requester_id=current)
        except Exception as exc:
            self._set_status(f"Undo failed: {exc}")
            return

        if not undone:
            self._set_status("Nothing to undo.")
            return

        self.area.queue_draw()
        self._set_status(f"Undid {len(undone)} move(s).")

    def _action_redo(self) -> None:
        current = self.session.state.current_player
        try:
            redone = self.session.redo(requester_id=current)
        except Exception as exc:
            self._set_status(f"Redo failed: {exc}")
            return

        if not redone:
            self._set_status("Nothing to redo.")
            return

        self.area.queue_draw()
        self._set_status(f"Redid {len(redone)} move(s).")

    def _action_pause(self) -> None:
        self._paused = not self._paused
        self._set_status("Game paused." if self._paused else "Game resumed.")

    def _action_hint(self) -> None:
        if self._paused:
            self._set_status("Game is paused.")
            return

        current = self.session.state.current_player
        try:
            move = find_best_move_minimax(
                self.session.state,
                ai_player_id=current,
                depth=1,
            )
        except Exception as exc:
            self._set_status(f"Hint unavailable: {exc}")
            return

        self._set_status(f"Hint for player {current}: {move}")

    def _show_shortcut_configuration(self) -> None:
        if self._shortcut_window is not None:
            self._shortcut_window.present()
            return

        window = Gtk.Window(transient_for=self, title="Shortcut configuration")
        window.set_modal(True)
        window.set_default_size(460, 420)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)

        info = Gtk.Label(
            label=(
                "Enter GTK accelerator strings (example: <Primary>n, "
                "<Primary><Shift>s)."
            )
        )
        info.set_wrap(True)
        info.set_xalign(0.0)
        root.append(info)

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        entries: dict[ActionType, Gtk.Entry] = {}

        for row, action_type in enumerate(ActionType):
            label = Gtk.Label(label=ACTION_LABELS[action_type])
            label.set_xalign(0.0)
            entry = Gtk.Entry()
            entry.set_text(self.shortcut_manager.get(action_type))
            grid.attach(label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            entries[action_type] = entry

        root.append(grid)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        reset_button = Gtk.Button(label="Reset defaults")
        save_button = Gtk.Button(label="Save")
        cancel_button = Gtk.Button(label="Cancel")

        reset_button.connect(
            "clicked",
            lambda _b: self._reset_shortcut_entries(entries),
        )
        save_button.connect(
            "clicked", lambda _b: self._save_shortcut_entries(window, entries)
        )
        cancel_button.connect("clicked", lambda _b: window.close())

        buttons.append(reset_button)
        buttons.append(save_button)
        buttons.append(cancel_button)
        root.append(buttons)

        window.connect("close-request", self._on_shortcut_window_closed)
        window.set_child(root)

        self._shortcut_window = window
        self._shortcut_entries = entries
        window.present()

    def _on_shortcut_window_closed(self, window: Gtk.Window):
        self._shortcut_window = None
        self._shortcut_entries = {}
        window.destroy()
        return False

    def _reset_shortcut_entries(
        self,
        entries: dict[ActionType, Gtk.Entry],
    ) -> None:
        defaults = ShortcutManager.with_defaults()
        for action_type, entry in entries.items():
            entry.set_text(defaults.get(action_type))

    def _save_shortcut_entries(
        self, window: Gtk.Window, entries: dict[ActionType, Gtk.Entry]
    ) -> None:
        candidate = {
            action_type: entry.get_text().strip()
            for action_type, entry in entries.items()
        }

        updated = ShortcutManager.with_defaults()
        try:
            updated.replace_all(candidate)
            self.config_manager.save_shortcuts(updated)
        except (ShortcutError, OSError) as exc:
            self._set_status(f"Shortcut save failed: {exc}")
            return

        self.shortcut_manager = updated
        self._bind_shortcuts()
        self._set_status("Shortcut configuration saved.")
        window.close()

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
            self._paused = False
            self.area.queue_draw()
            self._set_status(f"Loaded from: {path}")
        except Exception as exc:
            self._set_status(f"Load failed: {exc}")

    def _draw(self, _area, cr, _w, _h):
        size = self._board_size()
        cs = self._cell_size()
        self._update_origin(cs, size)
        self._draw_background(cr)
        self._draw_cells(cr, cs, size)
        self._draw_walls(cr, cs, size)
        self._draw_players(cr, cs, size)

    def _update_origin(self, cs, size):
        board = size * cs + (size - 1) * GAP
        self._ox = (self.area.get_width() - board) / 2
        self._oy = (self.area.get_height() - board) / 2

    def _draw_background(self, cr):
        cr.set_source_rgb(*COLOR_BACKGROUND)
        cr.paint()

    def _draw_cells(self, cr, cs, size):
        for r in range(size):
            for c in range(size):
                x, y = self._cell_xy(r, c)
                cr.set_source_rgb(*COLOR_CELL)
                cr.rectangle(x, y, cs, cs)
                cr.fill()
                cr.set_source_rgb(0, 0, 0)
                cr.set_line_width(0.5)
                cr.rectangle(x, y, cs, cs)
                cr.stroke()

    def _draw_walls(self, cr, cs, size):
        cr.set_source_rgb(*COLOR_WALL)
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
                        GAP, cs,
                    )
                else:
                    cr.rectangle(
                        self._ox + col * (cs + GAP),
                        self._oy + row * (cs + GAP) + cs,
                        cs, GAP,
                    )
                cr.fill()

    def _draw_players(self, cr, cs, size):
        for pid, pos in self.session.state.player_positions.items():
            x, y = self._cell_xy(*divmod(pos, size))
            cx = x + cs / 2
            cy = y + cs / 2

            if pid == self._drag_pid and self._drag_start:
                ox, oy = self._drag_offset
                cx = self._drag_start[0] + ox
                cy = self._drag_start[1] + oy

            color = PLAYER_COLORS.get(pid, (0.25, 0.25, 0.25))
            cr.set_source_rgb(*color)
            cr.arc(cx, cy, cs * 0.35, 0, math.pi * 2)
            cr.fill()


def main():
    app = Gtk.Application(application_id="fr.ubordeaux.quoridor.demo")
    app.connect("activate", lambda a: QuoridorWindow(a).present())
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
