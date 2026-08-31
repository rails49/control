"""Simulator: the milestone-1 layout interface, as a discrete-event engine.

Commands in, observations out, plus ownership of time (SYSTEM.md, layout
interface; ADR-0009, ADR-0047). The two commands it responds to,
`tc49/layout/align` and `tc49/layout/move`, are named for it rather than for
whoever sends them, and it never asks which component did: today the
dispatcher sends one and the driver the other, and nothing here would change
if that moved. It names its two commands rather than filtering by prefix,
which is the one exception rule 3 allows: a `tc49/layout/#` filter would
hand it back its own sensor events. It acts on a `move` only if that train
is standing at the transit's near end (ADR-0047): a stale redelivery
arrives after the train has left, so it is a no-op on state alone — no
clock, no stamp, no agreement between apps.

It mimics what real trains do, with fixed delays standing in for travel
time. On a `move` it schedules `block_occupied(destination)` after the
transit delay and `block_vacated(origin)` after a second one — the head
reaching the far detector, then the tail clearing the near one, which is
the physical order (ADR-0047). Both delays are configurable, private to
this app, and never on any topic (ADR-0030). No RNG: transit times are
fixed, so a run is reproducible by construction.

One event queue, ordered by (time, sequence), advances the run clock
(`tc49.lib.clock`), with the wait injected: batch (``run``) jumps the clock
to the next scheduled event and stops when the queue is empty — nothing is
pending and no train is rolling; the event budget is a backstop against
live-lock bugs only. Live (``run_live``, #69) sleeps the same spans on a
wall clock, polls for commands each period, and never terminates on
quiescence. The dispatcher cannot tell the modes apart: ADR-0009 stands,
and the same run leaves the same trace.

Given a path it keeps its **own placement file** (#123): where each train
stands, written when one moves and read at startup. On a real railroad the
steel is the persistence — the trains are simply still there in the morning
— and the simulator stands in for the steel, so this stays inside the app.
No bus topic, no inventory entry, and nothing about simulation in the
contract (ADR-0030).
"""

import time
from collections.abc import Callable
from heapq import heappop, heappush
from pathlib import Path

from tc49.lib import durable
from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import ON
from tc49.lib.layout import Layout, block_of

# One scheduled sensor event: fires at a time, in scheduling order among
# equals, and says which train's head or tail passed which detector.
_Event = tuple[float, int, str, str, str]  # (time, seq, leaf, train, block)


def placement_file(state: Path) -> Path:
    """Where the simulator keeps its placement, beside the session's state
    file: a sibling and never the same file, the bus's holding the contract's
    retained values and this one the steel."""
    return durable.sibling(state, "placement")


class Simulator:
    def __init__(
        self,
        bus: Bus,
        layout: Layout,
        clock: Clock,
        position: dict[str, str] | None = None,
        placement: Path | None = None,
        transit_s: float = 30.0,
        clear_s: float = 30.0,
    ) -> None:
        """`layout`: the track this binding stands in for; what resolves a
        move's transit to the block its train must be standing in.

        `clock`: the run clock this binding advances and everything else only
        reads (ADR-0009).

        `position`: where the steel stands before anything has run, train to
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

        `transit_s` and `clear_s`: the fixed delays — head to the far
        detector, then tail past the near one.
        """
        self._bus = bus
        self._layout = layout
        self._clock = clock
        self._placement = placement
        self._transit_s = transit_s
        self._clear_s = clear_s
        stood = durable.read(placement) if placement is not None else {}
        self._position = dict(position or {}) | dict(stood)
        self._events: list[_Event] = []
        self._seq = 0
        self._rolling: set[str] = set()  # trains between blocks, mid-move
        # Whether a train may move at all, stated from the constructor so a
        # joining client is served a value rather than left to read one out
        # of an absence (ADR-0032, ADR-0041). Simulated track is always live
        # and this binding never says otherwise: a power cut is a physical
        # act, and simulating one would be a field or a branch that ADR-0030
        # keeps out of every app. What exercises the dispatcher's side of it
        # is the topic, published by a test.
        bus.publish("tc49/layout/state/power", {"power": ON})
        # Simulated points are always aligned; subscribed because the layout
        # interface declares the command, and the ordering obligation is met
        # by the bus delivering `align` before the `move` that follows it.
        bus.subscribe("tc49/layout/align", lambda topic, payload: None)
        bus.subscribe("tc49/layout/move", self._on_move)
        bus.subscribe("tc49/dispatch/train_placed", self._on_placed)
        bus.subscribe("tc49/dispatch/train_removed", self._on_removed)

    def _on_placed(self, topic: str, payload: Payload) -> None:
        """A hand lifted a locomotive and put it somewhere else (#152).

        The one thing that moves a train and is not a `move`. On a real
        railroad the steel simply is where the hand left it and nobody has to
        say so; the simulator stands in for the steel, so it has to be told,
        and `train_placed` is the dispatcher having accepted that it was.
        Without it the next `move` would vacate the block the train used to
        be in and the sensors would describe a railroad nobody is on.
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

    def _near_end(self, move: Payload) -> str:
        """The block a train must stand in to take this move's transit: the
        transit end that is not the block entered."""
        a, b = self._layout.connections[move["connection"]].transits[move["transit"]]
        return block_of(b) if block_of(a) == move["into"] else block_of(a)

    def _on_move(self, topic: str, payload: Payload) -> None:
        """One transit accepted: the train starts rolling and its two sensor
        events are scheduled — the head into the destination after the
        transit delay, the tail off the origin after the clearing one. A
        move whose train is not standing at the transit's near end is stale
        — redelivered after arrival, mid-move, or overtaken by a hand's
        placement — and is ignored (ADR-0047)."""
        train, into = payload["train"], payload["into"]
        origin = self._near_end(payload)
        if train in self._rolling or self._position.get(train) != origin:
            return
        self._rolling.add(train)
        occupied_at = self._clock.now + self._transit_s
        self._schedule(occupied_at, "block_occupied", train, into)
        self._schedule(occupied_at + self._clear_s, "block_vacated", train, origin)

    def _schedule(self, at: float, leaf: str, train: str, block: str) -> None:
        heappush(self._events, (at, self._seq, leaf, train, block))
        self._seq += 1

    def _fire(self, event: _Event) -> None:
        """One detector speaks. The head arriving is when the train's
        position moves — and so when the placement file is written — and the
        tail clearing is when it stops rolling and stands again."""
        _at, _seq, leaf, train, block = event
        if leaf == "block_occupied":
            self._position[train] = block
            if self._placement is not None:
                durable.write(self._placement, self._position)
        else:
            self._rolling.discard(train)
        self._bus.publish(f"tc49/layout/{leaf}", {"block": block})

    def run(self, event_limit: int = 100_000) -> None:
        """Batch: jump the clock event to event and stop at quiescence —
        nothing scheduled means nothing pending and no train rolling."""
        self._bus.drain()  # the startup cascade: the whole timetable goes in
        for _ in range(event_limit):
            if not self._events:
                return
            event = heappop(self._events)
            self._clock.advance(event[0])
            self._fire(event)
            self._bus.drain()
        raise RuntimeError(f"no quiescence within {event_limit} events")

    def run_live(
        self,
        period_s: float,
        sleep: Callable[[float], None] = time.sleep,
        stop: Callable[[], bool] = lambda: False,
    ) -> None:
        """The live loop: the same queue with the waits slept on a wall
        clock, cut to the next scheduled event so a sensor fires at the time
        batch mode stamps it. `period_s` caps a wait so commands arriving
        over the bridge are drained while nothing is scheduled; `stop` is
        polled once per wait, and the interactive session ignores it and
        stops on Ctrl-C instead. No quiescence termination: an idle railroad
        keeps waiting until the session is stopped."""
        self._bus.drain()  # the startup cascade: standing locks reach the trace
        while not stop():
            step = period_s
            if self._events:
                step = min(step, self._events[0][0] - self._clock.now)
            sleep(max(step, 0.0))
            self._clock.advance(self._clock.now + max(step, 0.0))
            while self._events and self._events[0][0] <= self._clock.now:
                self._fire(heappop(self._events))
                self._bus.drain()
            self._bus.drain()
