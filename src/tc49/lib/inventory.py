"""The event inventory: canonical payload field order per topic.

Mirrors the inventory table of SYSTEM.md. The trace's canonical key order
depends on this module; leaf names are globally unique across all topics
(tested), because the trace's ``event`` field is the leaf alone.

Two mappings, because a topic is named two ways. ``TOPICS`` is the transit-level
contract, one whole topic per row. ``DEVICE_TOPICS`` is the device vocabulary
under the layout interface (ADR-0043) — the desired half and the observed half
alike — where the row is fixed and the address is trailing levels a railroad's
wiring decides, so the row is keyed by what is knowable. The namespace is one:
a name is unique across both.

A topic names the component that **declares** it: the events that component
emits, and the requests it responds to. Nothing in a name says who sent a
request, and no responder may read or infer it (SYSTEM.md, rule 4).

Browser-writability is a mark on the row rather than a prefix to read:
``INBOUND`` below is the marked rows, so a page's write surface widens only
where somebody writes ``browser=True``.

Where a field's *values* are a closed set the contract names, they live here
too, beside the field they belong to: ``run``, ``power`` and ``mode`` are
those fields. What an **enum** is, and which way an unreadable one falls, is
CONTEXT.md.

``AT`` is the one field no app supplies: every state row leads with it and
the binding that publishes stamps it (#240).
"""

from typing import NamedTuple


class Topic(NamedTuple):
    """One inventory row: the payload's fields in the trace's canonical
    order, whether a browser may publish on the topic, and — on a device row —
    the payload field that repeats the address the topic carries, empty where
    the row carries no address."""

    fields: tuple[str, ...]
    browser: bool = False
    address: str = ""


AT = "at"
"""The **stamp** every state payload carries and no event payload does: the
run clock's reading when the value was published, in seconds since the
session started (`tc49.lib.clock`).

It leads the field order of every state row, so a trace line shows it in a
fixed place. What it is for is ordering: MQTT promises order only from one
publisher, on one topic, and only while nothing reconnects or retransmits
(ADR-0008), so a state topic reordered on the wire would keep the older
value for good. A consumer keeps the later stamp and ignores the earlier
one, whoever published it — `tc49.lib.payload.Ordering` (#240).

Stamped by the binding that publishes and never by an app, so no app
component reads a clock (ADR-0009). It orders messages **within one
session** and says nothing across a restart: the clock resets to zero every
run, which is why a value loaded from the durable file is re-stamped as it
is read (SYSTEM.md, ADR-0030)."""


TOPICS: dict[str, Topic] = {
    "tc49/layout/block_occupied": Topic(("block",)),
    "tc49/layout/block_vacated": Topic(("block",)),
    "tc49/layout/power_wanted": Topic(("power",), browser=True),
    "tc49/layout/state/power": Topic((AT, "power")),
    "tc49/layout/align": Topic(("connection", "transit", "points")),
    "tc49/layout/move": Topic(("train", "connection", "transit", "into", "speed")),
    "tc49/layout/mode_wanted": Topic(("train", "mode"), browser=True),
    "tc49/layout/throttle_wanted": Topic(("train", "speed"), browser=True),
    "tc49/layout/state/mode": Topic((AT, "modes")),
    "tc49/schedule/request_wanted": Topic(("train", "dest"), browser=True),
    "tc49/schedule/reversal_wanted": Topic(("train",), browser=True),
    "tc49/schedule/state/exhausted": Topic((AT, "exhausted")),
    "tc49/schedule/state/facing": Topic((AT, "facing")),
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
    "tc49/dispatch/state/run": Topic((AT, "run", "moving")),
    "tc49/dispatch/state/aspects": Topic((AT, "aspects")),
    "tc49/dispatch/state/disputed": Topic((AT, "trains", "blocks")),
    "tc49/dispatch/state/allocation": Topic(
        (AT, "trains", "crossing", "locks", "requests")
    ),
}


DEVICE_PREFIX = "tc49/layout/state/"
"""What every device row's key starts with, and what a trace ``event`` strips
to name one: ``wanted/traction``, ``wanted/point``, ``device/point``. A device
row is named by two levels where an ordinary row is named by one, because the
desired half of the vocabulary and the observed half address the same hardware
— ``point`` alone would not say which of the two a line records."""


DEVICE_TOPICS: dict[str, Topic] = {
    "tc49/layout/state/wanted/traction": Topic((AT, "addr", "speed"), address="addr"),
    "tc49/layout/state/wanted/function": Topic(
        (AT, "addr", "function", "value"), address="addr"
    ),
    "tc49/layout/state/wanted/point": Topic((AT, "addr", "position"), address="addr"),
    "tc49/layout/state/wanted/signal": Topic((AT, "addr", "aspect"), address="addr"),
    "tc49/layout/state/wanted/track": Topic((AT, "power")),
    "tc49/layout/state/device/sensor": Topic(
        (AT, "addr", "occupancy", "reason"), address="addr"
    ),
    "tc49/layout/state/device/point": Topic((AT, "addr", "position"), address="addr"),
    "tc49/layout/state/device/track": Topic((AT, "power")),
    "tc49/layout/state/device/link": Topic(
        (AT, "system", "link", "detail"), address="system"
    ),
}
"""The device vocabulary under the layout interface, both halves of it: the
`wanted/` rows are what the hardware should do and the `device/` rows are what
it reports back. One retained state topic per device either way, and one
writer per topic (rule 1) — `layout` writes every desired row, and an observed
row is written by whatever answers for that address, which is exactly one
thing, so no ownership table is needed anywhere (ADR-0043).

Keyed by the **fixed part** of the topic, the address being trailing levels
rather than a leaf, and repeated in the payload — as ``addr``, or as ``system``
on `device/link`, which is addressed by the hardware system whose link it
reports — so a trace line reads on its own. `wanted/track` and `device/track`
are the two rows that carry no address: a power district is a hardware-level
fact that does not reach the bus, so there is one railroad-wide power desired
and one observed, and a translator maps it onto however many districts it
drives (#217).

A **sensor** is addressed by the block end it watches, ``<block>.<end>``,
never by a camera's own identifier: the drawing carries the mapping and the
detector is configured with the names it must publish, so nothing above the
layout interface learns detector geometry (#194, ADR-0043). One topic per
sensor and never a whole-railroad map — a map would make one camera the writer
of every sensor on the railroad, and a second camera could then not join
(ADR-0035).

`device/point` is published only where the hardware actually reports a
position, and a commanded one is never echoed back as a measured one
(ADR-0022): on this railroad turnouts have no feedback, so the `dccex`
translator writes none. `device/link` is where a broken link becomes
observable, so a UI can say the command station is unreachable rather than the
railroad merely looking idle — reported at runtime to a person who can act on
it, which is where verifying a link belongs (ADR-0050, #217).

Separate from ``TOPICS`` rather than in it because ``TOPICS`` maps a whole
topic to its field order, and a device row's whole topic is not knowable until
a railroad is wired. What the two mappings share is the namespace: a name is
unique across both (tested).

SYSTEM.md, *Layout interface*, carries the values each field takes and the two
address rules — a traction or function address is bare and a point or signal
address names its system first."""


def device_topic(prefix: str, *address: str) -> str:
    """The topic a device sits on: a ``DEVICE_TOPICS`` key and the levels of
    its address. The two `track` rows take none and are their own topics."""
    return "/".join((prefix, *address))


def split_device(topic: str) -> tuple[str, str] | None:
    """The inverse: a device topic's fixed part and the address under it, or
    ``None`` where the topic is no device row at all.

    A row is addressed exactly where it names the field its payload repeats
    the address in, so the two `track` rows split to an empty address and every
    other row wants at least one level. A bare addressed key names no device,
    and is no more a device topic than a name nobody declared."""
    for prefix, row in DEVICE_TOPICS.items():
        addressed = bool(row.address)
        if topic == prefix:
            return None if addressed else (prefix, "")
        if addressed and topic.startswith(prefix + "/"):
            return prefix, topic[len(prefix) + 1 :]
    return None


HELD = "held"
RUNNING = "running"
DRAINING = "draining"
"""The three values of ``tc49/dispatch/state/run``, and of the ``run_wanted``
gesture that moves it. An enum and not a boolean, which is what let the
ordinary-shutdown **drain** take a third value here rather than invent a
state of its own (#123, #294).

They differ by what the dispatcher will commit. `running` admits, launches
and grants; `draining` admits and grants a train already moving but launches
nothing, so the work under way runs out and nothing takes its place; `held`
admits and commits nothing at all. `draining` is therefore a value the
dispatcher writes as well as reads: it ends itself at `held` the first moment
no train is active and none is crossing, and that transition is the drain's
completion (ADR-0037).

Not to be read as the ``held`` ``grant_refused`` reason, which says a
resource is locked by another train and is a different thing on a different
topic (CONTEXT.md).

``moving`` rides beside them on the state row and is not a fourth value: a
boolean, true while any train is **active** or **crossing**, so a power cut
now would strand it (CONTEXT.md, **Moving**; ADR-0062). It is orthogonal to
the three — a `held` run can be moving, because a move already granted runs
to its sensor, and a `running` run with nothing granted is not — and it is
what says the drain's completion apart from a person's HOLD, which writes the
same word with trains still rolling (#406)."""


AUTOMATIC = "automatic"
MANUAL = "manual"
"""The two values of ``mode`` on ``tc49/layout/mode_wanted``, and of every
entry in the ``modes`` map on ``tc49/layout/state/mode``: who turns a train's
throttle. `automatic` is the resting value — taking a train in a throttle
makes it `manual` and releasing it puts it back — so a train the map does not
name is `automatic`. An unreadable value is **dropped** and the train's mode
stays where it was: falling to `manual` would hand a train to a person who is
not there, and falling to `automatic` would take one out of the hands of a
person who is (#207). Not a mode of the *system*: a manual train is still
dispatched, still holds its block and still may be granted, and *manual* names
only who turns the throttle (CONTEXT.md)."""


ON = "on"
STOPPED = "stopped"
OFF = "off"
"""The three values of ``tc49/layout/state/power``: the layout's answer to
whether a train may move at all. `stopped` is an **emergency stop** — every
locomotive told to stand with the track still live — and `off` is the supply
removed. They differ for the person recovering, who clears one and switches
the other back on, and not for the dispatcher, which branches on "not `on`"
(ADR-0041). `stopped` and not `stop`, which is an aspect: a different thing
on a different topic.

The same three on ``tc49/layout/power_wanted``, which is the command
direction of the one axis: the closed set goes wherever the field goes, as
``run`` does on its own gesture. A power command is applied on arrival —
there is no beat to quantise it against (#243) — and it changes no lock and
grants nothing, so it races with nothing the dispatcher is deciding
(ADR-0051)."""


OCCUPIED = "occupied"
CLEAR = "clear"
UNKNOWN = "unknown"
"""The three values of ``occupancy`` on
``tc49/layout/state/device/sensor/<block>.<end>``: what one detector sees at
the block end it watches.

A **level** and not an edge — presence is a thing that can be asked for at any
time — so the pair a block's two detectors report is what `layout` folds into
`tc49/layout/block_occupied` and `tc49/layout/block_vacated`, the anonymous
events everything above the layout interface reads (#288).

`unknown` is a value and not an absence: the detector knows *why* it cannot
say — no model, not calibrated, drift — and the free-text ``reason`` beside it
carries that for a person, while a consumer treats `unknown` as **no
information** about that end and keeps whatever level it last had
(CONTEXT.md, **detector**)."""


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
responds to it, so the eight gestures sit under `schedule`, `dispatch` and
`layout` beside everything else those three answer, and only the mark says a
page may send them.

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
