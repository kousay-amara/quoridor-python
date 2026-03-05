from pathlib import Path

from src.quoridor.config import DEFAULTS, load_or_init_config


def test_load_or_init_config_creates_minimal_file_when_missing(tmp_path: Path):
    config_path = tmp_path / ".qoridorrc"

    values = load_or_init_config(config_path)

    assert values == DEFAULTS
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "[defaults]" in content
    assert "verbose = false" in content
    assert "blitz = false" in content
    assert "time = 30" in content


def test_load_or_init_config_reads_valid_values(tmp_path: Path):
    config_path = tmp_path / ".qoridorrc"
    config_path.write_text(
        "[defaults]\n" "verbose = true\n" "blitz = true\n" "time = 12\n",
        encoding="utf-8",
    )

    values = load_or_init_config(config_path)

    assert values == {
        "verbose": True,
        "blitz": True,
        "time": 12,
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
