"""Persistence helpers for the Quoridor CLI."""

from __future__ import annotations

import gettext

from ..application.blitz import Blitz
from ..application.persistence_service import (
    load_blitz_snapshot,
    load_session,
    parse_history,
    record_to_notation,
    save_session,
    serialize_game,
    serialize_history,
    split_sections,
)
from ..application.game_session import GameSession
from ..core.game_state import GameState
from ..core.move_record import BlitzSnapshot

_ = gettext.gettext


def _record_to_notation(session: GameSession, record) -> str:
    del session
    return record_to_notation(record)


def _serialize_history_section(session: GameSession) -> str:
    return serialize_history(session)


def _split_sections(raw_text: str) -> dict[str, list[str]]:
    return split_sections(raw_text)


def _parse_history_section(raw_text: str) -> list[tuple[int, str]]:
    return parse_history(raw_text)


def _load_session_from_file(
    path: str,
    *,
    fallback_player_types: dict[int, str],
    fallback_walls_per_player: dict[int, int],
) -> GameSession:
    return load_session(
        path,
        fallback_player_types=fallback_player_types,
        fallback_walls_per_player=fallback_walls_per_player,
    )


def _load_blitz_snapshot_from_file(path: str) -> BlitzSnapshot | None:
    return load_blitz_snapshot(path)


def _serialize_game_section(state: GameState) -> str:
    return serialize_game(state)


def _save_session_to_file(
    path: str,
    session: GameSession,
    blitz: Blitz | None = None,
) -> None:
    snapshot = None if blitz is None else blitz.snapshot()
    save_session(path, session, blitz_snapshot=snapshot)


def _prompt_save_before_quit(
    session: GameSession,
    blitz: Blitz | None = None,
) -> bool:
    """Return True when the caller should quit."""
    try:
        choice = input("Save the game before quitting? [Y/N] ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return True

    if choice.lower() not in {"y", "yes"}:
        return True

    while True:
        try:
            path = input("Save file path: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return True

        if not path:
            print("Invalid path.")
        else:
            try:
                if blitz is None:
                    _save_session_to_file(path, session)
                else:
                    _save_session_to_file(path, session, blitz)
                print(_("Game saved to {path}").format(path=path))
                return True
            except OSError as exc:
                print(f"Cannot save file: {exc}")
            except Exception as exc:
                print(f"Cannot save game: {exc}")

        try:
            retry = input("Saving failed. Try again? [Y/N] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return True
        if retry.lower() not in {"y", "yes"}:
            return True
