"""The apps as processes: what a compose service starts, started from a test.

Here rather than in `tests/harness.py`, which is the in-process assembly, and
beside `tests/brokers.py`, which is the second process the apps come up
against: what these build is one container's worth of app — `python -m
tc49.<app>` with the flags its `__main__` parses — and the two system suites
that hold ADR-0059 decision 5 both want the same one.

Nothing here is a fixture. A test that starts an app decides when it starts,
when the store appears and which railroad it comes up on, and those are the
orders under test.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.brokers import Broker, free_port, listening, until

START_S = 30.0
"""How long a process is given to be answering. It covers a store client's
own backoff, which doubles from half a second (`lib/documents.py`) and is the
deployed one here: these suites start the deployment, so nothing about it is
shortened to suit them."""


def tc49() -> str:
    """The `tc49` script, as compose's store service runs it: the one beside
    the interpreter running this suite, so a checkout with two environments
    serves the store from the one under test."""
    beside = Path(sys.executable).with_name("tc49")
    return str(beside) if beside.exists() else "tc49"


class Process:
    """One process, started and stopped as a container's is.

    Its output goes to a file rather than a pipe: a pipe nobody reads fills
    and stops the app it was meant to watch, and what these tests want it for
    is a failure's message — and, for an app whose next state is not visible
    on the bus, the sentence it prints when it gets there.
    """

    def __init__(self, command: list[str], log: Path) -> None:
        self._command = command
        self._log = log
        self._running: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self._log.touch()
        with self._log.open("wb") as out:
            self._running = subprocess.Popen(
                self._command, stdout=out, stderr=subprocess.STDOUT
            )

    @property
    def running(self) -> bool:
        return self._running is not None and self._running.poll() is None

    def said(self) -> str:
        """Everything it has printed, for a failure to quote and for a test
        to wait on."""
        return self._log.read_text(errors="replace")

    def stop(self) -> None:
        """SIGTERM, which is how a container is stopped, and then a wait: an
        app that does not end on it is a defect of its own."""
        if self._running is None:
            return
        self._running.terminate()
        self._running.wait(timeout=10)
        self._running = None


class Store:
    """The store's face, started the same way and startable late: `tc49
    serve` on a port of its own, over a root a test made."""

    def __init__(self, root: Path, log: Path) -> None:
        self.port = free_port()
        self._process = Process(
            [
                tc49(),
                "serve",
                "--store",
                str(root),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            log,
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self._process.start()
        assert until(lambda: listening(self.port), START_S), self._process.said()

    def stop(self) -> None:
        self._process.stop()


@dataclass(frozen=True)
class App:
    """One of ADR-0059's six: how it is started, and what it leaves retained
    on the way up.

    The flags are the app's own — `dccex` takes a station and no railroad
    (hardware needs no layout, decision 5), the driver reads no documents and
    so takes no store. A table rather than six of everything, because what is
    asserted is one rule and the differences between the apps are the rule's
    own consequences.
    """

    name: str
    rows: tuple[str, ...]
    railroad: bool = True
    store: bool = False
    station: bool = False

    def command(self, broker: Broker, store: Store, railroad: str) -> list[str]:
        """What a compose service for this app runs, as it runs it."""
        args = [sys.executable, "-m", f"tc49.{self.name}"]
        args += ["--broker", f"127.0.0.1:{broker.port}"]
        if self.railroad:
            args += ["--railroad", railroad]
        if self.store:
            args += ["--store", store.url]
        if self.station:
            # An address nothing answers on: a translator whose command
            # station is not there reports the link it cannot make and stays
            # up (ADR-0050), and no test of ours needs hardware.
            args += ["--station", f"127.0.0.1:{free_port()}"]
        return args

    def process(self, broker: Broker, store: Store, railroad: str, at: Path) -> Process:
        """That command, ready to start, logging into `at`."""
        return Process(self.command(broker, store, railroad), at / f"{self.name}.log")


APPS = (
    App(
        "scheduler",
        store=True,
        rows=("tc49/schedule/state/facing", "tc49/schedule/state/exhausted"),
    ),
    App(
        "dispatcher",
        store=True,
        rows=(
            "tc49/dispatch/state/run",
            "tc49/dispatch/state/allocation",
            "tc49/dispatch/state/aspects",
            "tc49/dispatch/state/disputed",
        ),
    ),
    App("driver", rows=()),
    App(
        "layout",
        store=True,
        rows=(
            "tc49/layout/state/railroad",
            "tc49/layout/state/power",
            "tc49/layout/state/mode",
            "tc49/layout/state/wanted/track",
        ),
    ),
    App(
        "simulator",
        store=True,
        rows=("tc49/layout/state/railroad", "tc49/layout/state/power"),
    ),
    App(
        "dccex",
        railroad=False,
        station=True,
        rows=(
            "tc49/layout/state/device/track",
            "tc49/layout/state/device/link/dccex",
        ),
    ),
)
"""The six apps of ADR-0059, and the rows each opens with.

`driver` opens with none: it holds no state and reads no documents, so
silence is its cold start. `layout` writes no desired speed here although it
zeroes one per address it finds: on an empty broker there is nothing to zero,
which is the difference between a start and a restart.
"""
