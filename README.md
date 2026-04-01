# Quoridor

Python implementation of the **Quoridor** board game with:
- an interactive command-line interface (CLI),
- a contest mode (read a position file and output one move),
- an optional GTK graphical interface.

## Installation

From the project root (a virtual environment is recommended):

```bash
pip install -e .
```

For development (tests, coverage, formatting, docs):

```bash
pip install -e ".[dev]"
```

For the GUI (optional):

```bash
pip install -e ".[gui]"
```

## Run The Game

- **Interactive CLI mode**
  ```bash
  quoridor
  ```

- **Contest mode** (read a position file and print one move to stdout)
  ```bash
  quoridor -c path/to/file.txt
  ```

- **Version**
  ```bash
  quoridor -V
  ```

- **GTK GUI**
  From the repository root:
  ```bash
  python -m quoridor.interfaces.gui
  ```
  From `quoridor/interfaces`:
  ```bash
  python -m gui
  ```

## Tests

```bash
pytest
```

Without coverage:

```bash
pytest -q -p no:cov -o addopts= tests
```

Run only contest-mode tests:

```bash
PYTHONPATH=. pytest -q -p no:cov -o addopts= tests/test_contest.py
```

## Documentation

API documentation is generated with Sphinx. After installing dev dependencies:

```bash
pip install -r docs/requirements.txt
cd docs
make html
```

If the RTD theme is missing (`ThemeError: no theme named 'sphinx_rtd_theme'`):

```bash
pip install sphinx-rtd-theme
```

Then open: **`docs/_build/html/index.html`** (or [index.html](docs/_build/html/index.html) from the repository root).

## Development

- Manually test contest mode (example):  
  `PYTHONPATH=. python3 -m quoridor.interfaces.cli -c contest_example.txt`  
  (adjust the module path if your CLI entry point is different).
