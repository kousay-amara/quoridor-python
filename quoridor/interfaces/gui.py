from __future__ import annotations

import time
import math
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

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
    from quoridor.application.blitz import Blitz
    from quoridor.application.persistence_service import record_to_notation
    from quoridor.core.notation import get_notation_from_node
    from quoridor.interfaces.cli_render import _format_hint_move
else:
    from ..application.game_application_service import GameApplicationService
    from ..application.blitz import Blitz
    from ..application.persistence_service import record_to_notation
    from ..network import NetworkClient
    from ..application.game_session import (
        GameSession,
        initial_player_positions,
    )
    from ..core.notation import get_notation_from_node
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
    from .cli_render import _format_hint_move


class QuoridorWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        app: Gtk.Application,
        num_players=2,
        board_size=9,
        walls=DEFAULT_WALLS,
        blitz=False,
        time_limit=0,
        ai_players: list[int] | None = None,
        ai_mode: str = "iterative",
        ai_time: int = 5,
        ai_minimax_depth: int | None = None,
    ):
        super().__init__(application=app, title="Quoridor")
        self.set_default_size(680, 760)

        self._app = app
        self._paused = False
        self._ai_thinking = False
        self._game_over = False
        self._turn_start_time: float | None = None
        self._blitz_timer_id: int | None = None
        self._ai_players = (
            ai_players or []
        )  # Handle None by using an empty list.
        self._ai_mode = ai_mode
        self._ai_time = ai_time
        self._ai_minimax_depth = ai_minimax_depth
        self._num_players = num_players
        self._init_board_size = board_size
        self._init_walls = walls
        self._init_blitz = blitz
        self._init_time_limit = time_limit
        self._pause_elapsed: float = 0.0
        self._shortcut_window: Gtk.Window | None = None
        self._text_window: Gtk.Window | None = None
        self._config_window: Gtk.Window | None = None
        self._shortcut_entries: dict[ActionType, Gtk.Entry] = {}
        self._network_mode = False
        self._network_client = None
        self._network_player_id = None

        self.config_manager = ConfigManager.default()
        self.shortcut_manager = self.config_manager.load_shortcuts()
        self.action_registry = ActionRegistry(handlers={})

        self.session = self._build_new_session(
            size=board_size,
            players=num_players,
            walls=walls,
        )

        if self._init_blitz:
            self.blitz = Blitz(
                time_limit_minutes=self._init_time_limit,
                player_ids=self.session.state.player_positions,
            )
        else:
            self.blitz = Blitz(time_limit_minutes=0)

        self.service = GameApplicationService(
            session=self.session, blitz=self.blitz
        )
        self.status = Gtk.Label(label="Ready.")
        self.status.set_xalign(0.0)

        total = SIZE * CELL + (SIZE - 1) * GAP + 2 * MARGIN
        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_content_width(total)
        self.area.set_content_height(total)
        self.area.set_draw_func(self._draw)

        menubar = self._build_menubar()
        if self._init_blitz:
            self.blitz_label.set_visible(True)

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
        self._schedule_ai_turn()
        if (
            self.session.player_types.get(self.session.state.current_player)
            != "ai"
        ):
            self._start_blitz_turn()

    def _start_blitz_turn(self) -> None:
        if not self.blitz.is_enabled():
            return
        self._turn_start_time = time.time()
        self._blitz_timer_id = GLib.timeout_add(100, self._on_blitz_tick)

    def _stop_blitz_turn(self, player_id: int) -> bool:
        if not self.blitz.is_enabled():
            return False
        if self._turn_start_time is None:
            return False
        if self._blitz_timer_id is not None:
            GLib.source_remove(self._blitz_timer_id)
            self._blitz_timer_id = None
        elapsed = time.time() - self._turn_start_time
        self._turn_start_time = None
        return self.blitz.consume_time(player_id, elapsed)

    def _on_blitz_tick(self) -> bool:
        if self._turn_start_time is None:
            return False
        if self._paused:
            return True
        player_id = self.session.state.current_player
        elapsed = time.time() - self._turn_start_time
        remaining = self.blitz.remaining_time(player_id) - elapsed
        if remaining <= 0:
            self._stop_blitz_turn(player_id)
            self.session.timeout_player(player_id)
            self._set_status(f"Player {player_id} ran out of time!")
            if not self._apply_game_outcome():
                self._start_blitz_turn()
            return False
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        self.blitz_label.set_text(f"Player{player_id}: {mins}:{secs:02d}")
        return True

    def _build_menubar(self) -> Gtk.PopoverMenuBar:
        file_menu = Gio.Menu()
        file_menu.append("New Game", "win.new_game")
        file_menu.append("Load Game", "win.load_game")
        file_menu.append("Save Game", "win.save_game")
        file_menu.append("Game Configuration", "win.show_config")
        file_menu.append("Keyboard Shortcuts", "win.show_shortcuts")
        file_menu.append("Info", "win.show_info")
        file_menu.append("Quit", "win.quit_app")

        game_menu = Gio.Menu()
        game_menu.append("Undo", "win.undo")
        game_menu.append("Redo", "win.redo")
        game_menu.append("Pause", "win.pause")
        game_menu.append("Hint", "win.hint")
        game_menu.append("Show History", "win.show_history")
        game_menu.append("Show Time", "win.show_time")

        network_menu = Gio.Menu()
        network_menu.append("Join Server", "win.network_join")
        network_menu.append("Disconnect", "win.network_disconnect")
        network_menu.append("Players", "win.network_players")
        network_menu.append("New Game (invite)", "win.network_new_game")

        menu_model = Gio.Menu()
        menu_model.append_submenu("File", file_menu)
        menu_model.append_submenu("Game", game_menu)
        menu_model.append_submenu("Network", network_menu)

        menubar = Gtk.PopoverMenuBar(menu_model=menu_model)
        menubar.set_hexpand(True)

        self.blitz_label = Gtk.Label(label="")
        self.blitz_label.set_xalign(1.0)
        self.blitz_label.set_visible(False)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.append(menubar)
        bar.append(self.blitz_label)

        return bar

    def _build_new_session(
        self, *, size: int, players: int, walls: int = 20
    ) -> GameSession:
        positions = initial_player_positions(size, players)
        player_types = {}
        for p in positions:
            if p in self._ai_players:
                player_types[p] = "ai"
            else:
                player_types[p] = "human"
        return GameApplicationService.new_session(
            board_size=size,
            players=players,
            walls_per_player=walls,
            player_types=player_types,
        )

    def _play_one_ai_turn(self):
        if self._paused:
            self._set_status("Game is paused.")
            return
        if self._game_over:
            self._set_status("Game is over. Start a new game.")
            return
        if (
            self.session.player_types.get(self.session.state.current_player)
            != "ai"
        ):
            return
        self._ai_thinking = True
        current = self.session.state.current_player
        started = time.time()
        move = self.session.compute_ai_move(
            mode=self._ai_mode,
            depth=self._ai_minimax_depth,
            time_limit_sec=self._ai_time,
        )
        elapsed = time.time() - started
        if self.blitz.is_enabled():
            timed_out = self.blitz.consume_time(current, elapsed)
            if timed_out:
                self.session.timeout_player(current)
                self._set_status(f"Player {current} ran out of time!")
                self._apply_game_outcome()
                self.area.queue_draw()
                self._ai_thinking = False
                return
        self.session.apply_ai_move(move, player_id=current)
        if self._apply_game_outcome():
            self.area.queue_draw()
            self._ai_thinking = False
            return
        self._set_status(f"AI player {current} played.")
        self.area.queue_draw()
        self._ai_thinking = False
        if (
            self.session.player_types.get(self.session.state.current_player)
            == "ai"
        ):
            GLib.idle_add(self._play_one_ai_turn)
        else:
            self._start_blitz_turn()

    def _schedule_ai_turn(self) -> None:
        if not self._ai_players:
            return
        GLib.idle_add(self._play_one_ai_turn)

    def _install_actions(self) -> None:
        handlers = {
            ActionType.NEW_GAME: self._action_new_game,
            ActionType.LOAD_GAME: self._action_load_game,
            ActionType.SAVE_GAME: self._action_save_game,
            ActionType.SHOW_CONFIG: self._action_show_config,
            ActionType.SHOW_SHORTCUTS: self._action_show_shortcuts,
            ActionType.SHOW_HISTORY: self._action_show_history,
            ActionType.SHOW_TIME: self._action_show_time,
            ActionType.SHOW_INFO: self._action_show_info,
            ActionType.QUIT_APP: self._action_quit,
            ActionType.UNDO: self._action_undo,
            ActionType.REDO: self._action_redo,
            ActionType.PAUSE: self._action_pause,
            ActionType.HINT: self._action_hint,
            ActionType.NETWORK_NEW_GAME: self._action_network_new_game,
            ActionType.PLAYERS: self._action_network_players,
            ActionType.JOIN_SERVER: self._action_network_join,
            ActionType.DISCONNECT: self._action_network_disconnect,
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
        if self._ai_thinking:
            self._set_status("ai is thinking")
            return
        if self._network_mode and self.session.state.current_player != self._network_player_id:
            self._set_status("Ce n'est pas ton tour.")
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
            self.session.state.graph,
            positions,
            edges,
            target_funcs,
            self.session.state.remaining_walls,
            current,
        )
        if valid:
            if self._network_mode:
                col_char = chr(ord("a") + col)
                wall_notation = f"{col_char}{row + 1}{orient[0]}"
                self._network_client.move(wall_notation)
            else:
                self._stop_blitz_turn(current)
                self.session.place_wall(current, edges, orient)
                self._set_status(
                    f"Player {current} placed {orient} wall at ({row}, {col})."
                )
                self._schedule_ai_turn()
                if (
                    self.session.player_types.get(
                        self.session.state.current_player
                    )
                    != "ai"
                ):
                    self._start_blitz_turn()
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
                if self._network_mode:
                    from_notation = get_notation_from_node(from_node, self._board_size())
                    to_notation = get_notation_from_node(to_node, self._board_size())
                    notation = f"{from_notation}-{to_notation}"
                    print(f"Envoi coup réseau : {notation}")
                    result = self._network_client.move(notation)
                    print(f"Réponse serveur : {result}")
                else:
                    self._stop_blitz_turn(self._drag_pid)
                    self.session.play_pawn_move(self._drag_pid, to_node)
                    self.area.queue_draw()
                    if self._apply_game_outcome():
                        pass
                    else:
                        self._set_status(
                            f"Player {self._drag_pid} moved to ({row}, {col})."
                        )
                        self._schedule_ai_turn()
                        if (
                            self.session.player_types.get(
                                self.session.state.current_player
                            )
                            != "ai"
                        ):
                            self._start_blitz_turn()
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
        if self._blitz_timer_id is not None:
            GLib.source_remove(self._blitz_timer_id)
            self._blitz_timer_id = None
        self.session = self._build_new_session(
            size=self._init_board_size,
            players=self._num_players,
            walls=self._init_walls,
        )
        if self._init_blitz:
            self.blitz = Blitz(
                time_limit_minutes=self._init_time_limit,
                player_ids=self.session.state.player_positions,
            )
        else:
            self.blitz = Blitz(time_limit_minutes=0)
        self.service.set_context(session=self.session, blitz=self.blitz)
        self._paused = False
        self._game_over = False
        self.area.queue_draw()
        self._schedule_ai_turn()
        if (
            self.session.player_types.get(self.session.state.current_player)
            != "ai"
        ):
            self._start_blitz_turn()
        self._set_status("New game started.")

    def _action_load_game(self) -> None:
        self._on_load_clicked(None)

    def _action_save_game(self) -> None:
        self._on_save_clicked(None)

    def _action_show_config(self) -> None:
        self._show_game_configuration()

    def _action_show_shortcuts(self) -> None:
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
        if self._network_client is not None:
            self._network_client.disconnect()
        self.close()

    def _action_undo(self) -> None:
        if self._network_mode:
            self._set_status("Non disponible en mode réseau.")
            return
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
        self._game_over = False
        self._schedule_ai_turn()
        self.area.queue_draw()
        self._set_status(f"Undid {total} move(s).")

    def _action_redo(self) -> None:
        if self._network_mode:
            self._set_status("Non disponible en mode réseau.")
            return
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

        if not self._apply_game_outcome():
            self._schedule_ai_turn()
            self._set_status(f"Redid {total} move(s).")
        self.area.queue_draw()

    def _apply_game_outcome(self) -> bool:
        outcome = self.session.game_outcome()
        if outcome.status == "winner" and outcome.winner_id is not None:
            self._set_status(f"Player {outcome.winner_id} wins!")
            self._game_over = True
            return True
        if outcome.status == "draw":
            self._set_status("Draw game.")
            self._game_over = True
            return True
        self._game_over = False
        return False

    def _action_pause(self) -> None:
        if self._network_mode:
            self._set_status("Non disponible en mode réseau.")
            return
        self._paused = not self._paused
        if self.blitz.is_enabled():
            self.blitz.toggle_pause()
            if self._paused:
                if self._turn_start_time is not None:
                    self._pause_elapsed = time.time() - self._turn_start_time
            else:
                self._turn_start_time = time.time() - self._pause_elapsed
                self._pause_elapsed = 0.0
        self._set_status("Game paused." if self._paused else "Game resumed.")
        self.area.queue_draw()

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
            message = str(exc)
            if message == "Game is over. No hint available.":
                self._set_status(message)
            else:
                self._set_status(f"Hint unavailable: {exc}")
            return

        from_node = self.session.state.player_positions[current]
        best_hint = _format_hint_move(
            move,
            from_node=from_node,
            size=self.session.state.board_size,
        )
        self._set_status(f"Hint for player {current}: {best_hint}")

    def _history_text(self) -> str:
        records = self.session.history.records[: self.session.history.cursor + 1]
        if not records:
            return "No moves played yet."

        player_count = max(1, len(self.session.state.player_positions))
        lines = []
        for idx in range(0, len(records), player_count):
            turn = records[idx : idx + player_count]
            text = " ".join(
                f"{record.player_id} {record_to_notation(record)};"
                for record in turn
            )
            lines.append(text)
        return "[history]\n" + "\n".join(lines)

    def _action_show_history(self) -> None:
        self._show_text_window("Move History", self._history_text())

    def _action_show_time(self) -> None:
        if not self.blitz.is_enabled():
            self._set_status("Blitz mode is not enabled.")
            return
        remaining = self.blitz.remaining_times()
        text = ", ".join(
            f"Player {pid}: {int(sec)//60:02d}:{int(sec)%60:02d}"
            for pid, sec in sorted(remaining.items())
        )
        message = f"Blitz time -> {text}"
        self._set_status(message)
        self._show_text_window("Remaining Time", message)

    def _action_network_join(self) -> None:
        dialog = Gtk.Dialog(title="Join Server", transient_for=self)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Connect", Gtk.ResponseType.ACCEPT)

        host_entry = Gtk.Entry()
        host_entry.set_text("localhost")

        port_entry = Gtk.Entry()
        port_entry.set_text("9000")

        name_entry = Gtk.Entry()
        name_entry.set_text("player")

        content = dialog.get_content_area()
        content.set_spacing(6)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        content.set_margin_start(10)
        content.set_margin_end(10)

        for label_text, entry in [
            ("Host:", host_entry),
            ("Port:", port_entry),
            ("Pseudo:", name_entry),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.append(Gtk.Label(label=label_text))
            row.append(entry)
            content.append(row)

        dialog.connect(
            "response", self._on_join_response, host_entry, port_entry, name_entry
        )
        dialog.present()

    def _on_join_response(
        self, dialog, response, host_entry, port_entry, name_entry
    ) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            host = host_entry.get_text()
            port = int(port_entry.get_text())
            name = name_entry.get_text()
            self._set_status(f"Connecting to {host}:{port} as {name}...")
            client = NetworkClient(host=host, port=port, name=name)
            dialog.destroy()
            try:
                client.connect()
                self._network_client = client
                self._network_mode = True
                print(f"Mon client_id : {client.client_id}")
                self._network_client.set_opponent_move_callback(
                    lambda notation: GLib.idle_add(
                        self._handle_opponent_move, notation
                    )
                )
                self._network_client.set_game_state_callback(
                    lambda update: GLib.idle_add(
                        self._apply_game_state_update, update
                    )
                )
                self._network_client.set_notification_callback(
                    lambda msg: GLib.idle_add(self._handle_notification, msg)
                )
                self._network_client.set_connection_lost_callback(
                    lambda err: GLib.idle_add(self._handle_disconnect, err)
                )
                self._set_status(f"Connecté à {host}:{port} !")
            except Exception as e:
                self._set_status(f"Erreur de connexion : {e}")
        else:
            dialog.destroy()

    def _action_network_disconnect(self) -> None:
        if self._network_client is not None:
            self._network_client.disconnect()
            self._network_mode = False
            self._network_client = None
            self._set_status("player deconnecte")
        else:
            self._set_status("vous etes deja deconnecté")

    def _action_network_players(self) -> None:
        if self._network_client is None:
            self._set_status("vous n'etes pas connecte")
        else:
            players = self._network_client.players()
            if not players:
                self._set_status("Aucun joueur connecté.")
            else:
                text = ""
                for player_id, name, status in players:
                    text = text + f"{name}({status}) "
                self._set_status(f"Joueurs : {text}")

    def _action_network_new_game(self) -> None:
        if self._network_client is None:
            self._set_status("Vous n'êtes pas connecté.")
            return
        dialog = Gtk.Dialog(title="Invite Player", transient_for=self)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Invite", Gtk.ResponseType.ACCEPT)

        id_label = Gtk.Label(label="ID du joueur:")
        id_entry = Gtk.Entry()
        id_entry.set_text("1")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(id_label)
        row.append(id_entry)

        content = dialog.get_content_area()
        content.set_spacing(6)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        content.set_margin_start(10)
        content.set_margin_end(10)
        content.append(row)

        dialog.connect("response", self._on_new_game_response, id_entry)
        dialog.present()

    def _on_new_game_response(self, dialog, response, id_entry) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            player_id = id_entry.get_text()
            dialog.destroy()
            try:
                self._network_client.send_command(f"NEW {player_id}")
                self._set_status(f"Invitation envoyée au joueur {player_id} !")
            except Exception as e:
                self._set_status(f"Erreur : {e}")
        else:
            dialog.destroy()

    def _handle_opponent_move(self, notation) -> None:
        print(f"Coup adversaire reçu : {notation}")

    def _apply_game_state_update(self, update) -> None:
        print(
            f"GAME_STATE reçu : player_id={update['player_id']}, "
            f"winner={update['winner_id']}"
        )
        if self._network_player_id is None:
            self._network_player_id = update["player_id"]
        self.session.state.restore(update["state"])
        self.area.queue_draw()
        if update["winner_id"]:
            self._game_over = True
            self._set_status(f"Player {update['winner_id']} has won!")

    def _handle_notification(self, message) -> None:
        if message.startswith("INVITATION_RECEIVED"):
            parts = message.split()
            opponent = parts[1].split("=")[1]

            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE,
                text=f"{opponent} vous invite à jouer. Accepter ?",
            )
            dialog.add_button("Decline", Gtk.ResponseType.NO)
            dialog.add_button("Accept", Gtk.ResponseType.YES)
            dialog.connect("response", self._on_invitation_response)
            dialog.present()

    def _on_invitation_response(self, dialog, response) -> None:
        if response == Gtk.ResponseType.YES:
            self._network_client.accept()
            self._set_status("Invitation acceptée !")
        else:
            self._network_client.decline()
            self._set_status("Invitation refusée.")
        dialog.destroy()

    def _handle_disconnect(self, error) -> None:
        self._network_mode = False
        self._network_client = None
        if error:
            self._set_status(f"Déconnecté : {error}")
        else:
            self._set_status("Déconnecté du serveur.")

    def _runtime_config_text(self) -> str:
        walls_text = (
            "unlimited" if self._init_walls < 0 else str(self._init_walls)
        )
        return (
            "Current game configuration:\n"
            f"players={self._num_players}\n"
            f"walls_per_player={walls_text}\n"
            f"board_size={self._init_board_size}\n"
            f"blitz={self._init_blitz}\n"
            f"time_limit={self._init_time_limit}\n"
            f"ai_players={sorted(set(self._ai_players))}\n"
            f"ai_mode={self._ai_mode}\n"
            f"ai_time={self._ai_time}\n"
            f"ai_minimax_depth={self._ai_minimax_depth}"
        )

    def _parse_bool(self, raw: str, *, label: str) -> bool:
        value = raw.strip().lower()
        if value in {"true", "1", "yes", "y", "on"}:
            return True
        if value in {"false", "0", "no", "n", "off"}:
            return False
        raise ValueError(f"{label} must be true/false")

    def _parse_ai_players(self, raw: str, *, players: int) -> list[int]:
        text = raw.strip()
        if not text:
            return []
        values = text.replace(",", " ").split()
        parsed: list[int] = []
        seen: set[int] = set()
        for token in values:
            pid = int(token)
            if pid < 1 or pid > players:
                raise ValueError("ai_players ids must be between 1 and players")
            if pid not in seen:
                seen.add(pid)
                parsed.append(pid)
        return parsed

    def _apply_game_config(self, values: dict[str, str]) -> None:
        players = int(values["players"])
        size = int(values["board_size"])
        walls = int(values["walls_per_player"])
        blitz = self._parse_bool(values["blitz"], label="blitz")
        time_limit = float(values["time_limit"])
        ai_mode = values["ai_mode"].strip().lower()
        ai_time = int(values["ai_time"])
        depth_raw = values["ai_minimax_depth"].strip().lower()
        ai_depth = None if depth_raw in {"", "none", "null"} else int(depth_raw)
        ai_players = self._parse_ai_players(values["ai_players"], players=players)

        if players not in {2, 3, 4}:
            raise ValueError("players must be one of: 2, 3, 4")
        if size < 3 or size > 15 or size % 2 == 0:
            raise ValueError("board_size must be odd and between 3 and 15")
        if time_limit <= 0:
            raise ValueError("time_limit must be > 0")
        if ai_mode not in {"minimax", "iterative", "mcts"}:
            raise ValueError("ai_mode must be one of: minimax, iterative, mcts")
        if ai_time <= 0:
            raise ValueError("ai_time must be > 0")
        if ai_depth is not None and ai_depth <= 0:
            raise ValueError("ai_minimax_depth must be > 0 when set")
        if ai_mode == "minimax" and ai_depth is None:
            raise ValueError("ai_minimax_depth is required for minimax mode")

        self._num_players = players
        self._init_board_size = size
        self._init_walls = walls
        self._init_blitz = blitz
        self._init_time_limit = time_limit
        self._ai_players = sorted(set(ai_players))
        self._ai_mode = ai_mode
        self._ai_time = ai_time
        self._ai_minimax_depth = ai_depth
        self._action_new_game()
        self._set_status("Configuration applied to a new game.")

    def _show_text_window(self, title: str, text: str) -> None:
        if self._text_window is not None:
            self._text_window.destroy()
            self._text_window = None
        window = Gtk.Window(transient_for=self, title=title)
        window.set_modal(True)
        window.set_default_size(560, 420)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)

        label = Gtk.Label(label=text)
        label.set_xalign(0.0)
        label.set_wrap(True)
        root.append(label)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _btn: window.close())
        root.append(close_button)

        window.connect(
            "close-request",
            lambda win: (
                setattr(self, "_text_window", None),
                win.destroy(),
                False,
            )[2],
        )
        window.set_child(root)
        self._text_window = window
        window.present()

    def _show_game_configuration(self) -> None:
        if self._config_window is not None:
            self._config_window.present()
            return

        window = Gtk.Window(transient_for=self, title="Game configuration")
        window.set_modal(True)
        window.set_default_size(560, 560)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)

        info = Gtk.Label(
            label=(
                "Update values, then Apply. "
                "A new game will start with this configuration."
            )
        )
        info.set_wrap(True)
        info.set_xalign(0.0)
        root.append(info)

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        fields: list[tuple[str, str]] = [
            ("players", str(self._num_players)),
            ("board_size", str(self._init_board_size)),
            ("walls_per_player", str(self._init_walls)),
            ("blitz", str(self._init_blitz).lower()),
            ("time_limit", f"{self._init_time_limit:g}"),
            (
                "ai_players",
                ",".join(str(v) for v in sorted(set(self._ai_players))),
            ),
            ("ai_mode", self._ai_mode),
            ("ai_time", str(self._ai_time)),
            (
                "ai_minimax_depth",
                "none"
                if self._ai_minimax_depth is None
                else str(self._ai_minimax_depth),
            ),
        ]

        entries: dict[str, Gtk.Entry] = {}
        for row, (name, default) in enumerate(fields):
            label = Gtk.Label(label=name)
            label.set_xalign(0.0)
            entry = Gtk.Entry()
            entry.set_text(default)
            grid.attach(label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            entries[name] = entry
        root.append(grid)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        show_button = Gtk.Button(label="Show current")
        apply_button = Gtk.Button(label="Apply")
        close_button = Gtk.Button(label="Close")

        show_button.connect(
            "clicked",
            lambda _btn: self._show_text_window(
                "Current configuration", self._runtime_config_text()
            ),
        )

        def _apply(_btn) -> None:
            values = {
                name: entry.get_text().strip()
                for name, entry in entries.items()
            }
            try:
                self._apply_game_config(values)
                window.close()
            except Exception as exc:
                self._set_status(f"Configuration update failed: {exc}")

        apply_button.connect("clicked", _apply)
        close_button.connect("clicked", lambda _btn: window.close())

        buttons.append(show_button)
        buttons.append(apply_button)
        buttons.append(close_button)
        root.append(buttons)

        window.connect("close-request", self._on_config_window_closed)
        window.set_child(root)
        self._config_window = window
        window.present()

    def _on_config_window_closed(self, window: Gtk.Window):
        self._config_window = None
        window.destroy()
        return False

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
            self.session, loaded_blitz = self.service.load(
                path,
                fallback_player_types=self.session.player_types,
                fallback_walls_per_player=self.session.state.remaining_walls,
            )
            if self._blitz_timer_id is not None:
                GLib.source_remove(self._blitz_timer_id)
                self._blitz_timer_id = None
            self.blitz = loaded_blitz
            self.blitz_label.set_visible(self.blitz.is_enabled())
            self._paused = False
            self._game_over = False
            self.area.queue_draw()
            self._schedule_ai_turn()
            if (
                self.session.player_types.get(
                    self.session.state.current_player
                )
                != "ai"
            ):
                self._start_blitz_turn()
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


def main(
    num_players=2,
    board_size=9,
    walls=20,
    blitz=False,
    time_limit=0,
    ai_players=None,
    ai_mode="iterative",
    ai_time=5,
    ai_minimax_depth=None,
):
    app = Gtk.Application(application_id="fr.ubordeaux.quoridor.demo")
    app.connect(
        "activate",
        lambda a: QuoridorWindow(
            a,
            num_players=num_players,
            board_size=board_size,
            walls=walls,
            blitz=blitz,
            time_limit=time_limit,
            ai_players=ai_players,
            ai_mode=ai_mode,
            ai_time=ai_time,
            ai_minimax_depth=ai_minimax_depth,
        ).present(),
    )
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
