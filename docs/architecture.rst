Architecture
============

Overview
--------

The project is organized as a layered package under ``src/quoridor``:

- ``interfaces``: user-facing entry points (CLI, contest parser, GUI).
- ``application``: orchestration of game flows (session lifecycle, AI, contest mode).
- ``core``: domain model and core mechanics (game state, board, notation, validators).
- ``rules``: pure game rules (pawn moves, wall placement legality, win checks).
- ``utils``: shared technical helpers (graph utilities, traversal helpers).

Package Layout
--------------

- ``quoridor/__main__.py``: executable entry point used by the ``quoridor`` script.
- ``quoridor/config.py``: configuration loading and defaults.
- ``quoridor/i18n.py``: internationalization setup.

Data and Control Flow
---------------------

1. The CLI parses arguments and initializes runtime configuration.
2. A ``GameSession`` coordinates turns and state transitions.
3. ``GameState`` stores the authoritative state snapshot.
4. Rule modules validate moves and wall placements.
5. Optional AI logic evaluates and chooses moves.

Design Notes
------------

- Keep ``rules`` modules stateless and deterministic when possible.
- Keep ``application`` focused on orchestration, not low-level validation.
- Keep ``core`` as the single source of truth for mutable game state.
- Prefer explicit imports from ``quoridor.*`` modules for clarity.
