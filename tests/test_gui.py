from __future__ import annotations

import importlib
import sys
import types

import pytest


class _DummyLabel:
    def __init__(self) -> None:
        self.text = ""
        self.visible = True

    def set_text(self, value: str) -> None:
        self.text = value

    def set_visible(self, value: bool) -> None:
        self.visible = value


class _DummyArea:
    def __init__(self, width: int = 520, height: int = 520) -> None:
        self._width = width
        self._height = height
        self.draw_queued = False

    def get_width(self) -> int:
        return self._width

    def get_height(self) -> int:
        return self._height

    def queue_draw(self) -> None:
        self.draw_queued = True


class _DummyDialogFile:
    def __init__(self, path: str | None) -> None:
        self._path = path

    def get_path(self) -> str | None:
        return self._path


class _DummyDialog:
    def __init__(self, path: str | None) -> None:
        self._file = None if path is None else _DummyDialogFile(path)
        self.destroyed = False

    def get_file(self):
        return self._file

    def destroy(self) -> None:
        self.destroyed = True


class _DummyEntry:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def get_text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        self._text = text


class _DummyCairo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def set_source_rgb(self, *args) -> None:
        self.calls.append(("set_source_rgb", args))

    def paint(self) -> None:
        self.calls.append(("paint", ()))

    def rectangle(self, *args) -> None:
        self.calls.append(("rectangle", args))

    def fill(self) -> None:
        self.calls.append(("fill", ()))

    def set_line_width(self, *args) -> None:
        self.calls.append(("set_line_width", args))

    def stroke(self) -> None:
        self.calls.append(("stroke", ()))

    def arc(self, *args) -> None:
        self.calls.append(("arc", args))


@pytest.fixture
def gui_mod(monkeypatch):
    # Minimal gi/Gtk/Gio shim so gui.py can be imported without real GTK.
    fake_gi = types.ModuleType("gi")
    fake_repo = types.ModuleType("gi.repository")

    fake_gtk = types.SimpleNamespace(
        ApplicationWindow=type("ApplicationWindow", (), {}),
        Application=type("Application", (), {}),
        Window=type("Window", (), {}),
        Entry=type("Entry", (), {}),
        PopoverMenuBar=type("PopoverMenuBar", (), {}),
        FileChooserDialog=type("FileChooserDialog", (), {}),
        AboutDialog=type("AboutDialog", (), {}),
        GestureDrag=type("GestureDrag", (), {}),
        Label=type("Label", (), {}),
        DrawingArea=type("DrawingArea", (), {}),
        Box=type("Box", (), {}),
        Grid=type("Grid", (), {}),
        Button=type("Button", (), {}),
        Orientation=types.SimpleNamespace(VERTICAL=1, HORIZONTAL=2),
        FileChooserAction=types.SimpleNamespace(SAVE=1, OPEN=2),
        ResponseType=types.SimpleNamespace(CANCEL=0, ACCEPT=1),
    )

    class _SimpleAction:
        @staticmethod
        def new(_name, _param):
            return types.SimpleNamespace(connect=lambda *_a, **_k: None)

    fake_gio = types.SimpleNamespace(
        Menu=type("Menu", (), {}),
        SimpleAction=_SimpleAction,
    )
    fake_glib = types.SimpleNamespace(
        timeout_add=lambda *_a, **_k: 1,
        source_remove=lambda *_a, **_k: None,
        idle_add=lambda *_a, **_k: 1,
    )

    fake_gi.require_version = lambda *_a, **_k: None
    fake_repo.Gtk = fake_gtk
    fake_repo.Gio = fake_gio
    fake_repo.GLib = fake_glib
    fake_gi.repository = fake_repo

    monkeypatch.setitem(sys.modules, "gi", fake_gi)
    monkeypatch.setitem(sys.modules, "gi.repository", fake_repo)
    monkeypatch.delitem(sys.modules, "quoridor.interfaces.gui", raising=False)
    return importlib.import_module("quoridor.interfaces.gui")


def _make_window(gui_mod):
    win = gui_mod.QuoridorWindow.__new__(gui_mod.QuoridorWindow)
    win.status = _DummyLabel()
    win.blitz_label = _DummyLabel()
    win.area = _DummyArea()
    win._ox = gui_mod.MARGIN
    win._oy = gui_mod.MARGIN
    win._paused = False
    win._ai_thinking = False
    win._game_over = False
    win._turn_start_time = None
    win._blitz_timer_id = None
    win._ai_players = []
    win._num_players = 2
    win._init_board_size = 9
    win._init_walls = 10
    win._init_blitz = False
    win._init_time_limit = 0
    win._text_window = None
    win._config_window = None
    win._drag_pid = None
    win._drag_start = None
    win._drag_offset = (0, 0)
    win.blitz = types.SimpleNamespace(
        is_enabled=lambda: False,
        toggle_pause=lambda: None,
        consume_time=lambda *_a, **_k: False,
        remaining_time=lambda *_a, **_k: 0.0,
    )
    win.session = types.SimpleNamespace(
        state=types.SimpleNamespace(
            board_size=9,
            current_player=1,
            player_positions={1: 4, 2: 76},
            remaining_walls={1: 10, 2: 10},
            graph=types.SimpleNamespace(),
            vertical_walls=[],
            horizontal_walls=[],
        ),
        player_types={1: "human", 2: "human"},
        history=types.SimpleNamespace(records=[], cursor=-1),
        _build_player_target_funcs=lambda: [],
        place_wall=lambda *_args, **_kwargs: None,
        play_pawn_move=lambda *_args, **_kwargs: None,
        winner_id=lambda: None,
        game_outcome=lambda: types.SimpleNamespace(
            status="ongoing",
            winner_id=None,
            scores={1: 0, 2: 0},
        ),
    )
    return win


def test_geometry_helpers(gui_mod):
    win = _make_window(gui_mod)

    cell_size = win._cell_size()
    assert cell_size > 0

    x, y = win._cell_xy(0, 0)
    assert (x, y) == (gui_mod.MARGIN, gui_mod.MARGIN)

    assert win._xy_to_cell(x + 1, y + 1) == (0, 0)
    assert win._xy_to_cell(10_000, 10_000) is None


def test_gap_helpers(gui_mod):
    win = _make_window(gui_mod)
    cs = win._cell_size()
    step = cs + gui_mod.GAP

    vgap = win._xy_to_gap(win._ox + cs + 0.1, win._oy + 0.1)
    assert vgap == ("vertical", 0, 0)

    hgap = win._xy_to_gap(win._ox + 0.1, win._oy + cs + 0.1)
    assert hgap == ("horizontal", 0, 0)

    assert win._xy_to_gap(win._ox + step * 8 + cs + 0.1, win._oy + 0.1) is None

    edges_v, orient_v = win._gap_to_wall_edges("vertical", 0, 0)
    assert orient_v == "vertical"
    assert edges_v == [(0, 1), (9, 10)]

    edges_h, orient_h = win._gap_to_wall_edges("horizontal", 0, 0)
    assert orient_h == "horizontal"
    assert edges_h == [(0, 9), (1, 10)]

    edges_none, orient_none = win._gap_to_wall_edges("vertical", 8, 8)
    assert edges_none is None
    assert orient_none is None


def test_action_activated_handles_exceptions(gui_mod):
    win = _make_window(gui_mod)
    win.action_registry = types.SimpleNamespace(
        execute=lambda _action: (_ for _ in ()).throw(ValueError("boom"))
    )
    win._on_action_activated(None, None, object())
    assert win.status.text == "Action failed: boom"


def test_action_pause_and_hint(gui_mod):
    win = _make_window(gui_mod)

    win._action_pause()
    assert win._paused is True
    assert win.status.text == "Game paused."

    win._action_hint()
    assert win.status.text == "Game is paused."

    win._paused = False
    win.service = types.SimpleNamespace(
        hint=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("no move"))
    )
    win._action_hint()
    assert win.status.text == "Hint unavailable: no move"

    win.service = types.SimpleNamespace(hint=lambda **_kwargs: ("pawn", 13))
    win._action_hint()
    assert win.status.text == "Hint for player 1: e1-e2"

    win.service = types.SimpleNamespace(
        hint=lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Game is over. No hint available.")
        )
    )
    win._action_hint()
    assert win.status.text == "Game is over. No hint available."


def test_action_show_time(gui_mod):
    win = _make_window(gui_mod)

    win._action_show_time()
    assert win.status.text == "Blitz mode is not enabled."

    shown = {"title": None, "text": None}
    win._show_text_window = lambda title, text: shown.update(
        {"title": title, "text": text}
    )
    win.blitz = types.SimpleNamespace(
        is_enabled=lambda: True,
        remaining_times=lambda: {1: 60.0, 2: 45.0},
    )
    win._action_show_time()
    assert "Blitz time -> Player 1: 01:00, Player 2: 00:45" in win.status.text
    assert shown["title"] == "Remaining Time"


def test_history_text_and_action(gui_mod, monkeypatch):
    win = _make_window(gui_mod)
    rec1 = types.SimpleNamespace(
        action="move_pawn",
        before_state={"board_size": 9, "player_positions": {1: 4}},
        after_state={"board_size": 9, "player_positions": {1: 13}},
        player_id=1,
    )
    rec2 = types.SimpleNamespace(
        action="move_pawn",
        before_state={"board_size": 9, "player_positions": {2: 76}},
        after_state={"board_size": 9, "player_positions": {2: 67}},
        player_id=2,
    )
    win.session.history = types.SimpleNamespace(records=[rec1, rec2], cursor=1)

    monkeypatch.setattr(
        gui_mod,
        "record_to_notation",
        lambda rec: "e1-e2" if rec.player_id == 1 else "e9-e8",
    )

    shown = {"title": None, "text": None}
    win._show_text_window = lambda title, text: shown.update(
        {"title": title, "text": text}
    )
    win._action_show_history()
    assert shown["title"] == "Move History"
    assert "[history]" in shown["text"]
    assert "1 e1-e2; 2 e9-e8;" in shown["text"]


def test_apply_game_config_updates_runtime_and_restarts(gui_mod):
    win = _make_window(gui_mod)
    called = {"new_game": 0}
    win._action_new_game = lambda: called.__setitem__(
        "new_game", called["new_game"] + 1
    )

    win._apply_game_config(
        {
            "players": "4",
            "board_size": "11",
            "walls_per_player": "8",
            "blitz": "true",
            "time_limit": "1.5",
            "ai_players": "2,4",
            "ai_mode": "iterative",
            "ai_time": "3",
            "ai_minimax_depth": "5",
        }
    )

    assert win._num_players == 4
    assert win._init_board_size == 11
    assert win._init_walls == 8
    assert win._init_blitz is True
    assert win._init_time_limit == 1.5
    assert win._ai_players == [2, 4]
    assert win._ai_mode == "iterative"
    assert win._ai_time == 3
    assert win._ai_minimax_depth == 5
    assert called["new_game"] == 1
    assert win.status.text == "Configuration applied to a new game."


def test_apply_game_config_accepts_auto_depth_for_minimax(gui_mod):
    win = _make_window(gui_mod)
    called = {"new_game": 0}
    win._action_new_game = lambda: called.__setitem__(
        "new_game", called["new_game"] + 1
    )

    win._apply_game_config(
        {
            "players": "2",
            "board_size": "9",
            "walls_per_player": "20",
            "blitz": "false",
            "time_limit": "1",
            "ai_players": "2",
            "ai_mode": "minimax",
            "ai_time": "5",
            "ai_minimax_depth": "none",
        }
    )

    assert win._ai_mode == "minimax"
    assert win._ai_minimax_depth is None
    assert called["new_game"] == 1


def test_action_show_config_routes_to_game_configuration(gui_mod):
    win = _make_window(gui_mod)
    called = {"config": 0, "shortcuts": 0}
    win._show_game_configuration = lambda: called.__setitem__(
        "config", called["config"] + 1
    )
    win._show_shortcut_configuration = lambda: called.__setitem__(
        "shortcuts", called["shortcuts"] + 1
    )

    win._action_show_config()
    win._action_show_shortcuts()
    assert called == {"config": 1, "shortcuts": 1}


def test_undo_redo_actions(gui_mod):
    win = _make_window(gui_mod)

    win.service = types.SimpleNamespace(
        undo_groups=lambda **_kwargs: (1, 0),
        redo_groups=lambda **_kwargs: (1, 0),
    )
    win._action_undo()
    assert win.status.text == "Nothing to undo."
    win._action_redo()
    assert win.status.text == "Nothing to redo."

    win.service = types.SimpleNamespace(
        undo_groups=lambda **_kwargs: (1, 2),
        redo_groups=lambda **_kwargs: (1, 3),
    )
    win._action_undo()
    assert win.status.text == "Undid 2 move(s)."
    assert win.area.draw_queued is True

    win.area.draw_queued = False
    win._action_redo()
    assert win.status.text == "Redid 3 move(s)."
    assert win.area.draw_queued is True

    win.service = types.SimpleNamespace(
        undo_groups=lambda **_kwargs: (_ for _ in ()).throw(ValueError("u")),
        redo_groups=lambda **_kwargs: (_ for _ in ()).throw(ValueError("r")),
    )
    win._action_undo()
    assert win.status.text == "Undo failed: u"
    win._action_redo()
    assert win.status.text == "Redo failed: r"


def test_save_response_branches(gui_mod):
    win = _make_window(gui_mod)
    win.service = types.SimpleNamespace(save=lambda _path: None)

    dialog = _DummyDialog(path=None)
    win._on_save_response(dialog, gui_mod.Gtk.ResponseType.CANCEL)
    assert win.status.text == "Save cancelled."
    assert dialog.destroyed is True

    dialog = _DummyDialog(path=None)
    win._on_save_response(dialog, gui_mod.Gtk.ResponseType.ACCEPT)
    assert win.status.text == "Save failed: invalid file path."
    assert dialog.destroyed is True

    dialog = _DummyDialog(path="/tmp/game.qrd")
    win._on_save_response(dialog, gui_mod.Gtk.ResponseType.ACCEPT)
    assert win.status.text == "Saved to: /tmp/game.qrd"

    win.service = types.SimpleNamespace(
        save=lambda _path: (_ for _ in ()).throw(OSError("disk"))
    )
    dialog = _DummyDialog(path="/tmp/game.qrd")
    win._on_save_response(dialog, gui_mod.Gtk.ResponseType.ACCEPT)
    assert win.status.text == "Save failed: disk"


def test_load_response_branches(gui_mod):
    win = _make_window(gui_mod)

    dialog = _DummyDialog(path=None)
    win._on_load_response(dialog, gui_mod.Gtk.ResponseType.CANCEL)
    assert win.status.text == "Load cancelled."
    assert dialog.destroyed is True

    dialog = _DummyDialog(path=None)
    win._on_load_response(dialog, gui_mod.Gtk.ResponseType.ACCEPT)
    assert win.status.text == "Load failed: invalid file path."

    new_session = types.SimpleNamespace(
        state=types.SimpleNamespace(
            board_size=9,
            current_player=2,
            player_positions={1: 13, 2: 67},
            remaining_walls={1: 10, 2: 10},
            graph=types.SimpleNamespace(),
            vertical_walls=[],
            horizontal_walls=[],
        ),
        player_types={1: "human", 2: "human"},
    )
    loaded_blitz = types.SimpleNamespace(
        is_enabled=lambda: False,
        toggle_pause=lambda: None,
        consume_time=lambda *_a, **_k: False,
        remaining_time=lambda *_a, **_k: 0.0,
    )
    win._paused = True
    win._game_over = True
    win.service = types.SimpleNamespace(
        load=lambda *_args, **_kwargs: (new_session, loaded_blitz)
    )
    dialog = _DummyDialog(path="/tmp/game.qrd")
    win._on_load_response(dialog, gui_mod.Gtk.ResponseType.ACCEPT)
    assert win.session is new_session
    assert win._paused is False
    assert win._game_over is False
    assert win.status.text == "Loaded from: /tmp/game.qrd"

    win.service = types.SimpleNamespace(
        load=lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad"))
    )
    dialog = _DummyDialog(path="/tmp/game.qrd")
    win._on_load_response(dialog, gui_mod.Gtk.ResponseType.ACCEPT)
    assert win.status.text == "Load failed: bad"


def test_action_routing_new_game_show_info_quit(gui_mod, monkeypatch):
    win = _make_window(gui_mod)

    new_session = types.SimpleNamespace(state=win.session.state, player_types={})
    win._build_new_session = lambda **_kwargs: new_session
    called = {"ctx": None, "closed": False, "presented": False}
    win.service = types.SimpleNamespace(
        set_context=lambda **kwargs: called.__setitem__("ctx", kwargs)
    )
    win.close = lambda: called.__setitem__("closed", True)

    class _About:
        def __init__(self, **_kwargs) -> None:
            pass

        def present(self) -> None:
            called["presented"] = True

    monkeypatch.setattr(gui_mod.Gtk, "AboutDialog", _About)

    win._action_new_game()
    assert win.session is new_session
    assert called["ctx"]["session"] is new_session
    assert called["ctx"]["blitz"] is win.blitz
    assert called["ctx"]["blitz"].is_enabled() is False
    assert win.status.text == "New game started."

    win._action_show_info()
    assert called["presented"] is True

    win._action_quit()
    assert called["closed"] is True


def test_action_load_save_routing(gui_mod):
    win = _make_window(gui_mod)
    called = {"load": 0, "save": 0}
    win._on_load_clicked = lambda _btn: called.__setitem__(
        "load", called["load"] + 1
    )
    win._on_save_clicked = lambda _btn: called.__setitem__(
        "save", called["save"] + 1
    )
    win._action_load_game()
    win._action_save_game()
    assert called == {"load": 1, "save": 1}


def test_shortcut_helpers(gui_mod):
    win = _make_window(gui_mod)
    action_types = list(gui_mod.ActionType)
    entries = {a: _DummyEntry("x") for a in action_types}
    win._reset_shortcut_entries(entries)
    defaults = gui_mod.ShortcutManager.with_defaults()
    for action in action_types:
        assert entries[action].get_text() == defaults.get(action)

    save_called = {"ok": False, "bind": False}
    win.config_manager = types.SimpleNamespace(
        save_shortcuts=lambda _manager: save_called.__setitem__("ok", True)
    )
    win._bind_shortcuts = lambda: save_called.__setitem__("bind", True)
    window = types.SimpleNamespace(
        close=lambda: save_called.__setitem__("closed", True)
    )
    win._save_shortcut_entries(window, entries)
    assert save_called["ok"] is True
    assert save_called["bind"] is True
    assert save_called["closed"] is True
    assert win.status.text == "Shortcut configuration saved."

    bad_entries = {a: _DummyEntry("<Primary>n") for a in action_types}
    win._save_shortcut_entries(window, bad_entries)
    assert "Shortcut save failed:" in win.status.text


def test_shortcut_window_closed(gui_mod):
    win = _make_window(gui_mod)
    win._shortcut_window = object()
    win._shortcut_entries = {gui_mod.ActionType.NEW_GAME: _DummyEntry("a")}
    destroyed = {"ok": False}
    window = types.SimpleNamespace(destroy=lambda: destroyed.__setitem__("ok", True))
    assert win._on_shortcut_window_closed(window) is False
    assert win._shortcut_window is None
    assert win._shortcut_entries == {}
    assert destroyed["ok"] is True


def test_dialog_openers_attach_handlers(gui_mod, monkeypatch):
    win = _make_window(gui_mod)
    seen = {"save": None, "load": None}

    class _Chooser:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.buttons = []
            self.connected = None
            self.presented = False

        def add_button(self, label, response):
            self.buttons.append((label, response))

        def connect(self, signal, callback):
            self.connected = (signal, callback)

        def present(self):
            self.presented = True

    def factory(**kwargs):
        obj = _Chooser(**kwargs)
        key = (
            "save"
            if kwargs["action"] == gui_mod.Gtk.FileChooserAction.SAVE
            else "load"
        )
        seen[key] = obj
        return obj

    monkeypatch.setattr(gui_mod.Gtk, "FileChooserDialog", factory)
    win._on_save_clicked(None)
    win._on_load_clicked(None)
    assert seen["save"].connected[0] == "response"
    assert seen["save"].presented is True
    assert seen["load"].connected[0] == "response"
    assert seen["load"].presented is True


def test_draw_helpers(gui_mod):
    win = _make_window(gui_mod)
    cr = _DummyCairo()

    win._update_origin(10.0, 9)
    assert isinstance(win._ox, float)
    assert isinstance(win._oy, float)

    win._draw_background(cr)
    assert ("paint", ()) in cr.calls

    before = len(cr.calls)
    win._draw_cells(cr, 10.0, 2)
    assert len(cr.calls) > before

    win.session.state.vertical_walls = [(0, 1)]
    win.session.state.horizontal_walls = [(0, 9)]
    before = len(cr.calls)
    win._draw_walls(cr, 10.0, 9)
    assert len(cr.calls) > before

    win.session.state.player_positions = {1: 0, 9: 10}
    before = len(cr.calls)
    win._draw_players(cr, 10.0, 9)
    assert len(cr.calls) > before

    calls = {"bg": 0, "cells": 0, "walls": 0, "players": 0}
    win._draw_background = lambda _cr: calls.__setitem__("bg", calls["bg"] + 1)
    win._draw_cells = lambda _cr, _cs, _size: calls.__setitem__(
        "cells",
        calls["cells"] + 1,
    )
    win._draw_walls = lambda _cr, _cs, _size: calls.__setitem__(
        "walls",
        calls["walls"] + 1,
    )
    win._draw_players = lambda _cr, _cs, _size: calls.__setitem__(
        "players",
        calls["players"] + 1,
    )
    win._draw(None, object(), 0, 0)
    assert calls == {"bg": 1, "cells": 1, "walls": 1, "players": 1}


def test_drag_handlers(gui_mod, monkeypatch):
    win = _make_window(gui_mod)

    win._paused = True
    win._on_drag_begin(None, 0, 0)
    assert win.status.text == "Game is paused."
    win._paused = False
    win._game_over = True
    win._on_drag_begin(None, 0, 0)
    assert win.status.text == "Game is over. Start a new game."
    win._game_over = False

    x, y = win._cell_xy(0, 4)
    win._on_drag_begin(None, x + 1, y + 1)
    assert win._drag_pid == 1
    assert win._drag_start is not None

    win._on_drag_update(None, 5, 7)
    assert win._drag_offset == (5, 7)
    assert win.area.draw_queued is True

    monkeypatch.setattr(
        gui_mod,
        "validate_pawn_move",
        lambda *_a, **_k: (False, "blocked"),
    )
    win._on_drag_end(None, 0, gui_mod.GAP + win._cell_size())
    assert win.status.text == "blocked"
    assert win._drag_pid is None

    # Wall placement path from gap.
    called = {"wall": 0}
    win.session.place_wall = lambda *_a, **_k: called.__setitem__(
        "wall",
        called["wall"] + 1,
    )
    monkeypatch.setattr(gui_mod, "validate_wall", lambda *_a, **_k: (True, ""))
    cs = win._cell_size()
    win._on_drag_begin(None, win._ox + cs + 0.1, win._oy + 0.1)
    assert called["wall"] == 1

    # Successful pawn move and winner branch.
    win._drag_pid = 1
    win._drag_start = (x + 1, y + 1)
    monkeypatch.setattr(
        gui_mod,
        "validate_pawn_move",
        lambda *_a, **_k: (True, ""),
    )
    win.session.play_pawn_move = lambda *_a, **_k: None
    win.session.game_outcome = lambda: types.SimpleNamespace(
        status="winner",
        winner_id=1,
        scores={1: 1, 2: 0},
    )
    win._on_drag_end(None, 0, gui_mod.GAP + win._cell_size())
    assert win.status.text == "Player 1 wins!"

    # Successful pawn move and draw branch.
    win._game_over = False
    win._drag_pid = 1
    win._drag_start = (x + 1, y + 1)
    win.session.game_outcome = lambda: types.SimpleNamespace(
        status="draw",
        winner_id=None,
        scores={1: 0, 2: 0},
    )
    win._on_drag_end(None, 0, gui_mod.GAP + win._cell_size())
    assert win.status.text == "Draw game."
