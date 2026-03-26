"""Shared command catalog for user-facing help and completion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandHelp:
    name: str
    usage: str
    description: str


_HISTORY_DESCRIPTION = (
    "Show the played moves grouped by turns. "
    "Use Up/Down arrows to navigate command history. "
    "Use Ctrl+R for reverse history search (readline)."
)


COMMAND_CATALOG: tuple[CommandHelp, ...] = (
    CommandHelp(
        "new",
        "new [ARGS]",
        (
            "Start a new game. Without ARGS, reuse the current "
            "configuration. With ARGS, override it for the new game."
        ),
    ),
    CommandHelp("help", "help [CMD]", "Show shell help, or help for CMD."),
    CommandHelp("history", "history", _HISTORY_DESCRIPTION),
    CommandHelp("show history", "show history", _HISTORY_DESCRIPTION),
    CommandHelp("load", "load FILE", "Load a game position from FILE."),
    CommandHelp(
        "save",
        "save FILE",
        "Save the current game position to FILE.",
    ),
    CommandHelp(
        "set",
        "set PARAM=VALUE",
        (
            "Update the runtime configuration (example: "
            "set ai_mode=mcts or set time=0.5). "
            "Use new to apply board or blitz changes "
            "to a fresh game."
        ),
    ),
    CommandHelp(
        "hint",
        "hint",
        "Show a suggested move for the current player.",
    ),
    CommandHelp("show board", "show board", "Display only the current board."),
    CommandHelp(
        "show configuration",
        "show configuration",
        "Display current runtime configuration.",
    ),
    CommandHelp(
        "show time",
        "show time",
        "Display remaining blitz time for each player.",
    ),
    CommandHelp(
        "server list",
        "server list",
        "Display game servers discovered on the local network.",
    ),
    CommandHelp(
        "server start",
        "server start [PORT]",
        "Start a local game server and broadcast it on the network.",
    ),
    CommandHelp(
        "server status",
        "server status",
        (
            "Show local server status: listening port, connected "
            "clients and active games."
        ),
    ),
    CommandHelp(
        "server stop",
        "server stop",
        "Stop the local game server and disconnect its client.",
    ),
    CommandHelp(
        "join",
        "join [IP[:PORT]]",
        "Connect to a game server (default: localhost:12345).",
    ),
    CommandHelp(
        "ping",
        "ping",
        "Ping the connected game server and display round-trip time.",
    ),
    CommandHelp(
        "players",
        "players",
        "List players connected to the current game server.",
    ),
    CommandHelp("pause", "pause", "Toggle blitz timer pause/resume."),
    CommandHelp(
        "moves",
        "moves",
        "Display legal pawn moves for the current player.",
    ),
    CommandHelp(
        "move",
        "move <FROM-TO>",
        "Move the current pawn (example: move e2-e3). Shorthand: e2-e3.",
    ),
    CommandHelp(
        "wall",
        "wall <POSh|POSv>",
        "Place a wall (example: wall e2h or wall e2v). Shorthand: e2h/e2v.",
    ),
    CommandHelp("undo", "undo [N]", "Undo the last move-group (or N groups)."),
    CommandHelp(
        "redo",
        "redo [N]",
        "Redo the last undone move-group (or N groups).",
    ),
    CommandHelp(
        "quit",
        "quit",
        "Disconnect from the server or exit the program.",
    ),
)


OVERVIEW_TEXT = (
    "Commands: new [ARGS], help [CMD], load, save, set, hint, show board, "
    "show history, show configuration, show time, server list, server start, "
    "server status, server stop, join, ping, players, pause, moves, move, "
    "wall, "
    "undo, redo, quit\n"
    "Use: help <command>"
)


COMPLETION_COMMANDS = [
    "new",
    "help",
    "hint",
    "load ",
    "save ",
    "set ",
    "show board",
    "show history",
    "show configuration",
    "show time",
    "server list",
    "server start",
    "server status",
    "server stop",
    "join ",
    "ping",
    "players",
    "pause",
    "moves",
    "move ",
    "wall ",
    "undo",
    "redo",
    "quit",
]


def command_names_for_completion() -> list[str]:
    return list(COMPLETION_COMMANDS)


def help_overview() -> str:
    return OVERVIEW_TEXT


def help_for(command: str) -> str | None:
    normalized = command.strip().lower()
    for entry in COMMAND_CATALOG:
        if entry.name == normalized:
            return f"{entry.usage}\n  {entry.description}"
    return None
