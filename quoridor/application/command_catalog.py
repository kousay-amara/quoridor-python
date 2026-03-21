"""Shared command catalog for user-facing help and completion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandHelp:
    name: str
    usage: str
    description: str


COMMAND_CATALOG: tuple[CommandHelp, ...] = (
    CommandHelp("help", "help [CMD]", "Show shell help, or help for CMD."),
    CommandHelp(
        "history",
        "history",
        (
            "Show the played moves grouped by turns. "
            "Use Up/Down arrows to navigate command history. "
            "Use Ctrl+R for reverse history search (readline)."
        ),
    ),
    CommandHelp("load", "load FILE", "Load a game position from FILE."),
    CommandHelp("save", "save FILE", "Save the current game position to FILE."),
    CommandHelp("hint", "hint", "Show a suggested move for the current player."),
    CommandHelp("show board", "show board", "Display only the current board."),
    CommandHelp(
        "show configuration",
        "show configuration",
        "Display current runtime configuration.",
    ),
    CommandHelp("show time", "show time", "Display remaining blitz time for each player."),
    CommandHelp("pause", "pause", "Toggle blitz timer pause/resume."),
    CommandHelp("moves", "moves", "Display legal pawn moves for the current player."),
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
    CommandHelp("redo", "redo [N]", "Redo the last undone move-group (or N groups)."),
    CommandHelp("quit", "quit", "Exit the program."),
)


OVERVIEW_TEXT = (
    "Commands: help [CMD], history, load, save, hint, show board, "
    "show configuration, show time, pause, moves, move, wall, undo, redo, quit\n"
    "Use: help <command>"
)


COMPLETION_COMMANDS = [
    "help",
    "history",
    "hint",
    "load ",
    "save ",
    "show board",
    "show configuration",
    "show time",
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
