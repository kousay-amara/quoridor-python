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
    """Parser personnalisé pour la CLI de Quoridor."""

    def error(self, message: str) -> None:
        # Handles parsing errors: print the error, show help, then exit with a non-zero code
        sys.stderr.write(f"{self.prog}: {_('error')}: {message}\n\n")
        self.print_help(sys.stderr)
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    # Build and configure the command-line argument parser
    parser = QuoridorArgumentParser(
        prog="quoridor",
        description=_("Quoridor game command-line interface."),
        add_help=True,
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
    return parser


def _configure_logging(verbose: bool, debug: bool) -> None:
    # Configure logging level based on verbose and debug flags
    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _get_version() -> str:
    # Fetch the version of the installed Quoridor package
    try:
        return metadata.version("quoridor")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def main(argv: list[str] | None = None) -> int:
    # Main CLI entry point: parse options and run the program
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(_get_version())
        return 0

    _configure_logging(args.verbose, args.debug)
    print(_("Quoridor CLI started."))
    return 0


if __name__ == "__main__":
    # Allow direct execution or via the `qoridor` entry point
    raise SystemExit(main())
