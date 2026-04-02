"""Extracted command handlers for interactive shell commands."""

from __future__ import annotations

from typing import Any, Callable


def command_new(
    state: Any,
    line: str,
    *,
    parse_new_config: Callable[[Any, str], Any],
    configure_logging: Callable[[bool, bool], None],
    create_new_session: Callable[[Any], Any],
    start_shell_session: Callable[[Any, Any], tuple[Any, bool]],
    sync_active_ai_settings_from_config: Callable[[Any], None],
) -> bool:
    config = parse_new_config(state, line)
    configure_logging(config.verbose, config.debug)
    session = create_new_session(config)
    blitz_state, should_break = start_shell_session(session, config)
    state.session = session
    state.has_unsaved_changes = False
    state.verbose = config.verbose
    state.debug = config.debug
    state.ai_mode = config.ai_mode
    state.ai_time = config.ai_time
    state.ai_minimax_depth = config.ai_minimax_depth
    state.ai_mcts_selection = config.ai_mcts_selection
    state.players = config.players
    state.walls_per_player = config.walls_per_player
    state.board_size = config.board_size
    state.ai_players = list(config.ai_players)
    state.blitz_enabled = config.blitz_enabled
    state.time_limit = config.time_limit
    state.blitz = blitz_state
    sync_active_ai_settings_from_config(state)
    return should_break


def command_help(line: str, *, show_help: Callable[[str], bool]) -> bool:
    show_help(line)
    return False


def command_load(
    state: Any,
    line: str,
    *,
    handle_load: Callable[..., tuple[Any, Any, bool, bool]],
    sync_runtime_config_from_session: Callable[[Any], None],
    sync_active_ai_settings_from_config: Callable[[Any], None],
    contest_error_type: type[Exception],
) -> bool:
    file_path = line[5:].strip()
    if not file_path:
        raise ValueError("Invalid format. Use: load FILE")
    try:
        session, blitz, has_unsaved_changes, should_break = handle_load(
            state.session,
            file_path,
            state.current_ai_mode,
            state.current_ai_time,
            state.current_ai_minimax_depth,
            blitz=state.blitz,
        )
        state.session = session
        state.blitz = blitz
        sync_runtime_config_from_session(state)
        sync_active_ai_settings_from_config(state)
        state.has_unsaved_changes = has_unsaved_changes
        return should_break
    except contest_error_type as exc:
        print(f"Invalid load file: {exc}")
        return False
    except OSError as exc:
        print(f"Cannot load file: {exc}")
        return False


def command_history(
    state: Any,
    *,
    handle_history: Callable[[Any], None],
) -> bool:
    handle_history(state.session)
    return False


def command_save(
    state: Any,
    line: str,
    *,
    handle_save: Callable[..., bool],
) -> bool:
    file_path = line[5:].strip()
    if not file_path:
        raise ValueError("Invalid format. Use: save FILE")
    try:
        state.has_unsaved_changes = handle_save(
            state.session,
            file_path,
            blitz=state.blitz,
        )
        return False
    except OSError as exc:
        print(f"Cannot save file: {exc}")
        return False


def command_set(
    state: Any,
    line: str,
    *,
    handle_set: Callable[[Any, str], None],
) -> bool:
    handle_set(state, line)
    return False


def command_moves(
    state: Any,
    *,
    print_moves: Callable[[Any], None],
) -> bool:
    print_moves(state.session)
    return False


def command_quit(
    state: Any,
    *,
    disconnect_client: Callable[[Any], bool],
    handle_quit: Callable[..., None],
    stop_server: Callable[[Any], None],
) -> bool:
    if disconnect_client(state):
        return False

    handle_quit(
        state.session,
        state.has_unsaved_changes,
        blitz=state.blitz,
    )
    stop_server(state)
    return True
