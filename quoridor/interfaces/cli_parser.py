"""Argument parsing helpers for Quoridor CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cli_constants import (
    AI_MINIMAX_DEPTH_DEFAULT,
    AI_MINIMAX_SCORING_DEFAULT,
    AI_MODE_DEFAULT,
    AI_MODE_ITERATIVE,
    AI_MODE_MINIMAX,
    AI_MODE_MCTS,
    AI_MCTS_SELECTION_DEFAULT,
    AI_MCTS_SELECTION_ML,
    AI_MCTS_SELECTION_UCT,
    AI_TIME_DEFAULT,
    BOARD_SIZE_DEFAULT,
    BOARD_SIZE_MAX,
    BOARD_SIZE_MIN,
    PLAYER_COUNT_SUPPORTED,
    PLAYER_ID_MAX,
    PLAYER_ID_MIN,
    WALLS_DEFAULT,
)
from ..i18n import runtime_gettext
from ..network import DEFAULT_SERVER_PORT


def _(message: str) -> str:
    return runtime_gettext(message)


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
    if value not in PLAYER_COUNT_SUPPORTED:
        supported = ", ".join(str(v) for v in sorted(PLAYER_COUNT_SUPPORTED))
        raise argparse.ArgumentTypeError(f"players must be one of: {supported}")
    return value


def _size_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must be an integer") from exc
    if value < BOARD_SIZE_MIN or value > BOARD_SIZE_MAX or value % 2 == 0:
        raise argparse.ArgumentTypeError(
            "size must be odd and between " f"{BOARD_SIZE_MIN} and {BOARD_SIZE_MAX}"
        )
    return value


def _player_id_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("player id must be an integer") from exc
    if value < PLAYER_ID_MIN or value > PLAYER_ID_MAX:
        raise argparse.ArgumentTypeError(
            f"player id must be between {PLAYER_ID_MIN} and {PLAYER_ID_MAX}"
        )
    return value


def _positive_time_type(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must be a number") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("time must be > 0")
    return value


def _port_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if value < 1 or value > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return value


def _ai_selection_type(raw: str) -> str | int:
    if not raw or raw.upper() == "DEFAULT":
        return "DEFAULT"

    val_upper = raw.upper()
    if val_upper in {"A", "ALL"}:
        return "ALL"

    colors = {
        "RED": 1,
        "ROUGE": 1,
        "BLUE": 2,
        "BLEU": 2,
        "GREEN": 3,
        "VERT": 3,
        "YELLOW": 4,
        "JAUNE": 4,
    }

    if val_upper in colors:
        return colors[val_upper]

    try:
        return _player_id_type(raw)
    except Exception as exc:
        raise argparse.ArgumentTypeError(
            f"False AI value : '{raw}'. "
            "Use a color (ex: red), an ID (1-4), or 'A' for all."
        ) from exc


def _build_parser(
    defaults: dict[str, object],
) -> argparse.ArgumentParser:
    ai_players_default = defaults.get("ai_players", [])
    if isinstance(ai_players_default, list):
        ai_players = list(ai_players_default)
    else:
        ai_players = []

    ai_mode_default = defaults.get("ai_mode", AI_MODE_DEFAULT)
    if ai_mode_default not in [
        AI_MODE_MINIMAX,
        AI_MODE_ITERATIVE,
        AI_MODE_MCTS,
    ]:
        ai_mode_default = AI_MODE_DEFAULT

    ai_time_default = defaults.get("ai_time", AI_TIME_DEFAULT)
    if not isinstance(ai_time_default, int) or ai_time_default <= 0:
        ai_time_default = AI_TIME_DEFAULT

    depth_default = defaults.get("ai_minimax_depth", AI_MINIMAX_DEPTH_DEFAULT)
    if depth_default is not None:
        if not isinstance(depth_default, int) or depth_default <= 0:
            depth_default = AI_MINIMAX_DEPTH_DEFAULT

    scoring_default = defaults.get("ai_minimax_scoring", AI_MINIMAX_SCORING_DEFAULT)
    if not isinstance(scoring_default, int) or scoring_default not in {1, 2, 3}:
        scoring_default = AI_MINIMAX_SCORING_DEFAULT

    parser = QuoridorArgumentParser(
        prog=_cli_prog_name(),
        description=_("Quoridor game command-line interface."),
        add_help=True,
    )
    parser.add_argument("save_file", nargs="?", help=_("path to a saved game file"))
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help=_("show program version and exit"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=_("increase program verbosity"),
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help=_("show debug messages")
    )
    parser.add_argument(
        "-D",
        "--daemon",
        action="store_true",
        help=_("run in headless mode (requires --server)"),
    )
    parser.add_argument(
        "-g", "--gui", action="store_true", help=_("launch the GTK GUI")
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
        type=_positive_time_type,
        default=float(defaults["time"]),
        help=_("time limit in minutes for blitz mode"),
    )
    parser.add_argument(
        "-p",
        "--players",
        type=_players_type,
        default=int(defaults.get("players", min(PLAYER_COUNT_SUPPORTED))),
        help=_("number of players ({values})").format(
            values=", ".join(str(v) for v in sorted(PLAYER_COUNT_SUPPORTED))
        ),
    )
    parser.add_argument(
        "-w",
        "--walls",
        type=int,
        default=int(defaults.get("walls", WALLS_DEFAULT)),
        help=_("walls per player (negative means unlimited)"),
    )
    parser.add_argument(
        "-s",
        "--size",
        type=_size_type,
        default=int(defaults.get("size", BOARD_SIZE_DEFAULT)),
        help=_("board size (odd number between {min} and {max})").format(
            min=BOARD_SIZE_MIN, max=BOARD_SIZE_MAX
        ),
    )
    parser.add_argument(
        "-S",
        "--server",
        nargs="?",
        const=DEFAULT_SERVER_PORT,
        type=_port_type,
        default=None,
        metavar="PORT",
        help=_("start local server immediately (optional port)"),
    )
    parser.add_argument(
        "-a",
        "--ai",
        dest="ai_players",
        action="append",
        nargs="?",
        const="DEFAULT",
        default=ai_players,
        type=_ai_selection_type,
        help=_("Replace a player by an AI (Color, ID or 'A' for all)"),
    )
    parser.add_argument(
        "--ai-mode",
        choices=[AI_MODE_MINIMAX, AI_MODE_ITERATIVE, AI_MODE_MCTS],
        default=ai_mode_default,
        help=_("AI mode"),
    )
    parser.add_argument(
        "--ai-time",
        type=int,
        default=ai_time_default,
        help=_("AI thinking time in seconds (iterative, mcts)"),
    )
    parser.add_argument(
        "--ai-minimax-depth",
        type=int,
        default=depth_default,
        help=_("minimax depth (fixed for minimax, max for iterative)"),
    )
    parser.add_argument(
        "--ai-minimax-scoring",
        type=int,
        choices=[1, 2, 3],
        default=scoring_default,
        help=_("AI scoring type (1: Default, 2: Material, 3: Hybrid)"),
    )
    parser.add_argument(
        "--ai-mcts-selection",
        choices=[AI_MCTS_SELECTION_UCT, AI_MCTS_SELECTION_ML],
        default=AI_MCTS_SELECTION_DEFAULT,
        help=_("MCTS selection policy (UCT or ML)"),
    )
    parser.set_defaults(
        verbose=bool(defaults["verbose"]), blitz=bool(defaults["blitz"])
    )
    return parser


def _build_contest_parser() -> argparse.ArgumentParser:
    parser = QuoridorArgumentParser(
        prog=_cli_prog_name(),
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
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="show program version and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="increase program verbosity",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="show debug messages",
    )
    return parser


def _is_contest_on_cli(argv: list[str]) -> bool:
    return any(token in {"-c", "--contest"} for token in argv)


def _is_time_passed_on_cli(argv: list[str]) -> bool:
    return any(
        token in {"-t", "--time"} or token.startswith("--time=") for token in argv
    )


def _is_ai_time_passed_on_cli(argv: list[str]) -> bool:
    return any(token == "--ai-time" or token.startswith("--ai-time=") for token in argv)


def _cli_prog_name() -> str:
    """Use the invoked executable name so help/errors match the command."""
    raw = sys.argv[0] if sys.argv and sys.argv[0] else "quoridor"
    name = Path(raw).name.strip()
    return name or "quoridor"
