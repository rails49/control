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

**Everything the bus hands it is read and never trusted** (BUS.md, rule 4).
Thirteen topics from six publishers — the detectors joining them with the fold
(#288), the throttle's four gestures and the driving mode coming from where
a person's press already does (#297, ADR-0079, #849), and the moving row a
drain ends on (ADR-0078) — and the function rows it writes, read back
(below), none of which this app answers — it reports
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
reads `off` (ADR-0041). That is what makes a restart safe, and it has teeth on
every one of them now that the app comes up with the railroad off. A `move`
that arrives then is **kept**, not dropped: the dispatcher granted it, and
`on` resumes every granted move (ADR-0078, decision 6), so when `state/power`
next reads `on` each kept move is put back through all three rules, as a held
one is when its `align` lands. Through a drain the supply is on and a `move`
is acted on as it is while `on`: the train runs into the next block and stops
at its sensor, and the drain ends after it (#862).

**Power is one switch: `on`, `draining` or `off`** (ADR-0078). A
`power_wanted` is answered on arrival — there is no beat to quantise it
against, and an emergency stop that waits is not one (ADR-0051) — and the
rule is `lib.power.TrackPower`'s, the one the simulator keeps. `on` writes
`wanted/track: on`; `off` is the emergency stop, the traction rows zeroed and
`wanted/track: off` written at once whatever is moving; `draining`, from `on`
only, keeps the supply on while each moving train stops, and becomes that
same `off` the moment `tc49/dispatch/state/moving` reads false. `on` during a
drain ends it. The supply going is the one thing this app does without a
press of its own, and only at the end of a drain a person or the dispatcher
asked for.

**What `state/power` reads is observed from below, bar two words.** `on` and
`off` are folded from what the hardware reports: `_folded` is the rule. It
cannot verify that the supply really went and does not try; it is the system
designer's job to put a device there that does (#232). `draining` is held
from the press until the drain ends, no hardware being able to report one
(ADR-0063), and a cut reads `off` from the moment it is applied until the next
`on`, the supply still reporting live for as long as it takes to go dark.

**`on` resumes.** A train left between blocks by a cut has a move outstanding
and nothing turning its wheels, the cut having zeroed them, so the press that
brings the power back gives each one this app drives the speed its grant
implies and it finishes its move (ADR-0078, decision 6).

**On startup the railroad is off, and at rest.** The app comes up having
written `wanted/track: off` and `state/power: off`, so nothing moves and no
turnout throws until a person turns it on, normally from the panel. It never
writes `off` of its own accord thereafter: it writes the word it was told to
write, and the `off` a drain it was asked for ends in. It also comes up having written `0.0` over every retained
`wanted/traction` row it finds, so a speed the last run left on the broker is
not sent to a station at the first connect and the locomotive does not roll on
the power-on (ADR-0054). `wanted/point` replays instead: a point has
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

**Who drives.** The railroad has one driving mode, `manual` or `automatic`,
and at most one throttle holds a train (ADR-0079). `driving_wanted` moves the
mode and `state/driving` says where it stands, `manual` from the start;
`take_wanted` and `throttle_alive` move who holds which train, and
`state/taken` says it. Neither changes the route: a train is granted moves,
gets its points thrown and its near end checked whoever drives. What they
decide is who writes the wheels: the throttle holding a train, in either mode
and at any time, granted move or not (ADR-0081); within a granted move, this
app in `automatic` for a train no throttle holds; and nobody for a train no
throttle holds in `manual`, which stands at its signal. The move ending at its
sensor writes `0.0` whoever drives, and a lever reversing a running train
writes `0.0` until its throttle sends `0` (ADR-0084). A throttle this app has
not heard for `THROTTLE_SILENCE_S` by default, an installation setting its
own (docs/DEPLOY.md), lets go of its trains. A train let go of stops in
`manual`; in `automatic` mid-move it keeps the speed the person left until its
move ends, or is given its grant's speed if it stands (ADR-0083), and with no
move outstanding it is written `0.0`.

**A train's functions.** A throttle switches one by the name the catalogue
gives it, on `function_wanted`, and the press is the holding throttle's
alone, at any power and in either driving mode. It reaches the first car in
the train's order that has an address and declares the name, on that car's
first number for it, whichever way the train runs: one `wanted/function` row,
and nothing else ever writes one — a release, a silent throttle,
`train_removed`, a cut and a restart leave them standing. `state/functions`
says which of each train's functions are on, read off those rows: this app's
own writes and the ones a bus that outlived it hands back, so a light a
decoder still has on shows on after a restart (#849).

The simulator is untouched and remains the second binding of the same
interface (ADR-0030).
"""

import logging
from dataclasses import dataclass, replace

from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import (
    AUTOMATIC,
    DRAINING,
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
    end_letter,
    facing_ends,
    opposite_end,
    transit_ends,
)
from tc49.lib.loading import BUILT
from tc49.lib.payload import (
    Command,
    Ordering,
    alignment,
    alive_throttle,
    command,
    desired_function,
    detected,
    kept_allocation,
    kept_facing,
    link_up,
    named_train,
    placement,
    reported_reason,
    shown_aspects,
    supply,
    wanted_driving,
    wanted_function,
    wanted_take,
    wanted_throttle,
)
from tc49.lib.power import TrackPower
from tc49.lib.roster import FORWARD, Roster

_log = logging.getLogger(__name__)

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
POWER_WANTED = "tc49/layout/power_wanted"
DRIVING_WANTED = "tc49/layout/driving_wanted"
TAKE_WANTED = "tc49/layout/take_wanted"
THROTTLE_ALIVE = "tc49/layout/throttle_alive"
THROTTLE_WANTED = "tc49/layout/throttle_wanted"
FUNCTION_WANTED = "tc49/layout/function_wanted"
PLACED = "tc49/dispatch/train_placed"
REMOVED = "tc49/dispatch/train_removed"
ASPECTS = "tc49/dispatch/state/aspects"
MOVING = "tc49/dispatch/state/moving"
ALLOCATION = "tc49/dispatch/state/allocation"
FACING = "tc49/schedule/state/facing"
DEVICE = "tc49/layout/state/device/#"

RAILROAD = "tc49/layout/state/railroad"
ALIVE_CONFIRMED = "tc49/layout/alive_confirmed"
BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"
POWER = "tc49/layout/state/power"
DRIVING = "tc49/layout/state/driving"
TAKEN = "tc49/layout/state/taken"
FUNCTIONS = "tc49/layout/state/functions"
WANTED_TRACTION = "tc49/layout/state/wanted/traction"
WANTED_FUNCTION = "tc49/layout/state/wanted/function"
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

THROTTLE_SILENCE_S = 5.0
"""How long a throttle holding a train may go unheard before this app lets go
of its trains, in seconds of the run clock, by default: an installation sets
its own (`TC49_LAYOUT_THROTTLE_SILENCE`, docs/DEPLOY.md), and the default of
the constructor argument that carries it. A throttle says `throttle_alive`
once a second, so this is five of them missed: a phone gone to sleep, a page
closed, a network gone (ADR-0079)."""


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
    grant implies, which is what a train is given when this app takes up its
    driving mid-transit: released standing in `automatic`, the railroad
    switched to `automatic` under it, or `on` after a cut. `heading` is the
    same speed signed for the train, nose-first positive, before it is
    composed onto the cars: what a lever reversing the train is compared
    against (ADR-0084).

    `outstanding` is whether the move is still going anywhere. It goes false
    on the arrival, which is the first level the entered block settles
    occupied: the train is in the block it was sent to and the tail clearing
    is a fact about the block behind, so nothing here waits for the vacate
    (#296). A throttle's lever is applied either way (ADR-0081).

    `driving` is whether the wheels are this app's for the length of this
    crossing: true where it was granted in `automatic` to a train no throttle
    holds, and moved by a take, a release in `automatic` and a change of
    driving mode. The
    `0.0` at the arrival goes out where it is true or a throttle holds the
    train, since a car nothing was sent for is a car nothing may be sent for.
    """

    origin: str
    far: str
    train: str
    implied: tuple[tuple[str, float], ...] = ()
    heading: float = 0.0
    driving: bool = True
    outstanding: bool = True


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
        throttle_silence_s: float = THROTTLE_SILENCE_S,
        position: dict[str, str] | None = None,
        built: bool = True,
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

        `throttle_silence_s`: how long a throttle holding a train may go
        unheard before this app lets go of its trains, `THROTTLE_SILENCE_S`
        by default. Injected because how soon a phone sleeps is a fact about
        an installation and not about this app, which `__main__` reads off
        the environment (docs/DEPLOY.md).

        `position`: where each train stands as this app comes up, train to
        block. None from a process starting, which knows of no train until
        the dispatcher places one; the last build's, less any train whose
        block this drawing lacks, from a rebuild under the same railroad name
        (ADR-0071).

        `built`: whether `layout` is what the railroad's drawing derives to,
        said on `tc49/layout/state/railroad`. False where the drawing is not a
        valid drawing and `layout` is nothing under its name: the railroad
        stays named, nothing is built from it, and this app still answers the
        power (ADR-0085, decision 4).
        """
        self._bus = bus
        self._layout = layout
        self._roster = roster
        self._clock = clock
        self._settling_s = settling_s
        self._throttle_silence_s = throttle_silence_s
        # Where each train stands, which is the whole of the near-end check,
        # and which way each one points, which is half of the traction write's
        # sign. The one is this app's own record and the other is read off the
        # scheduler's state topic, there being nowhere else facing lives.
        # `train_placed` is an event, so a restarted app takes where each train
        # stands from the dispatcher's retained allocation, which is what the
        # dispatcher restores from too (#960).
        self._position: dict[str, str] = dict(position or {})
        kept = kept_allocation(bus.last_values.get(ALLOCATION))
        for train, block in (kept.trains if kept is not None else {}).items():
            if block in layout.blocks:
                self._position.setdefault(train, block)
        self._facing: dict[str, str] = {}
        # Who drives (ADR-0079): the railroad's one driving mode, which throttle
        # holds each train — what `state/taken` carries — and when each
        # throttle was last heard, on the run clock.
        self._driving = MANUAL
        self._taken: dict[str, str] = {}
        self._heard: dict[str, float] = {}
        # The last speed written on each address, zeros at startup and at a
        # cut included, which is what says whether a train released mid-move
        # is running (ADR-0083); and the last nonzero speed written for each
        # train, signed for the train, which is what a lever reversing it is
        # held against until its throttle sends `0` (ADR-0084).
        self._wrote: dict[str, float] = {}
        self._heading: dict[str, float] = {}
        # The bit on each `wanted/function` row this app knows of, by address
        # and function number: its own writes and the rows a bus that
        # outlived it hands back, which is what `state/functions` is made of.
        self._lit: dict[tuple[str, str], bool] = {}
        # The crossings an `align` has authorised, one entry per transit and
        # each spent by the move that takes it, and the moves waiting on one.
        self._aligned: set[str] = set()
        self._held: dict[str, Command] = {}
        # The moves granted while the rails are dead, one per transit, each
        # put back through the rules when `state/power` next reads `on`.
        self._kept: dict[str, Command] = {}
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
        # How a power press is answered, the rule both bindings keep: the
        # word applied, and the moving row a drain ends on (ADR-0078).
        self._track_power = TrackPower()
        # The two halves of the power fold, and what was last said about it.
        # A link is held under the id its publisher calls itself, which is
        # the topic's and nothing this app holds a list of: an id is learned
        # by being heard and never waited for (ADR-0058, ADR-0059).
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
        # The commands and the gestures, subscribed **before** a word is
        # published. A publish is asynchronous where a subscribe waits to be
        # acknowledged, so an app that published first would be deaf for as
        # long as its own subscriptions took to land — and what would be lost
        # in that gap is an event, which nothing hands over a second time: a
        # person's press on the power, a drag, a grant. The three state rows
        # this app reads are not here for the opposite reason: a retained
        # value is handed over whenever the subscription lands, so when it
        # lands does not matter, and the device rows below want to land
        # *after* the supply this app states (ADR-0059, decision 5).
        bus.subscribe(ALIGN, self._on_align)
        bus.subscribe(MOVE, self._on_move)
        bus.subscribe(POWER_WANTED, self._on_power_wanted)
        bus.subscribe(DRIVING_WANTED, self._on_driving_wanted)
        bus.subscribe(TAKE_WANTED, self._on_take_wanted)
        bus.subscribe(THROTTLE_ALIVE, self._on_throttle_alive)
        bus.subscribe(THROTTLE_WANTED, self._on_throttle_wanted)
        bus.subscribe(FUNCTION_WANTED, self._on_function_wanted)
        bus.subscribe(PLACED, self._on_placed)
        bus.subscribe(REMOVED, self._on_removed)
        # Which railroad this is, said before anything is said about it. One
        # broker runs one railroad and a view needs to know which, so the
        # binding of the layout interface that is running publishes it — it
        # is the one app bound to a railroad (ADR-0059 decision 2, as amended
        # by ADR-0060). The name is the layout's own, which is the name the
        # store lists it under: a drawing is filed under the name it declares
        # and derives to a layout wearing it, so there is no second place for
        # this to be told and no way for the two to disagree. Whether
        # anything was built from it rides along (ADR-0085, decision 4).
        bus.publish(RAILROAD, {"name": layout.name, BUILT: built})
        # The railroad comes up dark, and this is the first thing said about
        # its supply: a person turns it on (ADR-0051). Before the **device**
        # subscription, so that a retained value handed back by a bus that
        # outlived the app supersedes it rather than being overwritten by it —
        # what the hardware is saying now outranks what the last session was
        # left believing (ADR-0030).
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
        self._traction_rest()
        # And the railroad is `manual` with no train in a throttle, said
        # rather than left for a client to read out of an absence (ADR-0032).
        # Neither row is subscribed to, and a value left there by a previous
        # session is superseded rather than adopted: a throttle is a person's
        # hand, and a restart is not a hand (ADR-0079).
        bus.publish(DRIVING, {"driving": MANUAL})
        bus.publish(TAKEN, {"taken": {}})
        # No function is known to be on until a row says so. The rows are
        # read back rather than zeroed, unlike traction: a light left on is
        # no train rolling, and a row handed back is what the decoder was
        # last told, so it is what `state/functions` says (#849).
        bus.publish(FUNCTIONS, {"functions": {}})
        bus.subscribe(ASPECTS, self._on_aspects)
        bus.subscribe(MOVING, self._on_moving)
        bus.subscribe(FACING, self._on_facing)
        bus.subscribe(DEVICE, self._on_device)
        bus.subscribe(WANTED_FUNCTION + "/#", self._on_function_row)

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
        clock (ADR-0009). It is called by whoever owns the loop — this app's
        own process (`__main__`), which advances the clock to wall time and
        calls this once a turn, or the suite, driving the clock rather than
        sleeping on it. Levels are applied in the order they
        came due so that two ends settling in one call publish in the order the
        steel produced them.

        Nothing schedules the call: a detector publishes a level change and
        nothing else, so a level that goes occupied and stays occupied has no
        second frame to be noticed on, and an app that only settled when the
        next reading arrived would sit on a quiet railroad holding an arrival
        nobody was told about.

        The same turn lets go of the trains of every throttle silent for
        `throttle_silence_s`, which is the other thing here measured against
        the clock and for the same reason: a throttle that has gone says
        nothing more to be noticed on (ADR-0079).
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
        self._let_go_of_silent()

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

        An `align` naming no transit is a throw by hand the dispatcher let
        through (ADR-0068): its points are written like any other's, and it
        authorises no crossing, so no waiting `move` is let through. Nothing
        else is checked — no lock, no power, no run state — because this app
        holds none of what a check would need, and with the rails dead the
        row is stored for when they come back (ADR-0054).
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
        transit = aligning.transit_id
        if transit is None:
            return
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
        its `align` lands, and a kept one when `state/power` next reads `on`,
        since the railroad may have moved under it while it waited.

        Dead rails **keep** the command rather than act on it or drop it
        (#862). The dispatcher granted it before reading the `off`, so it
        holds the train in a crossing no sensor will end unless the move is
        carried out, and `on` resumes every granted move (ADR-0078, decision
        6). It is kept before the near-end check, which is applied when it is
        acted on: a train taken off or placed elsewhere meanwhile fails it
        then and the move is dropped. A second `move` for the same transit
        replaces the one kept, as it does the one held. `draining` is not
        dead: the supply is on, and the move runs to its sensor before the
        drain ends.

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

        A move this app is not to drive runs the whole of this and writes
        nothing: one for a train a throttle holds, whose speed is the
        person's, and one in `manual` for a train no throttle holds, which
        stands at its signal until a throttle takes it (ADR-0079). The refusal
        above has nothing to refuse there. The points still throw, the near
        end is still checked and the crossing is still recorded, because those
        are the route and not the driving (#297). What the move was worth is
        kept all the same: it is what the train is given if this app takes up
        its driving before it arrives.

        The crossing is what the fold needs and nothing above the interface
        could supply: no detector names the block a train is leaving, so the
        move that was carried out is the only thing that knows it (#288).
        """
        transit = commanded.transit_id
        ends = transit_ends(self._layout, commanded.into, transit)
        if ends is None:
            return
        entered, near = ends
        if self._power == OFF:
            self._kept[transit] = commanded
            return
        if self._position.get(commanded.train) != block_of(near):
            return
        if transit not in self._aligned:
            self._held[transit] = commanded
            return
        driving = self._drives(commanded.train)
        traction = self._traction(commanded, near)
        if traction is None:
            if driving:
                return
            # A move this app is not driving runs its course whatever it could
            # have made of the sign: nothing is being written, so there is no
            # wrong way to drive it and no refusal to make (#297).
            traction = (0.0, ())
        heading, wheels = traction
        # The authorisation is spent here, with the act it authorised: an
        # `align` stands for one crossing, so the next move over this transit
        # waits for one of its own (#305).
        self._aligned.discard(transit)
        self._position[commanded.train] = commanded.into
        crossing = _Crossing(
            origin=block_of(near),
            far=opposite_end(entered),
            train=commanded.train,
            implied=wheels,
            heading=heading,
            driving=driving,
        )
        self._crossing[commanded.into] = crossing
        if driving:
            self._give(commanded.into, crossing)

    # -- the traction write -------------------------------------------------

    def _traction(
        self, commanded: Command, near: str
    ) -> tuple[float, tuple[tuple[str, float], ...]] | None:
        """What this move is worth on each of the train's decoders: one signed
        speed per addressed car, `()` where the train has none, and None where
        the move is to be dropped for want of the facts to sign it (#296).
        Beside it, the same speed signed for the train, nose-first positive,
        which is the lever's sign and `0.0` where nothing is written.

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
        (GLOSSARY.md, **Facing**). The second is the car's `orientation`, the
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
        nothing here holds it (BUS.md, rule 4). A move that states no
        **speed** falls the same way and for the same reason: this app would
        have to choose a number nobody asked for.
        """
        addressed = self._addressed(commanded.train)
        if not addressed:
            return 0.0, ()
        facing = self._faces(commanded.train, block_of(near))
        if facing is None or commanded.speed is None:
            return None
        nose_first = facing_ends(facing)[1] == near
        magnitude = abs(commanded.speed)
        return (
            magnitude if nose_first else -magnitude,
            _composed(addressed, nose_first, magnitude),
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
        packet (ADR-0043). Held as the last speed written on it."""
        self._wrote[addr] = speed
        self._bus.publish(
            device_topic(WANTED_TRACTION, addr), {"addr": addr, "speed": speed}
        )

    def _headed(self, train: str, heading: float) -> None:
        """A speed written for the train, signed for the train: held as the
        last nonzero one, which a lever of the other sign is refused against
        (ADR-0084). A zero leaves the one held standing, as a stop by anything
        but the throttle's own `0` does."""
        if heading != 0.0:
            self._heading[train] = heading

    def _give(self, block: str, crossing: _Crossing) -> None:
        """The train crossing into `block` given the speed its grant implies,
        with its crossing this app's to drive from here to the arrival."""
        self._crossing[block] = replace(crossing, driving=True)
        if crossing.implied:
            self._headed(crossing.train, crossing.heading)
        for addr, speed in crossing.implied:
            self._traction_write(addr, speed)

    def _traction_rest(self) -> None:
        """Zero over every retained `wanted/traction` row the bus holds: the
        railroad at rest, which this app writes when it comes up and again
        when a cut is applied (ADR-0054, #435).

        Every row and not the ones this app has commanded: a row a session
        that is gone left behind, or one a person's throttle wrote, is
        exactly the one nothing else can reach, and a translator standing
        down zeroes only the addresses it sent to itself. Whose the row is
        goes unasked either way — a cut takes the whole supply.

        `wanted/point` is left to replay on purpose. Traction has a resting
        value and a point has none — there is no neutral position to write
        into the row — so the retained belief about where the last session
        left the blades is the only answer short of throwing every point.
        """
        for topic in self._bus.last_values:
            split = split_device(topic)
            if split is not None and split[0] == WANTED_TRACTION:
                self._traction_write(split[1], 0.0)

    # -- who drives, and a person's throttle ---------------------------------

    def _drives(self, train: str) -> bool:
        """Whether a grant to this train is this app's to drive: in
        `automatic`, and no throttle holds it (ADR-0079)."""
        return self._driving == AUTOMATIC and train not in self._taken

    def _on_driving_wanted(self, topic: str, payload: Payload) -> None:
        """A person switched the railroad's driving mode (ADR-0079).

        Accepted at any power, and stated on `state/driving` before a wheel is
        written. The dispatcher routes the same in both, so the switch reaches
        only the trains with a move outstanding that no throttle holds.

        **To `manual`**, nothing is written. A train this app is driving
        finishes its move, the arrival writing its `0.0` as it would have, and
        its next grant is nobody's until a throttle takes it: stopping it
        between two blocks would strand it where no sensor says it stopped.

        **To `automatic`**, each of them is given the speed its grant implies,
        as a train released standing in `automatic` is. Not over dead rails,
        where a grant implies nothing (`_take_up`).
        """
        wanted = wanted_driving(payload)
        if wanted is None or wanted == self._driving:
            return
        self._driving = wanted
        self._bus.publish(DRIVING, {"driving": wanted})
        if wanted != AUTOMATIC:
            return
        for train in {crossing.train for crossing in self._crossing.values()}:
            if train not in self._taken and self._outstanding(train) is not None:
                self._take_up(train)

    def _on_take_wanted(self, topic: str, payload: Payload) -> None:
        """A throttle took a train, or the train was released (ADR-0079).

        **At most one throttle holds a train.** A take of a train no throttle
        holds is applied, and one of a train another throttle holds is
        dropped to the trace: the second person asks the first. A take by the
        throttle already holding it changes nothing and counts as hearing
        from it.

        **Taking writes nothing.** The train keeps whatever speed it had and
        the person's first movement of the lever changes it: writing zero
        would stop a running train the instant somebody selected it (#207).
        What changes is the arrival's `0.0`, which is now written for the
        throttle rather than for this app.

        `throttle: null` releases the train whoever holds it, which is the
        force release a panel makes (`_let_go`).
        """
        wanted = wanted_take(payload)
        if wanted is None:
            return
        if wanted.throttle is None:
            self._let_go(wanted.train)
            return
        holder = self._taken.get(wanted.train)
        if holder is not None and holder != wanted.throttle:
            _log.info(
                "take of %s by %s dropped, %s holds it",
                wanted.train,
                wanted.throttle,
                holder,
            )
            return
        self._heard[wanted.throttle] = self._clock.now
        if holder is not None:
            return
        self._taken[wanted.train] = wanted.throttle
        self._publish_taken()
        flight = self._outstanding(wanted.train)
        if flight is not None:
            block, crossing = flight
            self._crossing[block] = replace(crossing, driving=False)

    def _on_throttle_alive(self, topic: str, payload: Payload) -> None:
        """A throttle saying it is still there, once a second while it holds a
        train. What it buys is `throttle_silence_s` more before this app lets
        go of its trains."""
        throttle = alive_throttle(payload)
        if throttle is None or throttle not in self._taken.values():
            return
        self._heard[throttle] = self._clock.now

    def _let_go_of_silent(self) -> None:
        """Release every train of each throttle not heard for
        `throttle_silence_s`, as `take_wanted` with `null` would: a phone gone
        to sleep does not leave its train running at its last speed
        (ADR-0079)."""
        holding = set(self._taken.values())
        self._heard = {
            throttle: at for throttle, at in self._heard.items() if throttle in holding
        }
        silent = {
            throttle
            for throttle, at in self._heard.items()
            if self._clock.now - at >= self._throttle_silence_s
        }
        for train, throttle in list(self._taken.items()):
            if throttle in silent:
                _log.info("%s released, %s went silent", train, throttle)
                self._let_go(train)

    def _let_go(self, train: str) -> None:
        """A train no throttle holds any longer, stated on `state/taken`
        before a wheel is written. A train no throttle held changes nothing
        and writes nothing.

        **In `manual`** it stops: `0.0` to each addressed car (ADR-0081,
        decision 5).

        **In `automatic`, mid-move over live rails**, `on` or `draining`, it
        keeps the speed the person left and nothing is written: a train a
        person was running slowly does not lurch to the driver's speed
        (ADR-0081, decision 6). The crossing becomes this app's, so the
        arrival writes its `0.0`, a switch to `manual` lets it finish, and an
        `on` after a cut gives it its grant's speed (`_resume`). Bar a train
        **standing**, whose last speed written is `0.0` on every car or none
        at all, the zeros at startup and at a cut counting: it would hold its
        route and never reach its sensor, so it is given its grant's speed
        (ADR-0083, `_take_up`).

        **In `automatic` otherwise**, with no move outstanding or over dead
        rails, `_take_up` writes `0.0`.
        """
        if self._taken.pop(train, None) is None:
            return
        self._publish_taken()
        if self._driving != AUTOMATIC:
            for addr, _orientation in self._addressed(train):
                self._traction_write(addr, 0.0)
            return
        flight = self._outstanding(train)
        if flight is not None and self._power != OFF and self._running(train):
            block, crossing = flight
            self._crossing[block] = replace(crossing, driving=True)
            return
        self._take_up(train)

    def _running(self, train: str) -> bool:
        """Whether the last speed written on any of the train's addressed
        cars is other than `0.0`. A car never written is standing: nothing
        this app said has moved it."""
        return any(
            self._wrote.get(addr, 0.0) != 0.0
            for addr, _orientation in self._addressed(train)
        )

    def _take_up(self, train: str) -> None:
        """This app taking up the driving of a train no throttle holds, in
        `automatic`: it is given the speed its outstanding grant implies,
        which is `0.0` where there is none. Reached by a train released
        standing (`_let_go`) and by the railroad switched to `automatic`
        under a train nobody was driving.

        There is no grant to imply a speed in three cases and they all write
        `0.0`: no move of this train's is outstanding, one is but this app
        could not sign it, and the rails are dead. The last is the third
        command rule arriving here — a grant cannot be acted on over dead
        track at all, so it implies nothing, and a desired speed left standing
        on a row is a train that would start the moment the power came back.
        A drain is not dead: the supply is on, and the move runs to its
        sensor before the drain ends.

        A train with no addressed car has nothing written either way, which is
        `_addressed` and not a case here.
        """
        flight = self._outstanding(train)
        if flight is not None and self._power != OFF and flight[1].implied:
            self._give(*flight)
            return
        for addr, _orientation in self._addressed(train):
            self._traction_write(addr, 0.0)

    def _publish_taken(self) -> None:
        self._bus.publish(TAKEN, {"taken": dict(self._taken)})

    def _outstanding(self, train: str) -> tuple[str, _Crossing] | None:
        """The move this train has outstanding — the block it is crossing
        into and the record of it — or None where it has none.

        The **last** crossing of the train's and not the first: a crossing
        lives until the block behind reports the tail clear, so a train that
        has arrived in Y and been granted Y to Z has two, and the one that is
        still going anywhere is the later. Once it has arrived the train has
        no move outstanding until its next grant.
        """
        found: tuple[str, _Crossing] | None = None
        for block, crossing in self._crossing.items():
            if crossing.train == train:
                found = (block, crossing)
        if found is None or not found[1].outstanding:
            return None
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

        **A throttle drives the train it holds at any time,** granted move or
        not, in either driving mode (ADR-0081, decision 1). A person backs a
        train up a few centimetres at a platform with no request made. Leaving
        the block is the person's to avoid: nothing here stops a held train at
        its block's ends, and one that leaves is a reading no move explains,
        which drains the railroad (ADR-0048). The end of a granted move still
        writes `0.0` (`_settled`), and the next frame drives the train on.

        Four things drop a gesture, and none of them is an error to answer:

        A frame that names **no throttle**, or a throttle that does **not
        hold** the train. The lever is that throttle's, in either driving
        mode, and nobody else's (ADR-0079).

        **Dead rails refuse a person's hand** as they refuse a grant
        (ADR-0041). Nothing is written rather than a zero: the row already
        holds whatever the last move left, and a gesture that could not be
        acted on has said nothing about it. A drain is not dead: the supply is
        on, and a person pulling back to stop is heard.

        A train with **no facing** is the `move`'s refusal, arriving here for
        the `move`'s reason: without it the lever's sign cannot be composed
        onto each car (#296). Which block the facing names is not asked, and
        `_faces` says why.

        A train that **stands nowhere**, never placed or taken off by
        `train_removed`: its decoder is in a hand, if anywhere. After a
        restart, a train the retained allocation names stands where it says
        (#960).

        **A lever reversing a running train stops it instead** (ADR-0084). A
        frame whose sign is opposite to the last nonzero speed written for the
        train — the lever's or a grant's, signed for the train — writes `0.0`
        to each car, and so does every later frame of that sign until the
        throttle sends `0`. How hard a decoder reverses is its make and its
        momentum, which the roster does not record, and behind a long train
        cars leave the rails.
        """
        turned = wanted_throttle(payload)
        if turned is None or turned.throttle is None:
            return
        train = turned.train
        if self._taken.get(train) != turned.throttle:
            return
        if self._power == OFF or train not in self._position:
            return
        if self._points(train) is None:
            return
        addressed = self._addressed(train)
        heading = self._heading.get(train)
        if turned.speed == 0.0:
            self._heading.pop(train, None)
        elif heading is not None and (turned.speed > 0.0) != (heading > 0.0):
            for addr, _orientation in addressed:
                self._traction_write(addr, 0.0)
            return
        self._headed(train, turned.speed)
        for addr, speed in _composed(addressed, turned.speed >= 0.0, abs(turned.speed)):
            self._traction_write(addr, speed)

    # -- a train's functions ------------------------------------------------

    def _on_function_wanted(self, topic: str, payload: Payload) -> None:
        """A person switched one of the train's functions, by the name the
        catalogue gives it (#849).

        The press is the holding throttle's and nobody else's, as the lever
        is (ADR-0079): a frame from another throttle, or naming none, is
        dropped. It is accepted at any power and in either driving mode — a
        light is not a wheel, and the row waits for the supply as any desired
        row does (ADR-0054).

        **The first addressed car declaring the name** is the one written,
        on that car's first number for it: `Train.functions` lists a name
        once, first car first, and a press reaches one decoder. Which way the
        train runs is not asked. A train the roster does not name, or a name
        no addressed car of it declares, is dropped with a log line: the
        throttle showed a button the roster cannot back.

        Nothing else writes a function row: a release, a silent throttle,
        `train_removed`, a cut and a restart leave them as they are.
        """
        switched = wanted_function(payload)
        if switched is None or self._taken.get(switched.train) != switched.throttle:
            return
        reached = self._reaches(switched.train, switched.function)
        if reached is None:
            _log.info(
                "%s of %s dropped, no addressed car declares it",
                switched.function,
                switched.train,
            )
            return
        addr, number = reached
        self._bus.publish(
            device_topic(WANTED_FUNCTION, addr, number),
            {"addr": addr, "function": number, "value": switched.on},
        )
        self._function_known(addr, number, switched.on)

    def _on_function_row(self, topic: str, payload: Payload) -> None:
        """A `wanted/function` row: this app's own write coming back, or one
        a bus that outlived it hands over at start. Read rather than trusted
        — a row that cannot be read is skipped — and stamp-guarded as every
        state row this app reads is (#240), so a light a decoder still has on
        shows on after a restart."""
        split = split_device(topic)
        if split is None or split[0] != WANTED_FUNCTION:
            return
        levels = split[1].split("/")
        value = desired_function(payload)
        if len(levels) != 2 or value is None:
            return
        if not self._ordering.accepts(topic, payload):
            return
        self._function_known(levels[0], levels[1], value)

    def _function_known(self, addr: str, number: str, value: bool) -> None:
        """A row's bit held, and `state/functions` said again where it moved."""
        if self._lit.get((addr, number)) == value:
            return
        self._lit[(addr, number)] = value
        self._bus.publish(FUNCTIONS, {"functions": self._functions()})

    def _reaches(self, train: str, name: str) -> tuple[str, str] | None:
        """The address and function number a press of `name` on `train`
        writes: the first car in the train's order that has an address and
        declares the name, on the first number it declares it on. None for a
        train the roster does not name and a name no addressed car declares."""
        made_up = self._roster.trains.get(train)
        for coupled in made_up.cars if made_up is not None else ():
            if coupled.car.addr is None:
                continue
            for number, function in coupled.car.functions.items():
                if function.name == name:
                    return coupled.car.addr, number
        return None

    def _functions(self) -> dict[str, dict[str, bool]]:
        """Which of each train's functions are on, by name: the bit on the
        row a press of that name writes. A train or name with no row known is
        absent, which reads off."""
        stated: dict[str, dict[str, bool]] = {}
        for train, made_up in self._roster.trains.items():
            for function in made_up.functions:
                reached = self._reaches(train, function.name)
                if reached is not None and reached in self._lit:
                    stated.setdefault(train, {})[function.name] = self._lit[reached]
        return stated

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

        It may come off running — a person lifts a train in any run state
        (ADR-0069) — and a decoder in a hand still holds the last speed it was
        told, so it would run the moment it is set down anywhere. Each
        addressed car is told `0.0`, manual or not and **whatever the power**:
        dead rails refuse a speed, not a stop, and a row left standing over
        them is a train that starts when the power comes back.

        Any move of the train's in flight is forgotten with it. The readings
        that crossing was waiting on are now about whatever the detectors see,
        which is not this train, so its arrival writes no speed for it and its
        tail releases nothing: the block behind reads clear on its own
        detectors, as any block does.
        """
        train = named_train(payload)
        if train is None:
            return
        self._position.pop(train, None)
        self._crossing = {
            block: crossing
            for block, crossing in self._crossing.items()
            if crossing.train != train
        }
        for addr, _orientation in self._addressed(train):
            self._traction_write(addr, 0.0)

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

    def _on_moving(self, topic: str, payload: Payload) -> None:
        """Whether the dispatcher says a train is moving: some train crossing
        (GLOSSARY.md, **Moving**).

        The one thing this app reads it for is the end of a drain: the supply
        goes the first moment it reads false, and not before, because a cut
        under a train in motion strands it where no sensor will ever say it
        stopped (ADR-0062, ADR-0078). Nothing else here branches on it — a
        `move` is acted on because it was granted.

        It is a **retained** state topic, so the last value is handed over on
        subscribing even with the dispatcher down, and stamp-guarded like
        every other state topic this app takes (#240): two values delivered
        backwards would end a drain on stale evidence. A value that cannot be
        read reads as a train moving, and so does no value at all, which
        leaves a drain running until a person presses `off`.
        """
        word = self._track_power.moving(topic, payload)
        if word is not None:
            self._apply(word)

    def _on_power_wanted(self, topic: str, payload: Payload) -> None:
        """A person asked the railroad for power, a drain, or the supply
        removed at once (ADR-0078), or the dispatcher asked for a drain on a
        fault. `lib.power.TrackPower` decides what is applied, the same rule
        the simulator keeps.

        A press that cannot be read is dropped rather than taken for `off`,
        which is the other direction from the reading of the same axis: `off`
        is a word this app writes only when it was told to, or at the end of a
        drain it was told to make. A `draining` from anything but `on` is
        dropped with it, to the trace with the reason (ADR-0034): there is
        nothing running to drain, and a drain from `off` would be one that
        turned the supply back on.
        """
        word = self._track_power.answer(payload, self._folded())
        if word is not None:
            self._apply(word)

    def _apply(self, word: str) -> None:
        """The word the rule settled on, applied to the device vocabulary.

        **`off` leaves the railroad at rest**, the traction rows zeroed the
        way they are at startup (#435, ADR-0054), whether it is a person's
        emergency stop or the end of a drain. "The railroad comes up at rest"
        is a promise about a **power off** and the `on` after it as well as
        about a process start: an arrival zeroes the row of a train this app
        drives and nothing zeroes the row of one a person holds in a
        throttle, so a cut would otherwise leave a speed standing and the
        next `on` would bring current back over it. The zeros go out
        **before** the word, and the order is load-bearing: a translator
        acts on desired rows as they arrive, so the last thing the station is
        told before the supply goes is a stop.

        **`draining` writes nothing to the hardware.** The supply stays on
        and only `state/power` moves: the dispatcher grants nothing new, and
        each moving train stops at the end of the move it was granted.

        **`on` resumes** what a cut left between blocks (`_resume`).
        """
        if word == OFF:
            self._traction_rest()
        if word != DRAINING:
            self._bus.publish(WANTED_TRACK, {"power": word})
        self._publish_power()
        if word == ON:
            self._resume()

    def _resume(self) -> None:
        """Every train with a move outstanding that this app drives — no
        throttle holds it, in `automatic` — given the speed its grant
        implies, so a train a cut left between blocks carries on to its
        sensor (ADR-0078, decision 6).

        Written on the press and not when the hardware reports the supply
        back: a translator holds the row and sends it once the rails are
        live, and a press that waited for the report would leave the train
        standing on a live railroad with its move outstanding. In `manual`
        nothing is written, the trains that carry on being the ones a
        throttle holds, whose speed the person sets (#825). A train still
        running when `on` ends a drain is written the speed it already has.
        """
        if self._driving != AUTOMATIC:
            return
        for train in {crossing.train for crossing in self._crossing.values()}:
            flight = self._outstanding(train)
            if train in self._taken or flight is None or not flight[1].implied:
                continue
            self._give(*flight)

    def _on_device(self, topic: str, payload: Payload) -> None:
        """What the hardware reports about itself. Three of the five rows are
        read: the supply, each publisher's link to the hardware it drives, and
        each detector's level at the block end it watches.

        Two pass by unread rather than being taken for something else. A
        `device/point` is a position where hardware reports one, and this app
        acts on none. A `device/refused` is the publisher's report that the
        hardware refused a command or could not parse it, keyed by whatever
        that publisher calls itself: it is for a UI, for a person to read, and
        nothing here branches on it — a refusal that is published happened,
        and one that is not published is no evidence that none occurred
        (ADR-0063). The row and the address come from the **topic**, which is
        where a device topic states them; the payload repeats the address so a
        trace line reads on its own, and a repetition is not a second
        authority.

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
            self._track = supply(payload)
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
        nothing in the system branches on it (BUS.md, *what the hardware
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
        to read occupied is the **arrival**, and the train is told to stand
        where this app or a throttle was driving it (#296, ADR-0079).

        And its **second** sensor going occupied says the train is fully in,
        so the block behind is clear. That is the one event no detector could
        produce: occupancy is anonymous and the block behind is named by the
        move this app carried out. The entered block's own event has already
        gone out on its first sensor, so the order is occupied then vacated.
        It is not the only order the steel can produce: a block's own
        detectors going clear publish its vacate too, and a train shorter
        than the gap to the next block's entry detector, or a dead detector
        there, reads clear behind before it reads occupied ahead. The
        dispatcher ends a move on both readings in either order (ADR-0077,
        amending ADR-0047).
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
        if crossing.outstanding:
            # The arrival: the train is in the block it was sent to, so it is
            # told to stand, whoever was driving it — this app or a throttle,
            # whose next lever frame drives the train on (ADR-0081).
            # It does not wait for the vacate — the tail clearing is a fact
            # about the block behind — and it happens on the first end of this
            # block to settle occupied, which is the end the train comes in at
            # unless a reading arrived out of order. A train nobody was
            # driving was never told to run and is told nothing. Either way
            # the grant implies nothing more once the train is there, so what
            # it implied goes with the arrival.
            if crossing.driving or crossing.train in self._taken:
                for addr, _orientation in self._addressed(crossing.train):
                    self._traction_write(addr, 0.0)
            crossing = replace(crossing, implied=(), outstanding=False)
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
        says: the supply's own word, and `off` for any id ever heard to say
        its link is down.

        A link that has gone reports a participant that cannot reach its
        hardware, and a railroad half of which is unreachable is not a
        railroad a train may move on — whatever the supply says, since the
        participant saying it may be the unreachable one. "Ever seen" and not
        "currently connected", because a link is a retained level: a publisher
        that said `down` and then died leaves the value standing, and
        forgetting it would turn a broken railroad back on (ADR-0050).

        An id nothing has published is an id this app knows nothing of and
        waits for no word from: nothing must announce itself to come up
        (ADR-0058), and the ids here are whatever has spoken.

        Anything that cannot be read falls the same way. `supply` answers
        `off` for a supply it cannot read and `link_up` answers false for a
        link it cannot, so the fold needs no case for an unreadable frame:
        the direction a state topic must fail in is already in the readers
        (#181).

        The supply's own word is `on` or `off`, and never `draining`: a drain
        keeps the supply on, so the row reads `on` through one, and a frame
        claiming otherwise claims something no hardware can observe and is
        refused with everything else this cannot read (ADR-0063). Whether the
        railroad is draining is not a fold from hardware and never can be. It
        is held instead, and `_publish_power` is where the two meet.
        """
        if not all(self._links.values()):
            return OFF
        return self._track

    def _publish_power(self) -> None:
        """Whether a train may move at all, on a last-value topic, and only
        when the value moves: a state topic republishing the value it already
        holds is noise on the trace and news to nobody. The opening `off` is
        the constructor's, so a client that joins before the hardware has said
        anything is served a value rather than left to read one out of an
        absence (ADR-0032).

        **Two held words outrank the fold**, and are the ones on this row not
        read from hardware. `draining` is held because no hardware can hold
        it: the supply is live through a drain and goes on saying so, so a
        row folded from `device/track` alone would read `on` and the
        dispatcher would route into the drain (ADR-0063, ADR-0078). `off` is
        held from a cut until the next `on` for the same reason the other way
        round: the hardware reports the supply live until it has gone, and in
        that moment the row must not read `on`. Everything else is the
        fold's, unchanged, and the fold answers again on `on` — what the
        hardware said meanwhile is what the row then reads, rather than an
        `on` this app has taken its own word for.
        """
        stated = self._track_power.stated(self._folded())
        if stated != self._power:
            self._power = stated
            self._bus.publish(POWER, {"power": stated})
            if stated == ON:
                self._carry_out_kept()

    def _carry_out_kept(self) -> None:
        """Every move kept over dead rails, put back through `_cross` now that
        `state/power` reads `on` (#862).

        Here and not on the `on` press, because what the row reads is folded
        from the hardware and can come back after the press. Each one meets
        every rule again: a train no longer at the near end is dropped, and a
        move whose `align` has not landed is held for it. Where `_resume` also
        writes a speed to a move carried out here, it is the same value on the
        same row.
        """
        kept, self._kept = self._kept, {}
        for commanded in kept.values():
            self._cross(commanded)
