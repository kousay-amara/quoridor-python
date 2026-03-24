"""Command-line interface for Quoridor."""

from __future__ import annotations

import logging
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from ..i18n import setup_i18n
from ..application.contest import run_contest
from ..application.mcts_engine import mcts_search
from ..application.minimax_engine import (
    find_best_move_minimax,
    find_best_move_iterative,
)
from ..config import DEFAULTS, load_or_init_config
from .cli_constants import AI_MODE_MINIMAX
from .contest_parser import ContestError, parse_contest_file
from .cli_parser import (
    QuoridorArgumentParser,
    _build_contest_parser,
    _build_parser,
    _is_ai_time_passed_on_cli,
    _is_contest_on_cli,
    _is_time_passed_on_cli,
    _player_id_type,
    _positive_time_type,
    _players_type,
    _size_type,
)
from .cli_render import (
    _format_hint_move,
    _node,
    _print_moves,
    _print_state,
    _render_ascii_board,
)
from .cli_io import (
    _load_blitz_snapshot_from_file,
    _load_session_from_file,
    _prompt_save_before_quit,
    _save_session_to_file,
    _serialize_game_section,
    _serialize_history_section,
)
from .cli_shell import (
    _auto_play_ai_until_human_or_end,
    _place_wall_from_token,
    _play_pawn_move_from_token,
    _run_interactive_shell,
)

__all__ = [
    "ContestError",
    "QuoridorArgumentParser",
    "_auto_play_ai_until_human_or_end",
    "_build_contest_parser",
    "_build_parser",
    "_configure_logging",
    "_format_hint_move",
    "_get_version",
    "_is_contest_on_cli",
    "_is_time_passed_on_cli",
    "_load_blitz_snapshot_from_file",
    "_load_session_from_file",
    "_main_contest",
    "_main_gui",
    "_main_interactive",
    "_node",
    "_place_wall_from_token",
    "_positive_time_type",
    "_player_id_type",
    "_players_type",
    "_play_pawn_move_from_token",
    "_print_moves",
    "_print_state",
    "_prompt_save_before_quit",
    "_render_ascii_board",
    "_run_interactive_shell",
    "_save_session_to_file",
    "_serialize_game_section",
    "_serialize_history_section",
    "_size_type",
    "find_best_move_iterative",
    "find_best_move_minimax",
    "main",
    "metadata",
    "mcts_search",
    "parse_contest_file",
    "run_contest",
    "setup_i18n",
]

LOGGER = logging.getLogger(__name__)


def _configure_logging(verbose: bool, debug: bool) -> None:
    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        force=True,
    )
    LOGGER.debug(
        "Logging configured with level=%s", logging.getLevelName(level)
    )


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


def _main_gui(args) -> int:
    try:
        from . import gui as gui_mod
    except ModuleNotFoundError as exc:
        if exc.name != "gi":
            raise

        fallback_python = Path("/usr/bin/python3")
        gui_script = Path(__file__).with_name("gui.py")
        if not fallback_python.exists():
            sys.stderr.write(
                "error: GTK GUI requires PyGObject ('gi'), which is not "
                "available in this Python environment\n"
            )
            return 1

        result = subprocess.run(
            [str(fallback_python), str(gui_script)],
            check=False,
        )
        return result.returncode

    return gui_mod.main(
        num_players=args.players,
        board_size=args.size,
        walls=args.walls,
    )

def _main_interactive(argv: list[str]) -> int:
    setup_i18n()
    defaults = load_or_init_config()
    parser = _build_parser(defaults)
    args = parser.parse_args(argv)

    if args.version:
        print(_get_version())
        return 0

    if args.gui:
        return _main_gui(args)

    if any(pid > args.players for pid in args.ai_player):
        parser.error("--ai-player id must be <= --players")
    if args.ai_time <= 0:
        parser.error("--ai-time must be > 0")
    if args.ai_minimax_depth is not None and args.ai_minimax_depth <= 0:
        parser.error("--ai-minimax-depth must be > 0")
    if args.ai_mode == AI_MODE_MINIMAX and args.ai_minimax_depth is None:
        parser.error("--ai-mode minimax requires --ai-minimax-depth")

    _configure_logging(args.verbose, args.debug)
    LOGGER.debug("Loaded defaults from .qoridorrc: %s", defaults)
    LOGGER.debug("Parsed CLI args: %s", vars(args))

    time_limit = args.time
    if _is_time_passed_on_cli(argv) and not args.blitz:
        sys.stderr.write(
            "warning: --time is ignored unless --blitz is enabled\n"
        )
        time_limit = float(defaults.get("time", DEFAULTS["time"]))
    if args.ai_mode == AI_MODE_MINIMAX and _is_ai_time_passed_on_cli(argv):
        sys.stderr.write(
            "warning: --ai-time is ignored in minimax mode\n"
        )
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
        verbose=args.verbose,
        debug=args.debug,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    cli_argv = sys.argv[1:] if argv is None else argv
    if _is_contest_on_cli(cli_argv):
        return _main_contest(cli_argv)
    return _main_interactive(cli_argv)


if __name__ == "__main__":
    raise SystemExit(main())
