"""The event inventory: canonical payload field order per topic.

Mirrors the inventory table of SYSTEM.md. The trace's canonical key order
depends on this module; leaf names are globally unique across all topics
(tested), because the trace's ``event`` field is the leaf alone.

Two mappings, because a topic is named two ways. ``TOPICS`` is the transit-level
contract, one whole topic per row. ``DEVICE_TOPICS`` is the device vocabulary
under the layout interface (ADR-0043), where the row is fixed and the address
is trailing levels a railroad's wiring decides, so the row is keyed by what is
knowable. The namespace is one: a name is unique across both.

A topic names the component that **declares** it: the events that component
emits, and the requests it responds to. Nothing in a name says who sent a
request, and no responder may read or infer it (SYSTEM.md, rule 4).

Browser-writability is a mark on the row rather than a prefix to read:
``INBOUND`` below is the marked rows, so a page's write surface widens only
where somebody writes ``browser=True``.

Where a field's *values* are a closed set the contract names, they live here
too, beside the field they belong to: ``run`` and ``power`` are those fields.
What an **enum** is, and which way an unreadable one falls, is CONTEXT.md.
"""

from typing import NamedTuple


class Topic(NamedTuple):
    """One inventory row: the payload's fields in the trace's canonical
    order, and whether a browser may publish on the topic."""

    fields: tuple[str, ...]
    browser: bool = False


TOPICS: dict[str, Topic] = {
    "tc49/layout/block_occupied": Topic(("block",)),
    "tc49/layout/block_vacated": Topic(("block",)),
    "tc49/layout/state/power": Topic(("power",)),
    "tc49/layout/align": Topic(("connection", "transit", "points")),
    "tc49/layout/move": Topic(("train", "connection", "transit", "into")),
    "tc49/schedule/request_wanted": Topic(("train", "dest"), browser=True),
    "tc49/schedule/reversal_wanted": Topic(("train",), browser=True),
    "tc49/schedule/state/exhausted": Topic(("exhausted",)),
    "tc49/schedule/state/facing": Topic(("facing",)),
    "tc49/dispatch/request_submitted": Topic(("id", "train", "depart", "dest")),
    "tc49/dispatch/run_wanted": Topic(("run",), browser=True),
    "tc49/dispatch/placement_wanted": Topic(("train", "block"), browser=True),
    "tc49/dispatch/cancel_wanted": Topic(("train",), browser=True),
    "tc49/dispatch/request_admitted": Topic(("id", "dest", "pruned")),
    "tc49/dispatch/request_rejected": Topic(("id", "reason")),
    "tc49/dispatch/request_completed": Topic(("id",)),
    "tc49/dispatch/request_cancelled": Topic(("id", "reason")),
    "tc49/dispatch/route_chosen": Topic(("id", "route", "k_tried")),
    "tc49/dispatch/move_granted": Topic(("id", "train", "transit", "into", "aspect")),
    "tc49/dispatch/grant_refused": Topic(("id", "reason", "obstacles")),
    "tc49/dispatch/lock_granted": Topic(("train", "resources")),
    "tc49/dispatch/lock_released": Topic(("train", "resources")),
    "tc49/dispatch/train_placed": Topic(("train", "block")),
    "tc49/dispatch/train_removed": Topic(("train",)),
    "tc49/dispatch/state/run": Topic(("run",)),
    "tc49/dispatch/state/aspects": Topic(("aspects",)),
    "tc49/dispatch/state/disputed": Topic(("trains", "blocks")),
    "tc49/dispatch/state/allocation": Topic(
        ("trains", "crossing", "locks", "requests")
    ),
}


DEVICE_PREFIX = "tc49/layout/state/"
"""What every device row's key starts with, and what a trace ``event`` strips
to name one: ``wanted/traction``, ``wanted/point``. A device row is named by
two levels where an ordinary row is named by one, because the desired half of
the vocabulary and the observed half address the same hardware — ``point``
alone would not say which of the two a line records."""


DEVICE_TOPICS: dict[str, Topic] = {
    "tc49/layout/state/wanted/traction": Topic(("addr", "speed")),
    "tc49/layout/state/wanted/function": Topic(("addr", "function", "value")),
    "tc49/layout/state/wanted/point": Topic(("addr", "position")),
    "tc49/layout/state/wanted/signal": Topic(("addr", "aspect")),
    "tc49/layout/state/wanted/track": Topic(("power",)),
}
"""The device vocabulary `layout` writes: what the hardware should do, one
retained state topic per device, `layout` the single writer (rule 1) and a
translator acting on whatever address it recognises (ADR-0043).

Keyed by the **fixed part** of the topic, the address being trailing levels
rather than a leaf, and repeated in the payload as ``addr`` so a trace line
reads on its own. `wanted/track` is the one row that carries no address: a
power district is a hardware-level fact that does not reach the bus, so there
is one railroad-wide desired power and a translator maps it onto however many
districts it drives (#217).

Separate from ``TOPICS`` rather than in it because ``TOPICS`` maps a whole
topic to its field order, and a device row's whole topic is not knowable until
a railroad is wired. What the two mappings share is the namespace: a name is
unique across both (tested).

SYSTEM.md, *Layout interface*, carries the values each field takes and the two
address rules — a traction or function address is bare and a point or signal
address names its system first."""


def device_topic(prefix: str, *address: str) -> str:
    """The topic a device sits on: a ``DEVICE_TOPICS`` key and the levels of
    its address. `wanted/track` takes none and is its own topic."""
    return "/".join((prefix, *address))


def split_device(topic: str) -> tuple[str, str] | None:
    """The inverse: a device topic's fixed part and the address under it, or
    ``None`` where the topic is no device row at all.

    A row is addressed exactly where its payload repeats the address, so
    `wanted/track` splits to an empty address and every other row wants at
    least one level. A bare addressed key names no device, and is no more a
    device topic than a name nobody declared."""
    for prefix, row in DEVICE_TOPICS.items():
        addressed = "addr" in row.fields
        if topic == prefix:
            return None if addressed else (prefix, "")
        if addressed and topic.startswith(prefix + "/"):
            return prefix, topic[len(prefix) + 1 :]
    return None


HELD = "held"
RUNNING = "running"
"""The two values of ``tc49/dispatch/state/run``. An enum and not a boolean:
the ordinary-shutdown drain adds ``draining`` as a third value here rather
than inventing a state of its own (#123). Not to be read as the ``held``
``grant_refused`` reason, which says a resource is locked by another train
and is a different thing on a different topic (CONTEXT.md)."""


ON = "on"
STOPPED = "stopped"
OFF = "off"
"""The three values of ``tc49/layout/state/power``: the layout's answer to
whether a train may move at all. `stopped` is an **emergency stop** — every
locomotive told to stand with the track still live — and `off` is the supply
removed. They differ for the person recovering, who clears one and switches
the other back on, and not for the dispatcher, which branches on "not `on`"
(ADR-0041). `stopped` and not `stop`, which is an aspect: a different thing
on a different topic."""


def is_state_topic(topic: str) -> bool:
    """Whether a topic is a state topic, read off the path: state is marked
    structurally by a ``state`` level under the component, so the split is a
    property of the name and not a list to keep (SYSTEM.md, rule 2).

    The mark is the **third** level and not the second from last, because a
    topic's name may go on past its own: an addressed device row is
    ``tc49/layout/state/wanted/point/dccex/5``, and reading backwards from
    the leaf would call that an event topic and drop its retained value
    (ADR-0043)."""
    levels = topic.split("/")
    return len(levels) > 3 and levels[2] == "state"


INBOUND = frozenset(topic for topic, row in TOPICS.items() if row.browser)
"""The topics a client writes: the panel's write surface, and what a broker's
ACL will grant it once the bridge is gone (ADR-0034). Named here rather than
in the bridge because the fact outlives the relay, and read off the rows'
marks rather than off a prefix — a topic now names the component that
responds to it, so the five gestures sit under `schedule` and `dispatch`
beside everything else those two answer, and only the mark says a page may
send them.

Event topics only. A page has concurrent instances — two tabs are two of
them — and concurrent writers may not write a state topic at all
(ADR-0035), and the bridge relies on it besides: a client's frame is
published from that client's own handler thread, and publishing a state topic
would write the bus's last-value map from there. So `browser=True` belongs on
event rows, and a state row must never carry it.

Gestures, never requests: `tc49/dispatch/request_submitted` carries no mark
and is refused inbound like any other unmarked topic, which is what makes the
scheduler's single-minter claim something the topic check enforces
(ADR-0036)."""


def leaf(topic: str) -> str:
    return topic.rsplit("/", 1)[-1]


LEAF_FIELDS: dict[str, tuple[str, ...]] = {
    leaf(topic): row.fields for topic, row in TOPICS.items()
}
