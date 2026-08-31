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


def reversal(payload: object) -> str | None:
    """The train a reversal gesture names, or None where it names none.

    A train is the whole payload: turning around at rest moves nothing, so
    there is no destination to state and no departure end to choose.
    """
    if not isinstance(payload, dict):
        return None
    train = cast(dict[str, object], payload).get("train")
    return train if isinstance(train, str) else None


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
