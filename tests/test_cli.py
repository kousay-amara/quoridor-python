from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.quoridor.application.game_session import GameSession
from src.quoridor.core.game_state import GameState
from src.quoridor.interfaces import cli as cli_mod
from src.quoridor.interfaces import cli_shell as shell_mod


def _run_shell(monkeypatch, commands: list[str], **kwargs) -> None:
    iterator = iter(commands)

    def fake_input(_prompt: str = "") -> str:
        if _prompt:
            print(_prompt, end="")
        try:
            return next(iterator)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr("builtins.input", fake_input)
    cli_mod._run_interactive_shell(
        blitz=False,
        time_limit=30,
        save_file=None,
        players=2,
        walls_per_player=20,
        board_size=9,
        ai_players=[],
        ai_mode="minimax",
        ai_time=5,
        ai_minimax_depth=2,
        **kwargs,
    )


def test_help_and_help_cmd(monkeypatch, capsys):
    _run_shell(monkeypatch, ["help", "help hint", "quit"])

    out = capsys.readouterr().out
    assert "Commands: help [CMD], load, save, hint, show board" in out
    assert "hint" in out
    assert "Show a suggested move for the current player." in out


def test_hint_uses_best_hint_action_format(monkeypatch, capsys):
    monkeypatch.setattr(
        cli_mod,
        "choose_best_move_minimax",
        lambda state, ai_player_id, depth: (
            "pawn",
            state.player_positions[ai_player_id] + state.board_size,
        ),
    )
    _run_shell(monkeypatch, ["hint", "quit"])

    out = capsys.readouterr().out
    assert "Best hint action: e1-e2" in out


def test_shorthand_pawn_move_is_case_insensitive(monkeypatch, capsys):
    _run_shell(monkeypatch, ["E1-E2", "quit", "n"])

    out = capsys.readouterr().out
    assert "Player 1: e2, Player 2: e9" in out
    assert "Save the game before quitting? [Y/N]" in out


def test_shorthand_wall_move_is_case_insensitive(monkeypatch, capsys):
    _run_shell(monkeypatch, ["G4V", "quit", "n"])

    out = capsys.readouterr().out
    assert "Walls -> Player 1: 19, Player 2: 20" in out


def test_show_board_prints_board_only(monkeypatch, capsys):
    _run_shell(monkeypatch, ["show board", "quit"])

    out = capsys.readouterr().out
    # One "Current player" from initial state print, no extra one from show board.
    assert out.count("Current player:") == 1


def test_save_then_load_roundtrip(monkeypatch, tmp_path: Path, capsys):
    save_path = tmp_path / "game.txt"
    _run_shell(
        monkeypatch,
        [
            "e1-e2",
            f"save {save_path}",
            f"load {save_path}",
            "quit",
            "n",
        ],
    )

    out = capsys.readouterr().out
    assert f"Game saved to {save_path}" in out
    assert f"Game loaded from {save_path}" in out
    assert "Player 1: e2, Player 2: e9" in out
    assert save_path.exists()


def test_quit_without_changes_does_not_prompt_save(monkeypatch, capsys):
    _run_shell(monkeypatch, ["quit"])

    out = capsys.readouterr().out
    assert "Save the game before quitting?" not in out


def test_quit_with_changes_prompts_save(monkeypatch, capsys):
    _run_shell(monkeypatch, ["e1-e2", "quit", "n"])

    out = capsys.readouterr().out
    assert "Save the game before quitting? [Y/N]" in out


def test_undo_redo_with_count(monkeypatch, capsys):
    _run_shell(
        monkeypatch,
        ["e1-e2", "e9-e8", "undo 2", "redo 2", "quit", "n"],
    )

    out = capsys.readouterr().out
    assert "Undone groups: 2, moves: 2" in out
    assert "Redone groups: 2, moves: 2" in out
    assert "Player 1: e2, Player 2: e8" in out


def test_undo_redo_with_invalid_count(monkeypatch, capsys):
    _run_shell(monkeypatch, ["undo 0", "redo abc", "quit"])

    out = capsys.readouterr().out
    assert "Invalid command: N must be > 0" in out
    assert "Invalid command: invalid literal for int() with base 10: 'abc'" in out


def test_cli_type_helpers_and_flags():
    assert cli_mod._players_type("2") == 2
    assert cli_mod._size_type("9") == 9
    assert cli_mod._player_id_type("4") == 4

    with pytest.raises(Exception):
        cli_mod._players_type("x")
    with pytest.raises(Exception):
        cli_mod._players_type("5")
    with pytest.raises(Exception):
        cli_mod._size_type("4")
    with pytest.raises(Exception):
        cli_mod._size_type("x")
    with pytest.raises(Exception):
        cli_mod._player_id_type("0")
    with pytest.raises(Exception):
        cli_mod._player_id_type("x")

    assert cli_mod._is_contest_on_cli(["--contest"])
    assert not cli_mod._is_contest_on_cli(["--version"])
    assert cli_mod._is_time_passed_on_cli(["--time=10"])
    assert cli_mod._is_time_passed_on_cli(["-t", "10"])
    assert not cli_mod._is_time_passed_on_cli(["--players", "2"])


def test_get_version_success_and_fallback(monkeypatch):
    monkeypatch.setattr(cli_mod.metadata, "version", lambda _name: "1.2.3")
    assert cli_mod._get_version() == "1.2.3"

    def _raise(_name):
        raise cli_mod.metadata.PackageNotFoundError

    monkeypatch.setattr(cli_mod.metadata, "version", _raise)
    assert cli_mod._get_version() == "0.0.0"


def test_main_dispatch(monkeypatch):
    monkeypatch.setattr(cli_mod, "_main_contest", lambda argv: 7)
    monkeypatch.setattr(cli_mod, "_main_interactive", lambda argv: 9)

    assert cli_mod.main(["-c", "state.txt"]) == 7
    assert cli_mod.main(["--version"]) == 9


def test_main_contest_paths(monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "run_contest", lambda _p: "e2-e3")
    assert cli_mod._main_contest(["-c", "state.txt"]) == 0
    out = capsys.readouterr().out
    assert "e2-e3" in out

    def _raise(_p):
        raise cli_mod.ContestError("bad file")

    monkeypatch.setattr(cli_mod, "run_contest", _raise)
    assert cli_mod._main_contest(["-c", "state.txt"]) == 1
    err = capsys.readouterr().err
    assert "error: bad file" in err

    with pytest.raises(SystemExit):
        cli_mod._main_contest(["-c"])


def test_main_interactive_version_and_validation(monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "setup_i18n", lambda: None)
    monkeypatch.setattr(
        cli_mod,
        "load_or_init_config",
        lambda: {
            "time": 30,
            "players": 2,
            "walls": 20,
            "size": 9,
            "verbose": False,
            "blitz": False,
        },
    )
    monkeypatch.setattr(cli_mod, "_get_version", lambda: "9.9.9")
    monkeypatch.setattr(cli_mod, "_run_interactive_shell", lambda **kwargs: None)

    assert cli_mod._main_interactive(["--version"]) == 0
    assert "9.9.9" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cli_mod._main_interactive(["--players", "2", "--ai-player", "3"])
    with pytest.raises(SystemExit):
        cli_mod._main_interactive(["--ai-time", "0"])
    with pytest.raises(SystemExit):
        cli_mod._main_interactive(["--ai-minimax-depth", "0"])


def test_main_interactive_time_behavior(monkeypatch, capsys):
    captured: list[dict] = []

    monkeypatch.setattr(cli_mod, "setup_i18n", lambda: None)
    monkeypatch.setattr(
        cli_mod,
        "load_or_init_config",
        lambda: {
            "time": 42,
            "players": 2,
            "walls": 20,
            "size": 9,
            "verbose": False,
            "blitz": False,
        },
    )
    monkeypatch.setattr(cli_mod, "_configure_logging", lambda *_args: None)
    monkeypatch.setattr(
        cli_mod, "_run_interactive_shell", lambda **kwargs: captured.append(kwargs)
    )

    assert cli_mod._main_interactive(["--time", "7"]) == 0
    assert captured[-1]["time_limit"] == 42
    assert (
        "warning: --time is ignored unless --blitz is enabled"
        in capsys.readouterr().err
    )

    assert cli_mod._main_interactive(["--blitz", "--time", "7"]) == 0
    assert captured[-1]["time_limit"] == 7


def test_format_hint_move_wall_and_other():
    wall_move = ("wall", [(10, 11), (19, 20)], "horizontal")
    assert cli_mod._format_hint_move(wall_move, from_node=0, size=9).endswith("h")
    assert (
        cli_mod._format_hint_move(("other", 123), from_node=0, size=9)
        == "('other', 123)"
    )


def test_load_session_and_save_helpers(monkeypatch, tmp_path: Path):
    parsed = SimpleNamespace(
        size=9,
        current_player=2,
        positions={1: 4, 2: 76},
        vertical_walls=[(4, 5), (13, 14)],
        horizontal_walls=[(40, 49), (41, 50)],
    )
    monkeypatch.setattr(cli_mod, "parse_contest_file", lambda _p: parsed)

    session = cli_mod._load_session_from_file(
        "dummy.txt",
        fallback_player_types={1: "human", 2: "ai"},
        fallback_walls_per_player={1: 20, 2: 10},
    )
    assert session.state.current_player == 2
    assert session.player_types[2] == "ai"
    assert session.state.remaining_walls == {1: 20, 2: 10}

    text = cli_mod._serialize_game_section(session.state)
    assert "[game]" in text
    assert "walls:" in text

    save_path = tmp_path / "s.txt"
    cli_mod._save_session_to_file(str(save_path), session)
    assert save_path.exists()


def test_prompt_save_before_quit_paths(monkeypatch, tmp_path: Path, capsys):
    session = SimpleNamespace(state=SimpleNamespace())

    # Immediate "no"
    responses = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    assert cli_mod._prompt_save_before_quit(session) is True

    # Retry on invalid path then stop
    responses = iter(["y", "", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    assert cli_mod._prompt_save_before_quit(session) is True
    assert "Invalid path." in capsys.readouterr().out

    # Successful save
    saved: list[str] = []

    def _fake_save(path, _session):
        saved.append(path)

    monkeypatch.setattr(cli_mod, "_save_session_to_file", _fake_save)
    responses = iter(["y", str(tmp_path / "ok.txt")])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    assert cli_mod._prompt_save_before_quit(session) is True
    assert saved


def test_main_uses_sys_argv_when_none(monkeypatch):
    monkeypatch.setattr(cli_mod, "_main_contest", lambda argv: 5)
    monkeypatch.setattr(cli_mod.sys, "argv", ["quoridor", "--contest", "s.txt"])
    assert cli_mod.main(None) == 5


def test_configure_logging_and_helpers_output(monkeypatch, capsys):
    cli_mod._configure_logging(verbose=True, debug=False)
    cli_mod._configure_logging(verbose=False, debug=True)

    _run_shell(
        monkeypatch, ["help unknown", "moves", "move z9-z8", "wall a1x", "blah", "quit"]
    )
    out = capsys.readouterr().out
    assert "Invalid command." in out
    assert "Legal pawn moves for player 1" in out
    assert "Invalid command:" in out


def test_load_and_save_error_paths(monkeypatch, capsys):
    monkeypatch.setattr(
        cli_mod,
        "_load_session_from_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(cli_mod.ContestError("bad")),
    )
    _run_shell(monkeypatch, ["load bad.txt", "quit"])
    assert "Invalid load file: bad" in capsys.readouterr().out

    monkeypatch.setattr(
        cli_mod,
        "_load_session_from_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("io")),
    )
    _run_shell(monkeypatch, ["load bad.txt", "quit"])
    assert "Cannot load file: io" in capsys.readouterr().out

    monkeypatch.setattr(
        cli_mod,
        "_save_session_to_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk")),
    )
    _run_shell(monkeypatch, ["save out.txt", "quit"])
    assert "Cannot save file: disk" in capsys.readouterr().out


def test_play_pawn_move_win_and_wall_format_errors(capsys):
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 67, 2: 4},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types={1: "human", 2: "human"})
    assert cli_mod._play_pawn_move_from_token(session, "e8-e9") is True
    out = capsys.readouterr().out
    assert "Player 1 wins!" in out

    with pytest.raises(ValueError):
        cli_mod._place_wall_from_token(session, "a")


def test_prompt_save_before_quit_exception_branches(monkeypatch, capsys):
    session = SimpleNamespace(state=SimpleNamespace())

    def _raise_eof(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise_eof)
    assert cli_mod._prompt_save_before_quit(session) is True

    answers = iter(["y"])

    def _mixed(_prompt=""):
        if "Save file path" in _prompt:
            raise KeyboardInterrupt
        return next(answers)

    monkeypatch.setattr("builtins.input", _mixed)
    assert cli_mod._prompt_save_before_quit(session) is True
    assert capsys.readouterr().out.endswith("\n")


def test_auto_play_ai_and_startup_messages(monkeypatch, capsys):
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 67, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types={1: "ai", 2: "human"})
    monkeypatch.setattr(
        session,
        "play_ai_turn",
        lambda depth=1: session.state.player_positions.__setitem__(1, 76),
    )
    assert cli_mod._auto_play_ai_until_human_or_end(session, ai_minimax_depth=1) is True
    out = capsys.readouterr().out
    assert "AI player 1 played." in out

    monkeypatch.setattr(
        cli_mod, "_auto_play_ai_until_human_or_end", lambda *_args, **_kwargs: False
    )
    iterator = iter(["quit"])

    def fake_input(_prompt: str = "") -> str:
        if _prompt:
            print(_prompt, end="")
        try:
            return next(iterator)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr("builtins.input", fake_input)
    cli_mod._run_interactive_shell(
        blitz=True,
        time_limit=30,
        save_file="seed.txt",
        players=3,
        walls_per_player=20,
        board_size=9,
        ai_players=[1],
        ai_mode="minimax",
        ai_time=5,
        ai_minimax_depth=2,
    )
    out = capsys.readouterr().out
    assert "Loading game from seed.txt" in out
    assert "warning: save/load not implemented yet" in out
    assert "blitz: 30 min/player" in out
    assert "3-player mode can be unbalanced" in out
    assert "AI players: [1]" in out


class _FakeReadline:
    def __init__(self, history: list[str] | None = None):
        self.history = [] if history is None else list(history)
        self.history_length = None

    def set_history_length(self, value: int) -> None:
        self.history_length = value

    def get_current_history_length(self) -> int:
        return len(self.history)

    def get_history_item(self, index: int) -> str | None:
        if 1 <= index <= len(self.history):
            return self.history[index - 1]
        return None

    def remove_history_item(self, index: int) -> None:
        del self.history[index]


def test_history_plus_term_executes_matching_command(monkeypatch, capsys):
    fake_readline = _FakeReadline(["older", "+mov"])
    monkeypatch.setattr(shell_mod, "readline", fake_readline)
    monkeypatch.setattr(shell_mod, "_get_last_history_match", lambda term: "moves")

    _run_shell(monkeypatch, ["+mov", "quit"])

    out = capsys.readouterr().out
    assert "History match: moves" in out
    assert "Legal pawn moves for player 1" in out
    assert fake_readline.history == ["older"]


def test_history_plus_without_term_prompts_and_executes(monkeypatch, capsys):
    fake_readline = _FakeReadline(["older", "+"])
    monkeypatch.setattr(shell_mod, "readline", fake_readline)
    monkeypatch.setattr(shell_mod, "_get_last_history_match", lambda term: "help")

    _run_shell(monkeypatch, ["+", "help", "quit"])

    out = capsys.readouterr().out
    assert "Search history:" in out
    assert "History match: help" in out
    assert "Commands: help [CMD], load, save, hint, show board" in out
    assert fake_readline.history == []


def test_history_plus_no_match_prints_message(monkeypatch, capsys):
    fake_readline = _FakeReadline(["older", "+abc"])
    monkeypatch.setattr(shell_mod, "readline", fake_readline)
    monkeypatch.setattr(shell_mod, "_get_last_history_match", lambda term: None)

    _run_shell(monkeypatch, ["+abc", "quit"])

    out = capsys.readouterr().out
    assert "No command found in history." in out
