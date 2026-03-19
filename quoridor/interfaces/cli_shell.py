"""Interactive shell loop for the Quoridor CLI."""

from __future__ import annotations

import argparse
import gettext
import shlex
import signal
import time
from dataclasses import dataclass
from typing import Callable

try:  # readline enables in-session history navigation with arrow keys.
    import readline  # type: ignore
except ImportError:  # pragma: no cover - platform-dependent
    readline = None

from ..application.blitz import Blitz
from ..application.game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.notation import get_edges_for_wall, get_node_from_notation
from ..core.validators import validate_pawn_move, validate_wall
from ..rules.win_rules import has_player_won
from .cli_constants import (
    AI_MODE_DEFAULT,
    AI_MODE_ITERATIVE,
    AI_MODE_MCTS,
    UNBALANCED_PLAYERS_COUNT,
    WALL_TOKEN_MIN_LENGTH,
)
from .cli_render import (
    _format_hint_move,
    _print_moves,
    _print_state,
    _render_ascii_board,
)
from .contest_parser import ContestError

_ = gettext.gettext

MAX_HISTORY_SIZE = 1000


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


QUORIDOR_COMMANDS = [
    "new",
    "help",
    "hint",
    "load ",
    "save ",
    "show board",
    "show history",
    "show configuration",
    "show time",
    "pause",
    "moves",
    "move ",
    "wall ",
    "undo",
    "redo",
    "quit",
]


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


@dataclass()
class _ShellConfig:
    blitz_enabled: bool
    time_limit: int
    players: int
    walls_per_player: int
    board_size: int
    ai_players: list[int]
    ai_mode: str
    ai_time: int
    ai_minimax_depth: int | None


def _config_from_state(state: "_ShellState") -> _ShellConfig:
    return _ShellConfig(
        blitz_enabled=state.blitz.is_enabled(),
        time_limit=state.blitz.time_limit_minutes,
        players=state.players,
        walls_per_player=state.walls_per_player,
        board_size=state.board_size,
        ai_players=sorted(set(state.ai_players)),
        ai_mode=state.ai_mode,
        ai_time=state.ai_time,
        ai_minimax_depth=state.ai_minimax_depth,
    )


def _fallback_player_types(config: _ShellConfig) -> dict[int, str]:
    player_ids = range(1, config.players + 1)
    ai_set = set(config.ai_players)
    return {
        pid: ("ai" if pid in ai_set else "human") for pid in player_ids
    }


def _fallback_remaining_walls(config: _ShellConfig) -> dict[int, int]:
    wall_count = (
        config.walls_per_player if config.walls_per_player >= 0 else -1
    )
    return {pid: wall_count for pid in range(1, config.players + 1)}


def _create_new_session(config: _ShellConfig) -> GameSession:
    state = GameState(
        board_size=config.board_size,
        current_player=1,
        player_positions=initial_player_positions(
            config.board_size, config.players
        ),
        remaining_walls=_fallback_remaining_walls(config),
        vertical_walls=[],
        horizontal_walls=[],
    )
    return GameSession(
        state=state,
        player_types=_fallback_player_types(config),
    )


def _create_blitz_state(config: _ShellConfig, session: GameSession) -> Blitz:
    if not config.blitz_enabled:
        return Blitz(time_limit_minutes=config.time_limit)
    return Blitz(
        time_limit_minutes=config.time_limit,
        player_ids=session.state.player_positions,
    )


def _session_ai_players(session: GameSession) -> list[int]:
    return sorted(
        pid
        for pid, player_type in session.player_types.items()
        if player_type == "ai"
    )


def _print_shell_startup(
    session: GameSession,
    config: _ShellConfig,
    *,
    blitz_state: Blitz,
) -> None:
    if config.blitz_enabled:
        print(
            _("New game started (blitz: {minutes} min/player).").format(
                minutes=config.time_limit
            )
        )
    else:
        print(_("New game started with default options."))

    if len(session.state.player_positions) == UNBALANCED_PLAYERS_COUNT:
        print(_("warning: 3-player mode can be unbalanced."))

    print(_("Type 'help' for available commands."))
    ai_players = _session_ai_players(session)
    if ai_players:
        depth_label = (
            "auto"
            if config.ai_minimax_depth is None
            else config.ai_minimax_depth
        )
        print(
            f"AI players: {ai_players} "
            f"(mode={config.ai_mode}, depth={depth_label}, "
            f"time={config.ai_time}s)"
        )
    if blitz_state.is_enabled():
        _print_blitz_times(blitz_state)
    _print_state(session)


def _start_shell_session(
    session: GameSession,
    config: _ShellConfig,
) -> tuple[Blitz, bool]:
    blitz_state = _create_blitz_state(config, session)
    _print_shell_startup(session, config, blitz_state=blitz_state)
    should_break = _auto_play_ai_until_human_or_end(
        session,
        config.ai_mode,
        config.ai_time,
        config.ai_minimax_depth,
        blitz=blitz_state,
    )
    return blitz_state, should_break


def _build_new_argument_parser(
    current_config: _ShellConfig,
) -> argparse.ArgumentParser:
    from . import cli_parser as parser_mod

    parser = argparse.ArgumentParser(
        prog="new",
        add_help=False,
        exit_on_error=False,
    )
    parser.add_argument(
        "-b",
        "--blitz",
        action="store_true",
        default=current_config.blitz_enabled,
    )
    parser.add_argument(
        "-t",
        "--time",
        type=int,
        default=current_config.time_limit,
    )
    parser.add_argument(
        "-p",
        "--players",
        type=parser_mod._players_type,
        default=current_config.players,
    )
    parser.add_argument(
        "-w",
        "--walls",
        type=int,
        default=current_config.walls_per_player,
    )
    parser.add_argument(
        "-s",
        "--size",
        type=parser_mod._size_type,
        default=current_config.board_size,
    )
    parser.add_argument(
        "--ai-player",
        action="append",
        default=list(current_config.ai_players),
        type=parser_mod._player_id_type,
    )
    parser.add_argument(
        "--ai-mode",
        choices=[AI_MODE_DEFAULT, AI_MODE_ITERATIVE, AI_MODE_MCTS],
        default=current_config.ai_mode,
    )
    parser.add_argument(
        "--ai-time",
        type=int,
        default=current_config.ai_time,
    )
    parser.add_argument(
        "--ai-minimax-depth",
        type=int,
        default=current_config.ai_minimax_depth,
    )
    return parser


def _parse_new_config(state: "_ShellState", line: str) -> _ShellConfig:
    current_config = _config_from_state(state)
    raw_args = line[3:].strip()
    if not raw_args:
        return current_config

    try:
        argv = shlex.split(raw_args)
    except ValueError as exc:
        raise ValueError(f"invalid new arguments: {exc}") from exc

    parser = _build_new_argument_parser(current_config)
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as exc:
        raise ValueError(str(exc)) from exc
    except SystemExit as exc:
        raise ValueError("invalid new arguments") from exc

    if args.time <= 0:
        raise ValueError("--time must be > 0")
    if args.ai_time <= 0:
        raise ValueError("--ai-time must be > 0")
    if args.ai_minimax_depth is not None and args.ai_minimax_depth <= 0:
        raise ValueError("--ai-minimax-depth must be > 0")
    if any(pid > args.players for pid in args.ai_player):
        raise ValueError("--ai-player id must be <= --players")

    return _ShellConfig(
        blitz_enabled=bool(args.blitz),
        time_limit=args.time,
        players=args.players,
        walls_per_player=args.walls,
        board_size=args.size,
        ai_players=sorted(set(args.ai_player)),
        ai_mode=args.ai_mode,
        ai_time=args.ai_time,
        ai_minimax_depth=args.ai_minimax_depth,
    )


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
        started = time.time()
        move = session.compute_ai_move(
            mode=ai_mode,
            depth=ai_minimax_depth,
            time_limit_sec=ai_time,
        )
        elapsed = time.time() - started
        if blitz.consume_time(current_ai, elapsed):
            if _handle_timeout(session, current_ai):
                return True
            continue
        session.apply_ai_move(move, player_id=current_ai)
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
    help_by_command = {
        "new": (
            "new [ARGS]\n  Start a new game. Without ARGS, reuse the "
            "current configuration. With ARGS, override it for the new "
            "game."
        ),
        "help": "help [CMD]\n  Show shell help, or help for CMD.",
        "show history": (
            "show history\n  Show the played moves grouped by turns. "
            "Use Up/Down arrows to navigate command history. "
            "Use +TERM to search the last command matching TERM."
        ),
        "load": "load FILE\n  Load a game position from FILE.",
        "save": "save FILE\n  Save the current game position to FILE.",
        "hint": "hint\n  Show a suggested move for the current player.",
        "show board": "show board\n  Display only the current board.",
        "show configuration": (
            "show configuration\n  Display current runtime configuration."
        ),
        "show time": (
            "show time\n  Display remaining blitz time for each player."
        ),
        "pause": "pause\n  Toggle blitz timer pause/resume.",
        "moves": "moves\n  Display legal pawn moves for the current player.",
        "move": (
            "move <FROM-TO>\n  Move the current pawn "
            "(example: move e2-e3). Shorthand: e2-e3."
        ),
        "wall": (
            "wall <POSh|POSv>\n  Place a wall "
            "(example: wall e2h or wall e2v). Shorthand: e2h/e2v."
        ),
        "undo": "undo [N]\n  Undo the last move-group (or N groups).",
        "redo": "redo [N]\n  Redo the last undone move-group (or N groups).",
        "quit": "quit\n  Exit the program.",
    }

    if line_lower == "help" or line_lower.startswith("help "):
        parts = line.split(maxsplit=1)
        if len(parts) == 1:
            print(
                "Commands: new [ARGS], help [CMD], load, save, hint, "
                "show board, show history, show configuration, show time, "
                "pause, "
                "moves, move, wall, undo, redo, quit"
            )
            print("Use: help <command>")
            return True

        target = parts[1].strip().lower()
        if target in help_by_command:
            print(help_by_command[target])
        else:
            print(_("Invalid command."))
        return True

    return False


def _apply_and_maybe_auto_play(
    session: GameSession,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz,
) -> tuple[bool, bool]:
    has_unsaved_changes = True
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
) -> tuple[GameSession, bool, bool]:
    from . import cli as cli_mod

    session = cli_mod._load_session_from_file(
        file_path,
        fallback_player_types=session.player_types,
        fallback_walls_per_player=session.state.remaining_walls,
    )
    has_unsaved_changes = True
    print(_("Game loaded from {path}").format(path=file_path))
    _print_state(session)
    has_unsaved_changes, should_break = _apply_and_maybe_auto_play(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz,
    )
    return session, has_unsaved_changes, should_break


def _handle_save(session: GameSession, file_path: str) -> bool:
    from . import cli as cli_mod

    cli_mod._save_session_to_file(file_path, session)
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
    from . import cli as cli_mod

    current = session.state.current_player
    if ai_mode == "mcts":
        move = cli_mod.mcts_search(session.state, time_limit=ai_time)
        if move is None:
            raise ValueError("no legal moves available for hint")
    elif ai_mode == "iterative" or ai_minimax_depth is None:
        move = cli_mod.find_best_move_iterative(
            session.state,
            ai_player_id=current,
            time_limit_sec=ai_time,
            max_depth=ai_minimax_depth,
        )
    elif ai_mode == "minimax":
        move = cli_mod.find_best_move_minimax(
            session.state,
            ai_player_id=current,
            depth=ai_minimax_depth,
        )
    else:
        raise ValueError(f"unsupported AI mode: {ai_mode}")
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


def _handle_quit(session: GameSession, has_unsaved_changes: bool) -> None:
    if has_unsaved_changes:
        from . import cli as cli_mod

        cli_mod._prompt_save_before_quit(session)
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


def _handle_timeout(session: GameSession, loser_id: int) -> bool:
    _record, winner = session.timeout_player(loser_id)
    print(f"Player {loser_id} ran out of time and loses.")
    if winner is not None:
        print(f"Player {winner} wins!")
    _print_state(session)
    return winner is not None


def _read_shell_input(
    state: "_ShellState", prompt: str
) -> tuple[str | None, bool]:
    timed_player = state.session.state.current_player
    timeout_sec = state.blitz.input_timeout_for(timed_player)
    if timeout_sec is not None and timeout_sec <= 0:
        state.has_unsaved_changes = True
        if _handle_timeout(state.session, timed_player):
            return None, True
        return "", False

    started = time.time()
    alarm_started, previous_handler = _start_blitz_alarm(timeout_sec)
    try:
        line = input(prompt).strip()
    except _BlitzInputTimeout:
        state.blitz.expire_player(timed_player)
        state.has_unsaved_changes = True
        if _handle_timeout(state.session, timed_player):
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
        if _handle_timeout(state.session, timed_player):
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


def _command_new(state: _ShellState, line: str) -> bool:
    config = _parse_new_config(state, line)
    session = _create_new_session(config)
    blitz_state, should_break = _start_shell_session(session, config)
    state.session = session
    state.has_unsaved_changes = False
    state.ai_mode = config.ai_mode
    state.ai_time = config.ai_time
    state.ai_minimax_depth = config.ai_minimax_depth
    state.players = config.players
    state.walls_per_player = config.walls_per_player
    state.board_size = config.board_size
    state.ai_players = list(config.ai_players)
    state.blitz = blitz_state
    return should_break


def _command_help(_state: _ShellState, line: str) -> bool:
    _show_help(line)
    return False


def _command_load(state: _ShellState, line: str) -> bool:
    file_path = line[5:].strip()
    if not file_path:
        print("Invalid format. Use: load FILE")
        return False
    try:
        session, has_unsaved_changes, should_break = _handle_load(
            state.session,
            file_path,
            state.ai_mode,
            state.ai_time,
            state.ai_minimax_depth,
            blitz=state.blitz,
        )
        state.session = session
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
        state.has_unsaved_changes = _handle_save(state.session, file_path)
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
    _handle_quit(state.session, state.has_unsaved_changes)
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


@dataclass
class _Command:
    matches: Callable[[str], bool]
    run: Callable[["_ShellState", str], bool]
    on_error: (
        Callable[["_ShellState", str, Exception], tuple[bool, bool]] | None
    ) = None


def _handle_invalid_command(exc: Exception) -> None:
    print(f"Invalid command: {exc}")


def _error_as_invalid(
    _state: _ShellState, _line: str, exc: Exception
) -> tuple[bool, bool]:
    _handle_invalid_command(exc)
    return True, False


def _error_passthrough(
    _state: _ShellState, _line: str, _exc: Exception
) -> tuple[bool, bool]:
    return False, False


def _match_help(line: str) -> bool:
    line_lower = line.lower()
    return line_lower == "help" or line_lower.startswith("help ")


def _match_new(line: str) -> bool:
    line_lower = line.lower()
    return line_lower == "new" or line_lower.startswith("new ")


def _match_load(line: str) -> bool:
    return line.lower().startswith("load ")


def _match_history(line: str) -> bool:
    return line.lower() == "show history"


def _match_save(line: str) -> bool:
    return line.lower().startswith("save ")


def _match_hint(line: str) -> bool:
    return line.lower() == "hint"


def _match_show_board(line: str) -> bool:
    return line.lower() == "show board"


def _match_show_configuration(line: str) -> bool:
    return line.lower() == "show configuration"


def _match_show_time(line: str) -> bool:
    return line.lower() == "show time"


def _match_pause(line: str) -> bool:
    return line.lower() == "pause"


def _match_moves(line: str) -> bool:
    return line.lower() == "moves"


def _match_move(line: str) -> bool:
    return line.lower().startswith("move ")


def _match_wall(line: str) -> bool:
    return line.lower().startswith("wall ")


def _match_undo(line: str) -> bool:
    line_lower = line.lower()
    return line_lower == "undo" or line_lower.startswith("undo ")


def _match_redo(line: str) -> bool:
    line_lower = line.lower()
    return line_lower == "redo" or line_lower.startswith("redo ")


def _match_shorthand_move(line: str) -> bool:
    return "-" in line and " " not in line


def _match_shorthand_wall(line: str) -> bool:
    return (
        " " not in line and len(line) >= 3 and line[-1].lower() in {"h", "v"}
    )


def _match_quit(line: str) -> bool:
    return line.lower() == "quit"


def _run_command_loop(
    state: _ShellState,
    line: str,
    commands: list[_Command],
) -> tuple[bool, bool]:
    for command in commands:
        if not command.matches(line):
            continue
        try:
            should_break = command.run(state, line)
            return True, should_break
        except Exception as exc:
            if command.on_error is None:
                raise
            return command.on_error(state, line, exc)
    return False, False


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
    config = _ShellConfig(
        blitz_enabled=blitz,
        time_limit=time_limit,
        players=players,
        walls_per_player=walls_per_player,
        board_size=board_size,
        ai_players=sorted(set(ai_players)),
        ai_mode=ai_mode,
        ai_time=ai_time,
        ai_minimax_depth=ai_minimax_depth,
    )
    if save_file:
        print(_("Loading game from {path}").format(path=save_file))

    if save_file:
        from . import cli as cli_mod

        fallback_player_types = _fallback_player_types(config)
        fallback_remaining_walls = _fallback_remaining_walls(config)
        session = cli_mod._load_session_from_file(
            save_file,
            fallback_player_types=fallback_player_types,
            fallback_walls_per_player=fallback_remaining_walls,
        )
        has_unsaved_changes = False
    else:
        session = _create_new_session(config)
        has_unsaved_changes = False
    blitz_state, should_break = _start_shell_session(session, config)
    if should_break:
        return

    state = _ShellState(
        session=session,
        has_unsaved_changes=has_unsaved_changes,
        ai_mode=config.ai_mode,
        ai_time=config.ai_time,
        ai_minimax_depth=config.ai_minimax_depth,
        players=config.players,
        walls_per_player=config.walls_per_player,
        board_size=config.board_size,
        ai_players=list(config.ai_players),
        blitz=blitz_state,
    )

    commands = [
        _Command(
            matches=_match_new,
            run=_command_new,
            on_error=_error_as_invalid,
        ),
        _Command(matches=_match_help, run=_command_help),
        _Command(matches=_match_history, run=_command_history),
        _Command(
            matches=_match_load,
            run=_command_load,
            on_error=_error_as_invalid,
        ),
        _Command(
            matches=_match_save,
            run=_command_save,
            on_error=_error_as_invalid,
        ),
        _Command(
            matches=_match_hint,
            run=_command_hint,
            on_error=_error_as_invalid,
        ),
        _Command(matches=_match_show_board, run=_command_show_board),
        _Command(
            matches=_match_show_configuration, run=_command_show_configuration
        ),
        _Command(matches=_match_show_time, run=_command_show_time),
        _Command(matches=_match_pause, run=_command_pause),
        _Command(matches=_match_moves, run=_command_moves),
        _Command(
            matches=_match_move,
            run=_command_move,
            on_error=_error_as_invalid,
        ),
        _Command(
            matches=_match_wall,
            run=_command_wall,
            on_error=_error_as_invalid,
        ),
        _Command(
            matches=_match_undo,
            run=_command_undo,
            on_error=_error_as_invalid,
        ),
        _Command(
            matches=_match_redo,
            run=_command_redo,
            on_error=_error_as_invalid,
        ),
        _Command(
            matches=_match_shorthand_move,
            run=_command_shorthand_move,
            on_error=_error_passthrough,
        ),
        _Command(
            matches=_match_shorthand_wall,
            run=_command_shorthand_wall,
            on_error=_error_passthrough,
        ),
        _Command(matches=_match_quit, run=_command_quit),
    ]

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

        if line.startswith("+"):
            if readline is not None:
                _maybe_remove_last_history_item()
            term = line[1:].strip()
            if not term:
                term, should_break = _read_shell_input(
                    state, "Search history: "
                )
                if should_break:
                    break
                if readline is not None:
                    _maybe_remove_last_history_item()
            if not term:
                continue
            match = _get_last_history_match(term)
            if match is None:
                print(_("No command found in history."))
                continue
            line = match
            print(_("History match: {command}").format(command=line))

        if not line:
            continue

        handled, should_break = _run_command_loop(state, line, commands)
        if should_break:
            break
        if not handled:
            print(_("Invalid command."))
