quoridor documentation
======================

Quoridor is a Python implementation of the Quoridor board game.
It provides:

- an interactive CLI mode,
- a contest mode (read a position and output one move),
- a modular architecture for rules, core game state, and application logic.

Quick Start
-----------

Install in editable mode:

.. code-block:: bash

   pip install -e .

Install development tools (tests, coverage, formatting, docs):

.. code-block:: bash

   pip install -e ".[dev]"

Run tests:

.. code-block:: bash

   pytest -q

Run the CLI:

.. code-block:: bash

   quoridor

Run contest mode:

.. code-block:: bash

   quoridor -c contest_example.txt

Documentation
-------------

Build the HTML documentation:

.. code-block:: bash

   cd docs
   make html

The generated site entry point is:
``docs/_build/html/index.html``

Architecture
------------

.. toctree::
   :maxdepth: 2

   architecture


API Reference
-------------

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules
