"""Configuration file support for Quoridor CLI defaults."""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

ConfigValue = bool | int | float | str | list[int] | None

_SUPPORTED_PLAYERS = {2, 3, 4}
_BOARD_SIZE_MIN = 3
_BOARD_SIZE_MAX = 15
_AI_MODES = {"minimax", "iterative", "mcts"}

DEFAULTS: dict[str, ConfigValue] = {
    "verbose": False,
    "blitz": False,
    "time": 30.0,
    "players": 2,
    "walls": 20,
    "size": 9,
    "ai_mode": "iterative",
    "ai_time": 5,
    "ai_minimax_depth": None,
    "ai_players": [],
}


def _copy_defaults() -> dict[str, ConfigValue]:
    defaults = DEFAULTS.copy()
    defaults["ai_players"] = list(DEFAULTS["ai_players"])
    return defaults


def _write_minimal_config(path: Path) -> None:
    """Write a minimal, valid .qoridorrc file."""
    parser = configparser.ConfigParser()
    parser["defaults"] = {
        "verbose": str(DEFAULTS["verbose"]).lower(),
        "blitz": str(DEFAULTS["blitz"]).lower(),
        "time": str(DEFAULTS["time"]),
        "players": str(DEFAULTS["players"]),
        "walls": str(DEFAULTS["walls"]),
        "size": str(DEFAULTS["size"]),
        "ai_mode": str(DEFAULTS["ai_mode"]),
        "ai_time": str(DEFAULTS["ai_time"]),
        "ai_minimax_depth": "none",
        "ai_players": "",
    }
    with path.open("w", encoding="utf-8") as stream:
        parser.write(stream)


def _parse_ai_players(raw: str) -> list[int]:
    raw = raw.strip()
    if not raw:
        return []

    player_ids: list[int] = []
    seen: set[int] = set()
    tokens = raw.replace(",", " ").split()
    for token in tokens:
        try:
            player_id = int(token)
        except ValueError as exc:
            raise ValueError("ai_players must contain integers") from exc
        if player_id < 1 or player_id > 4:
            raise ValueError("ai_players values must be between 1 and 4")
        if player_id not in seen:
            seen.add(player_id)
            player_ids.append(player_id)
    return player_ids


def load_or_init_config(
    path: Path | None = None,
) -> dict[str, ConfigValue]:
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
        return _copy_defaults()

    parser = configparser.ConfigParser()
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            parser.read_file(stream)

        if "defaults" not in parser:
            raise ValueError("missing [defaults] section")

        section = parser["defaults"]
        values = _copy_defaults()
        values["verbose"] = section.getboolean(
            "verbose", fallback=bool(values["verbose"])
        )
        values["blitz"] = section.getboolean(
            "blitz", fallback=bool(values["blitz"])
        )

        if "time" in section:
            timeout = section.getfloat("time")
        elif "timeout" in section:
            timeout = section.getfloat("timeout")
        else:
            timeout = float(values["time"])
        if timeout <= 0:
            raise ValueError("time must be > 0")
        values["time"] = timeout

        players = section.getint("players", fallback=int(values["players"]))
        if players not in _SUPPORTED_PLAYERS:
            raise ValueError("players must be one of: 2, 3, 4")
        values["players"] = players

        values["walls"] = section.getint(
            "walls", fallback=int(values["walls"])
        )

        size = section.getint("size", fallback=int(values["size"]))
        if (
            size < _BOARD_SIZE_MIN
            or size > _BOARD_SIZE_MAX
            or size % 2 == 0
        ):
            raise ValueError("size must be odd and between 3 and 15")
        values["size"] = size

        ai_mode = section.get("ai_mode", fallback=str(values["ai_mode"]))
        ai_mode = ai_mode.strip().lower()
        if ai_mode not in _AI_MODES:
            raise ValueError(
                "ai_mode must be one of: iterative, mcts, minimax"
            )
        values["ai_mode"] = ai_mode

        ai_time = section.getint("ai_time", fallback=int(values["ai_time"]))
        if ai_time <= 0:
            raise ValueError("ai_time must be > 0")
        values["ai_time"] = ai_time

        depth_raw = section.get("ai_minimax_depth", fallback="").strip()
        if not depth_raw or depth_raw.lower() in {"none", "null"}:
            values["ai_minimax_depth"] = None
        else:
            depth = int(depth_raw)
            if depth <= 0:
                raise ValueError("ai_minimax_depth must be > 0")
            values["ai_minimax_depth"] = depth

        values["ai_players"] = _parse_ai_players(
            section.get("ai_players", fallback="")
        )

        return values
    except (OSError, configparser.Error, ValueError) as exc:
        sys.stderr.write(
            f"warning: invalid config file '{config_path}': {exc}\n"
        )
        return _copy_defaults()
