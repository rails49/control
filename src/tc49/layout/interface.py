"""Layout: the core app behind the layout interface, hardware-independent.

The seam between the system and the track, as an app that always runs
(ADR-0043). Above it the railroad is blocks, transits and trains; below it is
the **device vocabulary**, one retained state topic per device — what each
should do, written here, and what each is observed to do, written by whatever
answers for that address and read here. Nothing above this app names a device
and nothing below it names a transit, which is what lets two hardware systems
drive one railroad with no ownership table anywhere.

It holds a `Layout` and nothing else of the railroad's: the points a transit
needs ride on `align` (ADR-0031), so this app throws what it is told, and the
signal standing at a block end is `signal_at`, which is why the aspect the
dispatcher publishes for a person to read needs no address on it (#203).

**Everything the bus hands it is read and never trusted** (SYSTEM.md, rule 4).
Six topics from five publishers — the detectors joining them with the fold
(#288) — none of which this app answers — it reports
observations — so a frame that cannot be read is **dropped**, silently and to
the trace, and a command the layout contradicts goes the same way. Raising on
one would take the app running the railroad down at the whim of whoever
published it. The reading is `lib.payload`'s and whether the names name
anything here is `lib.layout`'s.

Three rules govern the two commands, and each exists because the bus promises
less than it looks like it does:

**Align before move.** The two commands have two publishers and the bus
promises no ordering between topics, so a `move` naming a transit no `align`
has named is **held** until one does, and the points are written first. This
is the obligation SYSTEM.md puts on the interface, and starting a train onto
points that have not thrown is what it prevents.

**The near-end check.** A `move` is acted on only if that train is standing at
the transit's near end (ADR-0047). At-least-once delivery can repeat one
minutes late, and after arrival the train has left the near end — so a
redelivery is a no-op on state alone, with no clock, no stamp and no agreement
between apps. Where the train stands comes from `train_placed`,
`train_removed` and the moves this app has itself carried out.

**No move while the rails are dead.** Nothing is acted on while `state/power`
is not `on` (ADR-0041). That is what makes a restart safe, and it has teeth on
every one of them now that the app comes up with the railroad off.

**Power is commanded on arrival and observed from below.** A `power_wanted` is
written straight through to `wanted/track` — there is no beat to quantise it
against, and an emergency stop that waits is not one (ADR-0051) — and nothing
is said about `state/power` on the strength of having commanded it. What this
app publishes there is folded from what the hardware reports: `_folded` is the
whole rule. It cannot verify that the supply really went and does not try; it
is the system designer's job to put a device there that does (#232).

**On startup the railroad is off.** The app comes up having written
`wanted/track: off` and `state/power: off`, so nothing moves and no turnout
throws until a person turns it on, normally from the panel. It never writes
`off` of its own accord thereafter: it writes the word it was told to write.

**Levels in, edges out.** A detector reports presence at one block end, and
presence is a level that can be asked for at any time; the bus carries the
changes because it is an event bus (#243). So this app holds the level per
block end and publishes `block_occupied` or `block_vacated` only where a
**debounced** level moves. A repeated level is a no-op that re-asserts what is
already held, which is what at-least-once delivery needs and the whole of it:
no counter and no dedup. `unknown` is no information about an end — the level
held stands, no edge comes of it, and the `reason` is logged once for a person
(#288).

**Two ends into one block.** Both detectors of a block stay inside the
interface. A block reads occupied while either of its ends does, and that fold
is what a level change publishes. The second event a move produces is the one
no detector can name: a train entering block Y trips Y's first detector with
its head and its second once it is fully in, so the second is where
`block_vacated(X)` goes out — this app carried out the move, so it knows which
block X is. Occupied then vacated, the only order the steel can produce
(ADR-0047). A level no move explains still publishes its own block's
occupancy: what to make of a reading nothing accounts for is the dispatcher's
judgement and not this app's (ADR-0048).

**Time.** The settling time is the one thing here that waits, and the layout
interface is where a clock is allowed to be read (ADR-0009) — the simulator
advances one and this app reads one, which is the same rule from the two
bindings. `settle()` is what applies a level that has stood long enough,
called by whoever owns the loop, so nothing here sleeps and a test drives the
clock directly.

What is **not** here yet: the traction write that turns a wheel, which
composes a speed's sign out of facing and each car's orientation (#296), and
the mode and the throttle that reach a locomotive through it (#297). An
accepted `move` records the train as crossing and waits for the detectors. The
simulator is untouched and remains the milestone-1 binding of the same
interface (ADR-0030).
"""

import logging
from dataclasses import dataclass

from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import (
    OCCUPIED,
    OFF,
    ON,
    UNKNOWN,
    device_topic,
    split_device,
)
from tc49.lib.layout import Layout, block_of, end_across, end_crossed, opposite_end
from tc49.lib.payload import (
    Command,
    Ordering,
    alignment,
    command,
    commanded_power,
    detected,
    link_up,
    named_train,
    placement,
    power,
    reported_reason,
    shown_aspects,
)

_log = logging.getLogger(__name__)

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
POWER_WANTED = "tc49/layout/power_wanted"
PLACED = "tc49/dispatch/train_placed"
REMOVED = "tc49/dispatch/train_removed"
ASPECTS = "tc49/dispatch/state/aspects"
DEVICE = "tc49/layout/state/device/#"

BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"
POWER = "tc49/layout/state/power"
WANTED_POINT = "tc49/layout/state/wanted/point"
WANTED_SIGNAL = "tc49/layout/state/wanted/signal"
WANTED_TRACK = "tc49/layout/state/wanted/track"
DEVICE_SENSOR = "tc49/layout/state/device/sensor"
DEVICE_TRACK = "tc49/layout/state/device/track"
DEVICE_LINK = "tc49/layout/state/device/link"

SETTLING_S = 0.3
"""How long a new level has to stand before it is acted on, in seconds of the
run clock, and the default of the constructor argument that carries it.

A camera-based detector runs at 2-8 Hz with no debounce of its own and is
biased towards reporting occupied (the `research/occupancy` notes), so a level
that flips back inside this window is never seen upstream. The number is this
app's own and is on no topic: what it is worth is a property of the detectors
a railroad has, which is why it is injected and not a constant anyone reads
(ADR-0030)."""


@dataclass(frozen=True)
class _Crossing:
    """A move this app carried out, and what the entered block's detectors
    will report about it.

    `origin` is the block the train is leaving, which is the whole reason this
    is held: occupancy is anonymous and no detector can name the block behind
    a train, so the only thing that knows X is what accepted the move.

    `far` is the entered block's **second** sensor — the end a train trips
    once it is fully in — and not the end across the transit, which is the end
    it comes in *at*. The two are opposite ends of the one block and the axes
    have been confused before (#279).
    """

    origin: str
    far: str


@dataclass(frozen=True)
class _Settling:
    """A level that has been seen and not yet acted on: what it says, and the
    reading of the run clock at which it will have stood long enough."""

    level: str
    at: float


class LayoutInterface:
    def __init__(
        self,
        bus: Bus,
        layout: Layout,
        clock: Clock,
        settling_s: float = SETTLING_S,
    ) -> None:
        """`layout`: the railroad this app answers for — the transits a `move`
        may name, and the signal standing at each block end. The whole of what
        it reads: the points ride on `align`, and the roster arrives with the
        traction write, which is where a car's address and the way it is
        parked are read (#296).

        `clock`: the run clock, read and never advanced here — the one thing
        the settling time is measured against. Required rather than defaulted
        for `lib.bus`'s reason: an app given none would debounce against a
        clock that never moves, and the window the argument is for would
        quietly stop working.

        `settling_s`: how long a new level stands before it is acted on,
        `SETTLING_S` by default. Injected because what it is worth is a fact
        about the detectors a railroad has (ADR-0030), and so that a test can
        drive it rather than sleep through it.
        """
        self._bus = bus
        self._layout = layout
        self._clock = clock
        self._settling_s = settling_s
        # Where each train stands, which is the whole of the near-end check.
        self._position: dict[str, str] = {}
        # The transits an `align` has named, and the moves waiting on one.
        self._aligned: set[str] = set()
        self._held: dict[str, Command] = {}
        # The occupancy fold: the settled level at each block end, the level
        # each end has most recently said (which is what makes the log of an
        # `unknown` once per transition into it), the levels waiting out the
        # settling time, what was last published about each block, and the
        # moves whose second reading is still to come.
        self._level: dict[str, str] = {}
        self._said: dict[str, str] = {}
        self._settling: dict[str, _Settling] = {}
        self._occupied: dict[str, bool] = {}
        self._crossing: dict[str, _Crossing] = {}
        # The two halves of the power fold, and what was last said about it.
        self._track = OFF
        self._links: dict[str, bool] = {}
        self._power = OFF
        # The stamps held against the state topics this app consumes: the
        # aspects and every device row. Two values of one topic delivered
        # backwards would otherwise leave a signal showing an aspect the
        # railroad has moved on from, or the supply reading dead while it is
        # live, with nothing to notice (#240).
        self._ordering = Ordering()
        # The railroad comes up dark, and this is the first thing said about
        # it: a person turns it on (ADR-0051). Before the subscriptions, so
        # that a retained value handed back by a bus that outlived the app
        # supersedes it rather than being overwritten by it — what the
        # hardware is saying now outranks what the last session was left
        # believing (ADR-0030).
        bus.publish(WANTED_TRACK, {"power": OFF})
        bus.publish(POWER, {"power": OFF})
        bus.subscribe(ALIGN, self._on_align)
        bus.subscribe(MOVE, self._on_move)
        bus.subscribe(POWER_WANTED, self._on_power_wanted)
        bus.subscribe(PLACED, self._on_placed)
        bus.subscribe(REMOVED, self._on_removed)
        bus.subscribe(ASPECTS, self._on_aspects)
        bus.subscribe(DEVICE, self._on_device)

    # -- live state, for the tests ------------------------------------------

    @property
    def position(self) -> dict[str, str]:
        """Where this app believes each train stands. Nothing publishes it —
        occupancy is the detectors' and placement is the dispatcher's — and
        it is what the near-end check is made of."""
        return dict(self._position)

    # -- the settling time --------------------------------------------------

    def settle(self) -> None:
        """Act on every level that has now stood for the settling time, oldest
        deadline first.

        The one thing here that waits, and the only place this app reads the
        clock (ADR-0009). It is called by whoever owns the loop — this app has
        no command line yet (README), so today that is the suite, driving the
        clock rather than sleeping on it. Levels are applied in the order they
        came due so that two ends settling in one call publish in the order the
        steel produced them.

        Nothing schedules the call: a detector publishes a level change and
        nothing else, so a level that goes occupied and stays occupied has no
        second frame to be noticed on, and an app that only settled when the
        next reading arrived would sit on a quiet railroad holding an arrival
        nobody was told about.
        """
        due = [
            (settling.at, end, settling.level)
            for end, settling in self._settling.items()
            if settling.at <= self._clock.now
        ]
        # By deadline, and by arrival among equals: the sort is stable and the
        # comprehension runs in the order the readings landed, so two levels
        # coming due together keep the order the detectors reported them in.
        due.sort(key=lambda settled: settled[0])
        for _at, end, level in due:
            del self._settling[end]
            self._settled(end, level)

    # -- the two commands ---------------------------------------------------

    def _on_align(self, topic: str, payload: Payload) -> None:
        """Set the route: throw the points the command carries, then let
        through whatever `move` was waiting for it.

        One write per **address**, so two pairs naming one address are one
        write: a crossover's two ends on one accessory output move together,
        which is a wiring fact the layout is allowed to state twice
        (ADR-0031). Where the two disagree about the position the first is
        written — a way that wants one address in two positions cannot be set
        at all, and the drawing's review is where that fault is reported, not
        the wire.

        Written every time and not only on change, because a hand may have
        flipped a point since: a translator throws what it is told (ADR-0043).
        Whether this railroad holds the transit is not asked — this app holds
        no table of points and the command carries its own — and marking a
        transit it does not hold costs nothing, a `move` naming one being
        dropped anyway.
        """
        aligning = alignment(payload)
        if aligning is None:
            return
        thrown: dict[str, str] = {}
        for point in aligning.points:
            thrown.setdefault(point.addr, point.position)
        for addr, position in thrown.items():
            self._bus.publish(
                device_topic(WANTED_POINT, addr), {"addr": addr, "position": position}
            )
        transit = f"{aligning.connection}.{aligning.transit}"
        self._aligned.add(transit)
        waiting = self._held.pop(transit, None)
        if waiting is not None:
            self._cross(waiting)

    def _on_move(self, topic: str, payload: Payload) -> None:
        """Take a train across a transit, or hold the command until the
        `align` that names it arrives."""
        commanded = command(payload)
        if commanded is None:
            return
        self._cross(commanded)

    def _cross(self, commanded: Command) -> None:
        """The three rules, in the order a command meets them, applied at the
        moment of acting: a held command is put back through all of them when
        its `align` lands, since the railroad may have moved under it while it
        waited.

        A command naming a transit this railroad does not hold, or one whose
        transit reaches neither end of the block it says the train is
        entering, names no near end for a train to be standing at and is
        dropped like a frame that could not be read (#276). Everything else
        that stops it here is a command that was true once and is not now,
        and none of them is an error: the interface answers nothing, so a
        refusal would have nowhere to go (ADR-0034).

        The train is recorded as crossing and nothing is published: the write
        that turns a wheel is #296, and the sensors that will say the train
        arrived are the detectors'. Recording it at the moment of acting is
        what makes the redelivery a no-op — the train has left the near end
        as surely as it has on the steel.

        The crossing is what the fold needs and nothing above the interface
        could supply: no detector names the block a train is leaving, so the
        move that was carried out is the only thing that knows it (#288).
        """
        transit = f"{commanded.connection}.{commanded.transit}"
        # The two ends the transit joins, read off names that came off the
        # bus: the near end the train must be standing at, and the end of the
        # entered block it comes in through — the end across the transit from
        # where it stands, which asked of the block being entered is
        # `end_crossed`. Both fail the same two ways and neither is an error.
        near = end_across(self._layout, commanded.into, transit)
        entered = end_crossed(self._layout, commanded.into, transit)
        if near is None or entered is None:
            return
        if self._power != ON:
            return
        if self._position.get(commanded.train) != block_of(near):
            return
        if transit not in self._aligned:
            self._held[transit] = commanded
            return
        self._position[commanded.train] = commanded.into
        self._crossing[commanded.into] = _Crossing(
            origin=block_of(near), far=opposite_end(entered)
        )

    # -- where the trains stand ---------------------------------------------

    def _on_placed(self, topic: str, payload: Payload) -> None:
        """A hand lifted a train and put it somewhere else (#152), and the
        dispatcher accepted it. The one thing besides a `move` that moves a
        train: nothing is commanded on it, and what it changes is which move
        this app will act on next.

        A `train_placed` never carries a null block — a train taken off the
        layout is `train_removed`, which names the train alone (ADR-0039) —
        so one that does is read the way an unreadable frame is.
        """
        placed = placement(payload)
        if placed is None or placed.block is None:
            return
        self._position[placed.train] = placed.block

    def _on_removed(self, topic: str, payload: Payload) -> None:
        """A hand lifted a train off the layout: it stands nowhere, so it
        stands at no transit's near end and no `move` naming it is acted on.
        """
        train = named_train(payload)
        if train is None:
            return
        self._position.pop(train, None)

    # -- the signals --------------------------------------------------------

    def _on_aspects(self, topic: str, payload: Payload) -> None:
        """Every signalled end, restated as what the signal standing there is
        to show.

        The lookup is here and not in the dispatcher because `state/aspects`
        is read by the panel and by a person driving by eye, and neither wants
        an address (#203). An end no signal stands at is skipped: an end
        nothing ever leaves carries none, a signal that could only show `stop`
        being furniture.

        There is no seeding rule for startup and none is needed — the
        dispatcher's value names every signalled end, and a held run puts them
        all to `stop`, so the retained value this app is handed on subscribing
        is the seed. Two ends sharing one address are two writes to one topic
        and the last stands, which is the wiring saying that two signals show
        one aspect together.
        """
        if not self._ordering.accepts(topic, payload):
            return
        shown = shown_aspects(payload)
        if shown is None:
            return
        for end, aspect in shown.items():
            addr = self._layout.signal_at.get(end)
            if addr is None:
                continue
            self._bus.publish(
                device_topic(WANTED_SIGNAL, addr), {"addr": addr, "aspect": aspect}
            )

    # -- the power ----------------------------------------------------------

    def _on_power_wanted(self, topic: str, payload: Payload) -> None:
        """A person asked the railroad for power, an emergency stop, or the
        supply removed: the word is written straight through to the device
        vocabulary and applied on arrival (ADR-0051).

        Nothing is said about `state/power` here. What this app publishes
        there is what the hardware reports, and a command is not a report: a
        railroad that answered `on` because somebody pressed ON would be this
        app taking its own word for the state of the track.

        A gesture that cannot be read is dropped rather than taken for `off`,
        which is the other direction from the reading of the same axis: `off`
        is a word this app writes only when it was told to.
        """
        wanted = commanded_power(payload)
        if wanted is None:
            return
        self._bus.publish(WANTED_TRACK, {"power": wanted})

    def _on_device(self, topic: str, payload: Payload) -> None:
        """What the hardware reports about itself. Three of the four rows are
        read: the supply, each translator's link to the system it drives, and
        each detector's level at the block end it watches.

        A `device/point` is a position where hardware reports one and is not
        acted on: it passes by unread rather than being taken for something
        else. The row and the address come from the **topic**, which is where
        a device topic states them; the payload repeats the address so a trace
        line reads on its own, and a repetition is not a second authority.

        Every row is stamp-guarded for one reason (#240): two values of one
        topic delivered backwards would leave the older standing, which on a
        sensor row is a block end reading clear after the reading that said a
        train is on it.
        """
        split = split_device(topic)
        if split is None:
            return
        row, address = split
        if row == DEVICE_SENSOR:
            if not self._ordering.accepts(topic, payload):
                return
            self._on_reading(address, payload)
            return
        if row == DEVICE_TRACK:
            if not self._ordering.accepts(topic, payload):
                return
            self._track = power(payload)
        elif row == DEVICE_LINK:
            if not self._ordering.accepts(topic, payload):
                return
            self._links[address] = link_up(payload)
        else:
            return
        self._publish_power()

    # -- the occupancy fold -------------------------------------------------

    def _on_reading(self, end: str, payload: Payload) -> None:
        """One detector's level at one block end, held rather than acted on.

        Presence is a level, so what arrives here is what the end reads *now*
        and never an edge. A reading that re-asserts the level already held is
        an at-least-once repeat and a no-op, which is the whole of what
        delivery needs — no counter and no dedup (#243). A reading that
        differs starts the settling time, and one that goes back inside that
        window cancels it: the flip is never seen upstream, which is what a
        detector running at 2-8 Hz with no debounce of its own needs from the
        consumer.

        `unknown` is **no information** about that end. It is not a level to
        settle, it does not cancel a level that is settling, and it does not
        discard the level held: the end goes on reading whatever it last
        actually said. The `reason` is logged once per transition into
        `unknown`, for a person — the detector knows why it cannot say, and
        nothing in the system branches on it (SYSTEM.md, *what the hardware
        reports back*).

        The address is the block end the detector watches, taken from the
        topic, and whether it names an end of this railroad is not asked: a
        reading for an end no block here has folds into a block nothing above
        will claim, and the dispatcher already holds the run on a reading it
        cannot explain (ADR-0048).
        """
        level = detected(payload)
        said, self._said[end] = self._said.get(end), level
        if level == UNKNOWN:
            if said != UNKNOWN:
                _log.info(
                    "detector at %s says unknown: %s",
                    end,
                    reported_reason(payload) or "no reason given",
                )
            return
        if level == self._level.get(end):
            self._settling.pop(end, None)
            return
        settling = self._settling.get(end)
        if settling is not None and settling.level == level:
            return
        self._settling[end] = _Settling(level, self._clock.now + self._settling_s)

    def _settled(self, end: str, level: str) -> None:
        """A level that has stood for the settling time, turned into whatever
        events it is worth.

        Two things come of it. A **block** reads occupied while either of its
        ends does, and a change in that fold is the block's own occupancy
        event — the block a hand put a locomotive on, as much as the block a
        train was granted, since a level no move explains is still a level and
        judging it is the dispatcher's (ADR-0048).

        And where the block is one a train is crossing into, its **second**
        sensor going occupied says the train is fully in, so the block behind
        is clear. That is the one event no detector could produce: occupancy
        is anonymous and the block behind is named by the move this app
        carried out. The entered block's own event has already gone out on its
        first sensor, so the order is occupied then vacated — the only order
        the steel can produce (ADR-0047).
        """
        self._level[end] = level
        block = block_of(end)
        occupied = OCCUPIED in (level, self._level.get(opposite_end(end)))
        if self._occupied.get(block) != occupied:
            self._occupied[block] = occupied
            self._bus.publish(
                BLOCK_OCCUPIED if occupied else BLOCK_VACATED, {"block": block}
            )
        crossing = self._crossing.get(block)
        if crossing is not None and level == OCCUPIED and end == crossing.far:
            del self._crossing[block]
            self._bus.publish(BLOCK_VACATED, {"block": crossing.origin})

    def _folded(self) -> str:
        """Whether a train may move at all, folded from what the hardware
        says: the supply's own word, and `off` wherever any link ever seen is
        down.

        A link that has gone reports a translator that cannot reach its
        hardware, and a railroad half of which is unreachable is not a
        railroad a train may move on — whatever the supply says, since the
        translator saying it may be the unreachable one. "Ever seen" and not
        "currently connected", because a link is a retained level: a
        translator that published `down` and then died leaves the value
        standing, and forgetting it would turn a broken railroad back on
        (ADR-0050).

        Anything that cannot be read falls the same way. `power` answers
        `off` for a supply it cannot read and `link_up` answers false for a
        link it cannot, so the fold needs no case for an unreadable frame:
        the direction a state topic must fail in is already in the readers
        (#181).

        `stopped` reaches `state/power` as itself rather than as `off`, since
        the two differ for the person recovering — one is cleared and the
        other switched back on — and the dispatcher branches on "not `on`"
        either way (ADR-0041, CONTEXT.md **Emergency stop**).
        """
        if not all(self._links.values()):
            return OFF
        return self._track

    def _publish_power(self) -> None:
        """Whether a train may move at all, on a last-value topic, and only
        when the fold moves: a state topic republishing the value it already
        holds is noise on the trace and news to nobody. The opening `off` is
        the constructor's, so a client that joins before the hardware has said
        anything is served a value rather than left to read one out of an
        absence (ADR-0032)."""
        folded = self._folded()
        if folded != self._power:
            self._power = folded
            self._bus.publish(POWER, {"power": folded})
