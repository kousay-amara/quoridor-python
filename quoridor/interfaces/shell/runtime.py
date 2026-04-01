"""Runtime helpers for shell gameplay loop (pause, timeout, autoplay, input)."""

from __future__ import annotations

import signal
import time
from typing import Any, Callable


def _emit(event_bus: Any | None, event_name: str, **payload: Any) -> None:
    if event_bus is None:
        return
    emit = getattr(event_bus, "emit", None)
    if emit is None:
        return
    emit(event_name, **payload)


class BlitzInputTimeout(Exception):
    """Raised when a blitz timer interrupts a blocking CLI input."""


def _raise_blitz_input_timeout(_signum: int, _frame: object) -> None:
    raise BlitzInputTimeout


def start_blitz_alarm(timeout_sec: float | None) -> tuple[bool, object | None]:
    if timeout_sec is None or timeout_sec <= 0:
        return False, None

    try:
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _raise_blitz_input_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_sec)
    except (AttributeError, ValueError):
        return False, None

    return True, previous_handler


def stop_blitz_alarm(
    alarm_started: bool, previous_handler: object | None
) -> None:
    if not alarm_started:
        return

    signal.setitimer(signal.ITIMER_REAL, 0.0)
    signal.signal(signal.SIGALRM, previous_handler)


def effective_ai_time_limit(
    ai_time: int,
    *,
    blitz: Any,
    player_id: int,
) -> float:
    if not blitz.is_enabled():
        return float(ai_time)
    return min(float(ai_time), blitz.remaining_time(player_id))


def is_game_paused(blitz: Any) -> bool:
    return blitz.paused


def pause_blocks_gameplay(blitz: Any, *, print_fn: Callable[[str], None]) -> bool:
    if is_game_paused(blitz):
        print_fn("Game is paused.")
        return True
    return False


def handle_timeout(
    session: Any,
    loser_id: int,
    *,
    before_blitz_snapshot: Any = None,
    print_state: Callable[..., None],
    event_bus: Any | None = None,
    print_fn: Callable[[str], None] = print,
) -> bool:
    _record, winner = session.timeout_player(
        loser_id,
        before_blitz_snapshot=before_blitz_snapshot,
    )
    print_fn(f"Player {loser_id} ran out of time and loses.")
    if winner is not None:
        print_fn(f"Player {winner} wins!")
    print_state(session)
    _emit(
        event_bus,
        "game.timeout",
        loser_id=loser_id,
        winner_id=winner,
    )
    return winner is not None


def auto_play_ai_until_human_or_end(
    session: Any,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Any,
    print_state: Callable[..., None],
    has_player_won: Callable[[int, int, int], bool],
    timeout_handler: Callable[..., bool],
    now_fn: Callable[[], float] = time.time,
    event_bus: Any | None = None,
    print_fn: Callable[[str], None] = print,
) -> bool:
    if is_game_paused(blitz):
        return False

    while session.player_types.get(session.state.current_player) == "ai":
        current_ai = session.state.current_player
        before_blitz_snapshot = blitz.snapshot() if blitz.is_enabled() else None
        current_ai_time = effective_ai_time_limit(
            ai_time,
            blitz=blitz,
            player_id=current_ai,
        )
        started = now_fn()
        move = session.compute_ai_move(
            mode=ai_mode,
            depth=ai_minimax_depth,
            time_limit_sec=current_ai_time,
        )
        elapsed = now_fn() - started
        if blitz.consume_time(current_ai, elapsed):
            if timeout_handler(
                session,
                current_ai,
                before_blitz_snapshot=before_blitz_snapshot,
                event_bus=event_bus,
            ):
                return True
            continue
        session.apply_ai_move(move, player_id=current_ai)
        print_fn(f"AI player {current_ai} played.")
        _emit(
            event_bus,
            "game.ai_move_applied",
            player_id=current_ai,
            move=move,
        )

        new_pos = session.state.player_positions[current_ai]
        if has_player_won(current_ai, new_pos, session.state.board_size):
            print_fn(f"Player {current_ai} wins!")
            print_state(session)
            _emit(event_bus, "game.winner", player_id=current_ai)
            return True

        print_state(session)
    return False


def run_auto_play_with_interrupt_handling(
    session: Any,
    ai_mode: str,
    ai_time: int,
    ai_minimax_depth: int | None,
    *,
    blitz: Any,
    auto_play_fn: Callable[..., bool],
    event_bus: Any | None = None,
    print_fn: Callable[..., None] = print,
) -> tuple[bool, bool]:
    try:
        return (
            auto_play_fn(
                session,
                ai_mode,
                ai_time,
                ai_minimax_depth,
                blitz=blitz,
                event_bus=event_bus,
            ),
            False,
        )
    except KeyboardInterrupt:
        print_fn()
        _emit(event_bus, "shell.interrupted", reason="keyboard_interrupt")
        return False, True


def read_shell_input(
    state: Any,
    prompt: str,
    *,
    timeout_handler: Callable[..., bool],
    input_fn: Callable[[str], str] = input,
    now_fn: Callable[[], float] = time.time,
    event_bus: Any | None = None,
    print_fn: Callable[..., None] = print,
) -> tuple[str | None, bool]:
    timed_player = state.session.state.current_player
    before_blitz_snapshot = (
        state.blitz.snapshot() if state.blitz.is_enabled() else None
    )
    timeout_sec = state.blitz.input_timeout_for(timed_player)
    if timeout_sec is not None and timeout_sec <= 0:
        state.has_unsaved_changes = True
        if timeout_handler(
            state.session,
            timed_player,
            before_blitz_snapshot=before_blitz_snapshot,
            event_bus=event_bus,
        ):
            return None, True
        return "", False

    started = now_fn()
    alarm_started, previous_handler = start_blitz_alarm(timeout_sec)
    try:
        line = input_fn(prompt).strip()
    except BlitzInputTimeout:
        state.blitz.expire_player(timed_player)
        state.has_unsaved_changes = True
        if timeout_handler(
            state.session,
            timed_player,
            before_blitz_snapshot=before_blitz_snapshot,
            event_bus=event_bus,
        ):
            return None, True
        return "", False
    except (EOFError, KeyboardInterrupt):
        print_fn()
        _emit(event_bus, "shell.input_interrupted", reason="eof_or_keyboard")
        return None, True
    finally:
        stop_blitz_alarm(alarm_started, previous_handler)

    elapsed = now_fn() - started
    if state.blitz.consume_time(timed_player, elapsed):
        state.has_unsaved_changes = True
        if timeout_handler(
            state.session,
            timed_player,
            before_blitz_snapshot=before_blitz_snapshot,
            event_bus=event_bus,
        ):
            return None, True
        return "", False

    _emit(event_bus, "shell.input_received", line=line)
    return line, False
