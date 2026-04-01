"""Readline and shell input helpers."""

from __future__ import annotations

from typing import Callable

try:  # readline enables in-session history navigation with arrow keys.
    import readline  # type: ignore
except ImportError:  # pragma: no cover - platform-dependent
    readline = None


def has_readline() -> bool:
    return readline is not None


def build_completer(commands: list[str]) -> Callable[[str, int], str | None]:
    command_list = list(commands)

    def _completer(text: str, state: int) -> str | None:
        matches = [cmd for cmd in command_list if cmd.startswith(text)]
        if state < len(matches):
            return matches[state]
        return None

    return _completer


def get_last_history_match(term: str) -> str | None:
    if readline is None:
        return None

    length = readline.get_current_history_length()
    for index in range(length, 0, -1):
        item = readline.get_history_item(index)
        if item and term in item:
            return item
    return None


def maybe_remove_last_history_item() -> None:
    if readline is None:
        return

    length = readline.get_current_history_length()
    if length > 0:
        readline.remove_history_item(length - 1)


def setup_readline(
    *,
    completer: Callable[[str, int], str | None],
    history_size: int,
) -> None:
    if readline is None:
        return

    readline.set_history_length(history_size)
    readline.set_completer_delims("")
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
