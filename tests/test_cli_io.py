from __future__ import annotations

from pathlib import Path

import pytest

from quoridor.application.blitz import Blitz
from quoridor.application.game_session import GameSession
from quoridor.core.game_state import GameState
from quoridor.interfaces import cli_io


def _make_session() -> GameSession:
    state = GameState(
        board_size=9,
        current_player=1,
        player_positions={1: 4, 2: 76},
        remaining_walls={1: 20, 2: 20},
        vertical_walls=[],
        horizontal_walls=[],
    )
    return GameSession(state=state, player_types={1: "human", 2: "human"})


def test_cli_io_save_load_and_blitz_roundtrip(tmp_path: Path):
    session = _make_session()
    session.play_pawn_move_from_to(1, 4, 13)
    session.play_pawn_move_from_to(2, 76, 67)
    blitz = Blitz(time_limit_minutes=1, player_ids=[1, 2], paused=False)
    blitz.consume_time(1, 7.5)
    blitz.toggle_pause()

    path = tmp_path / "save.txt"
    cli_io._save_session_to_file(str(path), session, blitz=blitz)

    loaded = cli_io._load_session_from_file(
        str(path),
        fallback_player_types={1: "human", 2: "human"},
        fallback_walls_per_player={1: 20, 2: 20},
    )
    snapshot = cli_io._load_blitz_snapshot_from_file(str(path))

    assert loaded.state.player_positions == session.state.player_positions
    assert loaded.state.current_player == session.state.current_player
    assert snapshot is not None
    assert snapshot["enabled"] is True
    assert snapshot["paused"] is True
    assert snapshot["remaining_times"][1] < snapshot["remaining_times"][2]


def test_cli_io_split_and_parse_history_with_comments():
    raw = """
    { block comment must be ignored }
    [history]
    # line comment
    1 e1-e2; 2 e9-e8; # trailing comment
    """
    sections = cli_io._split_sections(raw)
    parsed = cli_io._parse_history_section(raw)

    assert "history" in sections
    assert parsed == [(1, "e1-e2"), (2, "e9-e8")]


def test_cli_io_parse_history_invalid_entry_raises():
    raw = """
    [history]
    invalid-entry-without-player-id;
    """
    with pytest.raises(ValueError, match="invalid history entry"):
        cli_io._parse_history_section(raw)


def test_cli_io_serialize_helpers_expose_expected_sections():
    session = _make_session()
    session.play_pawn_move_from_to(1, 4, 13)
    game_txt = cli_io._serialize_game_section(session.state)
    history_txt = cli_io._serialize_history_section(session)
    record_txt = cli_io._record_to_notation(session, session.history.records[0])

    assert "[game]" in game_txt
    assert "[history]" in history_txt
    assert record_txt == "e1-e2"


def test_cli_io_load_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        cli_io._load_session_from_file(
            str(missing),
            fallback_player_types={1: "human", 2: "human"},
            fallback_walls_per_player={1: 20, 2: 20},
        )


def test_prompt_save_before_quit_no_save(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert cli_io._prompt_save_before_quit(_make_session()) is True


def test_prompt_save_before_quit_save_success_after_empty_path(monkeypatch, capsys):
    answers = iter(["y", "", "y", "game.txt"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    calls: list[tuple[str, bool]] = []

    def fake_save(path, session, blitz=None):
        del session
        calls.append((path, blitz is not None))

    monkeypatch.setattr("quoridor.interfaces.cli._save_session_to_file", fake_save)
    assert cli_io._prompt_save_before_quit(_make_session(), blitz=Blitz(time_limit_minutes=0)) is True
    out = capsys.readouterr().out
    assert "Invalid path." in out
    assert "Game saved to game.txt" in out
    assert calls == [("game.txt", True)]


def test_prompt_save_before_quit_save_fails_then_abort(monkeypatch, capsys):
    answers = iter(["y", "bad.txt", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    def fake_save(_path, _session, blitz=None):
        del blitz
        raise OSError("disk full")

    monkeypatch.setattr("quoridor.interfaces.cli._save_session_to_file", fake_save)
    assert cli_io._prompt_save_before_quit(_make_session()) is True
    out = capsys.readouterr().out
    assert "Cannot save file: disk full" in out
    assert "Saving failed. Try again? [Y/N]" not in out
