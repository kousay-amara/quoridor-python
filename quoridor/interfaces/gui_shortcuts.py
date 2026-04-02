"""Shortcut models and persistence for the GTK GUI."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class ActionType(Enum):
    NEW_GAME = "new_game"
    LOAD_GAME = "load_game"
    SAVE_GAME = "save_game"
    SHOW_CONFIG = "show_config"
    SHOW_INFO = "show_info"
    QUIT_APP = "quit_app"
    UNDO = "undo"
    REDO = "redo"
    PAUSE = "pause"
    HINT = "hint"


DEFAULT_SHORTCUTS: dict[ActionType, str] = {
    ActionType.NEW_GAME: "<Primary>n",
    ActionType.LOAD_GAME: "<Primary>l",
    ActionType.SAVE_GAME: "<Primary>s",
    ActionType.SHOW_CONFIG: "<Primary>comma",
    ActionType.SHOW_INFO: "<Primary>i",
    ActionType.QUIT_APP: "<Primary>q",
    ActionType.UNDO: "<Primary>u",
    ActionType.REDO: "<Primary>r",
    ActionType.PAUSE: "<Primary>p",
    ActionType.HINT: "<Primary>h",
}


ACTION_LABELS: dict[ActionType, str] = {
    ActionType.NEW_GAME: "New game",
    ActionType.LOAD_GAME: "Load game",
    ActionType.SAVE_GAME: "Save game",
    ActionType.SHOW_CONFIG: "Show configuration",
    ActionType.SHOW_INFO: "Show information",
    ActionType.QUIT_APP: "Quit",
    ActionType.UNDO: "Undo",
    ActionType.REDO: "Redo",
    ActionType.PAUSE: "Pause",
    ActionType.HINT: "Hint",
}


class ShortcutError(ValueError):
    """Raised when shortcut configuration is invalid."""


@dataclass
class ShortcutManager:
    """Store and validate shortcut mappings for all GUI actions."""

    shortcuts: dict[ActionType, str]

    @classmethod
    def with_defaults(cls) -> "ShortcutManager":
        return cls(shortcuts=dict(DEFAULT_SHORTCUTS))

    def get(self, action: ActionType) -> str:
        return self.shortcuts[action]

    def set(self, action: ActionType, shortcut: str) -> None:
        normalized = shortcut.strip()
        if not normalized:
            raise ShortcutError("shortcut cannot be empty")

        updated = dict(self.shortcuts)
        updated[action] = normalized
        self._validate_unique(updated)
        self.shortcuts = updated

    def replace_all(self, mapping: dict[ActionType, str]) -> None:
        merged = {action: DEFAULT_SHORTCUTS[action] for action in ActionType}
        for action, shortcut in mapping.items():
            merged[action] = shortcut.strip()

        for action, shortcut in merged.items():
            if not shortcut:
                raise ShortcutError(
                    f"shortcut cannot be empty for action {action.value}"
                )
        self._validate_unique(merged)
        self.shortcuts = merged

    def as_serializable(self) -> dict[str, str]:
        return {action.value: self.shortcuts[action] for action in ActionType}

    @staticmethod
    def parse_serializable(raw: dict[str, str]) -> dict[ActionType, str]:
        parsed: dict[ActionType, str] = {}
        for key, value in raw.items():
            try:
                action = ActionType(key)
            except ValueError:
                continue
            parsed[action] = str(value).strip()
        return parsed

    @staticmethod
    def _validate_unique(mapping: dict[ActionType, str]) -> None:
        seen: dict[str, ActionType] = {}
        for action, shortcut in mapping.items():
            token = shortcut.lower()
            if token in seen and seen[token] != action:
                raise ShortcutError(
                    f"shortcut '{shortcut}' is already used by "
                    f"{seen[token].value}"
                )
            seen[token] = action


@dataclass
class ConfigManager:
    """Read/write GUI shortcut settings in the main INI config file."""

    path: Path

    @classmethod
    def default(cls) -> "ConfigManager":
        return cls(path=Path.home() / ".qoridorrc")

    def load_shortcuts(self) -> ShortcutManager:
        manager = ShortcutManager.with_defaults()
        if not self.path.exists():
            return manager

        parser = configparser.ConfigParser()
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                parser.read_file(stream)
        except (OSError, configparser.Error):
            return manager

        if "shortcuts" not in parser:
            return manager

        parsed = ShortcutManager.parse_serializable(dict(parser["shortcuts"]))
        try:
            manager.replace_all(parsed)
        except ShortcutError:
            return ShortcutManager.with_defaults()
        return manager

    def save_shortcuts(self, manager: ShortcutManager) -> None:
        parser = configparser.ConfigParser()
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as stream:
                    parser.read_file(stream)
            except (OSError, configparser.Error):
                parser = configparser.ConfigParser()

        parser["shortcuts"] = manager.as_serializable()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as stream:
            parser.write(stream)


@dataclass
class ActionRegistry:
    """Map GUI actions to callbacks."""

    handlers: dict[ActionType, Callable[[], None]]

    def register(
        self,
        action: ActionType,
        callback: Callable[[], None],
    ) -> None:
        self.handlers[action] = callback

    def execute(self, action: ActionType) -> None:
        if action not in self.handlers:
            raise KeyError(f"no handler registered for action {action.value}")
        self.handlers[action]()
