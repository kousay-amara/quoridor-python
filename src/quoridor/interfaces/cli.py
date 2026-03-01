"""Command-line interface for Quoridor."""
from __future__ import annotations

import argparse
import gettext
import logging
import sys
from importlib import metadata

from i18n import setup_i18n
from ..application.contest import run_contest
from ..config import DEFAULTS, load_or_init_config
from .contest_parser import ContestError
from ..application.game_session import GameSession
from ..core.game_state import GameState
from ..core.notation import get_edges_for_wall, get_node_from_notation, get_notation_from_node
from ..rules.pawn_rules import get_all_legal_pawn_moves
from ..core.validators import validate_pawn_move, validate_wall

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
    parser.add_argument("-v", "--verbose", action="store_true", help=_("increase program verbosity"))
    parser.add_argument("-d", "--debug", action="store_true", help=_("show debug messages"))
    parser.add_argument("-b", "--blitz", action="store_true", help=_("enable blitz mode"))
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
    parser.set_defaults(verbose=bool(defaults["verbose"]), blitz=bool(defaults["blitz"]))
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
    return any(token in {"-t", "--time"} or token.startswith("--time=") for token in argv)


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

    # Pour lookup rapide des murs
    vwalls = set(tuple(edge) for edge in state.vertical_walls)
    hwalls = set(tuple(edge) for edge in state.horizontal_walls)

    # positions inversées: node -> player_id
    player_at = {node: pid for pid, node in state.player_positions.items()}

    lines = []
    # Fixed-width header aligned with cell columns.
    lines.append("    " + "   ".join(chr(ord("a") + c) for c in range(size)))
    lines.append("")

    for r in range(size):
        # Cell row: one cell token and one vertical-separator token between cells.
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

        # Separator row between r and r+1: horizontal walls only.
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

    # take the current position of the current player
    from_node = session.state.player_positions[current]
    # and then see the legal moves
    all_positions = list(session.state.player_positions.values())
    legal_nodes = get_all_legal_pawn_moves(session.state.graph, from_node, all_positions)
    # transform in notation for visibily
    legal_notation = [get_notation_from_node(n, session.state.board_size) for n in sorted(legal_nodes)]
    print(f"Legal pawn moves for player {current}: {legal_notation}")


def _has_player_won(player_id: int, node: int, size: int) -> bool:
    row = node // size
    col = node % size
    if player_id == 1:
        return row == size - 1
    if player_id == 2:
        return row == 0
    if player_id == 3:
        return col == size - 1
    if player_id == 4:
        return col == 0
    return False


def _initial_player_positions(size: int, players: int) -> dict[int, int]:
    mid = size // 2
    all_positions = {
        1: _node(0, mid, size),
        2: _node(size - 1, mid, size),
        3: _node(mid, 0, size),
        4: _node(mid, size - 1, size),
    }
    return {pid: all_positions[pid] for pid in range(1, players + 1)}


def _auto_play_ai_until_human_or_end(
    session: GameSession,
    ai_minimax_depth: int,
) -> bool:
    while session.player_types.get(session.state.current_player) == "ai":
        current_ai = session.state.current_player
        session.play_ai_turn(depth=ai_minimax_depth)
        print(f"AI player {current_ai} played.")

        new_pos = session.state.player_positions[current_ai]
        if _has_player_won(current_ai, new_pos, session.state.board_size):
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
    # save/load pas encore implémenté
    if save_file:
        print(_("Loading game from {path}").format(path=save_file))
        print(_("warning: save/load not implemented yet, starting a new game."))

    player_positions = _initial_player_positions(board_size, players)
    wall_count = walls_per_player if walls_per_player >= 0 else -1
    remaining_walls = {pid: wall_count for pid in player_positions}
    ai_set = set(ai_players)
    player_types = {pid: ("ai" if pid in ai_set else "human") for pid in player_positions}

    # État initial
    state = GameState(
        board_size=board_size,
        current_player=1,
        player_positions=player_positions,
        remaining_walls=remaining_walls,
        vertical_walls=[],
        horizontal_walls=[],
    )
    session = GameSession(state=state, player_types=player_types)

    if blitz:
        print(_("New game started (blitz: {minutes} min/player).").format(minutes=time_limit))
    else:
        print(_("New game started with default options."))
    if players == 3:
        print(_("warning: 3-player mode can be unbalanced."))

    print(_("Type 'help' for available commands."))
    if ai_set:
        print(f"AI players: {sorted(ai_set)} (mode={ai_mode}, depth={ai_minimax_depth}, time={ai_time}s)")
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

        # 1) HELP
        if line == "help":
            print("Commands: help, show, moves, move <e2-e3>, wall <e2h|e2v>, undo, redo, quit")
            continue

        # 2) SHOW
        if line == "show":
            _print_state(session)
            continue

        # 3) MOVES
        if line == "moves":
            _print_moves(session)
            continue

        # 4) MOVE e2-e3
        if line.startswith("move "):
            try:
                move_token = line[5:].strip().lower()
                if "-" not in move_token:
                    print("Invalid format. Use: move e2-e3")
                    continue

                from_txt, to_txt = move_token.split("-", 1)
                from_node = get_node_from_notation(from_txt, session.state.board_size)
                to_node = get_node_from_notation(to_txt, session.state.board_size)

                current = session.state.current_player
                # verifier qu'il est valide et possible 
                if session.state.player_positions[current] != from_node:
                    print(f"Invalid move: current player pawn is not on {from_txt}")
                    continue

                valid, error = validate_pawn_move(
                    session.state.graph,
                    from_node,
                    to_node,
                    list(session.state.player_positions.values()),
                    session.state.board_size,
                )
                if not valid:
                    print(f"Invalid move: {error}")
                    continue

                session.play_pawn_move(current, to_node)

                # vérification cas de victoire 
                new_pos = session.state.player_positions[current]
                if _has_player_won(current, new_pos, session.state.board_size):
                    print(f"Player {current} wins!")
                    _print_state(session)
                    break

                _print_state(session)
                if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
                    break
            # commande invalid 
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        # 5) WALL e2h / e2v
        if line.startswith("wall "):
            try:
                wall_token = line[5:].strip().lower()
                if len(wall_token) < 3:
                    print("Invalid format. Use: wall e2h or wall e2v")
                    continue

                ori_char = wall_token[-1]
                if ori_char not in {"h", "v"}:
                    print("Invalid wall orientation. Use h or v")
                    continue

                wall_edges = get_edges_for_wall(wall_token, session.state.board_size)
                orientation = "horizontal" if ori_char == "h" else "vertical"

                current = session.state.current_player
                target_funcs = [
                    (lambda pid: (lambda node: _has_player_won(pid, node, session.state.board_size)))(p)
                    for p in session.state.player_positions
                ]
                valid, error = validate_wall(
                    session.state.graph,
                    list(session.state.player_positions.values()),
                    wall_edges,
                    target_funcs,
                    session.state.remaining_walls,
                    current
                )
                if not valid:
                    print(f"Invalid wall: {error}")
                    continue
                session.place_wall(current, wall_edges, orientation)

                _print_state(session)
                if _auto_play_ai_until_human_or_end(session, ai_minimax_depth):
                    break
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        # 6) UNDO
        if line == "undo":
            try:
                current = session.state.current_player
                undone = session.undo(requester_id=current)
                print(f"Undone moves: {len(undone)}")
                _print_state(session)
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        # 7) REDO
        if line == "redo":
            try:
                current = session.state.current_player
                redone = session.redo(requester_id=current)
                print(f"Redone moves: {len(redone)}")
                _print_state(session)
            except Exception as exc:
                print(f"Invalid command: {exc}")
            continue

        # 8) QUIT
        if line == "quit":
            print(_("Bye."))
            break

        print(_("Unknown command: {cmd}").format(cmd=line))

if __name__ == "__main__":
    raise SystemExit(main())
