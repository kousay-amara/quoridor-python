from __future__ import annotations

import builtins

from quoridor.application.game_session import GameSession
from quoridor.core.game_state import GameState
from quoridor.interfaces import cli_io


def _session() -> GameSession:
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    return GameSession(state=state, player_types={1: "human", 2: "human"})


def test_prompt_save_before_quit_handles_interrupts(monkeypatch, capsys):
    monkeypatch.setattr(
        builtins,
        "input",
        lambda _prompt: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    assert cli_io._prompt_save_before_quit(_session()) is True
    assert capsys.readouterr().out.endswith("\n")


def test_prompt_save_before_quit_handles_generic_save_error(monkeypatch, capsys):
    answers = iter(["y", "save.txt", "n"])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_io, "_save_session_to_file", fail_save)
    assert cli_io._prompt_save_before_quit(_session()) is True
    out = capsys.readouterr().out
    assert "Cannot save game: boom" in out


def test_prompt_save_before_quit_handles_interrupt_during_path(monkeypatch, capsys):
    answers = iter(["y"])

    def fake_input(_prompt: str):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr(builtins, "input", fake_input)
    assert cli_io._prompt_save_before_quit(_session()) is True
    assert capsys.readouterr().out.endswith("\n")
