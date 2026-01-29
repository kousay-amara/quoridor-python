"""Command-line interface for Quoridor."""
from __future__ import annotations

import argparse
import logging
import sys
from importlib import metadata


class QuoridorArgumentParser(argparse.ArgumentParser):
    """Parser personnalisé pour la CLI de Quoridor."""

    def error(self, message: str) -> None:
        # Gère les erreurs de parsing : affiche l'erreur, l'aide, puis quitte avec un code non nul
        sys.stderr.write(f"{self.prog}: error: {message}\n\n")
        self.print_help(sys.stderr)
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    # Construit et configure le parseur des arguments de la ligne de commande
    parser = QuoridorArgumentParser(
        prog="quoridor",
        description="Quoridor game command-line interface.",
        add_help=True,
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


def _configure_logging(verbose: bool, debug: bool) -> None:
    # Configure le niveau de logging en fonction des options verbose et debug
    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _get_version() -> str:
    # Récupère la version du package Quoridor installé dans l'environnement
    try:
        return metadata.version("quoridor")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def main(argv: list[str] | None = None) -> int:
    # Point d'entrée principal de la CLI : parse les options et lance le programme
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(_get_version())
        return 0

    _configure_logging(args.verbose, args.debug)
    print("Quoridor CLI started.")
    return 0


if __name__ == "__main__":
    # Permet l'exécution directe du module ou via l'entry-point `qoridor`
    raise SystemExit(main())