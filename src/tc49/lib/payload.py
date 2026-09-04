"""Reading a payload from outside, where both apps read the same one (#127).

Anything at all can be published on a topic a person's page writes, so a
payload is **read** rather than trusted, and reading it **never raises**
(ADR-0034): a field that is missing or the wrong shape fails the read whole,
and what a failed read is worth is the caller's — an answer where there is an
id to address, a drop where there is not.

The scheduler reads a gesture off `tc49/schedule/request_wanted`, the
dispatcher a request off `tc49/dispatch/request_submitted`. The two differ by
the id and the departure end the scheduler adds (ADR-0036) and agree on the
two fields a gesture is, so those two are read here and each app keeps its own
shape. The scheduler's other leaf, `tc49/schedule/reversal_wanted`, names a
train and nothing else, and is read here for the same reason: nothing raises.
The dispatcher's own two leaves, `tc49/dispatch/run_wanted` and
`tc49/dispatch/placement_wanted`, are read here beside them: which app reads a
gesture is not what decides where the reading lives — that nothing raises is
(#152).

`tc49/layout/state/power` is read here for that reason and not the first one:
no page writes it, but the layout binding is another process, and a dispatcher
that raised on a frame it sent would be taken down by that binding's bug the
moment the bus stops being in-process (#173). It is the one reader here that
answers a value rather than `None`, and `power` says why (#175).

Occupancy is read here beside it, so the whole layout role is read and no
frame that role publishes can take the dispatcher down (#181). The power enum
came first because it is the one whose *drop* would be unsafe, and the two
readers fail in opposite directions for that reason: `occupancy` says which
way it falls and why it may.

The dispatcher's **announcements** are read here for the layout binding's
reason and not the browser's, one step further out (#259): the scheduler
keeps facing off `move_granted`, `route_chosen`, `train_placed` and
`train_removed`, and a payload proves nothing about its sender, so a frame
claiming to be one of those may not take the scheduler down. They are the
first payloads read here that no gesture writes, which is why they are read
by shape alone — `grant` and `chosen` say that names were named, and whether
those names name anything is the layout's (`lib.layout.end_crossed`).

`move_granted` has a second reader in the driver, which turns each grant into
the command that moves the train (#261). Two apps reading one payload is what
this module is for, and it is the same reading: the driver holds no layout
either, so what it adds to `grant` is splitting the qualified transit its
command states bare, and that is the driver's own. The aspect is read here
beside it and not on `grant`, because the two readers want different fields of
the one frame (#283): `granted_aspect` says why.

That command is read here too, at the other end of it (#262): the layout
interface acts on `tc49/layout/move`, the topic names the interface because
the interface responds to it and says nothing about who published this frame,
and the process that publishes it today is the driver — another container
under MQTT, whose bug must not stop the binding running the railroad. It is
the first payload here read by whatever drives the track rather than by an app
on the bus's other side, so the milestone-1 simulator and a hardware binding
read the one reading (ADR-0030).

The **sensor** row is read here for that same reason (#288): `layout` folds a
block's two detectors into `block_occupied` and `block_vacated`, so the level
a detector states and the reason it gives for saying nothing are read on the
way in, where the occupancy events those become are read on the way out.

`align`, the other command, is read here beside it, and with it everything
else the core app `layout` is handed (#287): the power a page commands, the
aspects the dispatcher shows, and the two device rows the railroad's power is
folded from. They arrive from four different publishers and `layout` answers
none of them — it reports observations — so every one of them is a frame that
must be droppable. The milestone-1 simulator reads none of these: its points
are always aligned and its track is always live, which is why `align` had no
reader at all until there was an app that throws something.

The throttle's **two gestures** are read here for the first reason of them all
(#297): a person's page writes both, any number of pages may write either, and
`layout` acts on them with nothing to answer back to. They are the pair that
takes a train in a throttle and turns it, and `layout` is where the two meet
the roster and become a speed on a decoder — which is why neither reader knows
anything of a train beyond its name.

The **desired half of the device vocabulary** is read here from the other
side of the same seam (#289): `layout` writes those rows and a translator
acts on the ones it recognises, so the reading belongs where the writing's
does. A translator answers nothing either — it reports observations — and
there will be more than one of them, each reading the identical rows for the
hardware it drives, which is this module's first reason and its second at
once. `commanded_power` is the reader for `wanted/track`, the same word on
the same axis as the gesture that moved it, so the desired power is not read
twice.

The scheduler's **retained facing** is read here for a third reason (#277):
it is the first payload here whose reader is also its writer. A retained value
is handed back at construction by a broker that outlived the app, it can be
hand-edited there or have been written by an older build, and rule 4 exempts
no payload for having once been the reader's own. What subscripting one gives
is not a dropped frame but an app that does not start at all, so the scheduler
reads it and starts cold where it cannot.

The dispatcher's **retained allocation picture** is the second of those, and
the same rule (#278). A retained value being a payload is not a property of
the topic it sits on: the two are read side by side here so that neither app
has its own way of reading its own last value, and the entry-at-a-time rule
they share is `_named`.

The dispatcher's **run row** is read here beside the aspects, and for the
same reason one step on (#407): `layout` is handed it so that the guard on a
plain `off` is made where the command is answered rather than trusted to
whoever sent it (ADR-0062). The run word and `moving` are one reading,
because the guard wants the pair.

The **stamp** a state payload carries is read here for the first reason of
all (#240): it is a field like any other, arriving from another process,
and a reader that subscripted it would be taken down by whatever wrote it.
`Ordering` is the comparison a consumer makes with it, and it lives here
because this is where payloads are read — the stamping lives where the
binding publishes, in `lib.bus`.
"""

from dataclasses import dataclass
from typing import cast

from tc49.lib.inventory import (
    AT,
    AUTOMATIC,
    CLEAR,
    DRAINING,
    HELD,
    MANUAL,
    OCCUPIED,
    OFF,
    ON,
    RUNNING,
    STOPPED,
    UNKNOWN,
    is_state_topic,
)
from tc49.lib.layout import Point


@dataclass(frozen=True)
class Gesture:
    """The train and arrival ends a payload names: a gesture whole, and the
    part of a request that is one."""

    train: str
    arrivals: tuple[str, ...]


def gesture(payload: object) -> Gesture | None:
    """The gesture the payload names, or None where it names none."""
    if not isinstance(payload, dict):
        return None
    train, dest = (
        cast(dict[str, object], payload).get(key) for key in ("train", "dest")
    )
    if not isinstance(train, str) or not isinstance(dest, list):
        return None
    ends = cast(list[object], dest)
    if not all(isinstance(end, str) for end in ends):
        return None
    return Gesture(train, tuple(cast(list[str], ends)))


def named_train(payload: object) -> str | None:
    """The train a payload naming one and nothing else states, or None where
    it names none.

    A train is the whole payload on `tc49/schedule/reversal_wanted`, where
    turning around at rest moves nothing so there is no destination to state
    and no departure end to choose, and on `tc49/dispatch/train_removed`,
    where a train off the layout stands in no block (ADR-0039). One shape,
    one reader: which topic it arrived on is the caller's.
    """
    if not isinstance(payload, dict):
        return None
    train = cast(dict[str, object], payload).get("train")
    return train if isinstance(train, str) else None


def readable_id(payload: object) -> str | None:
    """The id an answer would be addressed to, or None where there is none.

    Every rejection is addressed by id and broadcast, so a frame carrying no
    readable one is answered to nobody; it is dropped instead, and the trace
    line it already has is what keeps a client bug diagnosable (ADR-0034).
    """
    if not isinstance(payload, dict):
        return None
    rid = cast(dict[str, object], payload).get("id")
    return rid if isinstance(rid, str) and rid else None


@dataclass(frozen=True)
class Grant:
    """The move a grant authorises: which train, over which transit, into
    which block.

    The three fields every consumer of `tc49/dispatch/move_granted` acts on.
    The id correlates and the aspect is the driver's, and each is read beside
    this one by whoever wants it — `readable_id` and `granted_aspect`.
    """

    train: str
    transit: str
    into: str


def grant(payload: object) -> Grant | None:
    """The granted move the payload names, or None where it names none.

    The transit is the qualified `<connection>.<transit>` the inventory
    states, and is left whole: splitting it is the driver's, and reading the
    end it crosses is `lib.layout`'s. Both need the layout or the connection
    to say anything, and neither is a question about the payload.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    train, transit, into = (fields.get(key) for key in ("train", "transit", "into"))
    if not all(isinstance(field, str) for field in (train, transit, into)):
        return None
    return Grant(cast(str, train), cast(str, transit), cast(str, into))


def granted_aspect(payload: object) -> str | None:
    """The aspect a grant shows, or None where it shows none.

    Beside `grant` rather than a field on it, as `readable_id` is: the
    scheduler reads the same frame for which way the train ends up facing and
    has no use for the aspect, so an aspect on `Grant` would cost it a facing
    it could have kept over a field it never looks at. The driver, which turns
    the aspect into the speed its command carries, reads both and drops the
    frame where either fails (ADR-0025).

    Whether the name is an aspect this build knows what to do with is the
    reader's question and not this one. `stop` reads perfectly well here and
    is no permission to move; the mapping from aspect to speed is the driver's
    alone, and a name is the whole of what there is to read in a payload.
    """
    if not isinstance(payload, dict):
        return None
    aspect = cast(dict[str, object], payload).get("aspect")
    return aspect if isinstance(aspect, str) else None


@dataclass(frozen=True)
class Chosen:
    """The request a launch fixed a route for, and the route it fixed:
    the alternating sequence of block and transit names, a single block for
    the degenerate already-there case."""

    id: str
    route: tuple[str, ...]


def chosen(payload: object) -> Chosen | None:
    """The route choice the payload names, or None where it names none.

    The route is read as a sequence of names and not as a path: that the
    entries alternate, that each names something, and that the something is
    reachable are the layout's questions and the chooser's, and a reader that
    asked them would be re-deriving the route rather than reading it. How
    much of one a consumer needs is its own — the scheduler wants the first
    block and the transit off it, and stops there.

    `k_tried` is left behind with them: it is the sweep's own record, on the
    trace for the benchmark to count and read by nothing.
    """
    rid = readable_id(payload)
    if rid is None:
        return None
    route = cast(dict[str, object], payload).get("route")
    if not isinstance(route, list):
        return None
    legs = cast(list[object], route)
    if not all(isinstance(leg, str) for leg in legs):
        return None
    return Chosen(rid, tuple(cast(list[str], legs)))


def run_state(payload: object) -> str | None:
    """The run state a gesture asks for, or None where it asks for none.

    The three values are the topic's whole vocabulary — hold, release, and
    the **drain** that asks for neither and ends at the first of them (#294)
    — so a payload naming a fourth is dropped rather than set: a gesture
    carries no id and there is nothing to address an answer to (ADR-0034).
    """
    if not isinstance(payload, dict):
        return None
    wanted = cast(dict[str, object], payload).get("run")
    if not isinstance(wanted, str) or wanted not in (HELD, RUNNING, DRAINING):
        return None
    return wanted


@dataclass(frozen=True)
class Run:
    """The run as its **state** row states it: the word the dispatcher holds
    it at, and whether anything is moving under it.

    The two are read together because what asks for them wants the pair:
    `layout`'s guard on a plain `off` refuses on `moving` as well as on the
    run word, a held run being able to be moving (ADR-0062).
    """

    run: str
    moving: bool


def kept_run(payload: object) -> Run | None:
    """The run a retained `tc49/dispatch/state/run` value states, or None
    where it states none.

    `run_state`'s opposite number on the reading direction of the one axis,
    as `power` is `commanded_power`'s, and it fails the way a reading of
    another app's state must: a value that cannot be read is no value, and
    the caller goes on with whatever it already held.

    **A row with no `moving` reads as nothing moving.** An older dispatcher
    says nothing about what is under way, and an absence is not evidence that
    a train is in motion — which is the direction the guard reading this
    falls in, refusing on evidence and on nothing else (ADR-0062, #406). A
    `moving` that is there and is not a boolean is another matter: that is a
    row this build cannot read, and it is dropped whole.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    held = fields.get("run")
    if not isinstance(held, str) or held not in (HELD, RUNNING, DRAINING):
        return None
    moving = fields.get("moving", False)
    if not isinstance(moving, bool):
        return None
    return Run(held, moving)


def power(payload: object) -> str:
    """The value the layout states about its supply, for a payload that can be
    read as one; `off` for a payload that cannot.

    It fails in the opposite direction from every other reader here, and that
    is the point. A gesture that cannot be read is dropped, and dropping a
    hold-or-release means doing nothing; dropping a *power* value would mean
    **not holding**, leaving the run committing over track whose state could
    not be read. So an unreadable payload is one of the "anything but `on`"
    cases the contract already has (DISPATCH.md) rather than an exception,
    and there is no `None` for a caller to have to think about.

    Which not-`on` value it is, is not a behavioural choice: the dispatcher
    branches on "not `on`" alone (ADR-0041), and `stopped` and `off` differ
    only for the person recovering — who has an unreadable payload to recover
    from, not an emergency stop.
    """
    if not isinstance(payload, dict):
        return OFF
    stated = cast(dict[str, object], payload).get("power")
    if not isinstance(stated, str) or stated not in (ON, STOPPED, OFF):
        return OFF
    return stated


def commanded_power(payload: object) -> str | None:
    """The power a gesture asks the railroad for, or None where it asks for
    none.

    `power`'s opposite number on the command direction of the one axis
    (ADR-0051), and it fails the other way round. A *reading* that cannot be
    read must still hold the run, so `power` has no `None`; a **command**
    that cannot be read is dropped like every other gesture, because cutting
    the supply on a malformed frame would be `layout` writing `off` of its
    own accord, which it never does (#287). A gesture carries no id, so there
    is nothing to address a refusal to either (ADR-0034).
    """
    if not isinstance(payload, dict):
        return None
    wanted = cast(dict[str, object], payload).get("power")
    if not isinstance(wanted, str) or wanted not in (ON, STOPPED, OFF):
        return None
    return wanted


@dataclass(frozen=True)
class Mode:
    """Who is to drive a train, as a `mode_wanted` gesture states it: the
    train it names, or `None` for **every** train at once.

    The `None` here is the gesture's own and is not the `None` `wanted_mode`
    answers with, which says the payload could not be read at all — the pair
    `Placement` carries, for the same reason: one gesture in two directions,
    and the wider of the two is a thing a person does to a railroad rather
    than to the train they have picked (#284).
    """

    train: str | None
    mode: str


def wanted_mode(payload: object) -> Mode | None:
    """The mode a gesture asks for, or None where it asks for none.

    An **enum**, read like the run state and the commanded power beside it: a
    payload naming a third word is dropped whole and the train's mode stays
    where it was, since falling to `manual` would hand a train to a person who
    is not there and falling to `automatic` would take one out of the hands of
    a person who is (`lib.inventory.AUTOMATIC`). A gesture carries no id, so
    there is nothing to address a refusal to either (ADR-0034).

    A **missing** `train` fails the read and an explicit `null` succeeds, the
    rule `placement` keeps on its block: handing over the whole railroad is
    too much to read into a frame that lost a field on the way, where a
    `null` a page wrote is a positive statement about every train.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    if "train" not in fields:
        return None
    train, mode = fields.get("train"), fields.get("mode")
    if not (train is None or isinstance(train, str)):
        return None
    if not isinstance(mode, str) or mode not in (AUTOMATIC, MANUAL):
        return None
    return Mode(train, mode)


@dataclass(frozen=True)
class Throttle:
    """The lever a person is holding: which train, and how fast.

    A **signed** fraction of that train's maximum, `-1.0` … `1.0` with `0.0`
    stop, and signed for the *train* rather than for a locomotive — positive
    is the way the train points (CONTEXT.md, **Throttle**). Which decoder that
    reaches, and which way round it stands, is `layout`'s: no throttle holds a
    roster and none names an address (#199).
    """

    train: str
    speed: float


def wanted_throttle(payload: object) -> Throttle | None:
    """The throttle a gesture turns, or None where it turns none.

    The speed is not read beside the train the way a `move`'s is read beside
    its four names: a throttle *is* a speed, so a frame that states none turns
    nothing and there is nothing left to act on. What a fraction past the
    range is worth is the same question `desired_speed` leaves to the
    translator — the contract states −1.0 … 1.0 and there is nothing above a
    train's maximum to ask for.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    train, speed = fields.get("train"), _fraction(fields, "speed")
    if not isinstance(train, str) or speed is None:
        return None
    return Throttle(train, speed)


def occupancy(payload: object) -> str | None:
    """The block an occupancy reading names, or None where it names none.

    The other direction from `power`, on the same role, and that asymmetry is
    the whole reason both are read here rather than one: a power value that
    cannot be read must still hold the run, so `power` has no `None`, while a
    reading that cannot be read is dropped, which is what this `None` is for.
    Why the two fail in opposite directions is SYSTEM.md, sole payload
    authority; a dropped frame is already on the trace by virtue of having
    been published (ADR-0034).

    Which reading it is — occupied or vacated — is the leaf it arrived on and
    not a field, so it is the caller's and not read here. Whether the block
    exists is the dispatcher's knowledge, as with `placement`.
    """
    if not isinstance(payload, dict):
        return None
    block = cast(dict[str, object], payload).get("block")
    return block if isinstance(block, str) else None


def detected(payload: object) -> str:
    """What one detector says it sees at the block end its row is addressed
    by: `occupied`, `clear` or `unknown`, and `unknown` for a row that cannot
    be read.

    The third reader here that answers a value rather than `None`, and it
    falls the way its own axis does. `power` falls to `off` and `link_up` to
    not-up because a supply or a link that cannot be read is not one a train
    may move on (#181). An occupancy row has a word of its own for exactly
    this — `unknown` is **no information** about that end, a value and not an
    absence (SYSTEM.md, *what the hardware reports back*) — and a frame that
    cannot be read carries no information about that end either. So the read
    that fails says the thing the contract already has a word for, and what a
    consumer does with `unknown` is the one behaviour rather than two: it
    neither calls the end clear nor invents an edge, and the level it last
    held stands (#288).

    The `reason` beside it is free text for a person and is not read: a
    consumer branches on the level alone, and the frame carrying the reason is
    on the trace by virtue of having been published (ADR-0034).
    """
    if not isinstance(payload, dict):
        return UNKNOWN
    seen = cast(dict[str, object], payload).get("occupancy")
    if not isinstance(seen, str) or seen not in (OCCUPIED, CLEAR, UNKNOWN):
        return UNKNOWN
    return seen


def reported_reason(payload: object) -> str | None:
    """Why the hardware reports what it does, or None where it gives no
    reason — free text and optional, on the two observed rows that carry one:
    a detector's `unknown`, and a supply the participant reporting it cannot
    reach (`{power: off, reason: "…"}`, ADR-0059).

    Read so that `layout` can put it in front of a person, which is the whole
    of what it is for: nothing branches on it, and a reason that is not a
    string is no reason.
    """
    if not isinstance(payload, dict):
        return None
    why = cast(dict[str, object], payload).get("reason")
    return why if isinstance(why, str) else None


@dataclass(frozen=True)
class Placement:
    """The train a placement gesture names and where it says the train is:
    the block it stands in, or `None` for **off the layout**.

    One gesture in two directions, so nowhere is one of the places a train
    can be said to be (ADR-0039). No facing either way: the gesture says
    where, and `reversal_wanted` is the correction where the train lands the
    wrong way round (ADR-0019).

    The `None` here is the gesture's own, and is not the `None` `placement`
    answers with a line below: that one says the payload could not be read at
    all.
    """

    train: str
    block: str | None


def placement(payload: object) -> Placement | None:
    """The placement the payload names, or None where it names none.

    Two topics, one shape: the gesture on `tc49/dispatch/placement_wanted`,
    and `tc49/dispatch/train_placed`, the fact the dispatcher publishes once
    it has accepted one. The fact never carries a null block — a train taken
    off the layout is `train_removed`, which names the train alone — so a
    consumer of the fact reads a null the same way it reads a payload it
    could not read at all, and drops it.

    Whether the block exists, is free and fits the train is not read here:
    that is knowledge only the dispatcher holds, and it drops what it cannot
    accept. This says only that a train and a place were named.

    A **missing** `block` fails the read and an explicit `null` succeeds, so
    the key's presence is load-bearing. A gesture is read and never trusted,
    and a frame that lost a field on the way is indistinguishable from one
    that never carried it — taking a train off the layout is too much to read
    into an absence, where a `null` a page wrote is a positive statement that
    the train is nowhere. That is not a sentinel in the ADR's sense: the
    dispatcher's own record of off-the-layout is absence from `block_of`, and
    this is a gesture naming a destination, which has to have one.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    if "block" not in fields:
        return None
    train, block = fields.get("train"), fields.get("block")
    if not isinstance(train, str) or not (block is None or isinstance(block, str)):
        return None
    return Placement(train, block)


@dataclass(frozen=True)
class Command:
    """The four names a `move` command states — which train, over which
    connection's which transit, into which block — and the speed it asks for.

    The four names are what makes a command readable and the speed is not
    (#283): the milestone-1 binding takes a fixed delay per transit, so it
    has nothing to do with a fraction of a locomotive's maximum, and a reader
    demanding one would drop commands that binding can carry out perfectly
    well. So it is read **beside** them and answers None where the frame
    states none, and what a move with no speed is worth is the binding's: the
    simulator ignores it, and `layout`, which turns it into a signed speed on
    every locomotive of the train, has nothing to send and drops the command
    rather than choose a speed nobody asked for (#296).

    A **magnitude** in 0.0 … 1.0 and never a signed one: which way a train
    runs along the track is the layout interface's to compose, out of the
    train's facing and the way round each of its cars is coupled, and no
    publisher of a `move` holds either fact (SYSTEM.md, *Layout interface*).
    """

    train: str
    connection: str
    transit: str
    into: str
    speed: float | None = None


def command(payload: object) -> Command | None:
    """The move the payload commands, or None where it commands none.

    The transit is bare and the connection stands beside it, which is the
    shape the command has and the grant has not: the driver splits the
    qualified transit, and a binding that has to ask the layout puts the two
    halves back together (`lib.layout.end_across`). Whether they name anything
    on this railroad is that layout question and not this one — a name is all
    there is to read in a payload.

    The speed rides beside the names and never with them: a frame that states
    none still commands a move, and what that is worth is the binding's
    (`Command`).
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    named = [fields.get(key) for key in ("train", "connection", "transit", "into")]
    if not all(isinstance(name, str) for name in named):
        return None
    train, connection, transit, into = cast(list[str], named)
    return Command(train, connection, transit, into, _fraction(fields, "speed"))


@dataclass(frozen=True)
class Alignment:
    """The route an `align` sets: the connection and the transit it names,
    and the points that transit's way needs thrown (ADR-0031).

    The transit is bare and the connection stands beside it, the shape
    `Command` has, because the two commands name a transit the same way.
    The points are `lib.layout.Point`, the pair the layout document already
    carries — an address and the position a way wants the point wearing in —
    since what rides on `align` is exactly what was read off the layout.
    """

    connection: str
    transit: str
    points: tuple[Point, ...]


def alignment(payload: object) -> Alignment | None:
    """The alignment the payload commands, or None where it commands none.

    The other command, read at the same door as `command` and for the same
    reason (#287): the layout interface acts on it, the topic names the
    interface rather than whoever published this frame, and a binding that
    raised on one would be taken down by that publisher. Until `layout` the
    topic had no reader at all — the milestone-1 simulator's points are
    always aligned, so it reads nothing off one.

    A pair that cannot be read fails the **whole** frame, where a retained
    map is read an entry at a time (`_named`). An alignment is one route:
    throwing the points that read and dropping the ones that did not would
    set a way half over, and a `move` would then be let onto it.

    Whether the connection and the transit name anything on this railroad is
    the layout's question, and whether a position is one a point can be in is
    the hardware's — a name is the whole of what there is to read in a
    payload. `points` is always present, `[]` where the way needs nothing
    thrown: the document is quiet and the wire explicit, so an absent list is
    a frame that lost a field rather than a way with no points on it.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    connection, transit, stated = (
        fields.get(key) for key in ("connection", "transit", "points")
    )
    if not isinstance(connection, str) or not isinstance(transit, str):
        return None
    if not isinstance(stated, list):
        return None
    points: list[Point] = []
    for entry in cast(list[object], stated):
        if not isinstance(entry, dict):
            return None
        pair = cast(dict[str, object], entry)
        addr, position = pair.get("addr"), pair.get("position")
        if not isinstance(addr, str) or not isinstance(position, str):
            return None
        points.append(Point(addr, position))
    return Alignment(connection, transit, tuple(points))


def shown_aspects(payload: object) -> dict[str, str] | None:
    """The aspects a `tc49/dispatch/state/aspects` value shows, block end to
    the aspect standing at it, or None where it shows none.

    Read an entry at a time, as `kept_facing` is and for the same reason: the
    value is the whole picture of the railroad's signals, so an entry that
    cannot be read costs that end its aspect and no other. An **aspect is not
    an enum** (CONTEXT.md), so the name is read as a name — what a signal
    makes of it is a translator's, as what a speed is worth is the driver's.

    Whether an end named here is one this railroad has, and whether a signal
    stands at it, is the layout's question (`Layout.signal_at`).
    """
    if not isinstance(payload, dict):
        return None
    shown = cast(dict[str, object], payload).get("aspects")
    if not isinstance(shown, dict):
        return None
    return _named(cast(dict[object, object], shown))


def link_up(payload: object) -> bool:
    """Whether a participant states that it can reach the hardware it drives.

    A boolean rather than a value, because the fold it feeds asks one
    question: the railroad has power only while every link that has ever been
    seen is up (#287). So anything that is not the word `up` — `down`, a word
    from outside the pair, a payload that is no object at all — reads as not
    up, which is `power`'s direction on the row beside it and for `power`'s
    reason (#181): a link a consumer cannot read is not a link it may call
    good. The id the row is keyed by is not read here: it is the topic's, and
    what the fold does with it is `layout`'s (ADR-0059).
    """
    if not isinstance(payload, dict):
        return False
    return cast(dict[str, object], payload).get("link") == "up"


def desired_speed(payload: object) -> float | None:
    """The speed a `wanted/traction` value asks a locomotive for, or None
    where it asks for none — a fraction of that locomotive's maximum, signed
    for direction along the track (CONTEXT.md, **Traction**).

    The first of the **desired** half of the device vocabulary read here, and
    read for the reason a command is: a translator answers nothing, so a
    frame it cannot read is dropped and a translator that raised on one would
    be taken down by whatever published it (#289). `layout` is the single
    writer of every one of these rows and rule 4 exempts no payload for that
    — a retained value can be hand-edited or left by an older build, which is
    why the scheduler reads its own facing back.

    A **boolean is not a speed**, refused ahead of the numeric read the way a
    stamp refuses one: JSON `true` is an `int` in Python and would otherwise
    be taken for full speed forward. What a fraction past the range is worth
    is the translator's and not read here: the contract states −1.0 … 1.0 and
    there is nothing above a locomotive's maximum to ask for.
    """
    return _fraction(payload, "speed")


def _fraction(payload: object, field: str) -> float | None:
    """One named number field of a payload, or None where the payload states
    no such thing.

    Shared by the two speeds — the one a `wanted/traction` value asks a
    locomotive for and the one a `move` asks of a train — because they fail
    the same way and differ only in whose speed they are. A **boolean is not
    a number**, refused ahead of the numeric read the way a stamp refuses
    one: JSON `true` is an `int` in Python and would otherwise be taken for
    full speed.
    """
    if not isinstance(payload, dict):
        return None
    stated = cast(dict[str, object], payload).get(field)
    if isinstance(stated, bool) or not isinstance(stated, (int, float)):
        return None
    return float(stated)


def desired_position(payload: object) -> str | None:
    """The position a `wanted/point` value asks a point for, or None where it
    asks for none. Whether the name is one the hardware has a packet for is
    the translator's, as an aspect's is."""
    return _stated(payload, "position")


def desired_aspect(payload: object) -> str | None:
    """The aspect a `wanted/signal` value asks a signal for, or None where it
    asks for none. An **aspect is not an enum** (CONTEXT.md): the name is read
    as a name here and what a head makes of it is the translator's, which is
    the same reading `shown_aspects` makes one end at a time."""
    return _stated(payload, "aspect")


def desired_function(payload: object) -> str | None:
    """The state a `wanted/function` value asks a function for, or None where
    it asks for none.

    The field is `value` rather than a name of its own, and what it may be is
    the model's: a function's values are fully configurable, `off` and `on`
    where a model states none (LAYOUT.md). So it is read as a string and
    nothing more, and which strings a decoder can actually be told is the
    translator's answer.
    """
    return _stated(payload, "value")


def _stated(payload: object, field: str) -> str | None:
    """One named string field of a device row, or None where the payload
    states no such thing. The three desired rows that carry a name rather
    than a number share it: each fails the same way, and the difference
    between them is which name they carry and who decides what it means."""
    if not isinstance(payload, dict):
        return None
    stated = cast(dict[str, object], payload).get(field)
    return stated if isinstance(stated, str) else None


def kept_facing(payload: object) -> dict[str, str] | None:
    """The facing a retained `tc49/schedule/state/facing` value states, train
    to the run it would make across its block, or None where it states none.

    The map is read one train at a time: a session's whole facing is in this
    one value, so an entry that cannot be read loses that train and no other,
    where a `None` here says there was no map to take an entry from. Whether
    a value that *is* a string spells a facing this build knows is
    `lib.layout`'s question — the `<block>.<A-to-B|B-to-A>` form is parsed
    there and nowhere else — and the scheduler asks it of what this answers.
    """
    if not isinstance(payload, dict):
        return None
    held = cast(dict[str, object], payload).get("facing")
    if not isinstance(held, dict):
        return None
    return _named(cast(dict[object, object], held))


@dataclass(frozen=True)
class Picture:
    """The two maps a retained `tc49/dispatch/state/allocation` value states
    that a restart takes: where each train stood, and which transit was
    taking it out of the block it stands in.

    `locks` and `requests` are not here, and their absence is the adoption
    policy's rather than the reading's: a restart rebuilds the lock table one
    block per train and comes up with an empty queue (ADR-0033, #123), so
    nothing reads those two and a reader that asked their shape would refuse
    a picture over a part nobody adopts.
    """

    trains: dict[str, str]  # train -> the block the picture stands it in
    crossing: dict[str, str]  # train -> the transit taking it out of there


def kept_allocation(payload: object) -> Picture | None:
    """The picture a retained allocation value states, or None where it
    states none.

    The dispatcher's own last value, and the second payload here whose reader
    is also its writer (#278): a bus binding that outlived the app hands it
    back at construction, where it can have been hand-edited or written by an
    older build, and rule 4 exempts no payload for having once been the
    reader's own. Subscripting one gives not a dropped frame but an app that
    does not start at all, and the moment that value exists for is the
    recovery after a restart or a power cut — exactly when it is most likely
    to be damaged.

    Both maps have to be maps, and a value stating either otherwise states no
    picture: the two are one statement about where the railroad stood, and a
    value carrying half of it was written by something other than the
    contract. Within each, entries are read one train at a time as
    `kept_facing` reads them, so a picture naming one train badly loses that
    train and keeps the rest. Whether a block or a transit named here is on
    this railroad is the layout's question and the dispatcher's, as it is for
    `placement`.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    trains, crossing = fields.get("trains"), fields.get("crossing")
    if not isinstance(trains, dict) or not isinstance(crossing, dict):
        return None
    return Picture(
        _named(cast(dict[object, object], trains)),
        _named(cast(dict[object, object], crossing)),
    )


def _named(stated: dict[object, object]) -> dict[str, str]:
    """The entries of a map that names a string against a string, in the
    order they were stated. What the two retained readers have in common: a
    map that is one session's whole record of something is read an entry at a
    time, so the unreadable ones cost their own subject and nobody else's.
    """
    return {
        subject: value
        for subject, value in stated.items()
        if isinstance(subject, str) and isinstance(value, str)
    }


def stamp(payload: object) -> float | None:
    """The instant a state payload states it was published at, or None where
    it states none — seconds since the session started, the run clock's own
    reading (`lib.clock`).

    A **boolean is not a stamp**, and is the one shape refused ahead of the
    numeric read: JSON `true` is an `int` in Python and would otherwise be
    taken for `1.0`, which is a real instant in a session's first second. An
    unreadable stamp is no stamp, and `Ordering` says what a value carrying
    none is worth.
    """
    if not isinstance(payload, dict):
        return None
    at = cast(dict[str, object], payload).get(AT)
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    return float(at)


class Ordering:
    """The stamps a consumer holds, one per state topic: what it takes to
    keep the later of two values of one topic whichever order they arrive in
    (#240).

    MQTT promises order from one publisher on one topic, and not across that
    publisher's reconnect or a retransmission with more than one message in
    flight (ADR-0008). A state topic keeps the last message published on it,
    so a pair delivered backwards would leave the *older* value standing, and
    the durable file would write it to disk. The stamp is what tells the two
    apart, and it does not care who published: whoever wrote the later one
    wrote the value that is kept.

    State topics only. An event topic reports something that happened and is
    never replayed, so there is no held value for a late one to lose to, and
    the guard is off the gate a topic's own name gives (SYSTEM.md, rule 2)
    rather than off whether a payload happens to carry a number.
    """

    def __init__(self) -> None:
        self._held: dict[str, float] = {}

    def accepts(self, topic: str, payload: object) -> bool:
        """Whether this value is the one to keep, and never raises.

        Later wins and equal replaces — two values of one instant are the
        publisher's own order, which the bus has already kept. An earlier
        stamp is ignored, and quietly: it is the case this exists for, not a
        fault to report.

        An **unstamped** value is accepted and clears the held stamp, so
        ordering restarts from the next stamped value. Keeping the old stamp
        would leave it refusing values whose own stamp is gone — a payload
        from a build that does not stamp, or one hand-edited on the way — and
        the publisher owns the value.
        """
        if not is_state_topic(topic):
            return True
        at = stamp(payload)
        if at is None:
            self._held.pop(topic, None)
            return True
        held = self._held.get(topic)
        if held is not None and at < held:
            return False
        self._held[topic] = at
        return True
