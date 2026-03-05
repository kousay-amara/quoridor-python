import argparse
from quoridor import __version__
from quoridor.interfaces.cli import main as cli_main

def main():
    """Point d'entrée principal du programme."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-V", "--version",
        help="affiche la version du programme",
        action="store_true",
    )
    args = parser.parse_args()
    if args.version:
        print(f"Quoridor: version {__version__}")
        return 0

    cli_main()
    return 0

if __name__ == "__main__":
    main()