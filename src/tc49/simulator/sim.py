"""Simulator: the milestone-1 layout interface, as a discrete-event engine.

Commands in, observations out, plus ownership of time (SYSTEM.md, layout
interface; ADR-0009, ADR-0047). The commands it responds to,
`tc49/layout/align`, `tc49/layout/move` and `tc49/layout/power_wanted`, are
named for it rather than for whoever sends them, and it never asks which
component did: today the dispatcher sends one, the driver another and a page
the third, and nothing here would change if that moved. It names its commands
rather than filtering by prefix, which is the one exception rule 3 allows: a
`tc49/layout/#` filter would hand it back its own sensor events. It acts on a `move` only if that train
is standing at the transit's near end (ADR-0047): a stale redelivery
arrives after the train has left, so it is a no-op on state alone — no
clock, no stamp, no agreement between apps.

Everything the bus hands it is **read** and never trusted (#262, rule 4): the
`move` it acts on and the two placements that move steel without one. A leaf
names the component that answers for it and not the process that published
this frame — under MQTT the driver, the dispatcher and a page are each another
container — so a payload proves nothing, and a binding that raised on one
would be taken down by whoever published it, leaving the railroad running
without the thing that watches it. A frame that cannot be read is **dropped**,
silently and to the trace: this binding reports observations and answers
nothing, so a refusal would have nowhere to go even where a frame carried an
id (ADR-0034). The reading itself is `lib.payload`'s, and whether the names
it read name anything on this railroad is `lib.layout`'s.

It mimics what real trains do, with fixed delays standing in for travel
time. On a `move` it schedules `block_occupied(destination)` after the
transit delay and `block_vacated(origin)` after a second one — the head
reaching the far detector, then the tail clearing the near one, which is
the physical order (ADR-0047). Both delays are configurable, private to
this app, and never on any topic (ADR-0030). No RNG: transit times are
fixed, so a run is reproducible by construction.

It answers the band's **power** presses as the layout interface does
(ADR-0070). It comes up `off`, and states on `state/power` the word each
answered `power_wanted` commanded, having no hardware to report one; a plain
`off` is applied only while the run is held and nothing moves (ADR-0062), the
check being `lib.power`'s and the layout's own. While the power is not `on`
no move starts and none advances: a `move` is dropped, and the sensor events
of a transit under way wait, firing at ON with the time they had left — a
train under an emergency stop on steel goes on at its kept speed.

The **speed** the command carries is ignored here for that same reason
(#283): a delay this app chose is not a distance divided by a speed, so
running the transit at 0.4 would take exactly as long as running it at 1.0
and pretending otherwise would put a travel-time model in the one place
ADR-0030 says the physical railroad decides. A binding that drives steel is
where the field means something.

One event queue, ordered by (time, sequence), advances the run clock
(`tc49.lib.clock`), with the wait injected: batch (``run``) jumps the clock
to the next scheduled event and stops when the queue is empty — nothing is
pending and no train is rolling — or when everything queued waits on power
that is not `on`; the event budget is a backstop against live-lock bugs only. Live (``run_live``, #69) sleeps the same spans on a
wall clock, polls for commands each period, and never terminates on
quiescence. The dispatcher cannot tell the modes apart: ADR-0009 stands,
and the same run leaves the same trace.

Where each train stands is held in memory and goes with the process. On a
real railroad the steel is the persistence — the trains are simply still
there in the morning — and this binding stands in for the steel, so where
that memory lives in a container is open and on no topic: retained state
lives in the broker and nowhere else, and a placement is nothing the
inventory names (ADR-0030, ADR-0059 decision 3, `tc49/simulator/__main__.py`).
"""

import logging
import time
from collections.abc import Callable
from heapq import heapify, heappop, heappush

from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import OFF, ON
from tc49.lib.layout import Layout, block_of, end_across
from tc49.lib.payload import (
    Command,
    Ordering,
    Run,
    command,
    commanded_power,
    kept_run,
    named_train,
    placement,
)
from tc49.lib.power import off_refused

_log = logging.getLogger(__name__)

# One scheduled sensor event: fires at a time, in scheduling order among
# equals, and says which train's head or tail passed which detector.
_Event = tuple[float, int, str, str, str]  # (time, seq, leaf, train, block)


class Simulator:
    def __init__(
        self,
        bus: Bus,
        layout: Layout,
        clock: Clock,
        position: dict[str, str] | None = None,
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
        arrives block by block as the dispatcher accepts each placement. A
        rebuild under the same railroad name is given the last build's, less
        any train whose block the new drawing lacks (ADR-0071).

        `transit_s` and `clear_s`: the fixed delays — head to the far
        detector, then tail past the near one.
        """
        self._bus = bus
        self._layout = layout
        self._clock = clock
        self._transit_s = transit_s
        self._clear_s = clear_s
        self._position = dict(position or {})
        self._events: list[_Event] = []
        self._seq = 0
        self._rolling: set[str] = set()  # trains between blocks, mid-move
        # Per train, the blocks this binding's own detectors last read
        # occupied for it, in the order they were read: what a hand lifting it
        # clears (ADR-0069 decision 7). A block a train was put in and never
        # read occupied for it is not here.
        self._occupied: dict[str, list[str]] = {}
        # The word this binding last stated on `state/power`, and the run
        # clock's reading when it last left `on`: what the waiting events are
        # moved later by when it comes back (ADR-0070, decision 4).
        self._power = OFF
        self._cut_at = clock.now
        # The last run row the dispatcher stated, for the check on a plain
        # `off` (ADR-0062), stamp-guarded as `layout` keeps it (#240).
        self._run: Run | None = None
        self._ordering = Ordering()
        # The commands, subscribed **before** a word is published. A publish
        # is asynchronous where a subscribe waits to be acknowledged, so an
        # app that published first would be deaf for as long as its own
        # subscriptions took to land, and every one of these is an event that
        # nothing hands over a second time: a granted move, a hand's
        # placement (ADR-0059, decision 5).
        #
        # Simulated points are always aligned; `align` is subscribed because
        # the layout interface declares the command, and the ordering
        # obligation is met by the bus delivering it before the `move` that
        # follows. Nothing is read off it, so nothing on it can fail to be
        # read: the command whose payload this binding does act on is `move`.
        bus.subscribe("tc49/layout/align", lambda topic, payload: None)
        bus.subscribe("tc49/layout/move", self._on_move)
        bus.subscribe("tc49/dispatch/train_placed", self._on_placed)
        bus.subscribe("tc49/dispatch/train_removed", self._on_removed)
        bus.subscribe("tc49/layout/power_wanted", self._on_power_wanted)
        bus.subscribe("tc49/dispatch/state/run", self._on_run)
        # Which railroad this binding stands in for, stated from the
        # constructor like the supply below: one broker runs one railroad and
        # a view needs to know which, and the binding of the layout interface
        # that is running is the one app bound to one (ADR-0059 decision 2,
        # as amended by ADR-0060). The name is the layout's own, which is the
        # name the store lists it under.
        bus.publish("tc49/layout/state/railroad", {"name": layout.name})
        # Whether a train may move at all, stated from the constructor so a
        # joining client is served a value rather than left to read one out
        # of an absence (ADR-0032, ADR-0041). `off`, as the layout interface
        # comes up: a person presses ON, and the bench harness publishes
        # `power_wanted: on` before a run (ADR-0070, decision 2).
        bus.publish("tc49/layout/state/power", {"power": OFF})

    @property
    def position(self) -> dict[str, str]:
        """Where each train stands on this binding's steel, train to block:
        what a rebuild under the same name carries into the next one
        (ADR-0071), as the layout interface's own `position` is."""
        return dict(self._position)

    def _on_run(self, topic: str, payload: Payload) -> None:
        """Where the dispatcher holds the run, and whether anything moves
        under it: what a plain `off` is checked against (ADR-0062). Read as
        `layout` reads it — an earlier stamp is ignored, and a value that
        cannot be read leaves the run already held standing."""
        if not self._ordering.accepts(topic, payload):
            return
        held = kept_run(payload)
        if held is None:
            return
        self._run = held

    def _on_power_wanted(self, topic: str, payload: Payload) -> None:
        """A person asked for power, an emergency stop, or the supply removed,
        and this binding answers it as the layout interface does (ADR-0070).
        There is no hardware to report the supply, so the word commanded is
        the word stated, and `stopped` stands until `on`.

        A press that cannot be read is dropped, and so is a plain `off` that
        `lib.power.off_refused` refuses, to the log with the reason: the
        supply is removed only while the run is held and nothing moves
        (ADR-0062).

        Leaving `on` stops the scheduled sensor events where they are; coming
        back to it moves each one later by the time the power was not `on`,
        so a transit goes on with the time it had left and the events keep
        their order (decision 4).
        """
        wanted = commanded_power(payload)
        if wanted is None:
            return
        if wanted == OFF:
            refusal = off_refused(self._run)
            if refusal is not None:
                _log.info("power off refused: %s", refusal)
                return
        if self._power == ON and wanted != ON:
            self._cut_at = self._clock.now
        elif self._power != ON and wanted == ON:
            waited = self._clock.now - self._cut_at
            self._events = [
                (at + waited, seq, leaf, train, block)
                for at, seq, leaf, train, block in self._events
            ]
            heapify(self._events)
        self._power = wanted
        self._bus.publish("tc49/layout/state/power", {"power": wanted})

    def _on_placed(self, topic: str, payload: Payload) -> None:
        """A hand lifted a locomotive and put it somewhere else (#152).

        The one thing that moves a train and is not a `move`. On a real
        railroad the steel simply is where the hand left it and nobody has to
        say so; the simulator stands in for the steel, so it has to be told,
        and `train_placed` is the dispatcher having accepted that it was.
        Without it the next `move` would vacate the block the train used to
        be in and the sensors would describe a railroad nobody is on.

        The fact is read like any other payload, and one naming no block is
        dropped with the rest: `train_placed` never carries a null — a train
        taken off the layout is `train_removed`, which names the train alone
        (ADR-0039) — so there is no steel to stand anywhere.

        The train's earlier readings and pending readings are forgotten, and
        it is no longer mid-move (#677): a head lifted short of the far
        detector never reaches it, and a tail lifted off the near one has
        nothing left to clear. Nothing is published: the block it left is not
        read clear and the block it is put in is not read occupied.
        """
        placed = placement(payload)
        if placed is None or placed.block is None:
            return
        train = placed.train
        self._occupied.pop(train, None)
        self._events = [event for event in self._events if event[3] != train]
        heapify(self._events)
        self._rolling.discard(train)
        self._position[train] = placed.block

    def _on_removed(self, topic: str, payload: Payload) -> None:
        """A hand lifted a train off the layout (#170), in any run state
        (ADR-0069).

        The other half of `_on_placed`: the steel is no longer there, so the
        simulator forgets where it was, and stands in for the hand that took
        it (decision 7). Every block its own detectors last read occupied for
        the train reads clear, and the readings it had scheduled for it are
        dropped — a head lifted short of the far detector never reaches it,
        and a tail lifted off the near one has nothing left to clear. A block
        the train was put in and never read occupied for reads nothing: no
        detector here ever said it was there.
        """
        train = named_train(payload)
        if train is None:
            return
        self._position.pop(train, None)
        self._rolling.discard(train)
        self._events = [event for event in self._events if event[3] != train]
        heapify(self._events)
        for block in self._occupied.pop(train, []):
            self._bus.publish("tc49/layout/block_vacated", {"block": block})

    def _near_end(self, commanded: Command) -> str | None:
        """The block a train must stand in to take this move's transit: the
        block across it from the one the command says the train is entering,
        or None where this railroad has no such transit or that transit
        reaches neither end of the block named.

        The command states the connection and a bare transit and the layout
        names a transit qualified, so the two halves go back together to ask
        it. Either way the command names no block a train could start from —
        there is no track over that transit into that block — and neither is
        an error to raise on but a command with nowhere to go (rule 4).
        """
        end = end_across(
            self._layout,
            commanded.into,
            f"{commanded.connection}.{commanded.transit}",
        )
        return None if end is None else block_of(end)

    def _on_move(self, topic: str, payload: Payload) -> None:
        """One transit accepted: the train starts rolling and its two sensor
        events are scheduled — the head into the destination after the
        transit delay, the tail off the origin after the clearing one. A
        move whose train is not standing at the transit's near end is stale
        — redelivered after arrival, mid-move, or overtaken by a hand's
        placement — and is ignored (ADR-0047). A command that cannot be read,
        or that names a transit this railroad does not hold, goes the same
        way: nothing rolls, and nothing raises. So does one whose transit
        reaches neither end of the block it says the train is entering
        (#276): that transit crosses no track to there, so the command names
        no near end to be standing at, and a train that happens to stand at
        one end of it is not being asked for a run this railroad can make."""
        commanded = command(payload)
        if commanded is None or self._power != ON:
            return
        train, into = commanded.train, commanded.into
        origin = self._near_end(commanded)
        if origin is None:
            return
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
        position moves, and the tail clearing is when it stops rolling and
        stands again."""
        _at, _seq, leaf, train, block = event
        read = self._occupied.setdefault(train, [])
        if leaf == "block_occupied":
            self._position[train] = block
            read.append(block)
        else:
            self._rolling.discard(train)
            if block in read:
                read.remove(block)
        self._bus.publish(f"tc49/layout/{leaf}", {"block": block})

    def run(self, event_limit: int = 100_000) -> None:
        """Batch: jump the clock event to event and stop at quiescence —
        nothing scheduled means nothing pending and no train rolling.

        It stops too where every queued event is waiting on power that is not
        `on`: nothing can fire, and a batch run never sends STOP, so that case
        is only for safety."""
        self._bus.drain()  # the startup cascade: the whole timetable goes in
        for _ in range(event_limit):
            if not self._events or self._power != ON:
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
        from the bus are drained while nothing is scheduled; `stop` is
        polled once per wait, and the deployed process sets it never and
        stops on a signal instead. No quiescence termination: an idle
        railroad keeps waiting until it is stopped.

        While the power is not `on` the scheduled events wait: a turn is the
        whole period, and nothing fires until a press brings the power back
        and moves them later by the time it was gone."""
        self._bus.drain()  # the startup cascade: standing locks reach the trace
        while not stop():
            step = period_s
            if self._events and self._power == ON:
                step = min(step, self._events[0][0] - self._clock.now)
            sleep(max(step, 0.0))
            self._clock.advance(self._clock.now + max(step, 0.0))
            while (
                self._power == ON
                and self._events
                and self._events[0][0] <= self._clock.now
            ):
                self._fire(heappop(self._events))
                self._bus.drain()
            self._bus.drain()
