"""Configuration file support for Quoridor CLI defaults."""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

DEFAULTS: dict[str, bool | int] = {
    "verbose": False,
    "blitz": False,
    "time": 30,
}


def _write_minimal_config(path: Path) -> None:
    """Write a minimal, valid .qoridorrc file."""
    parser = configparser.ConfigParser()
    parser["defaults"] = {
        "verbose": str(DEFAULTS["verbose"]).lower(),
        "blitz": str(DEFAULTS["blitz"]).lower(),
        "time": str(DEFAULTS["time"]),
    }
    with path.open("w", encoding="utf-8") as stream:
        parser.write(stream)


def load_or_init_config(path: Path | None = None) -> dict[str, bool | int]:
    """Load defaults from .qoridorrc, creating it if missing.

    If the config file exists but is invalid, print a warning and return
    built-in defaults without overwriting the file.
    """
    config_path = path if path is not None else Path.home() / ".qoridorrc"

    if not config_path.exists():
        try:
            _write_minimal_config(config_path)
        except OSError as exc:
            sys.stderr.write(
                "warning: could not create config file "
                f"'{config_path}': {exc}\n"
            )
        return DEFAULTS.copy()

    parser = configparser.ConfigParser()
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            parser.read_file(stream)

        if "defaults" not in parser:
            raise ValueError("missing [defaults] section")

        section = parser["defaults"]
        return {
            "verbose": section.getboolean(
                "verbose", fallback=bool(DEFAULTS["verbose"])
            ),
            "blitz": section.getboolean(
                "blitz", fallback=bool(DEFAULTS["blitz"])
            ),
            "time": section.getint("time", fallback=int(DEFAULTS["time"])),
        }
    except (OSError, configparser.Error, ValueError) as exc:
        sys.stderr.write(
            f"warning: invalid config file '{config_path}': {exc}\n"
        )
        return DEFAULTS.copy()
