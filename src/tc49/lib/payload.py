"""Reading a payload from outside, where both apps read the same one (#127).

Anything at all can be published on a topic a person's page writes, so a
payload is **read** rather than trusted, and reading it **never raises**
(ADR-0034): a field that is missing or the wrong shape fails the read whole,
and what a failed read is worth is the caller's — an answer where there is an
id to address, a drop where there is not.

The scheduler reads a gesture off `tc49/ui/request_wanted`, the dispatcher a
request off `tc49/schedule/request_submitted`. The two differ by the id and
the departure end the scheduler adds (ADR-0036) and agree on the two fields a
gesture is, so those two are read here and each app keeps its own shape. The
scheduler's other leaf, `tc49/ui/reversal_wanted`, names a train and nothing
else, and is read here for the same reason: nothing raises. The dispatcher's
own two leaves, `tc49/ui/run_wanted` and `tc49/ui/placement_wanted`, are read
here beside them: which app reads a gesture is not what decides where the
reading lives — that nothing raises is (#152).

`tc49/layout/state/power` is read here for that reason and not the first one:
no page writes it, but the layout binding is another process, and a dispatcher
that raised on a frame it sent would be taken down by that binding's bug the
moment the bus stops being in-process (#173). It is the one reader here that
answers a word rather than `None`, and `power` says why (#175).

It is also the only leaf of that role read here so far. Occupancy is still
subscripted where it arrives, and reading the whole layout role is #173's
sweep: the power word came first because it is the one whose *drop* would be
unsafe.
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

    The two words are the topic's whole vocabulary, so a payload naming a
    third is dropped rather than set: a gesture carries no id and there is
    nothing to address an answer to (ADR-0034). The drain's `draining` will
    be a third word here before it is a third answer (#123).
    """
    if not isinstance(payload, dict):
        return None
    wanted = cast(dict[str, object], payload).get("run")
    if not isinstance(wanted, str) or wanted not in (HELD, RUNNING):
        return None
    return wanted


def power(payload: object) -> str:
    """The word the layout states about its supply, for a payload that can be
    read as one; `off` for a payload that cannot.

    It fails in the opposite direction from every other reader here, and that
    is the point. A gesture that cannot be read is dropped, and dropping a
    hold-or-release means doing nothing; dropping a *power* word would mean
    **not holding**, leaving the run committing over track whose state could
    not be read. So an unreadable payload is one of the "anything but `on`"
    cases the contract already has (DISPATCH.md) rather than an exception,
    and there is no `None` for a caller to have to think about.

    Which not-`on` word it is, is not a behavioural choice: the dispatcher
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


@dataclass(frozen=True)
class Placement:
    """The train a placement gesture names and the block it says it stands
    in. No facing: the gesture says where, and `reversal_wanted` is the
    correction where the train lands the wrong way round (ADR-0019)."""

    train: str
    block: str


def placement(payload: object) -> Placement | None:
    """The placement the payload names, or None where it names none.

    Whether the block exists, is free and fits the train is not read here:
    that is knowledge only the dispatcher holds, and it drops what it cannot
    accept. This says only that a train and a block were named.
    """
    if not isinstance(payload, dict):
        return None
    train, block = (
        cast(dict[str, object], payload).get(key) for key in ("train", "block")
    )
    if not isinstance(train, str) or not isinstance(block, str):
        return None
    return Placement(train, block)
