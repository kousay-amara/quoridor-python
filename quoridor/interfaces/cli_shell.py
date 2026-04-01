"""Interactive shell loop for the Quoridor CLI."""

from __future__ import annotations

import argparse
import gettext
import shlex
import time

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
from .shell import bootstrap as shell_bootstrap
from .shell import command_handlers as shell_command_handlers
from .shell import commands as shell_commands
from .shell import events as shell_events
from .shell import input as shell_input
from .shell import network_handlers as shell_network_handlers
from .shell import runtime as shell_runtime
from .shell.state import _SavedLocalShellState, _ShellConfig, _ShellState

_ = gettext.gettext

MAX_HISTORY_SIZE = 1000


QUORIDOR_COMMANDS = command_names_for_completion()


def completer(text: str, state: int) -> str | None:
    matches = [cmd for cmd in QUORIDOR_COMMANDS if cmd.startswith(text)]
    if state < len(matches):
        return matches[state]
    return None


def _get_last_history_match(term: str) -> str | None:
    return shell_input.get_last_history_match(term)


def _maybe_remove_last_history_item() -> None:
    shell_input.maybe_remove_last_history_item()


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
        session.state.player_positions[player_id] for player_id in active_players
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
    return {pid: ("ai" if pid in ai_set else "human") for pid in player_ids}


def _format_minutes(minutes: float) -> str:
    return f"{minutes:g}"


def _fallback_remaining_walls(config: _ShellConfig) -> dict[int, int]:
    wall_count = config.walls_per_player if config.walls_per_player >= 0 else -1
    return {pid: wall_count for pid in range(1, config.players + 1)}


def _create_new_session(config: _ShellConfig) -> GameSession:
    state = GameState(
        board_size=config.board_size,
        current_player=1,
        player_positions=initial_player_positions(config.board_size, config.players),
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
        player_types={player_id: "human" for player_id in state.player_positions},
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
        pid for pid, player_type in session.player_types.items() if player_type == "ai"
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
            "auto" if config.ai_minimax_depth is None else config.ai_minimax_depth
        )
        time_label = (
            "" if config.ai_mode == AI_MODE_MINIMAX else f", time={config.ai_time}s"
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
        state.walls_per_player = _parse_int(value, field_name="walls_per_player")
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
            raise ValueError("ai_mode must be one of: minimax, iterative, mcts")
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
                raise ValueError("ai_minimax_depth cannot be auto/none in minimax mode")
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
    return shell_runtime.is_game_paused(blitz)


def _pause_blocks_gameplay(blitz: Blitz) -> bool:
    return shell_runtime.pause_blocks_gameplay(blitz, print_fn=print)


def _auto_play_ai_until_human_or_end(
    session: GameSession,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz | None = None,
    event_bus: shell_events.EventBus | None = None,
) -> bool:
    if blitz is None:
        blitz = Blitz(time_limit_minutes=0)
    return shell_runtime.auto_play_ai_until_human_or_end(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz,
        print_state=_print_state,
        has_player_won=has_player_won,
        timeout_handler=_handle_timeout,
        now_fn=time.time,
        event_bus=event_bus,
    )


def _run_auto_play_with_interrupt_handling(
    session: GameSession,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Blitz,
    event_bus: shell_events.EventBus | None = None,
) -> tuple[bool, bool]:
    return shell_runtime.run_auto_play_with_interrupt_handling(
        session,
        ai_mode,
        ai_time,
        ai_minimax_depth,
        blitz=blitz,
        auto_play_fn=_auto_play_ai_until_human_or_end,
        event_bus=event_bus,
        print_fn=print,
    )


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
        event_bus=state.event_bus,
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
        f"Player {pid}: {_format_blitz_time(remaining_times[pid])}" for pid in ordered
    )
    print(f"Blitz time -> {text}")


def _handle_timeout(
    session: GameSession,
    loser_id: int,
    *,
    before_blitz_snapshot=None,
    event_bus: shell_events.EventBus | None = None,
) -> bool:
    return shell_runtime.handle_timeout(
        session,
        loser_id,
        before_blitz_snapshot=before_blitz_snapshot,
        print_state=_print_state,
        event_bus=event_bus,
        print_fn=print,
    )


def _read_shell_input(state: "_ShellState", prompt: str) -> tuple[str | None, bool]:
    return shell_runtime.read_shell_input(
        state,
        prompt,
        timeout_handler=_handle_timeout,
        input_fn=input,
        now_fn=time.time,
        event_bus=state.event_bus,
        print_fn=print,
    )


def _print_configuration(state: "_ShellState") -> None:
    ai_sorted = sorted(set(state.ai_players))
    walls_text = (
        "unlimited" if state.walls_per_player < 0 else str(state.walls_per_player)
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

    return shell_command_handlers.command_new(
        state,
        line,
        parse_new_config=_parse_new_config,
        configure_logging=cli_mod._configure_logging,
        create_new_session=_create_new_session,
        start_shell_session=_start_shell_session,
        sync_active_ai_settings_from_config=_sync_active_ai_settings_from_config,
    )


def _command_help(_state: _ShellState, line: str) -> bool:
    _show_help(line)
    return False


def _command_load(state: _ShellState, line: str) -> bool:
    return shell_command_handlers.command_load(
        state,
        line,
        handle_load=_handle_load,
        sync_runtime_config_from_session=_sync_runtime_config_from_session,
        sync_active_ai_settings_from_config=_sync_active_ai_settings_from_config,
        contest_error_type=ContestError,
    )


def _command_history(state: _ShellState, _line: str) -> bool:
    return shell_command_handlers.command_history(
        state,
        handle_history=_handle_history,
    )


def _command_save(state: _ShellState, line: str) -> bool:
    return shell_command_handlers.command_save(
        state,
        line,
        handle_save=_handle_save,
    )


def _command_set(state: _ShellState, line: str) -> bool:
    return shell_command_handlers.command_set(
        state,
        line,
        handle_set=_handle_set,
    )


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
    return shell_network_handlers.command_server(
        state,
        line,
        command_server_fn=cli_network.command_server,
    )


def _apply_network_game_state_to_local_session(
    state: "_ShellState",
    game_state_update: dict,
) -> None:
    shell_network_handlers.apply_network_game_state_to_local_session(
        state,
        game_state_update,
        create_network_session=_create_network_session,
        print_state=_print_state,
    )


def _save_local_shell_state_before_network(state: "_ShellState") -> None:
    shell_network_handlers.save_local_shell_state_before_network(
        state,
        saved_state_factory=_SavedLocalShellState,
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
        state.current_ai_minimax_depth = saved_state.current_ai_minimax_depth
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
    def _on_notification(message: str) -> None:
        print(f"\n{message}")

    def _on_connection_lost(exc: OSError) -> None:
        print()
        cli_network._handle_connection_lost(state, exc)

    return shell_network_handlers.command_join(
        state,
        line,
        command_join_fn=cli_network.command_join,
        save_local_state_before_network=_save_local_shell_state_before_network,
        apply_game_state_to_local_session=_apply_network_game_state_to_local_session,
        on_notification=_on_notification,
        on_connection_lost=_on_connection_lost,
    )


def _command_ping(state: _ShellState, _line: str) -> bool:
    return shell_network_handlers.command_ping(
        state,
        _line,
        command_ping_fn=cli_network.command_ping,
    )


def _command_players(state: _ShellState, line: str) -> bool:
    return shell_network_handlers.command_players(
        state,
        line,
        command_players_fn=cli_network.command_players,
    )


def _command_scoreboard(state: _ShellState, line: str) -> bool:
    return shell_network_handlers.command_scoreboard(
        state,
        line,
        command_scoreboard_fn=cli_network.command_scoreboard,
    )


def _command_new_player(state: _ShellState, line: str) -> bool:
    return shell_network_handlers.command_new_player(
        state,
        line,
        command_new_player_fn=cli_network.command_new_player,
    )


def _command_accept(state: _ShellState, line: str) -> bool:
    return cli_network.command_accept(state, line)


def _command_decline(state: _ShellState, line: str) -> bool:
    return cli_network.command_decline(state, line)


def _command_cancel(state: _ShellState, line: str) -> bool:
    return cli_network.command_cancel(state, line)


def _command_away(state: _ShellState, line: str) -> bool:
    return cli_network.command_away(state, line)


def _command_back(state: _ShellState, line: str) -> bool:
    return cli_network.command_back(state, line)


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
    return shell_command_handlers.command_quit(
        state,
        disconnect_client=cli_network.disconnect_client,
        handle_quit=_handle_quit,
        stop_server=cli_network.stop_server,
    )


def _build_command_registry() -> shell_commands.CommandRegistry:
    return shell_commands.build_command_registry(
        command_new=_command_new,
        command_help=_command_help,
        command_history=_command_history,
        command_load=_command_load,
        command_save=_command_save,
        command_set=_command_set,
        command_hint=_command_hint,
        command_show_board=_command_show_board,
        command_show_configuration=_command_show_configuration,
        command_show_time=_command_show_time,
        command_pause=_command_pause,
        command_server=_command_server,
        command_join=_command_join,
        command_ping=_command_ping,
        command_players=_command_players,
        command_scoreboard=_command_scoreboard,
        command_accept=_command_accept,
        command_decline=_command_decline,
        command_cancel=_command_cancel,
        command_away=_command_away,
        command_back=_command_back,
        command_moves=_command_moves,
        command_move=_command_move,
        command_wall=_command_wall,
        command_undo=_command_undo,
        command_redo=_command_redo,
        command_shorthand_move=_command_shorthand_move,
        command_shorthand_wall=_command_shorthand_wall,
        command_quit=_command_quit,
        command_new_player=_command_new_player,
        invalid_handler=_handle_invalid_command,
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
    from . import cli as cli_mod

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
    state, should_break = shell_bootstrap.initialize_shell_state(
        config=config,
        save_file=save_file,
        shell_state_factory=_ShellState,
        create_new_session=_create_new_session,
        fallback_player_types=_fallback_player_types,
        fallback_remaining_walls=_fallback_remaining_walls,
        load_session_from_file=cli_mod._load_session_from_file,
        load_blitz_snapshot_from_file=cli_mod._load_blitz_snapshot_from_file,
        blitz_factory=Blitz,
        format_minutes=_format_minutes,
        print_state=_print_state,
        print_blitz_times=_print_blitz_times,
        session_ai_players=_session_ai_players,
        auto_play_fn=_auto_play_ai_until_human_or_end,
        ai_mode_minimax=AI_MODE_MINIMAX,
        unbalanced_players_count=UNBALANCED_PLAYERS_COUNT,
        translate=_,
    )
    if should_break or state is None:
        return
    state.event_bus = shell_events.EventBus()
    state.network_restore_callback = lambda: _restore_saved_local_shell_state(state)

    registry = _build_command_registry()
    discovery_listener = cli_network.start_discovery_listener()

    if startup_server_port is not None:
        cli_network.command_server(
            state,
            f"server start {startup_server_port}",
        )

    shell_input.setup_readline(completer=completer, history_size=MAX_HISTORY_SIZE)

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
