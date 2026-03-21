"""Interactive shell loop for the Quoridor CLI."""

from __future__ import annotations

import gettext
import signal
import time
from dataclasses import dataclass

try:  # readline enables in-session history navigation with arrow keys.
    import readline  # type: ignore
except ImportError:  # pragma: no cover - platform-dependent
    readline = None

from ..application.blitz import Blitz
from ..application.command_catalog import (
    command_names_for_completion,
    help_for,
    help_overview,
)
from ..application.game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.notation import get_edges_for_wall, get_node_from_notation
from ..core.validators import validate_pawn_move, validate_wall
from ..rules.win_rules import has_player_won
from .cli_constants import UNBALANCED_PLAYERS_COUNT, WALL_TOKEN_MIN_LENGTH
from .cli_render import (
    _format_hint_move,
    _print_moves,
    _print_state,
    _render_ascii_board,
)
from .contest_parser import ContestError
from .cli_io import _prompt_save_before_quit

_ = gettext.gettext

MAX_HISTORY_SIZE = 1000
HINT_MINIMAX_DEPTH = 1


class _BlitzInputTimeout(Exception):
    """Raised when a blitz timer interrupts a blocking CLI input."""


def _raise_blitz_input_timeout(_signum: int, _frame: object) -> None:
    raise _BlitzInputTimeout


def _start_blitz_alarm(
    timeout_sec: float | None,
) -> tuple[bool, object | None]:
    if timeout_sec is None or timeout_sec <= 0:
        return False, None

    try:
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _raise_blitz_input_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_sec)
    except (AttributeError, ValueError):
        return False, None

    return True, previous_handler


def _stop_blitz_alarm(
    alarm_started: bool, previous_handler: object | None
) -> None:
    if not alarm_started:
        return

    signal.setitimer(signal.ITIMER_REAL, 0.0)
    signal.signal(signal.SIGALRM, previous_handler)


QUORIDOR_COMMANDS = command_names_for_completion()


def completer(text: str, state: int) -> str | None:
    matches = []
    for cmd in QUORIDOR_COMMANDS:
        if cmd.startswith(text):
            matches.append(cmd)
    if state < len(matches):
        return matches[state]
    return None


def _get_last_history_match(term: str) -> str | None:
    if readline is None:
        return None

    length = readline.get_current_history_length()
    for index in range(length, 0, -1):
        item = readline.get_history_item(index)
        if item and term in item:
            return item
    return None


def _maybe_remove_last_history_item() -> None:
    if readline is None:
        return

    length = readline.get_current_history_length()
    if length > 0:
        readline.remove_history_item(length - 1)


def _play_pawn_move_from_token(session: GameSession, move_token: str) -> bool:
    token = move_token.strip().lower()
    if "-" not in token:
        raise ValueError("Invalid format. Use: e2-e3")

    from_txt, to_txt = token.split("-", 1)
    from_node = get_node_from_notation(from_txt, session.state.board_size)
    to_node = get_node_from_notation(to_txt, session.state.board_size)

    current = session.state.current_player
    all_positions = list(session.state.player_positions.values())
    ok, error_msg = validate_pawn_move(
        session.state.graph,
        from_node,
        to_node,
        all_positions,
        session.state.board_size,
    )
    if not ok:
        raise ValueError(error_msg)

    session.play_pawn_move_from_to(current, from_node, to_node)
    new_pos = session.state.player_positions[current]

    if has_player_won(current, new_pos, session.state.board_size):
        print(f"Player {current} wins!")
        _print_state(session)
        return True

    _print_state(session)
    return False


def _place_wall_from_token(session: GameSession, wall_token: str) -> None:
    token = wall_token.strip().lower()
    if len(token) < WALL_TOKEN_MIN_LENGTH:
        raise ValueError("Invalid format. Use: e2h or e2v")

    ori_char = token[-1]
    if ori_char not in {"h", "v"}:
        raise ValueError("Invalid wall orientation. Use h or v")

    wall_edges = get_edges_for_wall(token, session.state.board_size)
    orientation = "horizontal" if ori_char == "h" else "vertical"

    current = session.state.current_player
    active_players = session.active_player_ids()
    positions = [
        session.state.player_positions[player_id]
        for player_id in active_players
    ]
    target_funcs = session._build_player_target_funcs()
    ok, error_msg = validate_wall(
        session.state.graph,
        positions,
        wall_edges,
        target_funcs,
        session.state.remaining_walls,
        current,
    )
    if not ok:
        raise ValueError(error_msg)
    session.place_wall(current, wall_edges, orientation)
    _print_state(session)


def _auto_play_ai_until_human_or_end(
    session: GameSession,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz | None = None,
) -> bool:
    if blitz is None:
        blitz = Blitz(time_limit_minutes=0)

    while session.player_types.get(session.state.current_player) == "ai":
        current_ai = session.state.current_player
        before_blitz_snapshot = blitz.snapshot() if blitz.is_enabled() else None
        started = time.time()
        session.play_ai_turn(
            mode=ai_mode,
            depth=ai_minimax_depth,
            time_limit_sec=ai_time,
        )
        elapsed = time.time() - started
        if blitz.consume_time(current_ai, elapsed):
            if _handle_timeout(
                session,
                current_ai,
                before_blitz_snapshot=before_blitz_snapshot,
            ):
                return True
            continue
        print(f"AI player {current_ai} played.")

        new_pos = session.state.player_positions[current_ai]
        if has_player_won(current_ai, new_pos, session.state.board_size):
            print(f"Player {current_ai} wins!")
            _print_state(session)
            return True

        _print_state(session)
    return False


def _show_help(line: str) -> bool:
    line_lower = line.lower()
    if line_lower == "help" or line_lower.startswith("help "):
        parts = line.split(maxsplit=1)
        if len(parts) == 1:
            print(help_overview())
            return True

        target = parts[1].strip().lower()
        entry = help_for(target)
        if entry is None:
            print(_("Invalid command."))
        else:
            print(entry)
        return True

    return False


def _apply_and_maybe_auto_play(
    session: GameSession,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz,
    base_unsaved: bool = True,
) -> tuple[bool, bool]:
    has_unsaved_changes = base_unsaved
    before_ai_cursor = session.history.cursor
    if _auto_play_ai_until_human_or_end(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz,
    ):
        if session.history.cursor != before_ai_cursor:
            has_unsaved_changes = True
        return has_unsaved_changes, True
    if session.history.cursor != before_ai_cursor:
        has_unsaved_changes = True
    return has_unsaved_changes, False


def _auto_play_pending_ai(state: "_ShellState") -> bool:
    before_ai_cursor = state.session.history.cursor
    if _auto_play_ai_until_human_or_end(
        state.session,
        state.ai_mode,
        state.ai_time,
        state.ai_minimax_depth,
        blitz=state.blitz,
    ):
        if state.session.history.cursor != before_ai_cursor:
            state.has_unsaved_changes = True
        return True

    if state.session.history.cursor != before_ai_cursor:
        state.has_unsaved_changes = True
    return False


def _handle_load(
    session: GameSession,
    file_path: str,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz,
) -> tuple[GameSession, Blitz, bool, bool]:
    from . import cli as cli_mod

    session = cli_mod._load_session_from_file(
        file_path,
        fallback_player_types=session.player_types,
        fallback_walls_per_player=session.state.remaining_walls,
    )
    try:
        loaded_blitz_snapshot = cli_mod._load_blitz_snapshot_from_file(file_path)
    except (OSError, ValueError):
        loaded_blitz_snapshot = None

    loaded_blitz = (
        Blitz.from_snapshot(loaded_blitz_snapshot)
        if loaded_blitz_snapshot is not None
        else Blitz(time_limit_minutes=0)
    )
    session.attach_blitz(loaded_blitz)

    print(_("Game loaded from {path}").format(path=file_path))
    _print_state(session)
    has_unsaved_changes, should_break = _apply_and_maybe_auto_play(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=loaded_blitz,
        base_unsaved=False,
    )
    return session, loaded_blitz, has_unsaved_changes, should_break


def _handle_save(
    session: GameSession,
    file_path: str,
    *,
    blitz: Blitz,
) -> bool:
    from . import cli as cli_mod

    cli_mod._save_session_to_file(file_path, session, blitz)
    print(_("Game saved to {path}").format(path=file_path))
    return False


def _handle_history(session: GameSession) -> None:
    from . import cli as cli_mod

    print(cli_mod._serialize_history_section(session), end="")


def _handle_hint(
    session: GameSession,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
) -> None:
    del ai_mode, ai_time, ai_minimax_depth
    current = session.state.current_player
    from . import cli as cli_mod

    move = cli_mod.find_best_move_minimax(
        session.state,
        ai_player_id=current,
        depth=HINT_MINIMAX_DEPTH,
    )
    from_node = session.state.player_positions[current]
    best_hint = _format_hint_move(
        move, from_node=from_node, size=session.state.board_size
    )
    print(f"Best hint action: {best_hint}")


def _handle_move(
    session: GameSession,
    move_token: str,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz,
) -> tuple[bool, bool]:
    if _play_pawn_move_from_token(session, move_token):
        return True, True
    return _apply_and_maybe_auto_play(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz,
    )


def _handle_wall(
    session: GameSession,
    wall_token: str,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz,
) -> tuple[bool, bool]:
    _place_wall_from_token(session, wall_token)
    return _apply_and_maybe_auto_play(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz,
    )


def _handle_undo(session: GameSession, line: str) -> bool:
    current = session.state.current_player
    parts = line.split()
    if len(parts) > 2:
        raise ValueError("Invalid format. Use: undo [N]")
    count = 1
    if len(parts) == 2:
        count = int(parts[1])
        if count <= 0:
            raise ValueError("N must be > 0")

    total_undone = 0
    groups_done = 0
    for _step in range(count):
        undone = session.undo(requester_id=current)
        if not undone:
            break
        groups_done += 1
        total_undone += len(undone)

    print(f"Undone groups: {groups_done}, moves: {total_undone}")
    _print_state(session)
    return total_undone > 0


def _handle_redo(session: GameSession, line: str) -> bool:
    current = session.state.current_player
    parts = line.split()
    if len(parts) > 2:
        raise ValueError("Invalid format. Use: redo [N]")
    count = 1
    if len(parts) == 2:
        count = int(parts[1])
        if count <= 0:
            raise ValueError("N must be > 0")

    total_redone = 0
    groups_done = 0
    for _step in range(count):
        redone = session.redo(requester_id=current)
        if not redone:
            break
        groups_done += 1
        total_redone += len(redone)

    print(f"Redone groups: {groups_done}, moves: {total_redone}")
    _print_state(session)
    return total_redone > 0


def _handle_quit(
    session: GameSession,
    has_unsaved_changes: bool,
    *,
    blitz: Blitz,
) -> None:
    if has_unsaved_changes:
        _prompt_save_before_quit(session, blitz)
    print(_("Bye."))


def _format_blitz_time(seconds_left: float) -> str:
    seconds = max(0, int(seconds_left))
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _print_blitz_times(blitz: Blitz) -> None:
    remaining_times = blitz.remaining_times()
    ordered = sorted(remaining_times)
    text = ", ".join(
        f"Player {pid}: {_format_blitz_time(remaining_times[pid])}"
        for pid in ordered
    )
    print(f"Blitz time -> {text}")


def _handle_timeout(
    session: GameSession,
    loser_id: int,
    *,
    before_blitz_snapshot=None,
) -> bool:
    _record, winner = session.timeout_player(
        loser_id,
        before_blitz_snapshot=before_blitz_snapshot,
    )
    print(f"Player {loser_id} ran out of time and loses.")
    if winner is not None:
        print(f"Player {winner} wins!")
    _print_state(session)
    return winner is not None


def _read_shell_input(
    state: "_ShellState", prompt: str
) -> tuple[str | None, bool]:
    timed_player = state.session.state.current_player
    before_blitz_snapshot = (
        state.blitz.snapshot() if state.blitz.is_enabled() else None
    )
    timeout_sec = state.blitz.input_timeout_for(timed_player)
    if timeout_sec is not None and timeout_sec <= 0:
        state.has_unsaved_changes = True
        if _handle_timeout(
            state.session,
            timed_player,
            before_blitz_snapshot=before_blitz_snapshot,
        ):
            return None, True
        return "", False

    started = time.time()
    alarm_started, previous_handler = _start_blitz_alarm(timeout_sec)
    try:
        line = input(prompt).strip()
    except _BlitzInputTimeout:
        state.blitz.expire_player(timed_player)
        state.has_unsaved_changes = True
        if _handle_timeout(
            state.session,
            timed_player,
            before_blitz_snapshot=before_blitz_snapshot,
        ):
            return None, True
        return "", False
    except (EOFError, KeyboardInterrupt):
        print()
        return None, True
    finally:
        _stop_blitz_alarm(alarm_started, previous_handler)

    elapsed = time.time() - started
    if state.blitz.consume_time(timed_player, elapsed):
        state.has_unsaved_changes = True
        if _handle_timeout(
            state.session,
            timed_player,
            before_blitz_snapshot=before_blitz_snapshot,
        ):
            return None, True
        return "", False

    return line, False


def _print_configuration(state: "_ShellState") -> None:
    ai_sorted = sorted(set(state.ai_players))
    walls_text = (
        "unlimited"
        if state.walls_per_player < 0
        else str(state.walls_per_player)
    )
    print("Current configuration:")
    print(f"players={state.players}")
    print(f"walls_per_player={walls_text}")
    print(f"board_size={state.board_size}")
    print(f"ai_players={ai_sorted}")
    print(f"ai_mode={state.ai_mode}")
    print(f"ai_time={state.ai_time}")
    print(f"ai_minimax_depth={state.ai_minimax_depth}")
    print(f"blitz={state.blitz.is_enabled()}")
    print(f"time_limit={state.blitz.time_limit_minutes}")
    print(f"timer_paused={state.blitz.paused}")


def _command_help(_state: _ShellState, line: str) -> bool:
    _show_help(line)
    return False


def _command_load(state: _ShellState, line: str) -> bool:
    file_path = line[5:].strip()
    if not file_path:
        print("Invalid format. Use: load FILE")
        return False
    try:
        session, blitz, has_unsaved_changes, should_break = _handle_load(
            state.session,
            file_path,
            state.ai_mode,
            state.ai_time,
            state.ai_minimax_depth,
            blitz=state.blitz,
        )
        state.session = session
        state.blitz = blitz
        state.has_unsaved_changes = has_unsaved_changes
        return should_break
    except ContestError as exc:
        print(f"Invalid load file: {exc}")
        return False
    except OSError as exc:
        print(f"Cannot load file: {exc}")
        return False


def _command_history(state: _ShellState, _line: str) -> bool:
    _handle_history(state.session)
    return False


def _command_save(state: _ShellState, line: str) -> bool:
    file_path = line[5:].strip()
    if not file_path:
        print("Invalid format. Use: save FILE")
        return False
    try:
        state.has_unsaved_changes = _handle_save(
            state.session,
            file_path,
            blitz=state.blitz,
        )
        return False
    except OSError as exc:
        print(f"Cannot save file: {exc}")
        return False


def _command_hint(state: _ShellState, _line: str) -> bool:
    try:
        _handle_hint(
            state.session,
            state.ai_mode,
            state.ai_time,
            state.ai_minimax_depth,
        )
    except Exception as exc:
        print(f"No hint available: {exc}")
    return False


def _command_show_board(state: _ShellState, _line: str) -> bool:
    print(_render_ascii_board(state.session.state))
    return False


def _command_show_configuration(state: _ShellState, _line: str) -> bool:
    _print_configuration(state)
    return False


def _command_show_time(state: _ShellState, _line: str) -> bool:
    if not state.blitz.is_enabled():
        print("Blitz mode is not enabled.")
    else:
        _print_blitz_times(state.blitz)
        print(f"Timer paused: {'yes' if state.blitz.paused else 'no'}")
    return False


def _command_pause(state: _ShellState, _line: str) -> bool:
    if not state.blitz.is_enabled():
        print("Blitz mode is not enabled.")
        return False
    is_paused = state.blitz.toggle_pause()
    print("Blitz timer paused." if is_paused else "Blitz timer resumed.")
    return False


def _command_moves(state: _ShellState, _line: str) -> bool:
    _print_moves(state.session)
    return False


def _command_move(state: _ShellState, line: str) -> bool:
    has_unsaved_changes, should_break = _handle_move(
        state.session,
        line[5:],
        state.ai_mode,
        state.ai_time,
        state.ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_wall(state: _ShellState, line: str) -> bool:
    has_unsaved_changes, should_break = _handle_wall(
        state.session,
        line[5:],
        state.ai_mode,
        state.ai_time,
        state.ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_undo(state: _ShellState, line: str) -> bool:
    if _handle_undo(state.session, line):
        state.has_unsaved_changes = True
    return False


def _command_redo(state: _ShellState, line: str) -> bool:
    if _handle_redo(state.session, line):
        state.has_unsaved_changes = True
    return False


def _command_shorthand_move(state: _ShellState, line: str) -> bool:
    has_unsaved_changes, should_break = _handle_move(
        state.session,
        line,
        state.ai_mode,
        state.ai_time,
        state.ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_shorthand_wall(state: _ShellState, line: str) -> bool:
    has_unsaved_changes, should_break = _handle_wall(
        state.session,
        line,
        state.ai_mode,
        state.ai_time,
        state.ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_quit(state: _ShellState, _line: str) -> bool:
    _handle_quit(
        state.session,
        state.has_unsaved_changes,
        blitz=state.blitz,
    )
    return True


@dataclass
class _ShellState:
    session: GameSession
    has_unsaved_changes: bool
    ai_mode: str
    ai_time: int
    ai_minimax_depth: int | None
    players: int
    walls_per_player: int
    board_size: int
    ai_players: list[int]
    blitz: Blitz


class _BaseCommand:
    """Command interface for CLI actions."""

    def matches(self, line: str) -> bool:
        raise NotImplementedError

    def run(self, state: _ShellState, line: str) -> bool:
        raise NotImplementedError

    def on_error(
        self, _state: _ShellState, _line: str, exc: Exception
    ) -> tuple[bool, bool]:
        raise exc


class _InvalidAsCommandError(_BaseCommand):
    def on_error(
        self, _state: _ShellState, _line: str, exc: Exception
    ) -> tuple[bool, bool]:
        _handle_invalid_command(exc)
        return True, False


class _PassthroughOnError(_BaseCommand):
    def on_error(
        self, _state: _ShellState, _line: str, _exc: Exception
    ) -> tuple[bool, bool]:
        return False, False


class _HelpCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "help" or line_lower.startswith("help ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_help(state, line)


class _HistoryCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        return line.lower() == "history"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_history(state, line)


class _LoadCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower().startswith("load ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_load(state, line)


class _SaveCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower().startswith("save ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_save(state, line)


class _HintCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower() == "hint"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_hint(state, line)


class _ShowBoardCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        return line.lower() == "show board"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_show_board(state, line)


class _ShowConfigurationCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        return line.lower() == "show configuration"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_show_configuration(state, line)


class _ShowTimeCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        return line.lower() == "show time"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_show_time(state, line)


class _PauseCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        return line.lower() == "pause"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_pause(state, line)


class _MovesCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        return line.lower() == "moves"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_moves(state, line)


class _MoveCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower().startswith("move ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_move(state, line)


class _WallCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower().startswith("wall ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_wall(state, line)


class _UndoCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "undo" or line_lower.startswith("undo ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_undo(state, line)


class _RedoCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "redo" or line_lower.startswith("redo ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_redo(state, line)


class _ShorthandMoveCommand(_PassthroughOnError):
    def matches(self, line: str) -> bool:
        return "-" in line and " " not in line

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_shorthand_move(state, line)


class _ShorthandWallCommand(_PassthroughOnError):
    def matches(self, line: str) -> bool:
        return (
            " " not in line
            and len(line) >= 3
            and line[-1].lower() in {"h", "v"}
        )

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_shorthand_wall(state, line)


class _QuitCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        return line.lower() == "quit"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_quit(state, line)


class _CommandRegistry:
    """Dispatch user input to the first matching command object."""

    def __init__(self, commands: list[_BaseCommand]) -> None:
        self._commands = commands

    def dispatch(self, state: _ShellState, line: str) -> tuple[bool, bool]:
        for command in self._commands:
            if not command.matches(line):
                continue
            try:
                should_break = command.run(state, line)
                return True, should_break
            except Exception as exc:
                return command.on_error(state, line, exc)
        return False, False


def _build_command_registry() -> _CommandRegistry:
    return _CommandRegistry(
        [
            _HelpCommand(),
            _HistoryCommand(),
            _LoadCommand(),
            _SaveCommand(),
            _HintCommand(),
            _ShowBoardCommand(),
            _ShowConfigurationCommand(),
            _ShowTimeCommand(),
            _PauseCommand(),
            _MovesCommand(),
            _MoveCommand(),
            _WallCommand(),
            _UndoCommand(),
            _RedoCommand(),
            _ShorthandMoveCommand(),
            _ShorthandWallCommand(),
            _QuitCommand(),
        ]
    )


def _handle_invalid_command(exc: Exception) -> None:
    print(f"Invalid command: {exc}")


def _run_interactive_shell(
    *,
    blitz: bool,
    time_limit: int,
    save_file: str | None,
    players: int,
    walls_per_player: int,
    board_size: int,
    ai_players: list[int],
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
) -> None:
    if save_file:
        print(_("Loading game from {path}").format(path=save_file))

    player_positions = initial_player_positions(board_size, players)
    wall_count = walls_per_player if walls_per_player >= 0 else -1
    remaining_walls = {pid: wall_count for pid in player_positions}
    ai_set = set(ai_players)
    player_types = {
        pid: ("ai" if pid in ai_set else "human") for pid in player_positions
    }

    loaded_blitz_snapshot = None
    if save_file:
        from . import cli as cli_mod

        session = cli_mod._load_session_from_file(
            save_file,
            fallback_player_types=player_types,
            fallback_walls_per_player=remaining_walls,
        )
        try:
            loaded_blitz_snapshot = cli_mod._load_blitz_snapshot_from_file(save_file)
        except (OSError, ValueError):
            loaded_blitz_snapshot = None
        has_unsaved_changes = False
    else:
        state = GameState(
            board_size=board_size,
            current_player=1,
            player_positions=player_positions,
            remaining_walls=remaining_walls,
            vertical_walls=[],
            horizontal_walls=[],
        )
        session = GameSession(state=state, player_types=player_types)
        has_unsaved_changes = False
    blitz_state = Blitz(time_limit_minutes=time_limit)
    if loaded_blitz_snapshot is not None:
        blitz_state.restore_snapshot(loaded_blitz_snapshot)
        print(_("Game loaded with blitz timer state."))
    elif blitz:
        blitz_state = Blitz(
            time_limit_minutes=time_limit,
            player_ids=session.state.player_positions,
        )
        print(
            _("New game started (blitz: {minutes} min/player).").format(
                minutes=time_limit
            )
        )
    else:
        print(_("New game started with default options."))
    session.attach_blitz(blitz_state)
    if players == UNBALANCED_PLAYERS_COUNT:
        print(_("warning: 3-player mode can be unbalanced."))

    print(_("Type 'help' for available commands."))
    if ai_set:
        depth_label = "auto" if ai_minimax_depth is None else ai_minimax_depth
        print(
            f"AI players: {sorted(ai_set)} "
            f"(mode={ai_mode}, depth={depth_label}, time={ai_time}s)"
        )
    if blitz_state.is_enabled():
        _print_blitz_times(blitz_state)
    _print_state(session)

    if _auto_play_ai_until_human_or_end(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz_state,
    ):
        return

    state = _ShellState(
        session=session,
        has_unsaved_changes=has_unsaved_changes,
        ai_mode=ai_mode,
        ai_time=ai_time,
        ai_minimax_depth=ai_minimax_depth,
        players=players,
        walls_per_player=walls_per_player,
        board_size=board_size,
        ai_players=ai_players,
        blitz=blitz_state,
    )

    registry = _build_command_registry()

    if readline is not None:
        readline.set_history_length(MAX_HISTORY_SIZE)
        readline.set_completer_delims("")
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")

    while True:
        if _auto_play_pending_ai(state):
            break

        line, should_break = _read_shell_input(state, ">> ")
        if should_break:
            break

        if not line:
            continue

        handled, should_break = registry.dispatch(state, line)
        if should_break:
            break
        if not handled:
            print(_("Invalid command."))
