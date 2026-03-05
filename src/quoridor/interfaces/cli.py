"""Command-line interface for Quoridor."""

from __future__ import annotations

import argparse
import gettext
import logging
import sys
from importlib import metadata

from ..i18n import setup_i18n
from ..application.contest import run_contest
from ..application.minimax_engine import choose_best_move_minimax
from ..config import DEFAULTS, load_or_init_config
from .contest_parser import ContestError, parse_contest_file
from ..application.game_session import GameSession, initial_player_positions
from ..core.game_state import GameState
from ..core.notation import (
    get_edges_for_wall,
    get_node_from_notation,
    get_notation_from_node,
)
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..rules.win_rules import has_player_won

_ = gettext.gettext
LOGGER = logging.getLogger(__name__)


class QuoridorArgumentParser(argparse.ArgumentParser):
    """Custom parser for the Quoridor CLI."""

    def error(self, message: str) -> None:
        sys.stderr.write(f"{self.prog}: {_('error')}: {message}\n\n")
        self.print_help(sys.stderr)
        raise SystemExit(1)


def _players_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("players must be an integer") from exc
    if value not in {2, 3, 4}:
        raise argparse.ArgumentTypeError("players must be one of: 2, 3, 4")
    return value


def _size_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must be an integer") from exc
    if value < 3 or value > 15 or value % 2 == 0:
        raise argparse.ArgumentTypeError("size must be odd and between 3 and 15")
    return value


def _player_id_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("player id must be an integer") from exc
    if value < 1 or value > 4:
        raise argparse.ArgumentTypeError("player id must be between 1 and 4")
    return value


def _build_parser(defaults: dict[str, bool | int]) -> argparse.ArgumentParser:
    parser = QuoridorArgumentParser(
        prog="quoridor",
        description=_("Quoridor game command-line interface."),
        add_help=True,
    )
    parser.add_argument("save_file", nargs="?", help=_("path to a saved game file"))
    parser.add_argument(
        "-V", "--version", action="store_true", help=_("show program version and exit")
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help=_("increase program verbosity")
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help=_("show debug messages")
    )
    parser.add_argument(
        "-b", "--blitz", action="store_true", help=_("enable blitz mode")
    )
    parser.add_argument(
        "-c",
        "--contest",
        action="store_true",
        help=_("enable contest mode (read position file and output a move)"),
    )
    parser.add_argument(
        "-t",
        "--time",
        type=int,
        default=int(defaults["time"]),
        help=_("time limit in minutes for blitz mode"),
    )
    parser.add_argument(
        "-p",
        "--players",
        type=_players_type,
        default=int(defaults.get("players", 2)),
        help=_("number of players (2, 3, or 4)"),
    )
    parser.add_argument(
        "-w",
        "--walls",
        type=int,
        default=int(defaults.get("walls", 20)),
        help=_("walls per player (negative means unlimited)"),
    )
    parser.add_argument(
        "-s",
        "--size",
        type=_size_type,
        default=int(defaults.get("size", 9)),
        help=_("board size (odd number between 3 and 15)"),
    )
    parser.add_argument(
        "--ai-player",
        action="append",
        default=[],
        type=_player_id_type,
        help=_("player id controlled by AI (repeat option for multiple players)"),
    )
    parser.add_argument(
        "--ai-mode",
        choices=["minimax"],
        default="minimax",
        help=_("AI mode (currently only minimax is available)"),
    )
    parser.add_argument(
        "--ai-time",
        type=int,
        default=5,
        help=_("AI thinking time in seconds (reserved for iterative mode)"),
    )
    parser.add_argument(
        "--ai-minimax-depth",
        type=int,
        default=2,
        help=_("minimax search depth"),
    )
    parser.set_defaults(
        verbose=bool(defaults["verbose"]), blitz=bool(defaults["blitz"])
    )
    return parser


def _build_contest_parser() -> argparse.ArgumentParser:
    parser = QuoridorArgumentParser(
        prog="quoridor",
        description="Quoridor contest mode.",
        add_help=True,
    )
    parser.add_argument("save_file", nargs="?", help="path to a saved game file")
    parser.add_argument(
        "-c",
        "--contest",
        action="store_true",
        help="enable contest mode (read position file and output a move)",
    )
    return parser


def _is_contest_on_cli(argv: list[str]) -> bool:
    return any(token in {"-c", "--contest"} for token in argv)


def _is_time_passed_on_cli(argv: list[str]) -> bool:
    return any(
        token in {"-t", "--time"} or token.startswith("--time=") for token in argv
    )


def _configure_logging(verbose: bool, debug: bool) -> None:
    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    LOGGER.debug("Logging configured with level=%s", logging.getLevelName(level))


def _get_version() -> str:
    try:
        return metadata.version("quoridor")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def _main_contest(argv: list[str]) -> int:
    parser = _build_contest_parser()
    args = parser.parse_args(argv)
    if not args.save_file:
        parser.error("contest mode requires a game file argument")
    try:
        move = run_contest(args.save_file)
    except ContestError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    print(move)
    return 0


def _main_interactive(argv: list[str]) -> int:
    setup_i18n()
    defaults = load_or_init_config()
    parser = _build_parser(defaults)
    args = parser.parse_args(argv)
    if any(pid > args.players for pid in args.ai_player):
        parser.error("--ai-player id must be <= --players")
    if args.ai_time <= 0:
        parser.error("--ai-time must be > 0")
    if args.ai_minimax_depth <= 0:
        parser.error("--ai-minimax-depth must be > 0")

    if args.version:
        print(_get_version())
        return 0

    _configure_logging(args.verbose, args.debug)
    LOGGER.debug("Loaded defaults from .qoridorrc: %s", defaults)
    LOGGER.debug("Parsed CLI args: %s", vars(args))

    time_limit = args.time
    if _is_time_passed_on_cli(argv) and not args.blitz:
        sys.stderr.write(_("warning: --time is ignored unless --blitz is enabled\n"))
        time_limit = int(defaults.get("time", DEFAULTS["time"]))
    _run_interactive_shell(
        blitz=args.blitz,
        time_limit=time_limit,
        save_file=args.save_file,
        players=args.players,
        walls_per_player=args.walls,
        board_size=args.size,
        ai_players=args.ai_player,
        ai_mode=args.ai_mode,
        ai_time=args.ai_time,
        ai_minimax_depth=args.ai_minimax_depth,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    cli_argv = sys.argv[1:] if argv is None else argv
    if _is_contest_on_cli(cli_argv):
        return _main_contest(cli_argv)
    return _main_interactive(cli_argv)


def _node(row: int, col: int, size: int) -> int:
    return row * size + col


def _render_ascii_board(state) -> str:
    """
    Render proche du format contest/spec:
    - cellules: '_', '1','2','3','4'
    - mur vertical: préfixe 'X' devant la cellule de droite (col > 0)
    - ligne séparatrice: 'X' si mur horizontal, sinon '.'
    """
    size = state.board_size

    vwalls = set(tuple(edge) for edge in state.vertical_walls)
    hwalls = set(tuple(edge) for edge in state.horizontal_walls)

    player_at = {node: pid for pid, node in state.player_positions.items()}

    lines = []
    lines.append("    " + "   ".join(chr(ord("a") + c) for c in range(size)))
    lines.append("")

    for r in range(size):
        row_tokens = []
        for c in range(size):
            n = _node(r, c, size)
            cell = str(player_at[n]) if n in player_at else "_"
            row_tokens.append(cell)

            if c < size - 1:
                right = _node(r, c + 1, size)
                has_vwall = (n, right) in vwalls or (right, n) in vwalls
                row_tokens.append("X" if has_vwall else " ")

        lines.append(f"{r + 1:>2}  " + " ".join(row_tokens))

        if r < size - 1:
            sep_tokens = []
            for c in range(size):
                top = _node(r, c, size)
                bottom = _node(r + 1, c, size)
                has_hwall = (top, bottom) in hwalls or (bottom, top) in hwalls
                sep_tokens.append("X" if has_hwall else " ")
                if c < size - 1:
                    sep_tokens.append(" ")
            lines.append("    " + " ".join(sep_tokens))

    return "\n".join(lines)


def _print_state(session: GameSession) -> None:
    state = session.state
    size = state.board_size

    ordered_ids = sorted(state.player_positions.keys())
    players_line = ", ".join(
        f"Player {pid}: {get_notation_from_node(state.player_positions[pid], size)}"
        for pid in ordered_ids
    )
    walls_line = ", ".join(
        f"Player {pid}: "
        f"{'unlimited' if state.remaining_walls.get(pid, 0) < 0 else state.remaining_walls.get(pid, 0)}"
        for pid in ordered_ids
    )
    print(_render_ascii_board(state))
    print()
    print(f"Current player: {state.current_player}")
    print(players_line)
    print(f"Walls -> {walls_line}")


def _print_moves(session: GameSession) -> None:
    """Shows the legal moves for the current player"""
    current = session.state.current_player

    from_node = session.state.player_positions[current]
    all_positions = list(session.state.player_positions.values())
    legal_nodes = get_all_legal_pawn_moves(
        session.state.graph, from_node, all_positions
    )
    legal_notation = [
        get_notation_from_node(n, session.state.board_size) for n in sorted(legal_nodes)
    ]
    print(f"Legal pawn moves for player {current}: {legal_notation}")


def _play_pawn_move_from_token(session: GameSession, move_token: str) -> bool:
    token = move_token.strip().lower()
    if "-" not in token:
        raise ValueError("Invalid format. Use: e2-e3")

    from_txt, to_txt = token.split("-", 1)
    from_node = get_node_from_notation(from_txt, session.state.board_size)
    to_node = get_node_from_notation(to_txt, session.state.board_size)

    current = session.state.current_player
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
    if len(token) < 3:
        raise ValueError("Invalid format. Use: e2h or e2v")

    ori_char = token[-1]
    if ori_char not in {"h", "v"}:
        raise ValueError("Invalid wall orientation. Use h or v")

    wall_edges = get_edges_for_wall(token, session.state.board_size)
    orientation = "horizontal" if ori_char == "h" else "vertical"

    current = session.state.current_player
    session.place_wall(current, wall_edges, orientation)
    _print_state(session)


def _format_hint_move(move: tuple, *, from_node: int, size: int) -> str:
    move_type = move[0]
    if move_type == "pawn":
        to_node = int(move[1])
        return f"{get_notation_from_node(from_node, size)}-{get_notation_from_node(to_node, size)}"
    if move_type == "wall":
        edges = move[1]
        orientation = move[2]
        anchor = min(min(a, b) for a, b in edges)
        ori = "h" if orientation in {"h", "horizontal"} else "v"
        return f"{get_notation_from_node(anchor, size)}{ori}"
    return str(move)


def _load_session_from_file(
    path: str,
    *,
    fallback_player_types: dict[int, str],
    fallback_walls_per_player: dict[int, int],
) -> GameSession:
    position = parse_contest_file(path)
    players = sorted(position.positions.keys())
    remaining_walls = {pid: fallback_walls_per_player.get(pid, 20) for pid in players}
    player_types = {pid: fallback_player_types.get(pid, "human") for pid in players}
    state = GameState(
        board_size=position.size,
        current_player=position.current_player,
        player_positions=position.positions,
        remaining_walls=remaining_walls,
        vertical_walls=position.vertical_walls,
        horizontal_walls=position.horizontal_walls,
    )
    return GameSession(state=state, player_types=player_types)


def _serialize_game_section(state: GameState) -> str:
    size = state.board_size
    vwalls = set(tuple(edge) for edge in state.vertical_walls)
    hwalls = set(tuple(edge) for edge in state.horizontal_walls)
    player_at = {node: pid for pid, node in state.player_positions.items()}

    lines: list[str] = []
    lines.append("[game]")
    lines.append(str(state.current_player))

    for row in range(size):
        cell_tokens: list[str] = []
        for col in range(size):
            node = _node(row, col, size)
            cell = str(player_at[node]) if node in player_at else "_"

            prefix = ""
            if col > 0:
                left = _node(row, col - 1, size)
                has_vwall = (left, node) in vwalls or (node, left) in vwalls
                if has_vwall:
                    prefix = "X"
            cell_tokens.append(f"{prefix}{cell}")
        lines.append(" ".join(cell_tokens))

        if row < size - 1:
            sep_tokens: list[str] = []
            for col in range(size):
                top = _node(row, col, size)
                bottom = _node(row + 1, col, size)
                has_hwall = (top, bottom) in hwalls or (bottom, top) in hwalls
                sep_tokens.append("X" if has_hwall else ".")
            lines.append(" ".join(sep_tokens))

    ordered_players = sorted(state.remaining_walls.keys())
    walls_part = " ".join(str(state.remaining_walls[pid]) for pid in ordered_players)
    lines.append(f"walls: {walls_part}")
    return "\n".join(lines) + "\n"


def _save_session_to_file(path: str, session: GameSession) -> None:
    content = _serialize_game_section(session.state)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(content)


def _prompt_save_before_quit(session: GameSession) -> bool:
    """Return True when the caller should quit."""
    try:
        choice = input("Save the game before quitting? [Y/N] ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return True

    if choice.lower() not in {"y", "yes"}:
        return True

    while True:
        try:
            path = input("Save file path: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return True

        if not path:
            print("Invalid path.")
        else:
            try:
                _save_session_to_file(path, session)
                print(_("Game saved to {path}").format(path=path))
                return True
            except OSError as exc:
                print(f"Cannot save file: {exc}")
            except Exception as exc:
                print(f"Cannot save game: {exc}")

        try:
            retry = input("Saving failed. Try again? [Y/N] ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return True
        if retry.lower() not in {"y", "yes"}:
            return True


def _auto_play_ai_until_human_or_end(
    session: GameSession,
    ai_minimax_depth: int,
) -> bool:
    while session.player_types.get(session.state.current_player) == "ai":
        current_ai = session.state.current_player
        session.play_ai_turn(depth=ai_minimax_depth)
        print(f"AI player {current_ai} played.")

        new_pos = session.state.player_positions[current_ai]
        if has_player_won(current_ai, new_pos, session.state.board_size):
            print(f"Player {current_ai} wins!")
            _print_state(session)
            return True

        _print_state(session)
    return False


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
        print(_("warning: save/load not implemented yet, starting a new game."))

    player_positions = initial_player_positions(board_size, players)
    wall_count = walls_per_player if walls_per_player >= 0 else -1
    remaining_walls = {pid: wall_count for pid in player_positions}
    ai_set = set(ai_players)
    player_types = {
        pid: ("ai" if pid in ai_set else "human") for pid in player_positions
    }

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

    if blitz:
        print(
            _("New game started (blitz: {minutes} min/player).").format(
                minutes=time_limit
            )
        )
    else:
        print(_("New game started with default options."))
    if players == 3:
        print(_("warning: 3-player mode can be unbalanced."))

    print(_("Type 'help' for available commands."))
    if ai_set:
        print(
            f"AI players: {sorted(ai_set)} (mode={ai_mode}, depth={ai_minimax_depth}, time={ai_time}s)"
        )
    _print_state(session)

    if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
        return

    while True:
        try:
            line = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line == "help" or line.startswith("help "):
            help_by_command = {
                "help": "help [CMD]\n  Show shell help, or help for CMD.",
                "load": "load FILE\n  Load a game position from FILE.",
                "save": "save FILE\n  Save the current game position to FILE.",
                "hint": "hint\n  Show a suggested move for the current player.",
                "show board": "show board\n  Display only the current board.",
                "moves": "moves\n  Display legal pawn moves for the current player.",
                "move": "move <FROM-TO>\n  Move the current pawn (example: move e2-e3). Shorthand: e2-e3.",
                "wall": "wall <POSh|POSv>\n  Place a wall (example: wall e2h or wall e2v). Shorthand: e2h/e2v.",
                "undo": "undo [N]\n  Undo the last move-group (or N groups).",
                "redo": "redo [N]\n  Redo the last undone move-group (or N groups).",
                "quit": "quit\n  Exit the program.",
            }

            parts = line.split(maxsplit=1)
            if len(parts) == 1:
                print(
                    "Commands: help [CMD], load, save, hint, show board, moves, move, wall, undo, redo, quit"
                )
                print("Use: help <command>")
                continue

            target = parts[1].strip().lower()
            if target in help_by_command:
                print(help_by_command[target])
            else:
                print(_("Invalid command."))
            continue

        if line.lower().startswith("load "):
            file_path = line[5:].strip()
            if not file_path:
                print("Invalid format. Use: load FILE")
                continue
            try:
                session = _load_session_from_file(
                    file_path,
                    fallback_player_types=session.player_types,
                    fallback_walls_per_player=session.state.remaining_walls,
                )
                has_unsaved_changes = True
                print(_("Game loaded from {path}").format(path=file_path))
                _print_state(session)
                before_ai_cursor = session.history.cursor
                if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
                    if session.history.cursor != before_ai_cursor:
                        has_unsaved_changes = True
                    break
                if session.history.cursor != before_ai_cursor:
                    has_unsaved_changes = True
            except ContestError as exc:
                print(f"Invalid load file: {exc}")
            except OSError as exc:
                print(f"Cannot load file: {exc}")
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        if line.lower().startswith("save "):
            file_path = line[5:].strip()
            if not file_path:
                print("Invalid format. Use: save FILE")
                continue
            try:
                _save_session_to_file(file_path, session)
                has_unsaved_changes = False
                print(_("Game saved to {path}").format(path=file_path))
            except OSError as exc:
                print(f"Cannot save file: {exc}")
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        if line == "hint":
            try:
                current = session.state.current_player
                move = choose_best_move_minimax(
                    session.state, ai_player_id=current, depth=ai_minimax_depth
                )
                from_node = session.state.player_positions[current]
                best_hint = _format_hint_move(
                    move, from_node=from_node, size=session.state.board_size
                )
                print(f"Best hint action: {best_hint}")
            except Exception as exc:
                print(f"No hint available: {exc}")
            continue

        if line == "show board":
            print(_render_ascii_board(session.state))
            continue

        if line == "moves":
            _print_moves(session)
            continue

        if line.lower().startswith("move "):
            try:
                if _play_pawn_move_from_token(session, line[5:]):
                    has_unsaved_changes = True
                    break

                has_unsaved_changes = True
                before_ai_cursor = session.history.cursor
                if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
                    if session.history.cursor != before_ai_cursor:
                        has_unsaved_changes = True
                    break
                if session.history.cursor != before_ai_cursor:
                    has_unsaved_changes = True
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        if line.lower().startswith("wall "):
            try:
                _place_wall_from_token(session, line[5:])
                has_unsaved_changes = True
                before_ai_cursor = session.history.cursor
                if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
                    if session.history.cursor != before_ai_cursor:
                        has_unsaved_changes = True
                    break
                if session.history.cursor != before_ai_cursor:
                    has_unsaved_changes = True
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        if line == "undo" or line.lower().startswith("undo "):
            try:
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
                if total_undone > 0:
                    has_unsaved_changes = True
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        if line == "redo" or line.lower().startswith("redo "):
            try:
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
                if total_redone > 0:
                    has_unsaved_changes = True
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        if "-" in line and " " not in line:
            try:
                if _play_pawn_move_from_token(session, line):
                    has_unsaved_changes = True
                    break
                has_unsaved_changes = True
                before_ai_cursor = session.history.cursor
                if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
                    if session.history.cursor != before_ai_cursor:
                        has_unsaved_changes = True
                    break
                if session.history.cursor != before_ai_cursor:
                    has_unsaved_changes = True
            except Exception:
                pass
            else:
                continue

        if " " not in line and len(line) >= 3 and line[-1].lower() in {"h", "v"}:
            try:
                _place_wall_from_token(session, line)
                has_unsaved_changes = True
                before_ai_cursor = session.history.cursor
                if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
                    if session.history.cursor != before_ai_cursor:
                        has_unsaved_changes = True
                    break
                if session.history.cursor != before_ai_cursor:
                    has_unsaved_changes = True
            except Exception:
                pass
            else:
                continue

        if line == "quit":
            if has_unsaved_changes:
                _prompt_save_before_quit(session)
            print(_("Bye."))
            break

        print(_("Invalid command."))


if __name__ == "__main__":
    raise SystemExit(main())
