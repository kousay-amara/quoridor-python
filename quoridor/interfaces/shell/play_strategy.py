"""Strategies for executing play commands in local or network mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class PlayCommandStrategy(Protocol):
    """Execute one play command.

    Returns ``(has_unsaved_changes, should_break)``.
    """

    def execute(self, state: Any, text: str) -> tuple[bool, bool]: ...


@dataclass(frozen=True)
class LocalPlayCommandStrategy:
    """Run a play command against the local session."""

    local_handler: Callable[[Any, str], tuple[bool, bool]]

    def execute(self, state: Any, text: str) -> tuple[bool, bool]:
        return self.local_handler(state, text)


@dataclass(frozen=True)
class NetworkPlayCommandStrategy:
    """Run a play command through the network client."""

    network_handler: Callable[[Any, str], bool]

    def execute(self, state: Any, text: str) -> tuple[bool, bool]:
        should_break = self.network_handler(state, text)
        return state.has_unsaved_changes, should_break


def resolve_play_command_strategy(
    state: Any,
    *,
    local_strategy: PlayCommandStrategy,
    network_strategy: PlayCommandStrategy,
) -> PlayCommandStrategy:
    if getattr(state, "network_client", None) is not None:
        return network_strategy
    return local_strategy
