"""Simulator: the second layout interface binding, a discrete-event engine.

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
(ADR-0070). It comes up `off`, and states on `state/power` the last `on` or
`off` it applied, having no hardware to report one, with `draining` held over
it from the press until `tc49/dispatch/state/moving` reads false; `off` is
applied at once (ADR-0078). The rule is `lib.power.TrackPower`'s, which the
layout keeps too. A `move` starts while the supply is on, which a drain
leaves it; one arriving while the supply is off is **kept**, as the layout
keeps it, and put back through the same checks when the supply is next on
(#863). A move under way follows the supply, as a train on steel does (#832): a drain leaves the supply
on, so it runs to its sensors, and while the supply is off its sensor events
wait, firing at ON with the time they had left — a train a cut left between
blocks finishes its move when the power comes back.

The **speed** the command carries is ignored here for that same reason
(#283): a delay this app chose is not a distance divided by a speed, so
running the transit at 0.4 would take exactly as long as running it at 1.0
and pretending otherwise would put a travel-time model in the one place
ADR-0030 says the physical railroad decides. A binding that drives steel is
where the field means something.

One event queue, ordered by (time, sequence), advances the run clock
(`tc49.lib.clock`), with the wait injected: batch (``run``) jumps the clock
to the next scheduled event and stops when the queue is empty — nothing is
pending and no train is rolling — or when everything queued waits on a
supply that is off; the event budget is a backstop against live-lock bugs only. Live (``run_live``, #69) sleeps the same spans on a
wall clock, polls for commands each period, and never terminates on
quiescence. The dispatcher cannot tell the modes apart: ADR-0009 stands,
and the same run leaves the same trace.

It says the **fast clock** as `layout` does, on `tc49/layout/state/clock`,
when it is built with one (`lib.clock_row`): read off the run clock and said
once a second of it, which is a real second live and a simulated one in
batch, so a replay stays byte-identical (ADR-0090, decision 1). It is no
event on the queue, so it never holds a batch run open.

Where each train stands is held in memory and goes with the process. On a
real railroad the steel is the persistence — the trains are simply still
there in the morning — and this binding stands in for the steel, so where
that memory lives in a container is open and on no topic: retained state
lives in the broker and nowhere else, and a placement is nothing the
inventory names (ADR-0030, ADR-0059 decision 3, `tc49/simulator/__main__.py`).
"""

import time
from collections.abc import Callable
from heapq import heapify, heappop, heappush

from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.clock_row import FastClockRow
from tc49.lib.inventory import DRAINING, OFF, ON
from tc49.lib.layout import Layout, block_of, transit_ends
from tc49.lib.loading import BUILT
from tc49.lib.payload import Command, command, named_train, placement
from tc49.lib.power import TrackPower

CLOCK_S = 1.0
"""How often the fast clock is said, in seconds of run clock: once a real
second live, as `layout` says it, and once a simulated second in batch, so
the two runs say the same rows at the same stamps (ADR-0090, decision 1)."""

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
        built: bool = True,
        fast: FastClockRow | None = None,
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

        `built`: whether `layout` is what the railroad's drawing derives to,
        said on `tc49/layout/state/railroad` as the layout interface says it
        (ADR-0085, decision 4).

        `fast`: the fast clock, read off `clock`, said once each `CLOCK_S` of
        it from the run's start (ADR-0090). A run given none says none, which
        is the research harness's: its traces are what they were.
        """
        self._bus = bus
        self._layout = layout
        self._clock = clock
        self._transit_s = transit_s
        self._clear_s = clear_s
        self._position = dict(position or {})
        self._events: list[_Event] = []
        self._fast = fast
        # The run clock's next reading at which the fast clock is said.
        self._beat = clock.now
        self._seq = 0
        self._rolling: set[str] = set()  # trains between blocks, mid-move
        # The moves granted while the supply is off, one per train, each put
        # back through `_start` when it is next on (#863).
        self._kept: dict[str, Command] = {}
        # Per train, the blocks this binding's own detectors last read
        # occupied for it, in the order they were read: what a hand lifting it
        # clears (ADR-0069 decision 7). A block a train was put in and never
        # read occupied for it is not here.
        self._occupied: dict[str, list[str]] = {}
        # The word this binding last stated on `state/power`, the last `on`
        # or `off` it applied, and the run clock's reading when that supply
        # last went off: what the waiting events are moved later by when it
        # comes back (ADR-0070, decision 4).
        self._power = OFF
        self._supply = OFF
        self._cut_at = clock.now
        # How a power press is answered, the rule the layout keeps as well:
        # the word applied, and the moving row a drain ends on (ADR-0078).
        self._track_power = TrackPower()
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
        bus.subscribe("tc49/dispatch/state/moving", self._on_moving)
        # Which railroad this binding stands in for, stated from the
        # constructor like the supply below: one broker runs one railroad and
        # a view needs to know which, and the binding of the layout interface
        # that is running is the one app bound to one (ADR-0059 decision 2,
        # as amended by ADR-0060). The name is the layout's own, which is the
        # name the store lists it under, and whether anything was built from
        # it rides along (ADR-0085, decision 4).
        bus.publish("tc49/layout/state/railroad", {"name": layout.name, BUILT: built})
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

    def _on_moving(self, topic: str, payload: Payload) -> None:
        """Whether the dispatcher says a train is moving: what a drain ends
        on (ADR-0078), kept by `lib.power.TrackPower` as `layout` keeps it."""
        word = self._track_power.moving(topic, payload)
        if word is not None:
            self._apply(word)

    def _on_power_wanted(self, topic: str, payload: Payload) -> None:
        """A press on the one switch, `on`, `draining` or `off`, answered as
        the layout interface answers it (ADR-0070, ADR-0078): which press is
        applied, and when a drain ends, is `lib.power.TrackPower`'s."""
        word = self._track_power.answer(payload, self._supply)
        if word is not None:
            self._apply(word)

    def _apply(self, word: str) -> None:
        """The word the rule settled on. There is no hardware to report the
        supply, so the supply is the last `on` or `off` applied, which a drain
        leaves on, and `draining` stands over it until the drain ends (#752).

        The scheduled sensor events follow the supply, as a train on steel
        does (#832): a drain leaves it on, so a transit under way runs to its
        sensors. The supply going off stops them where they are, and coming
        back on moves each one later by the time it was off, so a transit goes
        on with the time it had left and the events keep their order (ADR-0070
        decision 4). Coming back on also starts the moves kept while it was
        off, each through `_start`'s checks again (#863).
        """
        supply = self._supply if word == DRAINING else word
        if supply != self._supply:
            if self._supply == ON:
                self._cut_at = self._clock.now
            elif supply == ON:
                waited = self._clock.now - self._cut_at
                self._events = [
                    (at + waited, seq, leaf, train, block)
                    for at, seq, leaf, train, block in self._events
                ]
                heapify(self._events)
            self._supply = supply
            if supply == ON:
                kept, self._kept = self._kept, {}
                for commanded in kept.values():
                    self._start(commanded)
        stated = self._track_power.stated(self._supply)
        if stated == self._power:
            return
        self._power = stated
        self._bus.publish("tc49/layout/state/power", {"power": stated})

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
        names a transit qualified, so it asks with `Command.transit_id`.
        Either way the command names no block a train could start from —
        there is no track over that transit into that block — and neither is
        an error to raise on but a command with nowhere to go (rule 4).
        """
        ends = transit_ends(self._layout, commanded.into, commanded.transit_id)
        return None if ends is None else block_of(ends[1])

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
        one end of it is not being asked for a run this railroad can make.

        It is the supply that decides, not the word stated (#863): a drain
        leaves the supply on, so a move granted then starts as it does while
        `on` and the drain ends after it. While the supply is off the move is
        **kept**, not dropped — the dispatcher granted it before reading the
        `off`, and it holds the train in a crossing no sensor would end — and
        started when the supply is next on. It is kept before the checks,
        which are applied when it starts: a train taken off or placed
        elsewhere meanwhile fails them then and the move is dropped. A second
        `move` for the same train replaces the one kept."""
        commanded = command(payload)
        if commanded is None:
            return
        if self._supply != ON:
            self._kept[commanded.train] = commanded
            return
        self._start(commanded)

    def _start(self, commanded: Command) -> None:
        """The checks a move meets at the moment it starts, and the start: its
        train must stand at the transit's near end and not be rolling."""
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

        It stops too where every queued event is waiting on a supply that is
        off: nothing can fire, and a batch run never presses `off`, so that
        case is only for safety.

        The fast clock, where there is one, is said at each whole `CLOCK_S`
        of run clock up to the last event, ahead of an event due at the same
        reading, as the live loop says it."""
        self._say_clock()
        self._bus.drain()  # the startup cascade: the whole timetable goes in
        fired = 0
        while self._events and self._supply == ON:
            if self._fast is not None and self._beat <= self._events[0][0]:
                self._clock.advance(self._beat)
                self._say_clock()
                continue
            if fired == event_limit:
                raise RuntimeError(f"no quiescence within {event_limit} events")
            fired += 1
            event = heappop(self._events)
            self._clock.advance(event[0])
            self._fire(event)
            self._bus.drain()

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

        While the supply is off the scheduled events wait: a turn is the
        whole period, and nothing fires until a press brings the power back
        and moves them later by the time it was gone. A drain leaves the
        supply on, so they fire through it.

        A wait is cut to the fast clock's next beat as well, where there is a
        clock, so it is said on the run clock's seconds and a live run's rows
        are a batch run's."""
        self._say_clock()
        self._bus.drain()  # the startup cascade: standing locks reach the trace
        while not stop():
            step = period_s
            if self._events and self._supply == ON:
                step = min(step, self._events[0][0] - self._clock.now)
            if self._fast is not None:
                step = min(step, self._beat - self._clock.now)
            sleep(max(step, 0.0))
            self._clock.advance(self._clock.now + max(step, 0.0))
            self._say_clock()
            while (
                self._supply == ON
                and self._events
                and self._events[0][0] <= self._clock.now
            ):
                self._fire(heappop(self._events))
                self._bus.drain()
            self._bus.drain()

    def _say_clock(self) -> None:
        """The fast clock said where a beat is due by the run clock, once
        however many were passed, and the next one set a `CLOCK_S` on from
        the one due, so the beats keep to the run's own seconds. The clock is
        no event: it runs whatever track power and the run are doing, and a
        batch run ends at quiescence without waiting on it (ADR-0090,
        decision 5)."""
        if self._fast is None or self._beat > self._clock.now:
            return
        self._fast.say()
        self._bus.drain()
        while self._beat <= self._clock.now:
            self._beat += CLOCK_S
