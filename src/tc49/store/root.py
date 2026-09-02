"""Where an installation's store is rooted: `~/tc49/`, or what overrides it.

A store holds the documents somebody's railroad is made of — its drawings,
the stock it owns, the catalogue of what was bought — and those are the
person's, not the checkout's. So the root is **visible and stable**: `~/tc49/`
is a directory to `cd` into, `git init` and push somewhere, and an XDG data
directory is the wrong promise for it, being where a system keeps what it may
throw away and rebuild ([#320](https://github.com/rails49/control/issues/320)).

**Nothing seeds it.** A fresh installation has no railroad, and an empty store
is an ordinary state rather than a fault: the store lists nothing, the server
comes up and answers, and `tc49 live <name>` refuses the name in words. A
fixture copied in on first run would be a document the person did not make and
cannot tell from one they did.

The benchmark's fixtures are somewhere else and stay there:
:func:`tc49.bench.runner.find_assets` roots a store at the checkout's `bench/`,
and `tc49 bench` and `tc49 sweep` read that whatever this says. Which is why
a developer's `tc49 live reversing-loops` needs the override — the railroad
they want is a fixture, and their own store does not hold it.
"""

import os
from pathlib import Path

STORE_ENV = "TC49_STORE"
"""The environment variable that says where the store is.

There has to be one that is not a flag: the UI opens the store with no
arguments, and a container is configured by its environment and not by
somebody's command line (docs/DEPLOY.md)."""

DEFAULT_STORE = "~/tc49"
"""Where an installation's documents are unless it is told otherwise."""


def store_root(override: Path | None = None) -> Path:
    """The root to open this installation's store at.

    The flag wins, then the environment, then the default — a person typing
    `--store` is answering the question for this one command, and that is the
    last word by definition. An empty or blank `TC49_STORE` is no value at
    all, so an unset variable and one exported empty by a shell script mean
    the same thing rather than rooting a store at the working directory.

    `~` is expanded here rather than left to a shell: the default carries one
    and nothing expands the environment's.
    """
    if override is not None:
        return override.expanduser()
    named = os.environ.get(STORE_ENV, "").strip()
    return Path(named or DEFAULT_STORE).expanduser()
