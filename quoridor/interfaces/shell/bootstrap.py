"""Bootstrap helpers for interactive shell startup."""

from __future__ import annotations

from typing import Any, Callable


def initialize_shell_state(
    *,
    config: Any,
    save_file: str | None,
    shell_state_factory: Callable[..., Any],
    create_new_session: Callable[[Any], Any],
    fallback_player_types: Callable[[Any], dict[int, str]],
    fallback_remaining_walls: Callable[[Any], dict[int, int]],
    load_session_from_file: Callable[..., Any],
    load_blitz_snapshot_from_file: Callable[[str], Any],
    blitz_factory: Callable[..., Any],
    format_minutes: Callable[[float], str],
    print_state: Callable[..., None],
    print_blitz_times: Callable[[Any], None],
    session_ai_players: Callable[[Any], list[int]],
    auto_play_fn: Callable[..., bool],
    ai_mode_minimax: str,
    unbalanced_players_count: int,
    translate: Callable[[str], str],
) -> tuple[Any | None, bool]:
    if save_file:
        print(translate("Loading game from {path}").format(path=save_file))

    loaded_blitz_snapshot = None
    if save_file:
        session = load_session_from_file(
            save_file,
            fallback_player_types=fallback_player_types(config),
            fallback_walls_per_player=fallback_remaining_walls(config),
        )
        try:
            loaded_blitz_snapshot = load_blitz_snapshot_from_file(save_file)
        except (OSError, ValueError):
            loaded_blitz_snapshot = None
        has_unsaved_changes = False
    else:
        session = create_new_session(config)
        has_unsaved_changes = False

    blitz_state = blitz_factory(time_limit_minutes=config.time_limit)
    if loaded_blitz_snapshot is not None:
        blitz_state.restore_snapshot(loaded_blitz_snapshot)
        print(translate("Game loaded with blitz timer state."))
    elif config.blitz_enabled:
        blitz_state = blitz_factory(
            time_limit_minutes=config.time_limit,
            player_ids=session.state.player_positions,
        )
        print(
            translate("New game started (blitz: {minutes} min/player).").format(
                minutes=format_minutes(config.time_limit)
            )
        )
    else:
        print(translate("New game started with default options."))

    session.attach_blitz(blitz_state)
    if len(session.state.player_positions) == unbalanced_players_count:
        print(translate("warning: 3-player mode can be unbalanced."))

    print(translate("Type 'help' for available commands."))
    active_ai_players = session_ai_players(session)
    if active_ai_players:
        depth_label = (
            "auto" if config.ai_minimax_depth is None else config.ai_minimax_depth
        )
        time_label = (
            "" if config.ai_mode == ai_mode_minimax else f", time={config.ai_time}s"
        )
        print(
            f"AI players: {active_ai_players} "
            f"(mode={config.ai_mode}, depth={depth_label}{time_label})"
        )
    if blitz_state.is_enabled():
        print_blitz_times(blitz_state)
    print_state(session)

    ai_mcts_selection = getattr(config, "ai_mcts_selection", "UCT")

    if auto_play_fn(
        session,
        config.ai_mode,
        config.ai_time,
        config.ai_minimax_depth,
        blitz=blitz_state,
        mcts_selection=ai_mcts_selection,
    ):
        return None, True

    state = shell_state_factory(
        session=session,
        has_unsaved_changes=has_unsaved_changes,
        verbose=config.verbose,
        debug=config.debug,
        ai_mode=config.ai_mode,
        ai_time=config.ai_time,
        ai_minimax_depth=config.ai_minimax_depth,
        ai_mcts_selection=ai_mcts_selection,
        current_ai_mode=config.ai_mode,
        current_ai_time=config.ai_time,
        current_ai_minimax_depth=config.ai_minimax_depth,
        current_ai_mcts_selection=ai_mcts_selection,
        players=len(session.state.player_positions),
        walls_per_player=config.walls_per_player,
        board_size=session.state.board_size,
        ai_players=session_ai_players(session),
        blitz_enabled=blitz_state.is_enabled(),
        time_limit=blitz_state.time_limit_minutes,
        blitz=blitz_state,
    )
    return state, False
