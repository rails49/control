"""Dispatcher: admits requests, chooses routes, grants moves deadlock-free.

The locking strategy is part of the public surface because it is chosen by
whoever assembles the run (ADR-0005). Everything else — the safety check,
route candidates, the lock table — is internal, and the tests that reach for
it import it by module on purpose.
"""

from tc49.dispatcher.dispatch import Dispatcher as Dispatcher
from tc49.dispatcher.locking import FullRoute as FullRoute
from tc49.dispatcher.locking import Incremental as Incremental
from tc49.dispatcher.locking import LockingStrategy as LockingStrategy
