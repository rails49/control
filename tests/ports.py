"""The port a test's server listens on.

Here rather than in `tests/brokers.py`, which is the second process the apps
come up against, or `tests/apps.py`, which is one container's worth of app:
what a number is wanted for is the same in both and in the suites that serve
a store on a thread, and three copies of the picking had grown.
"""

import socket


def free_port() -> int:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        return int(held.getsockname()[1])
