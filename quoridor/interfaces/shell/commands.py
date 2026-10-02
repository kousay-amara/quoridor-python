"""Command registry used by the interactive CLI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

ErrorPolicy = str
Matcher = Callable[[str], bool]
Runner = Callable[[Any, str], bool]
InvalidHandler = Callable[[Exception], None]

ERROR_POLICY_RAISE: ErrorPolicy = "raise"
ERROR_POLICY_INVALID: ErrorPolicy = "invalid"
ERROR_POLICY_PASSTHROUGH: ErrorPolicy = "passthrough"


@dataclass(frozen=True)
class CommandSpec:
    """Describe a CLI command dispatch rule."""

    matcher: Matcher
    runner: Runner
    error_policy: ErrorPolicy = ERROR_POLICY_RAISE


class CommandRegistry:
    """Dispatch user input to the first matching command rule."""

    def __init__(
        self,
        commands: list[CommandSpec],
        *,
        invalid_handler: InvalidHandler,
    ) -> None:
        self._commands = commands
        self._invalid_handler = invalid_handler

    def dispatch(self, state: Any, line: str) -> tuple[bool, bool]:
        for command in self._commands:
            if not command.matcher(line):
                continue
            try:
                should_break = command.runner(state, line)
                return True, should_break
            except Exception as exc:
                if command.error_policy == ERROR_POLICY_INVALID:
                    self._invalid_handler(exc)
                    return True, False
                if command.error_policy == ERROR_POLICY_PASSTHROUGH:
                    return False, False
                raise
        return False, False


def _is_prefix_command(line: str, token: str) -> bool:
    line_lower = line.lower()
    return line_lower == token or line_lower.startswith(f"{token} ")


def _is_network_new_player_command(line: str) -> bool:
    parts = line.split()
    if len(parts) < 2:
        return False
    if parts[0].lower() != "new":
        return False
    for value in parts[1:]:
        if value.startswith(("+", "-")):
            value = value[1:]
        if not value.isdigit():
            return False
    return True


def build_command_registry(
    *,
    command_new: Runner,
    command_help: Runner,
    command_history: Runner,
    command_load: Runner,
    command_save: Runner,
    command_set: Runner,
    command_hint: Runner,
    command_show_board: Runner,
    command_show_configuration: Runner,
    command_show_time: Runner,
    command_pause: Runner,
    command_server: Runner,
    command_join: Runner,
    command_ping: Runner,
    command_players: Runner,
    command_scoreboard: Runner,
    command_accept: Runner,
    command_decline: Runner,
    command_cancel: Runner,
    command_away: Runner,
    command_back: Runner,
    command_moves: Runner,
    command_move: Runner,
    command_wall: Runner,
    command_undo: Runner,
    command_redo: Runner,
    command_shorthand_move: Runner,
    command_shorthand_wall: Runner,
    command_quit: Runner,
    command_new_player: Runner,
    invalid_handler: InvalidHandler,
) -> CommandRegistry:
    return CommandRegistry(
        [
            CommandSpec(
                matcher=_is_network_new_player_command,
                runner=command_new_player,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "new"),
                runner=command_new,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "help"),
                runner=command_help,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() in {"history", "show history"},
                runner=command_history,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "load"),
                runner=command_load,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "save"),
                runner=command_save,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "set"),
                runner=command_set,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "hint",
                runner=command_hint,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "show board",
                runner=command_show_board,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "show configuration",
                runner=command_show_configuration,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "show time",
                runner=command_show_time,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "server"),
                runner=command_server,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "join"),
                runner=command_join,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "accept"),
                runner=command_accept,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "decline"),
                runner=command_decline,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "cancel"),
                runner=command_cancel,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "away"),
                runner=command_away,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "back"),
                runner=command_back,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "ping",
                runner=command_ping,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "players"),
                runner=command_players,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "scoreboard",
                runner=command_scoreboard,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "pause",
                runner=command_pause,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "moves",
                runner=command_moves,
            ),
            CommandSpec(
                matcher=lambda line: line.lower().startswith("move "),
                runner=command_move,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: line.lower().startswith("wall "),
                runner=command_wall,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "undo"),
                runner=command_undo,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: _is_prefix_command(line, "redo"),
                runner=command_redo,
                error_policy=ERROR_POLICY_INVALID,
            ),
            CommandSpec(
                matcher=lambda line: "-" in line and " " not in line,
                runner=command_shorthand_move,
                error_policy=ERROR_POLICY_PASSTHROUGH,
            ),
            CommandSpec(
                matcher=lambda line: (
                    " " not in line
                    and len(line) >= 3
                    and line[-1].lower() in {"h", "v"}
                ),
                runner=command_shorthand_wall,
                error_policy=ERROR_POLICY_PASSTHROUGH,
            ),
            CommandSpec(
                matcher=lambda line: line.lower() == "quit",
                runner=command_quit,
            ),
        ],
        invalid_handler=invalid_handler,
    )
