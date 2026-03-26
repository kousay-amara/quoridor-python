from pathlib import Path

from quoridor.config import DEFAULTS, load_or_init_config


def test_load_or_init_config_creates_minimal_file_when_missing(tmp_path: Path):
    config_path = tmp_path / ".qoridorrc"

    values = load_or_init_config(config_path)

    assert values == DEFAULTS
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "[defaults]" in content
    assert "verbose = false" in content
    assert "blitz = false" in content
    assert "time = 30.0" in content
    assert "players = 2" in content
    assert "walls = 20" in content
    assert "size = 9" in content
    assert "ai_mode = iterative" in content
    assert "ai_time = 5" in content
    assert "ai_minimax_depth = none" in content


def test_load_or_init_config_reads_valid_values(tmp_path: Path):
    config_path = tmp_path / ".qoridorrc"
    config_path.write_text(
        "[defaults]\n"
        "verbose = true\n"
        "blitz = true\n"
        "time = 12\n"
        "players = 4\n"
        "walls = -1\n"
        "size = 11\n"
        "ai_mode = mcts\n"
        "ai_time = 7\n"
        "ai_minimax_depth = 3\n"
        "ai_players = 1, 3\n",
        encoding="utf-8",
    )

    values = load_or_init_config(config_path)

    assert values == {
        "verbose": True,
        "blitz": True,
        "time": 12.0,
        "players": 4,
        "walls": -1,
        "size": 11,
        "ai_mode": "mcts",
        "ai_time": 7,
        "ai_minimax_depth": 3,
        "ai_players": [1, 3],
    }


def test_load_or_init_config_invalid_file_warns_and_does_not_overwrite(
    tmp_path: Path, capsys
):
    config_path = tmp_path / ".qoridorrc"
    original_content = "[defaults]\ntime = abc\n"
    config_path.write_text(original_content, encoding="utf-8")

    values = load_or_init_config(config_path)
    captured = capsys.readouterr()

    assert values == DEFAULTS
    assert "warning: invalid config file" in captured.err
    assert config_path.read_text(encoding="utf-8") == original_content


def test_load_or_init_config_reads_fractional_time(tmp_path: Path):
    config_path = tmp_path / ".qoridorrc"
    config_path.write_text(
        "[defaults]\nverbose = false\nblitz = true\ntime = 0.5\n",
        encoding="utf-8",
    )

    values = load_or_init_config(config_path)

    assert values == {
        "verbose": False,
        "blitz": True,
        "time": 0.5,
        "players": 2,
        "walls": 20,
        "size": 9,
        "ai_mode": "iterative",
        "ai_time": 5,
        "ai_minimax_depth": None,
        "ai_players": [],
    }


def test_load_or_init_config_supports_timeout_alias(tmp_path: Path):
    config_path = tmp_path / ".qoridorrc"
    config_path.write_text("[defaults]\ntimeout = 1.5\n", encoding="utf-8")

    values = load_or_init_config(config_path)

    assert values["time"] == 1.5
