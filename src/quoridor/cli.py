"""Command-line interface for Quoridor."""
from __future__ import annotations

import argparse
import gettext
import logging
import sys
from importlib import metadata

from i18n import setup_i18n


setup_i18n()
_ = gettext.gettext


class QuoridorArgumentParser(argparse.ArgumentParser):
    """Custom parser for the Quoridor CLI."""

    def error(self, message: str) -> None:
        # Print errors on stderr, then show help and exit with a non-zero code.
        sys.stderr.write(f"{self.prog}: {_('error')}: {message}\n\n")
        self.print_help(sys.stderr)
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    # Build and configure the command-line argument parser.
    parser = QuoridorArgumentParser(
        prog="quoridor",
        description=_("Quoridor game command-line interface."),
        add_help=True,
    )
    parser.add_argument(
        "save_file",
        nargs="?",
        help=_("path to a saved game file"),
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
        "-d",
        "--debug",
        action="store_true",
        help=_("show debug messages"),
    )
    parser.add_argument(
        "-b",
        "--blitz",
        action="store_true",
        help=_("enable blitz mode"),
    )
    parser.add_argument(
        "-t",
        "--time",
        type=int,
        default=30,
        help=_("time limit in minutes for blitz mode"),
    )
    return parser


def _configure_logging(verbose: bool, debug: bool) -> None:
    # Configure logging level based on verbose and debug flags.
    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _get_version() -> str:
    # Fetch the version of the installed Quoridor package.
    try:
        return metadata.version("quoridor")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def main(argv: list[str] | None = None) -> int:
    # Main CLI entry point: parse options and run the program.
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(_get_version())
        return 0

    _configure_logging(args.verbose, args.debug)
    time_limit = args.time
    if args.time != 30 and not args.blitz:
        sys.stderr.write(
            _("warning: --time is ignored unless --blitz is enabled\n")
        )
        time_limit = 30
    _run_interactive_shell(
        blitz=args.blitz,
        time_limit=time_limit,
        save_file=args.save_file,
    )
    return 0


def _run_interactive_shell(
    *,
    blitz: bool,
    time_limit: int,
    save_file: str | None,
) -> None:
    # Start a new game with default options (F4).
    if save_file:
        print(_("Loading game from {path}").format(path=save_file))
        return
    if blitz:
        print(
            _("New game started (blitz: {minutes} min/player).").format(
                minutes=time_limit
            )
        )
    else:
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
    # Allow direct execution or via the `qoridor` entry point.
    raise SystemExit(main())
