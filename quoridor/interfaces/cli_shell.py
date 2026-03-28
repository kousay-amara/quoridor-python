"""Interactive shell loop for the Quoridor CLI."""

from __future__ import annotations

import argparse
import gettext
import shlex
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

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
from ..application.game_application_service import GameApplicationService
from ..application.game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.move_record import GameSnapshot
from ..core.notation import get_edges_for_wall, get_node_from_notation
from ..network.basic_network import GameStateUpdate
from ..core.validators import validate_pawn_move, validate_wall
from ..rules.win_rules import has_player_won
from .cli_constants import (
    AI_MODE_ITERATIVE,
    AI_MODE_MINIMAX,
    AI_MODE_MCTS,
    UNBALANCED_PLAYERS_COUNT,
    WALL_TOKEN_MIN_LENGTH,
)
from .cli_parser import _is_ai_time_passed_on_cli
from .cli_render import (
    _format_hint_move,
    _print_moves,
    _print_state,
    _render_ascii_board,
)
from .contest_parser import ContestError
from .cli_io import _prompt_save_before_quit
from . import cli_network

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


@dataclass()
class _ShellConfig:
    verbose: bool
    debug: bool
    blitz_enabled: bool
    time_limit: float
    players: int
    walls_per_player: int
    board_size: int
    ai_players: list[int]
    ai_mode: str
    ai_time: int
    ai_minimax_depth: int | None


class _SavedLocalShellState:
    def __init__(
        self,
        *,
        session: GameSession,
        has_unsaved_changes: bool,
        current_ai_mode: str,
        current_ai_time: int,
        current_ai_minimax_depth: int | None,
        players: int,
        walls_per_player: int,
        board_size: int,
        ai_players: list[int],
        blitz_enabled: bool,
        time_limit: float,
        blitz: Blitz,
    ) -> None:
        self.session = session
        self.has_unsaved_changes = has_unsaved_changes
        self.current_ai_mode = current_ai_mode
        self.current_ai_time = current_ai_time
        self.current_ai_minimax_depth = current_ai_minimax_depth
        self.players = players
        self.walls_per_player = walls_per_player
        self.board_size = board_size
        self.ai_players = list(ai_players)
        self.blitz_enabled = blitz_enabled
        self.time_limit = time_limit
        self.blitz = blitz


def _config_from_state(state: "_ShellState") -> _ShellConfig:
    return _ShellConfig(
        verbose=state.verbose,
        debug=state.debug,
        blitz_enabled=state.blitz_enabled,
        time_limit=state.time_limit,
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


def _format_minutes(minutes: float) -> str:
    return f"{minutes:g}"


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


def _create_network_session(snapshot: GameSnapshot) -> GameSession:
    state = GameState.from_snapshot(snapshot)
    return GameSession(
        state=state,
        player_types={
            player_id: "human" for player_id in state.player_positions
        },
    )


def _create_blitz_state(config: _ShellConfig, session: GameSession) -> Blitz:
    if not config.blitz_enabled:
        return Blitz(time_limit_minutes=config.time_limit)
    return Blitz(
        time_limit_minutes=config.time_limit,
        player_ids=session.state.player_positions,
    )


def _effective_ai_time_limit(
    ai_time: int,
    *,
    blitz: Blitz,
    player_id: int,
) -> float:
    if not blitz.is_enabled():
        return float(ai_time)
    return min(float(ai_time), blitz.remaining_time(player_id))


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
                minutes=_format_minutes(config.time_limit)
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
        time_label = (
            ""
            if config.ai_mode == AI_MODE_MINIMAX
            else f", time={config.ai_time}s"
        )
        print(
            f"AI players: {ai_players} "
            f"(mode={config.ai_mode}, depth={depth_label}{time_label})"
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
    should_break, interrupted = _run_auto_play_with_interrupt_handling(
        session,
        config.ai_mode,
        config.ai_time,
        config.ai_minimax_depth,
        blitz=blitz_state,
    )
    return blitz_state, should_break or interrupted


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
        type=parser_mod._positive_time_type,
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
        choices=[AI_MODE_MINIMAX, AI_MODE_ITERATIVE, AI_MODE_MCTS],
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
    if args.ai_mode == AI_MODE_MINIMAX and args.ai_minimax_depth is None:
        raise ValueError("--ai-mode minimax requires --ai-minimax-depth")
    if any(pid > args.players for pid in args.ai_player):
        raise ValueError("--ai-player id must be <= --players")
    if args.ai_mode == AI_MODE_MINIMAX and _is_ai_time_passed_on_cli(argv):
        print("warning: --ai-time is ignored in minimax mode")

    return _ShellConfig(
        verbose=current_config.verbose,
        debug=current_config.debug,
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


_SET_ALIASES = {
    "verbose": "verbose",
    "debug": "debug",
    "players": "players",
    "walls": "walls_per_player",
    "walls_per_player": "walls_per_player",
    "size": "board_size",
    "board_size": "board_size",
    "blitz": "blitz_enabled",
    "blitz_enabled": "blitz_enabled",
    "time": "time_limit",
    "time_limit": "time_limit",
    "ai_players": "ai_players",
    "ai_player": "ai_players",
    "ai_mode": "ai_mode",
    "ai_time": "ai_time",
    "ai_minimax_depth": "ai_minimax_depth",
}


def _parse_set_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean value expected (true/false)")


def _parse_int(raw: str, *, field_name: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _parse_positive_int(raw: str, *, field_name: str) -> int:
    value = _parse_int(raw, field_name=field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _parse_set_ai_players(raw: str, *, players: int) -> list[int]:
    from . import cli_parser as parser_mod

    normalized = raw.strip()
    if not normalized or normalized.lower() == "none":
        return []

    tokens = normalized.replace(",", " ").split()
    parsed = sorted({parser_mod._player_id_type(token) for token in tokens})
    if any(pid > players for pid in parsed):
        raise ValueError("ai_players ids must be <= players")
    return parsed


def _sync_runtime_config_from_session(state: "_ShellState") -> None:
    state.players = len(state.session.state.player_positions)
    state.board_size = state.session.state.board_size
    state.ai_players = _session_ai_players(state.session)
    state.blitz_enabled = state.blitz.is_enabled()
    state.time_limit = state.blitz.time_limit_minutes


def _sync_active_ai_settings_from_config(state: "_ShellState") -> None:
    state.current_ai_mode = state.ai_mode
    state.current_ai_time = state.ai_time
    state.current_ai_minimax_depth = state.ai_minimax_depth


def _format_set_value(param: str, value: object) -> str:
    if param == "ai_players":
        return str(sorted(set(value)))
    if param == "time_limit":
        return _format_minutes(float(value))
    return str(value)


def _handle_set(state: "_ShellState", line: str) -> None:
    from . import cli_parser as parser_mod

    raw = line[3:].strip()
    if not raw or "=" not in raw:
        raise ValueError("Invalid format. Use: set PARAM=VALUE")

    param_raw, value_raw = raw.split("=", 1)
    param_key = param_raw.strip().lower().replace("-", "_")
    if not param_key:
        raise ValueError("Invalid format. Use: set PARAM=VALUE")

    param = _SET_ALIASES.get(param_key)
    if param is None:
        raise ValueError(f"unknown setting: {param_raw.strip()}")

    value = value_raw.strip()
    if param == "verbose":
        state.verbose = _parse_set_bool(value)
        parsed_value = state.verbose
    elif param == "debug":
        state.debug = _parse_set_bool(value)
        parsed_value = state.debug
    elif param == "players":
        parsed_value = parser_mod._players_type(value)
        if any(pid > parsed_value for pid in state.ai_players):
            raise ValueError("ai_players ids must be <= players")
        state.players = parsed_value
    elif param == "walls_per_player":
        state.walls_per_player = _parse_int(
            value, field_name="walls_per_player"
        )
        parsed_value = state.walls_per_player
    elif param == "board_size":
        state.board_size = parser_mod._size_type(value)
        parsed_value = state.board_size
    elif param == "blitz_enabled":
        state.blitz_enabled = _parse_set_bool(value)
        parsed_value = state.blitz_enabled
    elif param == "time_limit":
        state.time_limit = parser_mod._positive_time_type(value)
        parsed_value = state.time_limit
    elif param == "ai_players":
        state.ai_players = _parse_set_ai_players(value, players=state.players)
        parsed_value = state.ai_players
    elif param == "ai_mode":
        normalized = value.lower()
        if normalized not in {
            AI_MODE_MINIMAX,
            AI_MODE_ITERATIVE,
            AI_MODE_MCTS,
        }:
            raise ValueError(
                "ai_mode must be one of: minimax, iterative, mcts"
            )
        if normalized == AI_MODE_MINIMAX and state.ai_minimax_depth is None:
            raise ValueError("ai_mode=minimax requires ai_minimax_depth")
        state.ai_mode = normalized
        parsed_value = state.ai_mode
    elif param == "ai_time":
        state.ai_time = _parse_positive_int(value, field_name="ai_time")
        parsed_value = state.ai_time
    elif param == "ai_minimax_depth":
        normalized = value.lower()
        if normalized in {"auto", "none"}:
            if state.ai_mode == AI_MODE_MINIMAX:
                raise ValueError(
                    "ai_minimax_depth cannot be auto/none in minimax mode"
                )
            state.ai_minimax_depth = None
        else:
            state.ai_minimax_depth = _parse_positive_int(
                value, field_name="ai_minimax_depth"
            )
        parsed_value = state.ai_minimax_depth
    else:
        raise ValueError(f"unsupported setting: {param}")

    display_name = "blitz" if param == "blitz_enabled" else param
    print(
        f"Configuration updated: {display_name}="
        f"{_format_set_value(param, parsed_value)}"
    )
    print("Use 'new' to apply this setting to a fresh game.")


def _is_game_paused(blitz: Blitz) -> bool:
    return blitz.paused


def _pause_blocks_gameplay(blitz: Blitz) -> bool:
    if _is_game_paused(blitz):
        print("Game is paused.")
        return True
    return False


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

    if _is_game_paused(blitz):
        return False

    while session.player_types.get(session.state.current_player) == "ai":
        current_ai = session.state.current_player
        before_blitz_snapshot = (
            blitz.snapshot() if blitz.is_enabled() else None
        )
        effective_ai_time = _effective_ai_time_limit(
            ai_time,
            blitz=blitz,
            player_id=current_ai,
        )
        started = time.time()
        move = session.compute_ai_move(
            mode=ai_mode,
            depth=ai_minimax_depth,
            time_limit_sec=effective_ai_time,
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
        session.apply_ai_move(move, player_id=current_ai)
        print(f"AI player {current_ai} played.")

        new_pos = session.state.player_positions[current_ai]
        if has_player_won(current_ai, new_pos, session.state.board_size):
            print(f"Player {current_ai} wins!")
            _print_state(session)
            return True

        _print_state(session)
    return False


def _run_auto_play_with_interrupt_handling(
    session: GameSession,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz,
) -> tuple[bool, bool]:
    try:
        return (
            _auto_play_ai_until_human_or_end(
                session,
                ai_mode,
                ai_time,
                ai_minimax_depth,
                blitz=blitz,
            ),
            False,
        )
    except KeyboardInterrupt:
        print()
        return False, True


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
    game_over, interrupted = _run_auto_play_with_interrupt_handling(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz,
    )
    if interrupted:
        if session.history.cursor != before_ai_cursor:
            has_unsaved_changes = True
        return has_unsaved_changes, True
    if game_over:
        if session.history.cursor != before_ai_cursor:
            has_unsaved_changes = True
        return has_unsaved_changes, True
    if session.history.cursor != before_ai_cursor:
        has_unsaved_changes = True
    return has_unsaved_changes, False


def _auto_play_pending_ai(state: "_ShellState") -> bool:
    before_ai_cursor = state.session.history.cursor
    game_over, interrupted = _run_auto_play_with_interrupt_handling(
        state.session,
        state.current_ai_mode,
        state.current_ai_time,
        state.current_ai_minimax_depth,
        blitz=state.blitz,
    )
    if state.session.history.cursor != before_ai_cursor:
        state.has_unsaved_changes = True
    if game_over or interrupted:
        if state.session.history.cursor != before_ai_cursor:
            state.has_unsaved_changes = True
        return True
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
    service = GameApplicationService(session=session, blitz=blitz)
    session, loaded_blitz = service.load(
        file_path,
        fallback_player_types=session.player_types,
        fallback_walls_per_player=session.state.remaining_walls,
    )

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
    service = GameApplicationService(session=session, blitz=blitz)
    service.save(file_path)
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
    *,
    blitz: Blitz,
) -> None:
    from . import cli as cli_mod

    if _is_game_paused(blitz):
        raise ValueError("Game is paused.")

    service = GameApplicationService(session=session, blitz=blitz)
    move = service.hint(
        ai_mode=ai_mode,
        ai_time=ai_time,
        ai_minimax_depth=ai_minimax_depth,
        mcts_fn=cli_mod.mcts_search,
        iterative_fn=cli_mod.find_best_move_iterative,
        minimax_fn=cli_mod.find_best_move_minimax,
    )
    current = session.state.current_player
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


def _handle_undo(session: GameSession, line: str, *, blitz: Blitz) -> bool:
    current = session.state.current_player
    parts = line.split()
    if len(parts) > 2:
        raise ValueError("Invalid format. Use: undo [N]")
    count = 1
    if len(parts) == 2:
        count = _parse_positive_int(parts[1], field_name="N")

    service = GameApplicationService(session=session, blitz=blitz)
    groups_done, total_undone = service.undo_groups(
        requester_id=current,
        count=count,
    )

    print(f"Undone groups: {groups_done}, moves: {total_undone}")
    _print_state(session)
    return total_undone > 0


def _handle_redo(session: GameSession, line: str, *, blitz: Blitz) -> bool:
    if _is_game_paused(blitz):
        raise ValueError("Game is paused.")

    current = session.state.current_player
    parts = line.split()
    if len(parts) > 2:
        raise ValueError("Invalid format. Use: redo [N]")
    count = 1
    if len(parts) == 2:
        count = _parse_positive_int(parts[1], field_name="N")

    service = GameApplicationService(session=session, blitz=blitz)
    groups_done, total_redone = service.redo_groups(
        requester_id=current,
        count=count,
    )

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
    print(f"verbose={state.verbose}")
    print(f"debug={state.debug}")
    print(f"players={state.players}")
    print(f"walls_per_player={walls_text}")
    print(f"board_size={state.board_size}")
    print(f"ai_players={ai_sorted}")
    print(f"ai_mode={state.ai_mode}")
    print(f"ai_time={state.ai_time}")
    print(f"ai_minimax_depth={state.ai_minimax_depth}")
    print(f"blitz={state.blitz_enabled}")
    print(f"time_limit={_format_minutes(state.time_limit)}")
    print(f"timer_paused={state.blitz.paused}")


def _command_new(state: _ShellState, line: str) -> bool:
    from . import cli as cli_mod

    config = _parse_new_config(state, line)
    cli_mod._configure_logging(config.verbose, config.debug)
    session = _create_new_session(config)
    blitz_state, should_break = _start_shell_session(session, config)
    state.session = session
    state.has_unsaved_changes = False
    state.verbose = config.verbose
    state.debug = config.debug
    state.ai_mode = config.ai_mode
    state.ai_time = config.ai_time
    state.ai_minimax_depth = config.ai_minimax_depth
    state.players = config.players
    state.walls_per_player = config.walls_per_player
    state.board_size = config.board_size
    state.ai_players = list(config.ai_players)
    state.blitz_enabled = config.blitz_enabled
    state.time_limit = config.time_limit
    state.blitz = blitz_state
    _sync_active_ai_settings_from_config(state)
    return should_break


def _command_help(_state: _ShellState, line: str) -> bool:
    _show_help(line)
    return False


def _command_load(state: _ShellState, line: str) -> bool:
    file_path = line[5:].strip()
    if not file_path:
        raise ValueError("Invalid format. Use: load FILE")
    try:
        session, blitz, has_unsaved_changes, should_break = _handle_load(
            state.session,
            file_path,
            state.current_ai_mode,
            state.current_ai_time,
            state.current_ai_minimax_depth,
            blitz=state.blitz,
        )
        state.session = session
        state.blitz = blitz
        _sync_runtime_config_from_session(state)
        _sync_active_ai_settings_from_config(state)
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
        raise ValueError("Invalid format. Use: save FILE")
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


def _command_set(state: _ShellState, line: str) -> bool:
    _handle_set(state, line)
    return False


def _command_hint(state: _ShellState, _line: str) -> bool:
    if _pause_blocks_gameplay(state.blitz):
        return False

    try:
        _handle_hint(
            state.session,
            state.current_ai_mode,
            state.current_ai_time,
            state.current_ai_minimax_depth,
            blitz=state.blitz,
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
    is_paused = state.blitz.toggle_pause()
    if state.blitz.is_enabled():
        print("Blitz timer paused." if is_paused else "Blitz timer resumed.")
    else:
        print("Game paused." if is_paused else "Game resumed.")
    return False


def _command_moves(state: _ShellState, _line: str) -> bool:
    _print_moves(state.session)
    return False


def _command_move(state: _ShellState, line: str) -> bool:
    if _pause_blocks_gameplay(state.blitz):
        return False

    if state.network_client is not None:
        return cli_network.command_move(state, line)

    has_unsaved_changes, should_break = _handle_move(
        state.session,
        line[5:],
        state.current_ai_mode,
        state.current_ai_time,
        state.current_ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_wall(state: _ShellState, line: str) -> bool:
    if _pause_blocks_gameplay(state.blitz):
        return False

    if state.network_client is not None:
        return cli_network.command_wall(state, line)

    has_unsaved_changes, should_break = _handle_wall(
        state.session,
        line[5:],
        state.current_ai_mode,
        state.current_ai_time,
        state.current_ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _parse_server_port(value: str) -> int:
    return cli_network.parse_server_port(value)


def _command_server(state: _ShellState, line: str) -> bool:
    return cli_network.command_server(state, line)


def _apply_network_game_state_to_local_session(
    state: "_ShellState",
    game_state_update: GameStateUpdate,
) -> None:
    snapshot = game_state_update["state"]
    winner_player_id = game_state_update["winner_id"]
    local_player_id = game_state_update["player_id"]

    with state.network_sync_lock:
        state.session = _create_network_session(snapshot)
        state.players = len(state.session.state.player_positions)
        state.board_size = state.session.state.board_size
        if state.session.state.remaining_walls:
            state.walls_per_player = max(
                state.session.state.remaining_walls.values()
            )
        state.ai_players = []
        state.network_player_id = local_player_id
        state.has_unsaved_changes = True

        print()
        _print_state(
            state.session,
            perspective_player_id=state.network_player_id,
        )
        if winner_player_id is not None:
            print(f"Player {winner_player_id} wins!")


def _save_local_shell_state_before_network(state: "_ShellState") -> None:
    if state.saved_local_state is not None:
        return
    state.saved_local_state = _SavedLocalShellState(
        session=state.session,
        has_unsaved_changes=state.has_unsaved_changes,
        current_ai_mode=state.current_ai_mode,
        current_ai_time=state.current_ai_time,
        current_ai_minimax_depth=state.current_ai_minimax_depth,
        players=state.players,
        walls_per_player=state.walls_per_player,
        board_size=state.board_size,
        ai_players=list(state.ai_players),
        blitz_enabled=state.blitz_enabled,
        time_limit=state.time_limit,
        blitz=state.blitz,
    )


def _restore_saved_local_shell_state(state: "_ShellState") -> None:
    saved_state = state.saved_local_state
    if saved_state is None:
        return

    with state.network_sync_lock:
        state.session = saved_state.session
        state.has_unsaved_changes = saved_state.has_unsaved_changes
        state.current_ai_mode = saved_state.current_ai_mode
        state.current_ai_time = saved_state.current_ai_time
        state.current_ai_minimax_depth = (
            saved_state.current_ai_minimax_depth
        )
        state.players = saved_state.players
        state.walls_per_player = saved_state.walls_per_player
        state.board_size = saved_state.board_size
        state.ai_players = list(saved_state.ai_players)
        state.blitz_enabled = saved_state.blitz_enabled
        state.time_limit = saved_state.time_limit
        state.blitz = saved_state.blitz
        state.network_player_id = None
        state.saved_local_state = None

    print("Returned to local game.")
    _print_state(state.session)


def _command_join(state: _ShellState, line: str) -> bool:
    handled = cli_network.command_join(state, line)
    client = state.network_client
    if client is None:
        return handled
    _save_local_shell_state_before_network(state)

    def _on_opponent_move(move_notation: str) -> None:
        print(f"\nOPPONENT_MOVE {move_notation}")

    def _on_game_state(game_state_update: GameStateUpdate) -> None:
        _apply_network_game_state_to_local_session(state, game_state_update)

    client.set_opponent_move_callback(_on_opponent_move)
    client.set_game_state_callback(_on_game_state)
    for pending_move in client.drain_opponent_moves():
        _on_opponent_move(pending_move)
    for game_state_update in client.drain_game_state_updates():
        _on_game_state(game_state_update)
    return handled


def _command_ping(state: _ShellState, _line: str) -> bool:
    return cli_network.command_ping(state, _line)


def _command_players(state: _ShellState, line: str) -> bool:
    return cli_network.command_players(state, line)


def _command_scoreboard(state: _ShellState, line: str) -> bool:
    return cli_network.command_scoreboard(state, line)


def _command_new_player(state: _ShellState, line: str) -> bool:
    return cli_network.command_new_player(state, line)


def _command_undo(state: _ShellState, line: str) -> bool:
    if _pause_blocks_gameplay(state.blitz):
        return False

    if _handle_undo(state.session, line, blitz=state.blitz):
        state.has_unsaved_changes = True
    return False


def _command_redo(state: _ShellState, line: str) -> bool:
    if _pause_blocks_gameplay(state.blitz):
        return False

    if _handle_redo(state.session, line, blitz=state.blitz):
        state.has_unsaved_changes = True
    return False


def _command_shorthand_move(state: _ShellState, line: str) -> bool:
    if _pause_blocks_gameplay(state.blitz):
        return False

    if state.network_client is not None:
        return cli_network.command_shorthand_move(state, line)

    has_unsaved_changes, should_break = _handle_move(
        state.session,
        line,
        state.current_ai_mode,
        state.current_ai_time,
        state.current_ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_shorthand_wall(state: _ShellState, line: str) -> bool:
    if _pause_blocks_gameplay(state.blitz):
        return False

    if state.network_client is not None:
        return cli_network.command_shorthand_wall(state, line)

    has_unsaved_changes, should_break = _handle_wall(
        state.session,
        line,
        state.current_ai_mode,
        state.current_ai_time,
        state.current_ai_minimax_depth,
        blitz=state.blitz,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_quit(state: _ShellState, _line: str) -> bool:
    if cli_network.disconnect_client(state):
        return False

    _handle_quit(
        state.session,
        state.has_unsaved_changes,
        blitz=state.blitz,
    )
    cli_network.stop_server(state)
    return True


@dataclass
class _ShellState:
    session: GameSession
    has_unsaved_changes: bool
    verbose: bool
    debug: bool
    ai_mode: str
    ai_time: int
    ai_minimax_depth: int | None
    current_ai_mode: str
    current_ai_time: int
    current_ai_minimax_depth: int | None
    players: int
    walls_per_player: int
    board_size: int
    ai_players: list[int]
    blitz_enabled: bool
    time_limit: float
    blitz: Blitz
    network_server: cli_network.NetworkServer | None = None
    network_client: cli_network.NetworkClient | None = None
    network_restore_callback: Callable[[], None] | None = None
    network_player_id: int | None = None
    saved_local_state: _SavedLocalShellState | None = None
    network_sync_lock: threading.Lock = field(
        default_factory=threading.Lock
    )


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


class _NewCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "new" or line_lower.startswith("new ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_new(state, line)


class _NetworkNewPlayerCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
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

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_new_player(state, line)


class _HelpCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "help" or line_lower.startswith("help ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_help(state, line)


class _HistoryCommand(_BaseCommand):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower in {"history", "show history"}

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


class _SetCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "set" or line_lower.startswith("set ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_set(state, line)


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


class _ServerCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "server" or line_lower.startswith("server ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_server(state, line)


class _JoinCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        line_lower = line.lower()
        return line_lower == "join" or line_lower.startswith("join ")

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_join(state, line)


class _PingCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower() == "ping"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_ping(state, line)


class _PlayersCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower() == "players"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_players(state, line)


class _ScoreboardCommand(_InvalidAsCommandError):
    def matches(self, line: str) -> bool:
        return line.lower() == "scoreboard"

    def run(self, state: _ShellState, line: str) -> bool:
        return _command_scoreboard(state, line)


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
            _NetworkNewPlayerCommand(),
            _NewCommand(),
            _HelpCommand(),
            _HistoryCommand(),
            _LoadCommand(),
            _SaveCommand(),
            _SetCommand(),
            _HintCommand(),
            _ShowBoardCommand(),
            _ShowConfigurationCommand(),
            _ShowTimeCommand(),
            _ServerCommand(),
            _JoinCommand(),
            _PingCommand(),
            _PlayersCommand(),
            _ScoreboardCommand(),
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
    startup_server_port: int | None = None,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    config = _ShellConfig(
        verbose=verbose,
        debug=debug,
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

    loaded_blitz_snapshot = None
    if save_file:
        from . import cli as cli_mod

        fallback_player_types = _fallback_player_types(config)
        fallback_remaining_walls = _fallback_remaining_walls(config)
        session = cli_mod._load_session_from_file(
            save_file,
            fallback_player_types=fallback_player_types,
            fallback_walls_per_player=fallback_remaining_walls,
        )
        try:
            loaded_blitz_snapshot = (
                cli_mod._load_blitz_snapshot_from_file(save_file)
            )
        except (OSError, ValueError):
            loaded_blitz_snapshot = None
        has_unsaved_changes = False
    else:
        session = _create_new_session(config)
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
                minutes=_format_minutes(time_limit)
            )
        )
    else:
        print(_("New game started with default options."))
    session.attach_blitz(blitz_state)
    if len(session.state.player_positions) == UNBALANCED_PLAYERS_COUNT:
        print(_("warning: 3-player mode can be unbalanced."))

    print(_("Type 'help' for available commands."))
    session_ai_players = _session_ai_players(session)
    if session_ai_players:
        depth_label = "auto" if ai_minimax_depth is None else ai_minimax_depth
        time_label = (
            ""
            if ai_mode == AI_MODE_MINIMAX
            else f", time={ai_time}s"
        )
        print(
            f"AI players: {session_ai_players} "
            f"(mode={ai_mode}, depth={depth_label}{time_label})"
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
        verbose=config.verbose,
        debug=config.debug,
        ai_mode=config.ai_mode,
        ai_time=config.ai_time,
        ai_minimax_depth=config.ai_minimax_depth,
        current_ai_mode=config.ai_mode,
        current_ai_time=config.ai_time,
        current_ai_minimax_depth=config.ai_minimax_depth,
        players=len(session.state.player_positions),
        walls_per_player=config.walls_per_player,
        board_size=session.state.board_size,
        ai_players=_session_ai_players(session),
        blitz_enabled=blitz_state.is_enabled(),
        time_limit=blitz_state.time_limit_minutes,
        blitz=blitz_state,
    )
    state.network_restore_callback = (
        lambda: _restore_saved_local_shell_state(state)
    )

    registry = _build_command_registry()
    discovery_listener = cli_network.start_discovery_listener()

    if startup_server_port is not None:
        cli_network.command_server(
            state,
            f"server start {startup_server_port}",
        )

    if readline is not None:
        readline.set_history_length(MAX_HISTORY_SIZE)
        readline.set_completer_delims("")
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")

    try:
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
    finally:
        cli_network.stop_discovery_listener(discovery_listener)
