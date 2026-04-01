"""Network command handlers and callback wiring for interactive shell."""

from __future__ import annotations

from typing import Any, Callable


def _emit_from_state(state: Any, event_name: str, **payload: Any) -> None:
    event_bus = getattr(state, "event_bus", None)
    if event_bus is None:
        return
    emit = getattr(event_bus, "emit", None)
    if emit is None:
        return
    emit(event_name, **payload)


def command_server(
    state: Any,
    line: str,
    *,
    command_server_fn: Callable[[Any, str], bool],
) -> bool:
    handled = command_server_fn(state, line)
    _emit_from_state(state, "network.server_command", line=line, handled=handled)
    return handled


def apply_network_game_state_to_local_session(
    state: Any,
    game_state_update: dict,
    *,
    create_network_session: Callable[[dict], Any],
    print_state: Callable[..., None],
) -> None:
    snapshot = game_state_update["state"]
    winner_player_id = game_state_update["winner_id"]
    local_player_id = game_state_update["player_id"]

    with state.network_sync_lock:
        state.session = create_network_session(snapshot)
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
        print_state(
            state.session,
            perspective_player_id=state.network_player_id,
        )
        if winner_player_id is not None:
            print(f"Player {winner_player_id} wins!")
        _emit_from_state(
            state,
            "network.state_applied",
            winner_id=winner_player_id,
            local_player_id=local_player_id,
        )


def save_local_shell_state_before_network(
    state: Any,
    *,
    saved_state_factory: Callable[..., Any],
) -> None:
    if state.saved_local_state is not None:
        return
    state.saved_local_state = saved_state_factory(
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


def command_join(
    state: Any,
    line: str,
    *,
    command_join_fn: Callable[[Any, str], bool],
    save_local_state_before_network: Callable[[Any], None],
    apply_game_state_to_local_session: Callable[[Any, dict], None],
) -> bool:
    handled = command_join_fn(state, line)
    client = state.network_client
    if client is None:
        return handled
    save_local_state_before_network(state)

    def _on_opponent_move(move_notation: str) -> None:
        print(f"\nOPPONENT_MOVE {move_notation}")

    def _on_game_state(game_state_update: dict) -> None:
        apply_game_state_to_local_session(state, game_state_update)

    client.set_opponent_move_callback(_on_opponent_move)
    client.set_game_state_callback(_on_game_state)
    for pending_move in client.drain_opponent_moves():
        _on_opponent_move(pending_move)
    for game_state_update in client.drain_game_state_updates():
        _on_game_state(game_state_update)
    _emit_from_state(state, "network.join", line=line, handled=handled)
    return handled


def command_ping(
    state: Any,
    line: str,
    *,
    command_ping_fn: Callable[[Any, str], bool],
) -> bool:
    handled = command_ping_fn(state, line)
    _emit_from_state(state, "network.ping", handled=handled)
    return handled


def command_players(
    state: Any,
    line: str,
    *,
    command_players_fn: Callable[[Any, str], bool],
) -> bool:
    handled = command_players_fn(state, line)
    _emit_from_state(state, "network.players", handled=handled)
    return handled


def command_scoreboard(
    state: Any,
    line: str,
    *,
    command_scoreboard_fn: Callable[[Any, str], bool],
) -> bool:
    handled = command_scoreboard_fn(state, line)
    _emit_from_state(state, "network.scoreboard", handled=handled)
    return handled


def command_new_player(
    state: Any,
    line: str,
    *,
    command_new_player_fn: Callable[[Any, str], bool],
) -> bool:
    handled = command_new_player_fn(state, line)
    _emit_from_state(state, "network.new_player", handled=handled, line=line)
    return handled
