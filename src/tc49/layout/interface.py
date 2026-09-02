"""Layout: the core app behind the layout interface, hardware-independent.

The seam between the system and the track, as an app that always runs
(ADR-0043). Above it the railroad is blocks, transits and trains; below it is
the **device vocabulary**, one retained state topic per device — what each
should do, written here, and what each is observed to do, written by whatever
answers for that address and read here. Nothing above this app names a device
and nothing below it names a transit, which is what lets two hardware systems
drive one railroad with no ownership table anywhere.

It holds a `Layout` and a `Roster`: the points a transit needs ride on `align`
(ADR-0031), so this app throws what it is told; the signal standing at a block
end is `signal_at`, which is why the aspect the dispatcher publishes for a
person to read needs no address on it (#203); and the roster is how a train
becomes the addresses that answer for it, no address ever reaching a command
(#199).

**Everything the bus hands it is read and never trusted** (SYSTEM.md, rule 4).
Nine topics from six publishers — the detectors joining them with the fold
(#288), and the throttle's two gestures coming from where a person's press
already does (#297) — none of which this app answers — it reports
observations — so a frame that cannot be read is **dropped**, silently and to
the trace, and a command the layout contradicts goes the same way. Raising on
one would take the app running the railroad down at the whim of whoever
published it. The reading is `lib.payload`'s and whether the names name
anything here is `lib.layout`'s.

Three rules govern the two commands, and each exists because the bus promises
less than it looks like it does. A fourth thing stops a `move`, and it is a
refusal rather than a rule about the bus: **no facing, no move** (below).

**Align before move.** The two commands have two publishers and the bus
promises no ordering between topics, so a `move` naming a transit no `align`
has named is **held** until one does, and the points are written first. This
is the obligation SYSTEM.md puts on the interface, and starting a train onto
points that have not thrown is what it prevents. An `align` authorises **one**
crossing and the move that is acted on spends it, so the rule guards every
crossing of a transit rather than only its first — a record of every transit
ever aligned would let the second move through with the points unthrown, which
is a train taking the wrong path (#305). It costs nothing in the ordinary
order, the dispatcher sending an `align` with every grant.

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

**On startup the railroad is off, and at rest.** The app comes up having
written `wanted/track: off` and `state/power: off`, so nothing moves and no
turnout throws until a person turns it on, normally from the panel. It never
writes `off` of its own accord thereafter: it writes the word it was told to
write. It also comes up having written `0.0` over every retained
`wanted/traction` row it finds, so a speed the last session left on a durable
bus is not sent to a station at the first connect and the locomotive does not
roll on the power-on (ADR-0054). `wanted/point` replays instead: a point has
no resting value to write.

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

**The traction write.** On a `move` it acts on, this app publishes a signed
speed for every car of the train that has an address, and `0.0` for each of
them again on arrival. **How fast** is the move's own speed, a magnitude.
**Which way** is two facts composed: whether the move leaves the end the train
faces — read off `tc49/schedule/state/facing`, there being nowhere else facing
lives (ADR-0045) — and which way round each car is coupled. A move whose
facing this app has never seen is dropped rather than guessed, and a train
whose cars carry no address at all is carried out with nothing to publish
(#296).

**Who drives.** A train is `automatic` or `manual`, `mode_wanted` moves it and
`state/mode` says where it stands — `automatic` at rest, so a train the map
does not name is automatic (#207). The word names who turns the throttle and
nothing else: a manual train is dispatched like any other, holds its block,
is granted moves and gets its points thrown and its near end checked. What it
changes is exactly one thing — whether this app writes the wheels. A person's
`throttle_wanted` reaches those same rows, signed the same way, the lever
stating nose-first where a `move` states a destination block. Taking a train
writes nothing and giving it back writes what its grant implies, which is
`0.0` where there is none (#297).

What is **not** here yet: the function topic beside the traction write, which
is nobody's until a gesture carries a function press. The simulator is
untouched and remains the milestone-1 binding of the same interface
(ADR-0030).
"""

import logging
from dataclasses import dataclass, replace

from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import (
    MANUAL,
    OCCUPIED,
    OFF,
    ON,
    UNKNOWN,
    device_topic,
    split_device,
)
from tc49.lib.layout import (
    FACINGS,
    Layout,
    block_of,
    end_across,
    end_crossed,
    end_letter,
    facing_ends,
    opposite_end,
)
from tc49.lib.payload import (
    Command,
    Mode,
    Ordering,
    alignment,
    command,
    commanded_power,
    detected,
    kept_facing,
    link_up,
    named_train,
    placement,
    power,
    reported_reason,
    shown_aspects,
    wanted_mode,
    wanted_throttle,
)
from tc49.lib.roster import FORWARD, Roster

_log = logging.getLogger(__name__)

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
POWER_WANTED = "tc49/layout/power_wanted"
MODE_WANTED = "tc49/layout/mode_wanted"
THROTTLE_WANTED = "tc49/layout/throttle_wanted"
PLACED = "tc49/dispatch/train_placed"
REMOVED = "tc49/dispatch/train_removed"
ASPECTS = "tc49/dispatch/state/aspects"
FACING = "tc49/schedule/state/facing"
DEVICE = "tc49/layout/state/device/#"

BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"
POWER = "tc49/layout/state/power"
MODE = "tc49/layout/state/mode"
WANTED_TRACTION = "tc49/layout/state/wanted/traction"
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

    `train` is who is crossing, and it is here so that a train can be found by
    name: taking one in a throttle or giving it back has to reach the move it
    is in the middle of, and nothing else about a crossing says whose it is
    (#297).

    `implied` is what this move is worth on each addressed car — the speed the
    grant implies, which is what a train handed back mid-transit is given. It
    empties on the arrival, which is the first level the entered block settles
    occupied: the train is in the block it was sent to and the tail clearing
    is a fact about the block behind, so nothing here waits for the vacate
    (#296).

    `driving` is whether the wheels are this app's for the length of this
    crossing. It is true for an automatic train, false for a manual one whose
    throttle a person is holding, and it moves with the mode: what it decides
    is who writes — the speed at the start and the `0.0` at the arrival go out
    exactly where it is true, since a car nothing was sent for is a car
    nothing may be sent for.
    """

    origin: str
    far: str
    train: str
    implied: tuple[tuple[str, float], ...] = ()
    driving: bool = True


@dataclass(frozen=True)
class _Settling:
    """A level that has been seen and not yet acted on: what it says, and the
    reading of the run clock at which it will have stood long enough."""

    level: str
    at: float


def _composed(
    addressed: tuple[tuple[str, str], ...], nose_first: bool, magnitude: float
) -> tuple[tuple[str, float], ...]:
    """The signed speed each addressed car is given, out of how fast the train
    is to run, whether it runs nose-first, and which way round each of its cars
    is coupled.

    The one composition, made twice: a `move` gets `nose_first` from the end it
    departs through against the train's facing, and a person's throttle gets it
    from the sign of the lever, a lever being stated nose-first positive
    (SYSTEM.md, *Layout interface*). Either way a car runs positive when the
    movement is nose-first and the car is `forward`, or when the movement is
    propelled and the car is `reverse` — which is what lets one number drive a
    top-and-tail set, the two locomotives running opposite (ADR-0045)."""
    return tuple(
        (addr, magnitude if (orientation == FORWARD) == nose_first else -magnitude)
        for addr, orientation in addressed
    )


class LayoutInterface:
    def __init__(
        self,
        bus: Bus,
        layout: Layout,
        roster: Roster,
        clock: Clock,
        settling_s: float = SETTLING_S,
    ) -> None:
        """`layout`: the railroad this app answers for — the transits a `move`
        may name, and the signal standing at each block end. The whole of what
        it reads: the points ride on `align` (ADR-0031).

        `roster`: the cars the railroad owns and the trains made up from them,
        which is how a train becomes addresses. No address ever reaches
        `tc49/layout/move` (#199), so turning the train the command names into
        the decoders that answer for it is this app's, and each car's
        orientation — the way round it is coupled — is half of the sign the
        traction write carries (ADR-0045).

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
        self._roster = roster
        self._clock = clock
        self._settling_s = settling_s
        # Where each train stands, which is the whole of the near-end check,
        # and which way each one points, which is half of the traction write's
        # sign. The one is this app's own record and the other is read off the
        # scheduler's state topic, there being nowhere else facing lives.
        self._position: dict[str, str] = {}
        self._facing: dict[str, str] = {}
        # Who drives each train. Only the manual ones are held: `automatic` is
        # the resting value and a train the map does not name is automatic, so
        # this is the record of which trains a person has taken and it is what
        # `state/mode` carries.
        self._mode: dict[str, str] = {}
        # The crossings an `align` has authorised, one entry per transit and
        # each spent by the move that takes it, and the moves waiting on one.
        self._aligned: set[str] = set()
        self._held: dict[str, Command] = {}
        # The occupancy fold: the settled level at each block end, the level
        # each end has most recently said (which is what makes the log of an
        # `unknown` once per transition into it), the levels waiting out the
        # settling time, what was last published about each block, the ends
        # whose occupied level a departure has already spent, and the moves
        # whose second reading is still to come.
        self._level: dict[str, str] = {}
        self._said: dict[str, str] = {}
        self._settling: dict[str, _Settling] = {}
        self._occupied: dict[str, bool] = {}
        self._spent: set[str] = set()
        self._crossing: dict[str, _Crossing] = {}
        # The two halves of the power fold, and what was last said about it.
        self._track = OFF
        self._links: dict[str, bool] = {}
        self._power = OFF
        # The stamps held against the state topics this app consumes: the
        # aspects, the facing and every device row. Two values of one topic
        # delivered
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
        # And it comes up **at rest**, which is the same ruling one level
        # down. A traction row is retained, so a bus that outlived the app
        # hands the last session's speed back verbatim and a translator
        # subscribed to it sends that speed at the first connect: the
        # locomotive rolls the moment somebody powers the rails, with no
        # grant, the run still held, and nothing on the bus that says why
        # (#333, ADR-0054). Held-by-default never enters the path, the row
        # having been written by a session that is gone.
        #
        # Zero is written here rather than by a translator standing down,
        # because this app is the row's one writer and this is where "the
        # railroad comes up dark" already lives: the ruling then holds when a
        # process is killed as well as when it exits.
        #
        # `wanted/point` is left to replay on purpose. Traction has a resting
        # value and a point has none — there is no neutral position to write
        # into the row — so the retained belief about where the last session
        # left the blades is the only answer short of throwing every point at
        # startup.
        for topic in bus.last_values:
            split = split_device(topic)
            if split is not None and split[0] == WANTED_TRACTION:
                self._traction_write(split[1], 0.0)
        # And every train is automatic, which is the resting value and the
        # honest one: this app's map of who drives is empty, so the topic says
        # so rather than leaving a client to read that out of an absence
        # (ADR-0032). It is not subscribed to and a value left there by a
        # previous session is superseded rather than adopted — the mode is a
        # person's hand on a throttle, and a restart is not a hand.
        bus.publish(MODE, {"modes": {}})
        bus.subscribe(ALIGN, self._on_align)
        bus.subscribe(MOVE, self._on_move)
        bus.subscribe(POWER_WANTED, self._on_power_wanted)
        bus.subscribe(MODE_WANTED, self._on_mode_wanted)
        bus.subscribe(THROTTLE_WANTED, self._on_throttle_wanted)
        bus.subscribe(PLACED, self._on_placed)
        bus.subscribe(REMOVED, self._on_removed)
        bus.subscribe(ASPECTS, self._on_aspects)
        bus.subscribe(FACING, self._on_facing)
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

        The train is recorded as crossing and every car of it that has an
        address is told how fast and which way to run. Recording the crossing
        at the moment of acting is what makes the redelivery a no-op — the
        train has left the near end as surely as it has on the steel — and the
        sensors that will say it arrived are the detectors'.

        There is a fourth thing that stops a command here and it is a refusal
        rather than a rule about the bus: a train with wheels to turn and no
        facing this app has seen is **dropped**, because the sign cannot be
        composed and a guess is a locomotive driven the wrong way down the
        track (`_traction`). It is checked last, after the hold, so a command
        waiting for its `align` is judged on the facing it has when it acts,
        like every other rule here.

        A **manual** train's move runs the whole of this and writes nothing:
        the throttle is a person's, so this app neither starts the train on
        the grant nor stops it on arrival, and the refusal above has nothing
        to refuse. The points still throw, the near end is still checked and
        the crossing is still recorded, because those are the route and not
        the driving (#297). What the move was worth is kept all the same: it
        is what the train is given if it is handed back before it arrives.

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
        driving = self._mode.get(commanded.train) != MANUAL
        wheels = self._traction(commanded, near)
        if wheels is None:
            if driving:
                return
            # A manual train's move runs its course whatever this app could
            # have made of the sign: nothing is being written, so there is no
            # wrong way to drive it and no refusal to make (#297).
            wheels = ()
        # The authorisation is spent here, with the act it authorised: an
        # `align` stands for one crossing, so the next move over this transit
        # waits for one of its own (#305).
        self._aligned.discard(transit)
        self._position[commanded.train] = commanded.into
        self._crossing[commanded.into] = _Crossing(
            origin=block_of(near),
            far=opposite_end(entered),
            train=commanded.train,
            implied=wheels,
            driving=driving,
        )
        if not driving:
            return
        for addr, speed in wheels:
            self._traction_write(addr, speed)

    # -- the traction write -------------------------------------------------

    def _traction(
        self, commanded: Command, near: str
    ) -> tuple[tuple[str, float], ...] | None:
        """What this move is worth on each of the train's decoders: one signed
        speed per addressed car, `()` where the train has none, and None where
        the move is to be dropped for want of the facts to sign it (#296).

        **How fast** is the move's own speed, a magnitude — the sign is this
        app's to give and never the command's, so the magnitude is taken and
        whatever sign a publisher put on it is not (SYSTEM.md, *Layout
        interface*).

        **Which way** is two facts composed. The first is whether the move
        leaves the end the train faces: `near` is the end of the origin block
        this transit crosses, which is the end the train departs through, and
        facing says which end its nose points at. Equal is nose-first;
        different is **propelled** — pushed out of the end its nose points
        away from — which is an ordinary movement and not an error
        (CONTEXT.md, **Facing**). The second is the car's `orientation`, the
        way round it is coupled: that is what lets a locomotive at each end of
        a train run opposite (ADR-0045). So a car runs positive when the move
        is nose-first and the car is `forward`, or when the move is propelled
        and the car is `reverse`, and negative otherwise.

        **Which cars.** Every car with an `addr`, in the train's own order. No
        `kind` is read: a powered van is a real thing, and the address is what
        says a car can be told a speed.

        **No address, no command**, and it is not a failure: a train whose
        cars carry no address at all — the simulator's trains are like this,
        and so is anything a hand moves — still gets its `align`, its near-end
        check and its crossing record, and simply has nothing to publish. That
        is why the answer is `()` rather than None, and why a train the roster
        does not name at all reaches the same answer: there are no wheels
        here to turn wrongly.

        **No facing, no move.** A train that has wheels to turn and no facing
        this app has seen — none published, one it cannot spell, or one naming
        another block than the one the train is departing — is dropped whole.
        Facing arriving later does not run it: the command was dropped, and
        nothing here holds it (SYSTEM.md, rule 4). A move that states no
        **speed** falls the same way and for the same reason: this app would
        have to choose a number nobody asked for.
        """
        addressed = self._addressed(commanded.train)
        if not addressed:
            return ()
        facing = self._faces(commanded.train, block_of(near))
        if facing is None or commanded.speed is None:
            return None
        return _composed(
            addressed, facing_ends(facing)[1] == near, abs(commanded.speed)
        )

    def _addressed(self, train: str) -> tuple[tuple[str, str], ...]:
        """Each car of the train that can be told a speed, as its address and
        the way round it is coupled, in the train's own order.

        `()` for a train the roster does not name and for one whose cars carry
        no address, which are the same answer arrived at a step apart: either
        way there are no wheels here to turn. No `kind` is read — a powered
        van is a real thing, and the address is what says a car can be told
        anything (ADR-0045)."""
        made_up = self._roster.trains.get(train)
        return tuple(
            (coupled.car.addr, coupled.orientation)
            for coupled in (made_up.cars if made_up is not None else ())
            if coupled.car.addr is not None
        )

    def _points(self, train: str) -> str | None:
        """The facing this app holds for the train, or None where it holds
        none it can spell: none published for that train, or a value outside
        the `<block>.<A-to-B|B-to-A>` form, which the bare end letter this
        topic once carried is (#241)."""
        facing = self._facing.get(train)
        if facing is None or end_letter(facing) not in FACINGS:
            return None
        return facing

    def _faces(self, train: str, block: str) -> str | None:
        """The same, of a train standing in `block`: None where the facing
        held names another block.

        A facing is a run across one block, so a value about a block the train
        is not in says nothing about what it would do here and is refused
        rather than read as propelled (#296). Asked by the `move`, whose sign
        is composed out of the end it departs through, and **not** by the
        throttle, whose sign is the lever's own: a facing lags the train it is
        about, being published by another app on another topic, and a lever
        that went dead for as long as the lag lasted would be a person pulling
        back to stop and not being heard."""
        facing = self._points(train)
        return facing if facing is not None and block_of(facing) == block else None

    def _traction_write(self, addr: str, speed: float) -> None:
        """One decoder told how fast and which way to run, on the row that
        answers for its address. The address is **bare**, unlike a point's: a
        decoder answers to the number it was programmed with whoever sends the
        packet (ADR-0043)."""
        self._bus.publish(
            device_topic(WANTED_TRACTION, addr), {"addr": addr, "speed": speed}
        )

    # -- who drives, and a person's throttle ---------------------------------

    def _on_mode_wanted(self, topic: str, payload: Payload) -> None:
        """A person took a train in a throttle, or gave it back (#207).

        The gesture states where the mode is to **stand** rather than asking
        for a change, so a second `manual` on a train already taken is not a
        race and changes nothing. `train: null` names every train at once,
        which is a thing a person does to a railroad rather than to the train
        they have picked: every train this app holds becomes manual, or the map
        empties, `automatic` being the resting value.

        The map is published before a wheel is written, and the two writes go
        out in that order for a reason: `state/mode` is what says whose the
        throttle is, and the speed that follows is this app taking a train back
        rather than driving one it does not have.

        Nothing else moves the mode. A train lifted off the layout keeps whoever
        was driving it, because a hand putting it down again is not a gesture
        about who drives, and the throttle's own refusals are where a train
        this app no longer holds is dealt with.
        """
        wanted = wanted_mode(payload)
        if wanted is None:
            return
        after = self._modes(wanted)
        if after == self._mode:
            return
        taken = [train for train in after if self._mode.get(train) != MANUAL]
        given = [train for train in self._mode if after.get(train) != MANUAL]
        self._mode = after
        self._bus.publish(MODE, {"modes": dict(after)})
        for train in taken:
            self._took(train)
        for train in given:
            self._gave(train)

    def _modes(self, wanted: Mode) -> dict[str, str]:
        """The whole map as this gesture leaves it. Only the manual trains are
        in it: a train the map does not name is automatic, so giving one back
        is dropping it and handing the railroad over is naming every train it
        holds — which is every train it has a position for, since a train that
        stands nowhere is one nobody is driving."""
        if wanted.train is None:
            return (
                dict.fromkeys(self._position, MANUAL) if wanted.mode == MANUAL else {}
            )
        after = dict(self._mode)
        if wanted.mode == MANUAL:
            after[wanted.train] = MANUAL
        else:
            after.pop(wanted.train, None)
        return after

    def _took(self, train: str) -> None:
        """A train taken over: **nothing is written**. It keeps whatever speed
        it had, and the person's first movement of the lever is what changes
        it — writing zero on take-over would stop a running train the instant
        somebody selected it, which is not what selecting it means (#207).

        What does change is the arrival: a crossing this app was driving stops
        being its to stop, so the `0.0` it was going to write when the train
        got there does not go out. A person stops their own train, and the
        signal at the far end is what tells them to.
        """
        flight = self._flight(train)
        if flight is None:
            return
        block, crossing = flight
        self._crossing[block] = replace(crossing, driving=False)

    def _gave(self, train: str) -> None:
        """A train handed back: it is given the speed its current grant
        implies, which is `0.0` where there is none. A train handed back
        mid-transit does not keep the speed a person left on it, and one
        standing does not keep it either.

        There is no grant to imply a speed in three cases and they all write
        `0.0`: no move of this train's is in flight, one is but this app could
        not sign it, and the rails are dead. The last is the third command rule
        arriving here — a grant cannot be acted on over dead track at all, so
        it implies nothing, and a desired speed left standing on a row is a
        train that would start the moment the power came back.

        A train with no addressed car has nothing written either way, which is
        `_addressed` and not a case here.
        """
        flight = self._flight(train)
        if flight is not None and self._power == ON and flight[1].implied:
            block, crossing = flight
            self._crossing[block] = replace(crossing, driving=True)
            for addr, speed in crossing.implied:
                self._traction_write(addr, speed)
            return
        for addr, _orientation in self._addressed(train):
            self._traction_write(addr, 0.0)

    def _flight(self, train: str) -> tuple[str, _Crossing] | None:
        """The move this train is in the middle of — the block it is crossing
        into and the record of it — or None where it is in the middle of none.

        The **last** match and not the first: a crossing lives until the block
        behind reports the tail clear, so a train that has arrived in Y and
        been granted Y to Z has two, and the one that is still going anywhere
        is the later. A train arriving empties its own crossing of the speed it
        implied, so the older one has nothing left to say in any case.
        """
        found: tuple[str, _Crossing] | None = None
        for block, crossing in self._crossing.items():
            if crossing.train == train:
                found = (block, crossing)
        return found

    def _on_throttle_wanted(self, topic: str, payload: Payload) -> None:
        """A person turned a lever, which reaches a locomotive by the same road
        a grant does: one signed speed per addressed car, composed the way a
        `move`'s is (#297).

        The lever is signed for the **train** — positive nose-first — so the
        sign is the composition's `nose_first` outright, and what the facing is
        for here is not the number but the refusal beside it. A person pushes
        forward and the train moves nose-first, whichever way round the
        locomotives are wired and however many of them there are.

        Four things drop a gesture, and none of them is an error to answer:

        A train that is **not manual** is not a person's to drive. The grant
        is what moves an automatic train, and a lever a nobody is holding does
        not get to overtake it.

        **Dead rails refuse a person's hand** as they refuse a grant
        (ADR-0041). Nothing is written rather than a zero: the row already
        holds whatever the last move left, and a gesture that could not be
        acted on has said nothing about it.

        A train this app **does not hold** — one standing nowhere it knows of
        — and one with **no facing** are the `move`'s two refusals, arriving
        here for the `move`'s reason: this app will not drive a train the rest
        of the system is not holding the geometry of (#296). Which block the
        facing names is not asked, and `_faces` says why.
        """
        turned = wanted_throttle(payload)
        if turned is None:
            return
        if self._mode.get(turned.train) != MANUAL or self._power != ON:
            return
        if turned.train not in self._position or self._points(turned.train) is None:
            return
        wheels = _composed(
            self._addressed(turned.train), turned.speed >= 0.0, abs(turned.speed)
        )
        for addr, speed in wheels:
            self._traction_write(addr, speed)

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

    # -- which way each train points ----------------------------------------

    def _on_facing(self, topic: str, payload: Payload) -> None:
        """Which way each train points, as the scheduler holds it: the run
        each would make across its block (ADR-0019).

        Read here because the sign of a speed cannot be composed without it
        and there is nowhere else it lives — `train_placed` carries a train
        and a block, and nothing under the interface knows which way round a
        train stands (ADR-0045). It is a **retained** state topic, so the last
        value is there to be handed over on subscribing even with the
        scheduler down, and stamp-guarded like every other state topic this
        app takes (#240).

        The value is the whole map and is adopted as one: a state topic's last
        value is what facing *is*, so a train missing from a value that reads
        has no facing here and its next move is dropped, which is the safe
        direction. A value that cannot be read at all is no value: the map
        already held stands, since forgetting every train's facing on one bad
        frame would stop the railroad on a payload.
        """
        if not self._ordering.accepts(topic, payload):
            return
        held = kept_facing(payload)
        if held is None:
            return
        self._facing = held

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

        Three things come of it. A **block** reads occupied while either of
        its ends does, and a change in that fold is the block's own occupancy
        event — the block a hand put a locomotive on, as much as the block a
        train was granted, since a level no move explains is still a level and
        judging it is the dispatcher's (ADR-0048). Bar an end a departure has
        already spent: that level is the train that left, and `_release` has
        said so once already (#311).

        Where the block is one a train is crossing into, the first of its ends
        to read occupied is the **arrival**, and every car that move commanded
        is told to stand (#296).

        And its **second** sensor going occupied says the train is fully in,
        so the block behind is clear. That is the one event no detector could
        produce: occupancy is anonymous and the block behind is named by the
        move this app carried out. The entered block's own event has already
        gone out on its first sensor, so the order is occupied then vacated —
        the only order the steel can produce (ADR-0047).
        """
        self._level[end] = level
        # This end has just said something of its own, so whatever a departure
        # spent of it is spent no longer.
        self._spent.discard(end)
        block = block_of(end)
        occupied = any(
            self._level.get(watched) == OCCUPIED and watched not in self._spent
            for watched in (end, opposite_end(end))
        )
        if self._occupied.get(block) != occupied:
            self._occupied[block] = occupied
            if occupied:
                # A block this app has just said is occupied is a block whose
                # ends both count again: whatever departure spent them, a new
                # train standing here ends its account (#331).
                self._spent -= {end, opposite_end(end)}
            self._bus.publish(
                BLOCK_OCCUPIED if occupied else BLOCK_VACATED, {"block": block}
            )
        crossing = self._crossing.get(block)
        if crossing is None or level != OCCUPIED:
            return
        if crossing.implied:
            # The arrival: the train is in the block it was sent to, so every
            # car this move commanded is told to stand. It does not wait for
            # the vacate — the tail clearing is a fact about the block behind
            # — and it happens on the first end of this block to settle
            # occupied, which is the end the train comes in at unless a
            # reading arrived out of order. A **manual** train is stopped by
            # the person driving it and gets no zero here (#297); either way
            # the grant implies nothing more once the train is there, so what
            # it implied goes with the arrival.
            if crossing.driving:
                for addr, _speed in crossing.implied:
                    self._traction_write(addr, 0.0)
            crossing = replace(crossing, implied=())
            self._crossing[block] = crossing
        if end == crossing.far:
            del self._crossing[block]
            self._release(crossing.origin)

    def _release(self, block: str) -> None:
        """The block a train has just left, said once however the two routes
        to it fall (#311).

        The same departure reaches this app twice: as the move it carried out,
        which is what names the block behind, and as that block's own
        detectors going clear a moment later. Both are the tail leaving, and
        the two orders are a race — the train is out of the block behind at
        the instant it is fully into the block ahead — so neither can be the
        one that always arrives first.

        So one writer per fact. `self._occupied` is the record of what this
        app has said about each block, and this rule reads it before it writes
        it: nothing goes out for a block already released. The ends this
        release **spends** are the ends of this block reading occupied at the
        moment it runs — the train that left — so the fold does not read them
        as a train still standing there and publish it back again.

        They count again as soon as the departure they belong to is over: when
        that end settles a level of its own, and when this block is published
        occupied again, which un-spends both of its ends because a new train
        standing here ends the old departure's account (#331). Otherwise an
        end that was spent and never changes again — a stranded car, a
        detector stuck occupied — would be out of the fold for good, and a
        level no move explains is still a level (ADR-0048).

        The record is set to clear rather than dropped, and the levels go on
        standing as the detectors reported them: a block that reads occupied
        again is an ordinary change in the fold, wherever it comes from.
        """
        for end in (f"{block}.A", f"{block}.B"):
            if self._level.get(end) == OCCUPIED:
                self._spent.add(end)
        if self._occupied.get(block) is False:
            return
        self._occupied[block] = False
        self._bus.publish(BLOCK_VACATED, {"block": block})

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
