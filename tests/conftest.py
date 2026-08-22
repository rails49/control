"""What pytest has to be told by name.

The suite's shared scaffolding lives in `tests/harness.py`, imported like any
other module — except a fixture, which pytest resolves by name and no test
imports. Registering the harness as a plugin is what puts its fixtures in
every suite's reach without a second declaration of one.
"""

pytest_plugins = ["tests.harness"]
