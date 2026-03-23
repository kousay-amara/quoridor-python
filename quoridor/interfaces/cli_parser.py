"""Argument parsing helpers for Quoridor CLI."""

from __future__ import annotations

import argparse
import gettext
import sys

from .cli_constants import (
    AI_MINIMAX_DEPTH_DEFAULT,
    AI_MODE_DEFAULT,
    AI_MODE_ITERATIVE,
    AI_MODE_MCTS,
    AI_TIME_DEFAULT,
    BOARD_SIZE_DEFAULT,
    BOARD_SIZE_MAX,
    BOARD_SIZE_MIN,
    PLAYER_COUNT_SUPPORTED,
    PLAYER_ID_MAX,
    PLAYER_ID_MIN,
    WALLS_DEFAULT,
)

_ = gettext.gettext


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
        raise argparse.ArgumentTypeError(
            f"players must be one of: {supported}"
        )
    return value


def _size_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must be an integer") from exc
    if value < BOARD_SIZE_MIN or value > BOARD_SIZE_MAX or value % 2 == 0:
        raise argparse.ArgumentTypeError(
            "size must be odd and between "
            f"{BOARD_SIZE_MIN} and {BOARD_SIZE_MAX}"
        )
    return value


def _player_id_type(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "player id must be an integer"
        ) from exc
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


def _build_parser(
    defaults: dict[str, bool | int | float],
) -> argparse.ArgumentParser:
    parser = QuoridorArgumentParser(
        prog="quoridor",
        description=_("Quoridor game command-line interface."),
        add_help=True,
    )
    parser.add_argument(
        "save_file", nargs="?", help=_("path to a saved game file")
    )
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
        "--ai-player",
        action="append",
        default=[],
        type=_player_id_type,
        help=_(
            "player id controlled by AI (repeat option for multiple players)"
        ),
    )
    parser.add_argument(
        "--ai-mode",
        choices=[AI_MODE_DEFAULT, AI_MODE_ITERATIVE, AI_MODE_MCTS],
        default=AI_MODE_DEFAULT,
        help=_("AI mode"),
    )
    parser.add_argument(
        "--ai-time",
        type=int,
        default=AI_TIME_DEFAULT,
        help=_("AI thinking time in seconds"),
    )
    parser.add_argument(
        "--ai-minimax-depth",
        type=int,
        default=AI_MINIMAX_DEPTH_DEFAULT,
        help=_("maximum minimax search depth"),
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
    parser.add_argument(
        "save_file", nargs="?", help="path to a saved game file"
    )
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
        token in {"-t", "--time"} or token.startswith("--time=")
        for token in argv
    )
