from __future__ import annotations

import importlib


def test_main_module_delegates_to_cli_main(monkeypatch):
    main_mod = importlib.import_module("quoridor.__main__")
    monkeypatch.setattr(main_mod, "cli_main", lambda: 123)
    assert main_mod.main() == 123
