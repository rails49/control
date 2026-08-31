"""Simulator: the milestone-1 layout interface.

Commands in, observations out, plus ownership of time (SYSTEM.md, layout
interface; ADR-0009). The commands have two publishers — `align` is the
dispatcher's, `move` the driver's — so it subscribes to both, and the
obligation that comes with the split is satisfied for free: batching to the
tick is why it can never act on a `move` before the `align` naming the same
transit (ADR-0031). The **tick** is this binding's word for its beat; what
goes on the bus is the grant boundary every binding publishes
(`tc49/layout/boundary`, ADR-0027). Each advance executes the buffered
commands, publishes their sensor events, then the boundary — a tick's
sensors precede the boundary itself. Batch mode (``run``) stops when the
scheduler was already exhausted at the start of a tick and that tick's
cascade produced no commands (BENCHMARKS.md, termination); the tick budget
is a backstop against live-lock bugs only. Live mode (``run_live``, #69)
paces the same advance on a wall clock and never terminates on quiescence —
an idle railroad keeps ticking until the session is stopped. The dispatcher
cannot tell the modes apart: ADR-0009 stands, and the boundary counter stays
a deterministic integer.

Given a path it keeps its **own placement file** (#123): where each train
stands, written when one moves and read at startup. On a real railroad the
steel is the persistence — the trains are simply still there in the morning —
and the simulator stands in for the steel, so this stays inside the app. No
bus topic, no inventory entry, and nothing about simulation in the contract
(ADR-0030).
"""

import time
from collections.abc import Callable
from pathlib import Path

from tc49.lib import durable
from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import ON


def placement_file(state: Path) -> Path:
    """Where the simulator keeps its placement, beside the session's state
    file: a sibling and never the same file, the bus's holding the contract's
    retained values and this one the steel."""
    return durable.sibling(state, "placement")


class Simulator:
    def __init__(
        self,
        bus: Bus,
        position: dict[str, str] | None = None,
        placement: Path | None = None,
    ) -> None:
        """`position`: where the steel stands before anything has run, train to
        block, which is the harness's — a run built from a scenario document
        (`bench/runner.py`). A run an operator drives is given none: its steel
        arrives block by block as the dispatcher accepts each placement.

        `placement`: the file this railroad's steel stands in for, or None to
        forget everything when the process ends.

        The file is the steel's own memory and comes first: a train it names
        is where it was left, including one no document places, which is a
        train a hand put on the rails (ADR-0039). A train the file does not
        name — one added since, or a first run — starts where it was built
        standing, if anywhere.
        """
        self._bus = bus
        self._placement = placement
        stood = durable.read(placement) if placement is not None else {}
        self._position = dict(position or {}) | dict(stood)
        self._moves: list[Payload] = []
        self._saw_command = False
        self._exhausted = False
        # Whether a train may move at all, stated from the constructor so a
        # joining client is served a value rather than left to read one out
        # of an absence (ADR-0032, ADR-0041). Simulated track is always live
        # and this binding never says otherwise: a power cut is a physical
        # act, and simulating one would be a field or a branch that ADR-0030
        # keeps out of every app. What exercises the dispatcher's side of it
        # is the topic, published by a test.
        bus.publish("tc49/layout/state/power", {"power": ON})
        bus.subscribe("tc49/drive/+", self._on_command)
        bus.subscribe("tc49/dispatch/align", self._on_command)
        bus.subscribe("tc49/dispatch/train_placed", self._on_placed)
        bus.subscribe("tc49/dispatch/train_removed", self._on_removed)
        bus.subscribe("tc49/schedule/state/exhausted", self._on_exhausted)

    def _on_command(self, topic: str, payload: Payload) -> None:
        self._saw_command = True
        if topic.endswith("/move"):
            self._moves.append(payload)

    def _on_placed(self, topic: str, payload: Payload) -> None:
        """A hand lifted a locomotive and put it somewhere else (#152).

        The one thing that moves a train and is not a `move`. On a real
        railroad the steel simply is where the hand left it and nobody has to
        say so; the simulator stands in for the steel, so it has to be told,
        and `train_placed` is the dispatcher having accepted that it was.
        Without it the next `move` would vacate the block the train used to
        be in and the sensors would describe a railroad nobody is on. It is
        not a command and not a tick: nothing is buffered, and no boundary
        moves.
        """
        self._position[payload["train"]] = payload["block"]
        if self._placement is not None:
            durable.write(self._placement, self._position)

    def _on_removed(self, topic: str, payload: Payload) -> None:
        """A hand lifted a train off the layout (#170).

        The other half of `_on_placed`: the steel is no longer there, so the
        simulator forgets where it was. Its detectors say nothing about it —
        the binding reports occupancy when a train crosses, and this train
        crosses nothing now.
        """
        self._position.pop(payload["train"], None)
        if self._placement is not None:
            durable.write(self._placement, self._position)

    def _on_exhausted(self, topic: str, payload: Payload) -> None:
        self._exhausted = payload["exhausted"]

    def _advance(self) -> None:
        """Execute the moves buffered since the last tick: each train
        reaches the block it was told to cross into, and its sensors say so.
        The only thing that moves a train, and so the only thing that has to
        write the placement file."""
        moves, self._moves = self._moves, []
        for move in moves:
            train, into = move["train"], move["into"]
            origin = self._position[train]
            self._position[train] = into
            self._bus.publish("tc49/layout/block_vacated", {"block": origin})
            self._bus.publish("tc49/layout/block_occupied", {"block": into})
        if moves and self._placement is not None:
            durable.write(self._placement, self._position)

    def run(self, tick_limit: int = 10_000) -> None:
        self._bus.drain()  # the startup cascade: standing locks reach the trace
        for now in range(tick_limit):
            exhausted_at_start = self._exhausted
            self._saw_command = False
            self._advance()
            self._bus.publish("tc49/layout/boundary", {"boundary": now})
            self._bus.drain()
            if exhausted_at_start and not self._saw_command:
                return
        raise RuntimeError(f"no quiescence within {tick_limit} ticks")

    def run_live(
        self,
        period_s: float,
        sleep: Callable[[float], None] = time.sleep,
        stop: Callable[[], bool] = lambda: False,
    ) -> None:
        """The live loop: one sleep of the period before every tick, and no
        quiescence termination. `sleep` is the injectable time source, so
        tests pace the loop without waiting; `stop` is polled once per tick,
        and the interactive session ignores it and stops on Ctrl-C instead."""
        self._bus.drain()  # the startup cascade: standing locks reach the trace
        now = 0
        while not stop():
            sleep(period_s)
            self._advance()
            self._bus.publish("tc49/layout/boundary", {"boundary": now})
            self._bus.drain()
            now += 1
