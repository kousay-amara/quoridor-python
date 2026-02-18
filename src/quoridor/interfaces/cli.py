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


_ = gettext.gettext
LOGGER = logging.getLogger(__name__)


class QuoridorArgumentParser(argparse.ArgumentParser):
    """Custom parser for the Quoridor CLI."""

    def error(self, message: str) -> None:
        sys.stderr.write(f"{self.prog}: {_('error')}: {message}\n\n")
        self.print_help(sys.stderr)
        raise SystemExit(1)


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
    _run_interactive_shell(blitz=args.blitz, time_limit=time_limit, save_file=args.save_file)
    return 0


def main(argv: list[str] | None = None) -> int:
    cli_argv = sys.argv[1:] if argv is None else argv
    if _is_contest_on_cli(cli_argv):
        return _main_contest(cli_argv)
    return _main_interactive(cli_argv)


def _run_interactive_shell(*, blitz: bool, time_limit: int, save_file: str | None) -> None:
    if save_file:
        LOGGER.info("Loading saved game: %s", save_file)
        print(_("Loading game from {path}").format(path=save_file))
        return
    if blitz:
        LOGGER.info("Starting blitz game with time limit=%s", time_limit)
        print(_("New game started (blitz: {minutes} min/player).").format(minutes=time_limit))
    else:
        LOGGER.info("Starting game with default options")
        print(_("New game started with default options."))
    print(_("Type 'help' for available commands."))

    while True:
        try:
            line = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line == "help":
            print(_("Available commands: help, quit"))
            continue

        if line == "quit":
            print(_("Bye."))
            break

        print(_("Unknown command: {cmd}").format(cmd=line))


if __name__ == "__main__":
    raise SystemExit(main())
