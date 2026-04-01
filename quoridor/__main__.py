"""CLI entry point for the Quoridor package."""

from quoridor.interfaces.cli import main as cli_main


def main():
    """Main program entry point."""
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
