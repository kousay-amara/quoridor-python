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

    from quoridor.application.game_application_service import (  # noqa: E402
        GameApplicationService,
    )
    from quoridor.application.game_session import (  # noqa: E402
        GameSession,
        initial_player_positions,
    )
    from quoridor.core.validators import validate_pawn_move, validate_wall
    from quoridor.interfaces.gui_shortcuts import (  # noqa: E402
        ACTION_LABELS,
        ActionRegistry,
        ActionType,
        ConfigManager,
        ShortcutError,
        ShortcutManager,
    )
    from quoridor.interfaces.gui_constants import (  # noqa: E402
        CELL,
        COLOR_BACKGROUND,
        COLOR_CELL,
        COLOR_WALL,
        DEFAULT_WALLS,
        GAP,
        MARGIN,
        PLAYER_COLORS,
        SIZE,
    )
else:
    from ..application.game_application_service import GameApplicationService
    from ..application.game_session import (
        GameSession,
        initial_player_positions,
    )
    from ..core.validators import validate_pawn_move, validate_wall
    from .gui_shortcuts import (
        ACTION_LABELS,
        ActionRegistry,
        ActionType,
        ConfigManager,
        ShortcutError,
        ShortcutManager,
    )
    from .gui_constants import (
        CELL,
        COLOR_BACKGROUND,
        COLOR_CELL,
        COLOR_WALL,
        DEFAULT_WALLS,
        GAP,
        MARGIN,
        PLAYER_COLORS,
        SIZE,
    )


class QuoridorWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        app: Gtk.Application,
        num_players=2,
        board_size=9,
        walls=DEFAULT_WALLS,
    ):
        super().__init__(application=app, title="Quoridor")
        self.set_default_size(680, 760)

        self._app = app
        self._paused = False
        self._game_over = False
        self._num_players = num_players
        self._init_board_size = board_size
        self._init_walls = walls
        self._shortcut_window: Gtk.Window | None = None
        self._shortcut_entries: dict[ActionType, Gtk.Entry] = {}

        self.config_manager = ConfigManager.default()
        self.shortcut_manager = self.config_manager.load_shortcuts()
        self.action_registry = ActionRegistry(handlers={})

        self.session = self._build_new_session(
            size=board_size,
            players=num_players,
            walls=walls,
        )
        self.service = GameApplicationService(session=self.session, blitz=None)
        self.status = Gtk.Label(label="Ready.")
        self.status.set_xalign(0.0)

        total = SIZE * CELL + (SIZE - 1) * GAP + 2 * MARGIN
        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_content_width(total)
        self.area.set_content_height(total)
        self.area.set_draw_func(self._draw)

        menubar = self._build_menubar()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(10)
        root.set_margin_bottom(10)
        root.set_margin_start(10)
        root.set_margin_end(10)
        root.append(menubar)
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

    def _build_menubar(self) -> Gtk.PopoverMenuBar:
        file_menu = Gio.Menu()
        file_menu.append("New Game", "win.new_game")
        file_menu.append("Load Game", "win.load_game")
        file_menu.append("Save Game", "win.save_game")
        file_menu.append("Configuration", "win.show_config")
        file_menu.append("Info", "win.show_info")
        file_menu.append("Quit", "win.quit_app")

        game_menu = Gio.Menu()
        game_menu.append("Undo", "win.undo")
        game_menu.append("Redo", "win.redo")
        game_menu.append("Pause", "win.pause")
        game_menu.append("Hint", "win.hint")

        menu_model = Gio.Menu()
        menu_model.append_submenu("File", file_menu)
        menu_model.append_submenu("Game", game_menu)

        return Gtk.PopoverMenuBar(menu_model=menu_model)

    def _build_new_session(
        self, *, size: int, players: int, walls: int = 20
    ) -> GameSession:
        positions = initial_player_positions(size, players)
        return GameApplicationService.new_session(
            board_size=size,
            players=players,
            walls_per_player=walls,
            player_types={p: "human" for p in positions},
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
        size = self._board_size()
        cs = self._cell_size()
        step = cs + GAP
        col = int((x - self._ox) / step)
        row = int((y - self._oy) / step)
        if 0 <= row < size and 0 <= col < size:
            in_cell_x = (x - self._ox) - col * step
            in_cell_y = (y - self._oy) - row * step
            if in_cell_x <= cs and in_cell_y <= cs:
                return row, col
        return None

    def _on_drag_begin(self, gesture, start_x, start_y):
        if self._paused:
            self._set_status("Game is paused.")
            return
        if self._game_over:
            self._set_status("Game is over. Start a new game.")
            return
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
                winner = self.session.winner_id()
                if winner is not None:
                    self._set_status(f"Player {winner} wins!")
                    self._game_over = True
                else:
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
        self.session = self._build_new_session(
            size=self._init_board_size,
            players=self._num_players,
            walls=self._init_walls,
        )
        self.service.set_context(session=self.session, blitz=None)
        self._paused = False
        self._game_over = False
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
            _groups, total = self.service.undo_groups(
                requester_id=current,
                count=1,
            )
        except Exception as exc:
            self._set_status(f"Undo failed: {exc}")
            return

        if total == 0:
            self._set_status("Nothing to undo.")
            return
        self._game_over=False
        self.area.queue_draw()
        self._set_status(f"Undid {total} move(s).")

    def _action_redo(self) -> None:
        current = self.session.state.current_player
        try:
            _groups, total = self.service.redo_groups(
                requester_id=current,
                count=1,
            )
        except Exception as exc:
            self._set_status(f"Redo failed: {exc}")
            return

        if total == 0:
            self._set_status("Nothing to redo.")
            return

        winner = self.session.winner_id()
        if winner is not None:
            self._game_over = True
            self._set_status(f"Player {winner} wins!")           
        self.area.queue_draw()
        self._set_status(f"Redid {total} move(s).")

    def _action_pause(self) -> None:
        self._paused = not self._paused
        self._set_status("Game paused." if self._paused else "Game resumed.")

    def _action_hint(self) -> None:
        if self._paused:
            self._set_status("Game is paused.")
            return

        current = self.session.state.current_player
        try:
            move = self.service.hint(
                ai_mode="minimax",
                ai_time=2,
                ai_minimax_depth=1,
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
        dialog = Gtk.FileChooserDialog(
            title="Save Quoridor game",
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
        dialog.connect("response", self._on_save_response)
        dialog.present()

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
            self.service.save(path)
            self._set_status(f"Saved to: {path}")
        except OSError as exc:
            self._set_status(f"Save failed: {exc}")

    def _on_load_clicked(self, _button) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Load Quoridor game",
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Load", Gtk.ResponseType.ACCEPT)
        dialog.connect("response", self._on_load_response)
        dialog.present()

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
            self.session, _blitz = self.service.load(
                path,
                fallback_player_types=self.session.player_types,
                fallback_walls_per_player=self.session.state.remaining_walls,
            )
            self._paused = False
            self._game_over = False
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


def main(num_players=2, board_size=9, walls=20):
    app = Gtk.Application(application_id="fr.ubordeaux.quoridor.demo")
    app.connect(
        "activate",
        lambda a: QuoridorWindow(
            a,
            num_players=num_players,
            board_size=board_size,
            walls=walls,
        ).present(),
    )
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
