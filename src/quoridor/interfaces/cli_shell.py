"""Interactive shell loop for the Quoridor CLI."""

from __future__ import annotations

import gettext
import time
from dataclasses import dataclass
from typing import Callable

try:  # readline enables in-session history navigation with arrow keys.
    import readline  # type: ignore
except ImportError:  # pragma: no cover - platform-dependent
    readline = None

from ..application.game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.notation import get_edges_for_wall, get_node_from_notation
from ..core.validators import validate_pawn_move, validate_wall
from ..rules.win_rules import has_player_won
from .cli_constants import UNBALANCED_PLAYERS_COUNT, WALL_TOKEN_MIN_LENGTH
from .cli_render import _format_hint_move, _print_moves, _print_state, _render_ascii_board
from .contest_parser import ContestError

_ = gettext.gettext

MAX_HISTORY_SIZE = 1000


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
        session.state.graph, from_node, to_node, all_positions, session.state.board_size
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
    positions = [
        session.state.player_positions[p]
        for p in sorted(session.state.player_positions)
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
    ai_minimax_depth: int,
    *,
    blitz_remaining_times: dict[int, float] | None = None,
    blitz_paused: bool = False,
) -> bool:
    while session.player_types.get(session.state.current_player) == "ai":
        current_ai = session.state.current_player
        started = time.monotonic()
        session.play_ai_turn(depth=ai_minimax_depth)
        elapsed = time.monotonic() - started
        if blitz_remaining_times is not None and not blitz_paused:
            blitz_remaining_times[current_ai] -= elapsed
            if blitz_remaining_times[current_ai] <= 0:
                return _handle_timeout(session, current_ai)
        print(f"AI player {current_ai} played.")

        new_pos = session.state.player_positions[current_ai]
        if has_player_won(current_ai, new_pos, session.state.board_size):
            print(f"Player {current_ai} wins!")
            _print_state(session)
            return True

        _print_state(session)
    return False


def _show_help(line: str) -> bool:
    help_by_command = {
        "help": "help [CMD]\n  Show shell help, or help for CMD.",
        "history": "history\n  Show the played moves grouped by turns. Use Up/Down arrows to navigate command history. Use +TERM to search the last command matching TERM.",
        "load": "load FILE\n  Load a game position from FILE.",
        "save": "save FILE\n  Save the current game position to FILE.",
        "hint": "hint\n  Show a suggested move for the current player.",
        "show board": "show board\n  Display only the current board.",
        "show configuration": "show configuration\n  Display current runtime configuration.",
        "show time": "show time\n  Display remaining blitz time for each player.",
        "pause": "pause\n  Toggle blitz timer pause/resume.",
        "moves": "moves\n  Display legal pawn moves for the current player.",
        "move": "move <FROM-TO>\n  Move the current pawn (example: move e2-e3). Shorthand: e2-e3.",
        "wall": "wall <POSh|POSv>\n  Place a wall (example: wall e2h or wall e2v). Shorthand: e2h/e2v.",
        "undo": "undo [N]\n  Undo the last move-group (or N groups).",
        "redo": "redo [N]\n  Redo the last undone move-group (or N groups).",
        "quit": "quit\n  Exit the program.",
    }

    if line == "help" or line.startswith("help "):
        parts = line.split(maxsplit=1)
        if len(parts) == 1:
            print(
                "Commands: help [CMD], history, load, save, hint, show board, show configuration, show time, pause, moves, move, wall, undo, redo, quit"
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
    ai_minimax_depth: int,
    *,
    blitz_remaining_times: dict[int, float] | None = None,
    blitz_paused: bool = False,
) -> tuple[bool, bool]:
    has_unsaved_changes = True
    before_ai_cursor = session.history.cursor
    if _auto_play_ai_until_human_or_end(
        session,
        ai_minimax_depth,
        blitz_remaining_times=blitz_remaining_times,
        blitz_paused=blitz_paused,
    ):
        if session.history.cursor != before_ai_cursor:
            has_unsaved_changes = True
        return has_unsaved_changes, True
    if session.history.cursor != before_ai_cursor:
        has_unsaved_changes = True
    return has_unsaved_changes, False


def _handle_load(
    session: GameSession,
    file_path: str,
    ai_minimax_depth: int,
    *,
    blitz_remaining_times: dict[int, float] | None = None,
    blitz_paused: bool = False,
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
        ai_minimax_depth,
        blitz_remaining_times=blitz_remaining_times,
        blitz_paused=blitz_paused,
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


def _handle_hint(session: GameSession, ai_minimax_depth: int) -> None:
    from . import cli as cli_mod

    current = session.state.current_player
    move = cli_mod.choose_best_move_minimax(
        session.state, ai_player_id=current, depth=ai_minimax_depth
    )
    from_node = session.state.player_positions[current]
    best_hint = _format_hint_move(
        move, from_node=from_node, size=session.state.board_size
    )
    print(f"Best hint action: {best_hint}")


def _handle_move(
    session: GameSession,
    move_token: str,
    ai_minimax_depth: int,
    *,
    blitz_remaining_times: dict[int, float] | None = None,
    blitz_paused: bool = False,
) -> tuple[bool, bool]:
    if _play_pawn_move_from_token(session, move_token):
        return True, True
    return _apply_and_maybe_auto_play(
        session,
        ai_minimax_depth,
        blitz_remaining_times=blitz_remaining_times,
        blitz_paused=blitz_paused,
    )


def _handle_wall(
    session: GameSession,
    wall_token: str,
    ai_minimax_depth: int,
    *,
    blitz_remaining_times: dict[int, float] | None = None,
    blitz_paused: bool = False,
) -> tuple[bool, bool]:
    _place_wall_from_token(session, wall_token)
    return _apply_and_maybe_auto_play(
        session,
        ai_minimax_depth,
        blitz_remaining_times=blitz_remaining_times,
        blitz_paused=blitz_paused,
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


def _print_blitz_times(remaining_times: dict[int, float]) -> None:
    ordered = sorted(remaining_times)
    text = ", ".join(
        f"Player {pid}: {_format_blitz_time(remaining_times[pid])}" for pid in ordered
    )
    print(f"Blitz time -> {text}")


def _handle_timeout(session: GameSession, loser_id: int) -> bool:
    players = sorted(session.state.player_positions)
    winner = next((pid for pid in players if pid != loser_id), None)
    print(f"Player {loser_id} ran out of time and loses.")
    if winner is not None:
        print(f"Player {winner} wins!")
    _print_state(session)
    return True


def _print_configuration(state: "_ShellState") -> None:
    ai_sorted = sorted(set(state.ai_players))
    walls_text = (
        "unlimited" if state.walls_per_player < 0 else str(state.walls_per_player)
    )
    print("Current configuration:")
    print(f"players={state.players}")
    print(f"walls_per_player={walls_text}")
    print(f"board_size={state.board_size}")
    print(f"ai_players={ai_sorted}")
    print(f"ai_mode={state.ai_mode}")
    print(f"ai_time={state.ai_time}")
    print(f"ai_minimax_depth={state.ai_minimax_depth}")
    print(f"blitz={state.blitz_enabled}")
    print(f"time_limit={state.time_limit}")
    print(f"timer_paused={state.blitz_paused}")


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
            state.ai_minimax_depth,
            blitz_remaining_times=state.blitz_remaining_times,
            blitz_paused=state.blitz_paused,
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
        _handle_hint(state.session, state.ai_minimax_depth)
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
    if state.blitz_remaining_times is None:
        print("Blitz mode is not enabled.")
    else:
        _print_blitz_times(state.blitz_remaining_times)
        print(f"Timer paused: {'yes' if state.blitz_paused else 'no'}")
    return False


def _command_pause(state: _ShellState, _line: str) -> bool:
    if state.blitz_remaining_times is None:
        print("Blitz mode is not enabled.")
        return False
    state.blitz_paused = not state.blitz_paused
    print("Blitz timer paused." if state.blitz_paused else "Blitz timer resumed.")
    return False


def _command_moves(state: _ShellState, _line: str) -> bool:
    _print_moves(state.session)
    return False


def _command_move(state: _ShellState, line: str) -> bool:
    has_unsaved_changes, should_break = _handle_move(
        state.session,
        line[5:],
        state.ai_minimax_depth,
        blitz_remaining_times=state.blitz_remaining_times,
        blitz_paused=state.blitz_paused,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_wall(state: _ShellState, line: str) -> bool:
    has_unsaved_changes, should_break = _handle_wall(
        state.session,
        line[5:],
        state.ai_minimax_depth,
        blitz_remaining_times=state.blitz_remaining_times,
        blitz_paused=state.blitz_paused,
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
        state.ai_minimax_depth,
        blitz_remaining_times=state.blitz_remaining_times,
        blitz_paused=state.blitz_paused,
    )
    state.has_unsaved_changes = has_unsaved_changes
    return should_break


def _command_shorthand_wall(state: _ShellState, line: str) -> bool:
    has_unsaved_changes, should_break = _handle_wall(
        state.session,
        line,
        state.ai_minimax_depth,
        blitz_remaining_times=state.blitz_remaining_times,
        blitz_paused=state.blitz_paused,
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
    ai_minimax_depth: int
    players: int
    walls_per_player: int
    board_size: int
    ai_players: list[int]
    ai_mode: str
    ai_time: int
    blitz_enabled: bool
    time_limit: int
    blitz_remaining_times: dict[int, float] | None
    blitz_paused: bool


@dataclass
class _Command:
    matches: Callable[[str], bool]
    run: Callable[["_ShellState", str], bool]
    on_error: Callable[["_ShellState", str, Exception], tuple[bool, bool]] | None = None


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
    return line == "help" or line.startswith("help ")


def _match_load(line: str) -> bool:
    return line.lower().startswith("load ")


def _match_history(line: str) -> bool:
    return line == "history"


def _match_save(line: str) -> bool:
    return line.lower().startswith("save ")


def _match_hint(line: str) -> bool:
    return line == "hint"


def _match_show_board(line: str) -> bool:
    return line == "show board"


def _match_show_configuration(line: str) -> bool:
    return line == "show configuration"


def _match_show_time(line: str) -> bool:
    return line == "show time"


def _match_pause(line: str) -> bool:
    return line == "pause"


def _match_moves(line: str) -> bool:
    return line == "moves"


def _match_move(line: str) -> bool:
    return line.lower().startswith("move ")


def _match_wall(line: str) -> bool:
    return line.lower().startswith("wall ")


def _match_undo(line: str) -> bool:
    return line == "undo" or line.lower().startswith("undo ")


def _match_redo(line: str) -> bool:
    return line == "redo" or line.lower().startswith("redo ")


def _match_shorthand_move(line: str) -> bool:
    return "-" in line and " " not in line


def _match_shorthand_wall(line: str) -> bool:
    return " " not in line and len(line) >= 3 and line[-1].lower() in {"h", "v"}


def _match_quit(line: str) -> bool:
    return line == "quit"


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
    ai_minimax_depth: int,
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

    if save_file:
        from . import cli as cli_mod

        session = cli_mod._load_session_from_file(
            save_file,
            fallback_player_types=player_types,
            fallback_walls_per_player=remaining_walls,
        )
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
    remaining_times: dict[int, float] | None = None
    blitz_paused = False
    if blitz:
        remaining_times = {
            pid: float(time_limit * 60) for pid in sorted(session.state.player_positions)
        }

    if blitz:
        print(
            _("New game started (blitz: {minutes} min/player).").format(
                minutes=time_limit
            )
        )
    else:
        print(_("New game started with default options."))
    if players == UNBALANCED_PLAYERS_COUNT:
        print(_("warning: 3-player mode can be unbalanced."))

    print(_("Type 'help' for available commands."))
    if ai_set:
        print(
            f"AI players: {sorted(ai_set)} (mode={ai_mode}, depth={ai_minimax_depth}, time={ai_time}s)"
        )
    if remaining_times is not None:
        _print_blitz_times(remaining_times)
    _print_state(session)

    if _auto_play_ai_until_human_or_end(
        session,
        ai_minimax_depth,
        blitz_remaining_times=remaining_times,
        blitz_paused=blitz_paused,
    ):
        return

    state = _ShellState(
        session=session,
        has_unsaved_changes=has_unsaved_changes,
        ai_minimax_depth=ai_minimax_depth,
        players=players,
        walls_per_player=walls_per_player,
        board_size=board_size,
        ai_players=ai_players,
        ai_mode=ai_mode,
        ai_time=ai_time,
        blitz_enabled=blitz,
        time_limit=time_limit,
        blitz_remaining_times=remaining_times,
        blitz_paused=blitz_paused,
    )

    commands = [
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
        _Command(matches=_match_show_configuration, run=_command_show_configuration),
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

    while True:
        timed_player = state.session.state.current_player
        turn_started = time.monotonic()
        try:
            line = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        elapsed = time.monotonic() - turn_started
        if state.blitz_remaining_times is not None and not state.blitz_paused:
            state.blitz_remaining_times[timed_player] -= elapsed
            if state.blitz_remaining_times[timed_player] <= 0:
                _handle_timeout(state.session, timed_player)
                break

        if line.startswith("+"):
            if readline is not None:
                _maybe_remove_last_history_item()
            term = line[1:].strip()
            if not term:
                try:
                    term = input("Search history: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
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
