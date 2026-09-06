"""What pytest has to be told by name.

The suite's shared scaffolding lives in `tests/harness.py`, the in-process
assembly, `tests/brokers.py`, a real broker for the apps that come up against
one, and `tests/startup.py`, the retained window they come up through —
imported like any other module, except a fixture, which pytest resolves by
name and no test imports. Registering the three as plugins is what puts their
fixtures in every suite's reach without a second declaration of one.
"""

pytest_plugins = ["tests.harness", "tests.brokers", "tests.startup"]
