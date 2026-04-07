from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import quoridor.interfaces as interfaces_pkg
from quoridor.application.blitz import Blitz
from quoridor.application.game_session import GameSession
from quoridor.core.game_state import GameState
from quoridor.interfaces import cli as cli_mod
from quoridor.interfaces import cli_shell
from quoridor.interfaces.cli_render import _render_ascii_board

MAIN_DEFAULTS = {
    "time": 30,
    "players": 2,
    "walls": 20,
    "size": 9,
    "verbose": False,
    "blitz": False,
    "ai_minimax_scoring": 1,
}

SHELL_DEFAULTS = {
    "blitz": False,
    "time_limit": 30,
    "save_file": None,
    "players": 2,
    "walls_per_player": 20,
    "board_size": 9,
    "ai_players": [],
    "ai_mode": "minimax",
    "ai_time": 5,
    "ai_minimax_depth": 2,
    "ai_minimax_scoring": 1,
    "verbose": False,
    "debug": False,
}


def patch_main_defaults(monkeypatch, **overrides):
    defaults = dict(MAIN_DEFAULTS)
    defaults.update(overrides)
    monkeypatch.setattr(cli_mod, "setup_i18n", lambda: None)
    monkeypatch.setattr(cli_mod, "load_or_init_config", lambda: defaults)
    return defaults


def make_gui_args(
    players: int = 2,
    size: int = 9,
    walls: int = 20,
    blitz: bool = False,
    time: int = 30,
):
    return SimpleNamespace(
        players=players,
        size=size,
        walls=walls,
        blitz=blitz,
        time=time,
    )


def run_shell(monkeypatch, capsys, commands: list[str], **overrides):
    iterator = iter(commands)

    def fake_input(prompt: str = "") -> str:
        if prompt:
            print(prompt, end="")
        try:
            return next(iterator)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr("builtins.input", fake_input)
    shell_options = dict(SHELL_DEFAULTS)
    shell_options.update(overrides)
    cli_mod._run_interactive_shell(**shell_options)
    return capsys.readouterr()


# Interactive shell scenarios

def test_help_commands_explain_available_actions(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["help", "help new", "help set", "help show history", "quit"],
    )

    out = captured.out
    assert "Commands: new [ARGS], help [CMD], load, save, set, hint" in out
    assert "Start a new game." in out
    assert "set PARAM=VALUE" in out
    assert "Show the played moves grouped by turns." in out


def test_hint_uses_minimax_depth_from_runtime_settings(monkeypatch, capsys):
    called = {"depth": None, "score": None}

    def fake_minimax(state, ai_player_id, depth, eval_fn):
        called["depth"] = depth
        called["score"] = eval_fn(state, ai_player_id)
        return (
            "pawn",
            state.player_positions[ai_player_id] + state.board_size,
        )

    monkeypatch.setattr(cli_mod, "find_best_move_minimax", fake_minimax)

    captured = run_shell(monkeypatch, capsys, ["hint", "quit"])

    assert "Best hint action: e1-e2" in captured.out
    assert called["depth"] == 2
    assert isinstance(called["score"], float)


def test_hint_uses_iterative_time_limit_when_requested(monkeypatch, capsys):
    called = {"time_limit_sec": None, "max_depth": None, "score": None}

    def fake_iterative(state, ai_player_id, eval_fn, time_limit_sec, max_depth):
        called["time_limit_sec"] = time_limit_sec
        called["max_depth"] = max_depth
        called["score"] = eval_fn(state, ai_player_id)
        return (
            "pawn",
            state.player_positions[ai_player_id] + state.board_size,
        )

    monkeypatch.setattr(cli_mod, "find_best_move_iterative", fake_iterative)

    captured = run_shell(
        monkeypatch,
        capsys,
        ["hint", "quit"],
        ai_mode="iterative",
        ai_time=3,
    )

    assert "Best hint action: e1-e2" in captured.out
    assert called["time_limit_sec"] == 3
    assert called["max_depth"] == 2
    assert isinstance(called["score"], float)


def test_hint_uses_mcts_time_limit_when_requested(monkeypatch, capsys):
    called = {"time_limit": None}

    def fake_mcts(state, time_limit):
        called["time_limit"] = time_limit
        return ("pawn", state.player_positions[state.current_player] + 9)

    monkeypatch.setattr(cli_mod, "mcts_search", fake_mcts)

    captured = run_shell(
        monkeypatch,
        capsys,
        ["hint", "quit"],
        ai_mode="mcts",
        ai_time=7,
    )

    assert "Best hint action: e1-e2" in captured.out
    assert called["time_limit"] == 7


def test_hint_keyboard_interrupt_is_handled_cleanly(monkeypatch, capsys):
    def fake_handle_hint(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_shell, "_handle_hint", fake_handle_hint)

    captured = run_shell(monkeypatch, capsys, ["hint", "quit"])

    assert "Hint interrupted." in captured.out
    assert "Traceback" not in captured.err


def test_hint_reports_game_over_message_without_prefix(monkeypatch, capsys):
    def fake_handle_hint(*_args, **_kwargs):
        raise ValueError("Game is over. No hint available.")

    monkeypatch.setattr(cli_shell, "_handle_hint", fake_handle_hint)

    captured = run_shell(monkeypatch, capsys, ["hint", "quit"])

    assert "Game is over. No hint available." in captured.out
    assert "No hint available: Game is over. No hint available." not in captured.out


def test_shorthand_pawn_move_is_case_insensitive(monkeypatch, capsys):
    captured = run_shell(monkeypatch, capsys, ["E1-E2", "quit", "n"])

    assert "Player 1: e2, Player 2: e9" in captured.out
    assert "Save the game before quitting? [y/N]" in captured.out


def test_shorthand_wall_move_is_case_insensitive(monkeypatch, capsys):
    captured = run_shell(monkeypatch, capsys, ["G4V", "quit", "n"])

    assert "Walls -> Player 1: 19, Player 2: 20" in captured.out


def test_show_board_does_not_repeat_the_state_summary(monkeypatch, capsys):
    captured = run_shell(monkeypatch, capsys, ["show board", "quit"])

    assert captured.out.count("Current player:") == 1


def test_ascii_board_uses_dot_separators_in_empty_spaces():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )

    board = _render_ascii_board(state)
    assert "1 . _" in board
    assert "\n    . . ." in board


def test_ascii_board_keeps_walls_as_x_and_dots_elsewhere():
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[(33, 34), (42, 43)],
        horizontal_walls=[(33, 42), (34, 43)],
    )

    board = _render_ascii_board(state)
    assert "X" in board
    assert "." in board


def test_commands_are_case_insensitive(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["SHOW TIME", "HeLp ShOw HiStoRy", "QUIT"],
    )

    out = captured.out
    assert "Blitz mode is not enabled." in out
    assert "Show the played moves grouped by turns." in out
    assert "Bye." in out


def test_save_and_load_restore_the_game_and_history(
    monkeypatch,
    capsys,
    tmp_path: Path,
):
    save_path = tmp_path / "game.txt"
    captured = run_shell(
        monkeypatch,
        capsys,
        [
            "e1-e2",
            "e9-e8",
            f"save {save_path}",
            f"load {save_path}",
            "show history",
            "quit",
            "n",
        ],
    )

    out = captured.out
    assert f"Game saved to {save_path}" in out
    assert f"Game loaded from {save_path}" in out
    assert "Player 1: e2, Player 2: e9" in out
    assert "Player 1: e2, Player 2: e8" in out
    assert "[history]" in out
    assert "1 e1-e2; 2 e9-e8;" in out
    assert save_path.exists()
    saved = save_path.read_text(encoding="utf-8")
    assert "[history]" in saved
    assert "1 e1-e2; 2 e9-e8;" in saved


def test_save_and_load_restore_program_settings(monkeypatch, capsys, tmp_path: Path):
    save_path = tmp_path / "config-save.txt"
    captured = run_shell(
        monkeypatch,
        capsys,
        [
            "set debug=true",
            "set ai_mode=minimax",
            "set ai_time=6",
            "set ai_minimax_depth=4",
            "set ai_minimax_scoring=2",
            "set ai_mcts_selection=ML",
            f"save {save_path}",
            "set debug=false",
            "set ai_mode=iterative",
            "set ai_time=2",
            "set ai_minimax_depth=1",
            "set ai_minimax_scoring=1",
            "set ai_mcts_selection=UCT",
            f"load {save_path}",
            "show configuration",
            "quit",
        ],
    )

    out = captured.out
    load_idx = out.index(f"Game loaded from {save_path}")
    after_load = out[load_idx:]

    assert "debug=true" in save_path.read_text(encoding="utf-8")
    assert "ai-mode=minimax" in save_path.read_text(encoding="utf-8")
    assert "ai-time=6" in save_path.read_text(encoding="utf-8")
    assert "ai-minimax-depth=4" in save_path.read_text(encoding="utf-8")
    assert "ai-minimax-scoring=2" in save_path.read_text(encoding="utf-8")
    assert "ai-mcts-selection=ML" in save_path.read_text(encoding="utf-8")
    assert "Current configuration:" in after_load
    assert "debug=True" in after_load
    assert "ai_mode=minimax" in after_load
    assert "ai_time=6" in after_load
    assert "ai_minimax_depth=4" in after_load
    assert "ai_minimax_scoring=2" in after_load
    assert "ai_mcts_selection=ML" in after_load


def test_quit_without_changes_skips_the_save_prompt(monkeypatch, capsys):
    captured = run_shell(monkeypatch, capsys, ["quit"])

    assert "Save the game before quitting?" not in captured.out


def test_quit_after_changes_prompts_for_save(monkeypatch, capsys):
    captured = run_shell(monkeypatch, capsys, ["e1-e2", "quit", "n"])

    assert "Save the game before quitting? [y/N]" in captured.out


def test_undo_and_redo_restore_the_previous_state(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["e1-e2", "e9-e8", "undo 2", "redo 2", "quit", "n"],
    )

    out = captured.out
    assert "Undone groups: 2, moves: 2" in out
    assert "Redone groups: 2, moves: 2" in out
    assert "Player 1: e2, Player 2: e8" in out


def test_undo_and_redo_reject_invalid_counts(monkeypatch, capsys):
    captured = run_shell(monkeypatch, capsys, ["undo 0", "redo abc", "quit"])

    out = captured.out
    assert "Invalid command: N must be > 0" in out
    assert "Invalid command: N must be an integer" in out


def test_show_history_prints_turns_grouped_by_move(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["e1-e2", "e9-e8", "show history", "quit", "n"],
    )

    assert "[history]" in captured.out
    assert "1 e1-e2; 2 e9-e8;" in captured.out


def test_new_resets_the_session_and_clears_unsaved_changes(
    monkeypatch,
    capsys,
):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["e1-e2", "e9-e8", "new", "show history", "quit"],
    )

    out = captured.out
    assert out.count("New game started with default options.") == 2
    assert "[history]" in out
    assert "1 e1-e2; 2 e9-e8;" not in out
    assert "Save the game before quitting?" not in out


def test_new_accepts_cli_style_options(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        [
            (
                "new --players 4 --walls -1 --size 11 --blitz --time 0.5 "
                "--ai-player 2 --ai-player 4 --ai-mode iterative "
                "--ai-time 3 --ai-minimax-depth 5 --ai-minimax-scoring 3"
            ),
            "show configuration",
            "quit",
        ],
    )

    out = captured.out
    assert "blitz: 0.5 min/player" in out
    assert "players=4" in out
    assert "walls_per_player=unlimited" in out
    assert "board_size=11" in out
    assert "ai_players=[2, 4]" in out
    assert "ai_mode=iterative" in out
    assert "ai_time=3" in out
    assert "ai_minimax_depth=5" in out
    assert "ai_minimax_scoring=3" in out
    assert "blitz=True" in out
    assert "time_limit=0.5" in out


# Scenario: changing defaults is not enough on its own. The next `new`
# command is what applies them to a fresh session.
def test_set_updates_defaults_and_new_reuses_them(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        [
            "set verbose=true",
            "set debug=true",
            "set blitz=true",
            "set time=0.5",
            "set players=4",
            "set walls=-1",
            "set size=11",
            "set ai_players=2,4",
            "set ai_mode=iterative",
            "set ai_time=3",
            "set ai_minimax_depth=5",
            "set ai_minimax_scoring=2",
            "show configuration",
            "new",
            "show configuration",
            "quit",
        ],
    )

    out = captured.out
    assert "Configuration updated: verbose=True" in out
    assert "Configuration updated: debug=True" in out
    assert "Configuration updated: blitz=True" in out
    assert "Configuration updated: time_limit=0.5" in out
    assert "Configuration updated: players=4" in out
    assert "Configuration updated: walls_per_player=-1" in out
    assert "Configuration updated: board_size=11" in out
    assert "Configuration updated: ai_players=[2, 4]" in out
    assert "Configuration updated: ai_mode=iterative" in out
    assert "Configuration updated: ai_time=3" in out
    assert "Configuration updated: ai_minimax_depth=5" in out
    assert "Configuration updated: ai_minimax_scoring=2" in out
    assert "New game started (blitz: 0.5 min/player)." in out
    assert "verbose=True" in out
    assert "debug=True" in out
    assert out.count("players=4") >= 2
    assert "walls_per_player=unlimited" in out
    assert "board_size=11" in out
    assert "ai_players=[2, 4]" in out
    assert "ai_mode=iterative" in out
    assert "ai_time=3" in out
    assert "ai_minimax_depth=5" in out
    assert "ai_minimax_scoring=2" in out
    assert "blitz=True" in out
    assert "time_limit=0.5" in out


def test_new_applies_logging_configuration_from_set(monkeypatch, capsys):
    calls: list[tuple[bool, bool]] = []

    monkeypatch.setattr(
        cli_mod,
        "_configure_logging",
        lambda verbose, debug: calls.append((verbose, debug)),
    )

    run_shell(
        monkeypatch,
        capsys,
        ["set verbose=true", "set debug=true", "new", "quit"],
    )

    assert calls == [(True, True)]


def test_set_ai_players_only_affects_the_next_game(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["set ai_players=2", "e1-e2", "quit", "n"],
    )

    out = captured.out
    assert "Configuration updated: ai_players=[2]" in out
    assert "Use 'new' to apply this setting to a fresh game." in out
    assert "AI player 2 played." not in out
    assert "Current player: 2" in out


def test_set_ai_search_settings_apply_only_after_new(monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    def fake_compute_ai_move(self, **kwargs):
        calls.append(kwargs)
        current = self.state.current_player
        target = self.state.player_positions[current] - self.state.board_size
        return ("pawn", target)

    monkeypatch.setattr(GameSession, "compute_ai_move", fake_compute_ai_move)

    captured = run_shell(
        monkeypatch,
        capsys,
        [
            "set ai_mode=iterative",
            "set ai_time=1",
            "set ai_minimax_depth=5",
            "set ai_minimax_scoring=3",
            "e1-e2",
            "quit",
            "n",
        ],
        ai_players=[2],
        ai_mode="minimax",
        ai_time=7,
        ai_minimax_depth=2,
        ai_minimax_scoring=1,
    )

    out = captured.out
    assert "Configuration updated: ai_mode=iterative" in out
    assert "Configuration updated: ai_time=1" in out
    assert "Configuration updated: ai_minimax_depth=5" in out
    assert "Configuration updated: ai_minimax_scoring=3" in out
    assert len(calls) == 1
    assert calls[0]["mode"] == "minimax"
    assert calls[0]["time_limit_sec"] == 7
    assert calls[0]["depth"] == 2
    assert calls[0]["minimax_scoring"] == 1


def test_set_rejects_invalid_format_and_values(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["set", "set unknown=1", "set ai_players=3", "quit"],
    )

    out = captured.out
    assert "Invalid format. Use: set PARAM=VALUE" in out
    assert "unknown setting: unknown" in out
    assert "ai_players ids must be <= players" in out

    captured = run_shell(monkeypatch, capsys, ["set blitz=maybe", "quit"])
    assert "boolean value expected (true/false)" in captured.out


def test_load_and_save_without_file_show_explicit_usage_errors(
    monkeypatch, capsys
):
    captured = run_shell(monkeypatch, capsys, ["load", "save", "quit"])

    out = captured.out
    assert "Invalid format. Use: load FILE" in out
    assert "Invalid format. Use: save FILE" in out
    assert "Bye." in out


def test_show_configuration_prints_runtime_settings(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        ["show configuration", "quit"],
        blitz=True,
        time_limit=0.5,
        players=4,
        walls_per_player=-1,
        board_size=11,
        ai_players=[2, 4],
        ai_mode="minimax",
        ai_time=9,
        ai_minimax_depth=3,
        ai_minimax_scoring=2,
    )

    out = captured.out
    assert "Current configuration:" in out
    assert "players=4" in out
    assert "walls_per_player=unlimited" in out
    assert "board_size=11" in out
    assert "ai_players=[2, 4]" in out
    assert "ai_minimax_scoring=2" in out
    assert "blitz=True" in out
    assert "time_limit=0.5" in out


def test_show_time_and_pause_report_blitz_state(monkeypatch, capsys):
    moments = iter([0.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    monkeypatch.setattr(cli_shell.time, "time", lambda: next(moments))

    captured = run_shell(
        monkeypatch,
        capsys,
        ["show time", "pause", "show time", "quit"],
        blitz=True,
        time_limit=1,
    )

    out = captured.out
    assert "Blitz time -> Player 1: 00:50, Player 2: 01:00" in out
    assert "Blitz timer paused." in out
    assert "Timer paused: yes" in out


def test_pause_blocks_gameplay_commands_until_resumed(monkeypatch, capsys):
    captured = run_shell(
        monkeypatch,
        capsys,
        [
            "pause",
            "move e1-e2",
            "hint",
            "undo",
            "redo",
            "pause",
            "move e1-e2",
            "quit",
            "n",
        ],
        blitz=True,
        time_limit=1,
    )

    out = captured.out
    assert "Blitz timer paused." in out
    assert out.count("Game is paused.") == 4
    assert "Blitz timer resumed." in out
    assert "Player 1: e2, Player 2: e9" in out


def test_pause_also_blocks_gameplay_when_blitz_is_disabled(
    monkeypatch,
    capsys,
):
    captured = run_shell(
        monkeypatch,
        capsys,
        [
            "pause",
            "move e1-e2",
            "hint",
            "pause",
            "move e1-e2",
            "quit",
            "n",
        ],
        blitz=False,
    )

    out = captured.out
    assert "Game paused." in out
    assert out.count("Game is paused.") >= 2
    assert "Game resumed." in out
    assert "Player 1: e2, Player 2: e9" in out


def test_auto_play_ai_does_not_run_while_blitz_is_paused(monkeypatch):
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types={1: "ai", 2: "human"})
    blitz = Blitz(time_limit_minutes=1, player_ids=[1, 2])
    blitz.toggle_pause()

    called = {"count": 0}

    def fake_compute_ai_move(**_kwargs):
        called["count"] += 1
        return ("pawn", 13)

    monkeypatch.setattr(session, "compute_ai_move", fake_compute_ai_move)

    assert (
        cli_mod._auto_play_ai_until_human_or_end(
            session,
            ai_mode="iterative",
            ai_time=5,
            ai_minimax_depth=2,
            blitz=blitz,
        )
        is False
    )
    assert called["count"] == 0
    assert session.state.player_positions[1] == 4
    assert session.state.current_player == 1


def test_blitz_timeout_causes_an_immediate_loss(monkeypatch, capsys):
    moments = iter([0.0, 61.0])
    monkeypatch.setattr(cli_shell.time, "time", lambda: next(moments))

    captured = run_shell(
        monkeypatch,
        capsys,
        ["quit"],
        blitz=True,
        time_limit=1,
    )

    out = captured.out
    assert "Player 1 ran out of time and loses." in out
    assert "Player 2 wins!" in out


def test_cli_reports_draw_when_draw_condition_is_met(monkeypatch, capsys):
    def fake_new_session(_config):
        state = GameState(
            board_size=9,
            current_player=1,
            player_positions={1: 4, 2: 76},
            remaining_walls={1: 20, 2: 20},
            vertical_walls=[],
            horizontal_walls=[],
        )
        return GameSession(
            state=state,
            player_types={1: "human", 2: "human"},
            draw_turn_limit=1,
        )

    monkeypatch.setattr(cli_shell, "_create_new_session", fake_new_session)

    captured = run_shell(
        monkeypatch,
        capsys,
        ["move e1-e2", "quit", "n"],
        blitz=False,
    )

    assert "Draw game." in captured.out


def test_format_hint_move_formats_wall_and_unknown_moves():
    wall_move = ("wall", [(10, 11), (19, 20)], "horizontal")

    assert cli_mod._format_hint_move(
        wall_move,
        from_node=0,
        size=9,
    ).endswith("h")
    assert cli_mod._format_hint_move(
        ("other", 123),
        from_node=0,
        size=9,
    ) == "('other', 123)"


# CLI helper and entry-point tests

def test_cli_type_helpers_validate_values_and_flags():
    assert cli_mod._players_type("2") == 2
    assert cli_mod._size_type("9") == 9
    assert cli_mod._player_id_type("4") == 4

    with pytest.raises(argparse.ArgumentTypeError):
        cli_mod._players_type("x")
    with pytest.raises(argparse.ArgumentTypeError):
        cli_mod._players_type("5")
    with pytest.raises(argparse.ArgumentTypeError):
        cli_mod._size_type("4")
    with pytest.raises(argparse.ArgumentTypeError):
        cli_mod._size_type("x")
    with pytest.raises(argparse.ArgumentTypeError):
        cli_mod._player_id_type("0")
    with pytest.raises(argparse.ArgumentTypeError):
        cli_mod._player_id_type("x")

    assert cli_mod._is_contest_on_cli(["--contest"])
    assert not cli_mod._is_contest_on_cli(["--version"])
    assert cli_mod._is_time_passed_on_cli(["--time=10"])
    assert cli_mod._is_time_passed_on_cli(["-t", "10"])
    assert not cli_mod._is_time_passed_on_cli(["--players", "2"])
    assert cli_mod._is_ai_time_passed_on_cli(["--ai-time=5"])
    assert not cli_mod._is_ai_time_passed_on_cli(["--version"])


def test_positive_time_helper_accepts_float_minutes():
    assert cli_mod._positive_time_type("0.5") == 0.5
    with pytest.raises(argparse.ArgumentTypeError):
        cli_mod._positive_time_type("0")


def test_get_version_returns_installed_version_or_fallback(monkeypatch):
    monkeypatch.setattr(cli_mod.metadata, "version", lambda _name: "1.2.3")
    assert cli_mod._get_version() == "1.2.3"

    def raise_not_found(_name):
        raise cli_mod.metadata.PackageNotFoundError

    monkeypatch.setattr(cli_mod.metadata, "version", raise_not_found)
    assert cli_mod._get_version() == "0.0.0"


def test_main_dispatches_to_contest_or_interactive(monkeypatch):
    monkeypatch.setattr(cli_mod, "_main_contest", lambda argv: 7)
    monkeypatch.setattr(cli_mod, "_main_interactive", lambda argv: 9)

    assert cli_mod.main(["-c", "state.txt"]) == 7
    assert cli_mod.main(["--version"]) == 9


def test_help_option_prints_help_to_stdout_and_exits_zero(
    monkeypatch, capsys
):
    patch_main_defaults(monkeypatch)

    with pytest.raises(SystemExit) as exc:
        cli_mod.main(["--help"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()
    assert "--version" in captured.out
    assert captured.err == ""


def test_qoridor_help_uses_qoridor_prog_and_exits_zero(
    monkeypatch, capsys
):
    patch_main_defaults(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["qoridor"])

    with pytest.raises(SystemExit) as exc:
        cli_mod._main_interactive(["--help"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage: qoridor " in captured.out
    assert captured.err == ""


def test_invalid_option_prints_error_and_help_to_stderr(monkeypatch, capsys):
    patch_main_defaults(monkeypatch)

    with pytest.raises(SystemExit) as exc:
        cli_mod._main_interactive(["--definitely-invalid-option"])

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error" in captured.err.lower()
    assert "usage:" in captured.err.lower()


def test_qoridor_invalid_option_uses_qoridor_prog_and_exits_one(
    monkeypatch, capsys
):
    patch_main_defaults(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["qoridor"])

    with pytest.raises(SystemExit) as exc:
        cli_mod._main_interactive(["--definitely-invalid-option"])

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "qoridor: error:" in captured.err
    assert "usage: qoridor " in captured.err


def test_version_option_prints_to_stdout_only(monkeypatch, capsys):
    patch_main_defaults(monkeypatch)
    monkeypatch.setattr(cli_mod, "_get_version", lambda: "9.9.9")
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **_kwargs: pytest.fail("shell should not start"),
    )

    assert cli_mod._main_interactive(["--version"]) == 0
    captured = capsys.readouterr()
    assert "9.9.9" in captured.out
    assert captured.err == ""


def test_qoridor_version_prints_to_stdout_only(monkeypatch, capsys):
    patch_main_defaults(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["qoridor"])
    monkeypatch.setattr(cli_mod, "_get_version", lambda: "9.9.9")
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **_kwargs: pytest.fail("shell should not start"),
    )

    assert cli_mod._main_interactive(["--version"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "9.9.9\n"
    assert captured.err == ""


def test_main_interactive_starts_with_save_file_argument(monkeypatch):
    patch_main_defaults(monkeypatch)
    captured: dict[str, object] = {}

    def fake_run_interactive_shell(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        fake_run_interactive_shell,
    )

    assert cli_mod._main_interactive(["save.txt"]) == 0
    assert captured["save_file"] == "save.txt"


def test_main_interactive_handles_missing_save_file_cleanly(
    monkeypatch, capsys
):
    patch_main_defaults(monkeypatch)
    missing = "path/to/missing_save.txt"

    assert cli_mod._main_interactive([missing]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error: cannot load save file" in captured.err.lower()
    assert missing in captured.err
    assert "traceback" not in captured.err.lower()


def test_main_interactive_handles_invalid_save_file_cleanly(
    monkeypatch, capsys, tmp_path: Path
):
    patch_main_defaults(monkeypatch)
    bad_save = tmp_path / "bad_save.txt"
    bad_save.write_text("not a valid save file", encoding="utf-8")

    assert cli_mod._main_interactive([str(bad_save)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error: cannot load save file" in captured.err.lower()
    assert str(bad_save) in captured.err
    assert "traceback" not in captured.err.lower()


def test_main_contest_prints_move_and_reports_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "setup_i18n", lambda: None)
    monkeypatch.setattr(cli_mod, "run_contest", lambda _path: "e2-e3")
    assert cli_mod._main_contest(["-c", "state.txt"]) == 0
    assert "e2-e3" in capsys.readouterr().out

    def raise_contest_error(_path):
        raise cli_mod.ContestError("bad file")

    monkeypatch.setattr(cli_mod, "run_contest", raise_contest_error)
    assert cli_mod._main_contest(["-c", "state.txt"]) == 1
    assert "error: bad file" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        cli_mod._main_contest(["-c"])


def test_main_contest_success_writes_only_move_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "setup_i18n", lambda: None)
    monkeypatch.setattr(cli_mod, "run_contest", lambda _path: "b2-a2")

    assert cli_mod._main_contest(["-c", "state.txt"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "b2-a2\n"
    assert captured.err == ""


def test_main_contest_handles_missing_file_without_traceback(capsys):
    missing = "path/to/contest_state.txt"
    assert cli_mod._main_contest(["-c", missing]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert missing in captured.err


def test_main_contest_accepts_f1_options(monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "setup_i18n", lambda: None)
    calls = []
    monkeypatch.setattr(
        cli_mod,
        "_configure_logging",
        lambda verbose, debug: calls.append((verbose, debug)),
    )
    monkeypatch.setattr(cli_mod, "run_contest", lambda _path: "e2-e3")
    monkeypatch.setattr(cli_mod, "_get_version", lambda: "1.2.3")

    assert cli_mod._main_contest(["-c", "--version"]) == 0
    assert "1.2.3" in capsys.readouterr().out

    assert cli_mod._main_contest(["-c", "-v", "-d", "state.txt"]) == 0
    assert calls[-1] == (True, True)


def test_main_contest_initializes_i18n_like_interactive_mode(
    monkeypatch, capsys
):
    monkeypatch.setenv("LANG", "C")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setattr(cli_mod, "_get_version", lambda: "1.2.3")

    assert cli_mod._main_contest(["-c", "--version"]) == 0
    captured = capsys.readouterr()
    assert "1.2.3" in captured.out
    assert "warning: unsupported language 'c'" in captured.err.lower()


def test_main_contest_uses_french_locale_when_supported(
    monkeypatch, capsys
):
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)

    with pytest.raises(SystemExit):
        cli_mod._main_contest(["-c"])

    captured = capsys.readouterr()
    assert "erreur" in captured.err.lower()
    assert "unsupported language" not in captured.err.lower()


def test_main_interactive_shows_version_and_validates_arguments(
    monkeypatch,
    capsys,
):
    captured = []
    patch_main_defaults(monkeypatch)
    monkeypatch.setattr(cli_mod, "_get_version", lambda: "9.9.9")
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **kwargs: captured.append(kwargs),
    )

    assert cli_mod._main_interactive(["--version"]) == 0
    assert "9.9.9" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cli_mod._main_interactive(["--players", "2", "--ai-player", "3"])
    with pytest.raises(SystemExit):
        cli_mod._main_interactive(["--ai-time", "0"])
    with pytest.raises(SystemExit):
        cli_mod._main_interactive(["--ai-minimax-depth", "0"])

    assert cli_mod._main_interactive(["--ai-mode", "minimax"]) == 0
    assert captured[-1]["ai_mode"] == "minimax"
    assert captured[-1]["ai_minimax_depth"] is None


def test_main_interactive_routes_gui_requests_to_main_gui(monkeypatch):
    captured = []

    patch_main_defaults(monkeypatch)
    monkeypatch.setattr(
        cli_mod,
        "_main_gui",
        lambda args: captured.append(args) or 4,
    )
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **_kwargs: pytest.fail("interactive shell should not start"),
    )

    assert cli_mod._main_interactive(["--gui"]) == 4
    assert len(captured) == 1
    assert captured[0].gui is True


def test_main_interactive_routes_server_modes(monkeypatch):
    shell_calls = []
    daemon_calls = []

    patch_main_defaults(monkeypatch)
    monkeypatch.setattr(cli_mod, "_configure_logging", lambda *_args: None)
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **kwargs: shell_calls.append(kwargs),
    )
    monkeypatch.setattr(
        cli_mod,
        "_run_server_daemon",
        lambda port: daemon_calls.append(port) or 0,
    )

    assert cli_mod._main_interactive(["-S", "23456"]) == 0
    assert shell_calls[-1]["startup_server_port"] == 23456

    assert cli_mod._main_interactive(["-S"]) == 0
    assert shell_calls[-1]["startup_server_port"] == cli_mod.DEFAULT_SERVER_PORT

    assert cli_mod._main_interactive(["-D", "-S", "23456"]) == 0
    assert daemon_calls == [23456]
    assert len(shell_calls) == 2

    with pytest.raises(SystemExit):
        cli_mod._main_interactive(["-D"])


def test_main_gui_calls_gui_main_with_cli_values(monkeypatch):
    calls = []
    fake_gui = SimpleNamespace(
        main=lambda num_players, board_size, walls, blitz, time_limit: calls.append(
            (num_players, board_size, walls, blitz, time_limit)
        )
        or 7
    )

    monkeypatch.setitem(sys.modules, "quoridor.interfaces.gui", fake_gui)
    monkeypatch.setattr(interfaces_pkg, "gui", fake_gui, raising=False)

    assert cli_mod._main_gui(make_gui_args(players=4, size=11, walls=8)) == 7
    assert calls == [(4, 11, 8, False, 30)]


def test_main_gui_falls_back_to_system_python_when_gi_is_missing(monkeypatch):
    import builtins

    monkeypatch.delitem(sys.modules, "quoridor.interfaces.gui", raising=False)
    monkeypatch.delattr(interfaces_pkg, "gui", raising=False)

    real_import = builtins.__import__
    calls = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "gi":
            raise ModuleNotFoundError("No module named 'gi'", name="gi")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(cli_mod.Path, "exists", lambda self: True)

    def fake_run(cmd, check=False):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli_mod.subprocess, "run", fake_run)

    assert cli_mod._main_gui(make_gui_args(players=4, size=11, walls=8)) == 0
    assert calls == [
        [
            "/usr/bin/python3",
            str(Path(cli_mod.__file__).with_name("gui.py")),
        ]
    ]


def test_main_interactive_ignores_time_without_blitz(monkeypatch, capsys):
    captured = []

    patch_main_defaults(monkeypatch, time=42)
    monkeypatch.setattr(cli_mod, "_configure_logging", lambda *_args: None)
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **kwargs: captured.append(kwargs),
    )

    assert cli_mod._main_interactive(["--time", "0.5"]) == 0
    assert captured[-1]["time_limit"] == 42
    assert (
        "warning: --time is ignored unless --blitz is enabled"
        in capsys.readouterr().err
    )

    assert cli_mod._main_interactive(["--blitz", "--time", "0.5"]) == 0
    assert captured[-1]["time_limit"] == 0.5
    assert captured[-1]["ai_minimax_depth"] is None
    assert captured[-1]["ai_minimax_scoring"] == 1


def test_main_interactive_passes_explicit_ai_depth(monkeypatch):
    captured = []

    patch_main_defaults(monkeypatch, time=42)
    monkeypatch.setattr(cli_mod, "_configure_logging", lambda *_args: None)
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **kwargs: captured.append(kwargs),
    )

    assert cli_mod._main_interactive(["--ai-minimax-depth", "4"]) == 0
    assert captured[-1]["ai_mode"] == "minimax"
    assert captured[-1]["ai_minimax_depth"] == 4
    assert captured[-1]["ai_minimax_scoring"] == 1


def test_main_interactive_keeps_auto_depth_for_minimax_when_unspecified(
    monkeypatch,
):
    captured = []

    patch_main_defaults(monkeypatch, time=42)
    monkeypatch.setattr(cli_mod, "_configure_logging", lambda *_args: None)
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **kwargs: captured.append(kwargs),
    )

    assert cli_mod._main_interactive(["--ai-mode", "minimax", "--ai-time", "6"]) == 0
    assert captured[-1]["ai_mode"] == "minimax"
    assert captured[-1]["ai_time"] == 6
    assert captured[-1]["ai_minimax_depth"] is None


def test_main_interactive_uses_ai_defaults_from_config(monkeypatch):
    captured = []

    patch_main_defaults(
        monkeypatch,
        players=4,
        ai_mode="mcts",
        ai_time=9,
        ai_minimax_depth=3,
        ai_minimax_scoring=2,
        ai_players=[2, 4],
    )
    monkeypatch.setattr(cli_mod, "_configure_logging", lambda *_args: None)
    monkeypatch.setattr(
        cli_mod,
        "_run_interactive_shell",
        lambda **kwargs: captured.append(kwargs),
    )

    assert cli_mod._main_interactive([]) == 0
    assert captured[-1]["ai_mode"] == "mcts"
    assert captured[-1]["ai_time"] == 9
    assert captured[-1]["ai_minimax_depth"] == 3
    assert captured[-1]["ai_minimax_scoring"] == 2
    assert captured[-1]["ai_players"] == [2, 4]
