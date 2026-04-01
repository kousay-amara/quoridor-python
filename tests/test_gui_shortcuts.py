from __future__ import annotations

from pathlib import Path

import pytest

from quoridor.interfaces.gui_shortcuts import (
    ActionRegistry,
    ActionType,
    ConfigManager,
    ShortcutError,
    ShortcutManager,
)


def test_shortcut_manager_defaults_cover_all_actions():
    manager = ShortcutManager.with_defaults()

    for action in ActionType:
        assert manager.get(action)


def test_shortcut_manager_rejects_duplicate_shortcuts():
    manager = ShortcutManager.with_defaults()
    same = manager.get(ActionType.NEW_GAME)

    with pytest.raises(ShortcutError):
        manager.set(ActionType.LOAD_GAME, same)


def test_shortcut_manager_replace_all_normalizes_and_validates():
    manager = ShortcutManager.with_defaults()
    manager.replace_all(
        {
            ActionType.NEW_GAME: " <Primary><Shift>n ",
            ActionType.HINT: "<Primary>slash",
        }
    )

    assert manager.get(ActionType.NEW_GAME) == "<Primary><Shift>n"
    assert manager.get(ActionType.HINT) == "<Primary>slash"


def test_config_manager_roundtrip(tmp_path: Path):
    path = tmp_path / ".qoridorrc"
    path.write_text("[defaults]\nplayers = 2\n", encoding="utf-8")
    config = ConfigManager(path=path)

    manager = ShortcutManager.with_defaults()
    manager.set(ActionType.UNDO, "<Primary>z")
    config.save_shortcuts(manager)

    loaded = config.load_shortcuts()
    assert loaded.get(ActionType.UNDO) == "<Primary>z"
    saved = path.read_text(encoding="utf-8")
    assert "[defaults]" in saved
    assert "players = 2" in saved
    assert "[shortcuts]" in saved


def test_config_manager_invalid_file_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / ".qoridorrc"
    path.write_text("[shortcuts\nbroken", encoding="utf-8")

    config = ConfigManager(path=path)
    loaded = config.load_shortcuts()

    assert loaded.get(ActionType.NEW_GAME) == ShortcutManager.with_defaults().get(
        ActionType.NEW_GAME
    )


def test_action_registry_executes_registered_callback():
    called: list[str] = []
    registry = ActionRegistry(handlers={})
    registry.register(ActionType.SAVE_GAME, lambda: called.append("save"))

    registry.execute(ActionType.SAVE_GAME)

    assert called == ["save"]


def test_action_registry_missing_handler_raises():
    registry = ActionRegistry(handlers={})

    with pytest.raises(KeyError):
        registry.execute(ActionType.SAVE_GAME)
