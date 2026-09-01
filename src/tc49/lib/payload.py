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
read the one reading (ADR-0030). `align`, the other command, has no reader:
the simulated points are always aligned, so that binding reads nothing off it
and nothing can fail.

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
"""

from dataclasses import dataclass
from typing import cast

from tc49.lib.inventory import HELD, OFF, ON, RUNNING, STOPPED


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
    """The run state a hold-or-release gesture asks for, or None where it
    asks for none.

    The two values are the topic's whole vocabulary, so a payload naming a
    third is dropped rather than set: a gesture carries no id and there is
    nothing to address an answer to (ADR-0034). The drain's `draining` will
    be a third value here before it is a third answer (#123).
    """
    if not isinstance(payload, dict):
        return None
    wanted = cast(dict[str, object], payload).get("run")
    if not isinstance(wanted, str) or wanted not in (HELD, RUNNING):
        return None
    return wanted


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
class Move:
    """The four names a `move` command states: which train, over which
    connection's which transit, into which block.

    Not the speed the command also carries (#283): the milestone-1 binding
    takes a fixed delay per transit, so it has nothing to do with a fraction
    of a locomotive's maximum, and a reader demanding one would drop commands
    that binding can carry out perfectly well. A binding that drives a real
    locomotive reads it where it turns it into whatever its hardware wants.
    """

    train: str
    connection: str
    transit: str
    into: str


def move(payload: object) -> Move | None:
    """The move the payload commands, or None where it commands none.

    The transit is bare and the connection stands beside it, which is the
    shape the command has and the grant has not: the driver splits the
    qualified transit, and a binding that has to ask the layout puts the two
    halves back together (`lib.layout.far_end`). Whether they name anything on
    this railroad is that layout question and not this one — a name is all
    there is to read in a payload.
    """
    if not isinstance(payload, dict):
        return None
    fields = cast(dict[str, object], payload)
    named = [fields.get(key) for key in ("train", "connection", "transit", "into")]
    if not all(isinstance(name, str) for name in named):
        return None
    train, connection, transit, into = cast(list[str], named)
    return Move(train, connection, transit, into)


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
