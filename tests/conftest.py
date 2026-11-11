"""What pytest has to be told by name.

The suite's shared scaffolding lives in `rails49_testing.broker`, a real
broker and the `broker` fixture, `tests/harness.py`, the in-process assembly,
`tests/brokers.py`, the bus over that broker for the apps that come up against
one, and `tests/startup.py`, the retained window they come up through —
imported like any other module, except a fixture, which pytest resolves by
name and no test imports. Registering the four as plugins is what puts their
fixtures in every suite's reach without a second declaration of one.
"""

pytest_plugins = [
    "rails49_testing.broker",
    "tests.harness",
    "tests.brokers",
    "tests.startup",
]
