"""The event inventory: canonical payload field order per topic.

Mirrors the inventory table of BUS.md. The trace's canonical key order
depends on this module; leaf names are globally unique across all topics
(tested), because the trace's ``event`` field is the leaf alone.

Three mappings, because a topic is named three ways. ``TOPICS`` is the
transit-level contract, one whole topic per row. ``DEVICE_TOPICS`` is the device
vocabulary under the layout interface (ADR-0043) — the desired half and the
observed half alike — where the row is fixed and the address is trailing levels
a railroad's wiring decides, so the row is keyed by what is knowable.
``WIDGET_TOPICS`` is the drawing's widgets under `ui` (ADR-0087), where the row
is fixed and the widget's name is the last level. The namespace is one: a name
is unique across all three.

A topic names the component that **declares** it: the events that component
emits, and the requests it responds to. Nothing in a name says who sent a
request, and no responder may read or infer it (BUS.md, rule 4).

Browser-writability is a mark on the row rather than a prefix to read:
``INBOUND`` below is the marked rows, so a page's write surface widens only
where somebody writes ``browser=True``.

Where a field's *values* are a closed set the contract names, they live here
too, beside the field they belong to: ``run``, ``mode``, ``driving``,
``power``, the
supply, ``occupancy``, ``position``, ``aspect``, the ``grant_refused``
``reason`` and ``link``. The ``request_rejected`` and ``request_cancelled``
reasons are ``tc49.lib.rejection`` and ``tc49.lib.cancellation``. What an
**enum** is, and which way an unreadable one falls, is BUS.md, payload
schemas.

``AT`` is the one field no app supplies: every state row leads with it and
the binding that publishes stamps it (#240).
"""

from enum import StrEnum
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
component reads a clock (ADR-0009). It orders messages **within one run**
and says nothing across a restart: the in-process clock resets to zero every
run and the broker stamps from wall time, so what a restarted app adopts is
the oldest thing it knows (BUS.md, ADR-0030)."""


TOPICS: dict[str, Topic] = {
    # Which railroad this broker runs, and so what every row under it is
    # about: `name` is the railroad as the store lists it (ADR-0059).
    "tc49/layout/state/railroad": Topic((AT, "name", "built")),
    # And the gesture that moves it: a person choosing which railroad the
    # apps run, while they run (ADR-0060). `railroad` rather than `name`,
    # because a leaf's fields are read beside its own row and this one names
    # the thing wanted rather than naming itself.
    "tc49/layout/railroad_wanted": Topic(("railroad",), browser=True),
    # `layout` saying it is up, once a second while built on a railroad, for
    # whatever cuts track power when it stops (#716). Nothing to carry.
    "tc49/layout/alive_confirmed": Topic(()),
    "tc49/layout/block_occupied": Topic(("block",)),
    "tc49/layout/block_vacated": Topic(("block",)),
    "tc49/layout/power_wanted": Topic(("power",), browser=True),
    "tc49/layout/state/power": Topic((AT, "power")),
    "tc49/layout/align": Topic(("connection", "transit", "points")),
    "tc49/layout/move": Topic(("train", "connection", "transit", "into", "speed")),
    "tc49/layout/throttle_wanted": Topic(("train", "speed", "throttle"), browser=True),
    # At most one throttle holds a train (ADR-0079). A throttle is named by
    # the id its page mints when it opens; `null` releases a train whoever
    # holds it. `throttle_alive` is said once a second while a throttle holds
    # a train, and `layout` releases the trains of one it has not heard for
    # 5 s. `taken` maps train to throttle id, empty when `layout` starts.
    "tc49/layout/take_wanted": Topic(("train", "throttle"), browser=True),
    "tc49/layout/throttle_alive": Topic(("throttle",), browser=True),
    "tc49/layout/state/taken": Topic((AT, "taken")),
    # A throttle switches one of its train's functions by the name the
    # catalogue gives it, and `layout` writes the `wanted/function` row of the
    # first addressed car declaring that name (#849). `functions` maps each
    # train to its functions by name, each to the bit its row carries; a train
    # or name with no row is absent, which reads off.
    "tc49/layout/function_wanted": Topic(
        ("train", "throttle", "function", "on"), browser=True
    ),
    "tc49/layout/state/functions": Topic((AT, "functions")),
    # The railroad's one driving mode, asked for at any power and stated by
    # `layout`, which comes up `manual` (ADR-0079).
    "tc49/layout/driving_wanted": Topic(("driving",), browser=True),
    "tc49/layout/state/driving": Topic((AT, "driving")),
    # The fast clock, once a real second while a railroad is loaded:
    # `time` in whole fast-clock seconds since midnight, `speed_up` the fast
    # seconds per real second (ADR-0090). Nothing in the control path reads
    # it (ADR-0044).
    "tc49/layout/state/clock": Topic((AT, "time", "speed_up")),
    "tc49/schedule/request_wanted": Topic(("train", "dest"), browser=True),
    "tc49/schedule/reversal_wanted": Topic(("train",), browser=True),
    "tc49/schedule/state/exhausted": Topic((AT, "exhausted")),
    "tc49/schedule/state/facing": Topic((AT, "facing")),
    # A train's later request starts where its earlier one ends (#820):
    # `after` is the id of the train's request this one follows, and is left
    # out where it follows none. With it `depart` is `null`, the departure end
    # being the dispatcher's once the earlier request has arrived (ADR-0080).
    "tc49/dispatch/request_submitted": Topic(
        ("id", "train", "depart", "dest", "after")
    ),
    "tc49/dispatch/placement_wanted": Topic(("train", "block"), browser=True),
    # The waiting requests are a list a person orders (ADR-0080): one
    # request is cancelled by its id, and one moved in front of `before`, or
    # to the end of the list where `before` is `null`.
    "tc49/dispatch/cancel_wanted": Topic(("id",), browser=True),
    "tc49/dispatch/reorder_wanted": Topic(("id", "before"), browser=True),
    "tc49/dispatch/point_wanted": Topic(("addr", "position"), browser=True),
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
    # True while any train is crossing, and what `layout` reads to
    # end a drain (ADR-0078).
    "tc49/dispatch/state/moving": Topic((AT, "moving")),
    "tc49/dispatch/state/aspects": Topic((AT, "aspects")),
    "tc49/dispatch/state/disputed": Topic((AT, "trains", "blocks")),
    "tc49/dispatch/state/unfit": Topic((AT, "trains")),
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
    "tc49/layout/state/device/track": Topic((AT, "power", "reason")),
    "tc49/layout/state/device/link": Topic((AT, "id", "link", "detail"), address="id"),
    "tc49/layout/state/device/refused": Topic(
        (AT, "id", "addr", "detail"), address="id"
    ),
}
"""The device vocabulary under the layout interface, both halves of it: the
`wanted/` rows are what the hardware should do and the `device/` rows are what
it reports back. One retained state topic per device either way, and one
writer per topic (rule 1) — `layout` writes every desired row, and an observed
row is written by whatever answers for that address, which is exactly one
thing, so no ownership table is needed anywhere (ADR-0043).

Keyed by the **fixed part** of the topic, the address being trailing levels
rather than a leaf, and repeated in the payload — as ``addr``, or as ``id`` on
`device/link`, which is keyed by whatever the publisher calls itself — so a
trace line reads on its own. `wanted/track` and `device/track` are the two
rows that carry no address: a power district is a hardware-level fact that
does not reach the bus, so there is one railroad-wide power desired and one
observed, and a translator maps it onto however many districts it drives
(#217).

A **sensor** is addressed by the block end it watches, ``<block>.<end>``,
never by a camera's own identifier, and by that on every railroad, so a trace
is comparable between installations. The drawing carries the name the hardware
knows each sensor by, one per block end and defaulting to that same string,
and whoever publishes the row reads it from the store, so the name reaches no
payload and nothing above the layout interface learns detector geometry (#194,
ADR-0043, ADR-0063). One topic per
sensor and never a whole-railroad map — a map would make one camera the writer
of every sensor on the railroad, and a second camera could then not join
(ADR-0035).

`wanted/function`'s ``value`` is a **boolean**, where every other desired
row carries a name or a number. A function is one bit on the wire wherever it
was checked, so the row carries the bit and the catalogue carries a name on a
number and no value list at all; what people mean by a range — volume,
brightness, momentum — is written as decoder configuration, a different
capability that would be a different row (ADR-0063).
``tc49.lib.payload.desired_function`` is the reader.

`device/point` is published only where the hardware actually reports a
position, and a commanded one is never echoed back as a measured one
(ADR-0022): on this railroad turnouts have no feedback, so the translator
driving them writes none. `device/link` is where a participant that knows it
cannot reach its hardware says so, so a UI can say the command station is
unreachable rather than the railroad merely looking idle — reported at runtime
to a person who can act on it, which is where verifying a link belongs
(ADR-0050, #217). Its ``id`` is whatever the publisher calls itself and
appears in no drawing, no configuration and no list of ours; it is a key
because two participants publishing on one row would erase each other, and
`layout` folds the supply to `off` for any id it has heard say `down` without
ever waiting for one it has not heard (ADR-0058, ADR-0059). `device/track`
carries the free-text `reason` for the same person: the participant that
reports the supply and cannot reach it says why on the row itself, rather than
leaving them a second row to find. It also names a district the hardware cut
itself, with `power` `on` while the other districts are powered — a district
reaches no topic, and that frame would otherwise read like a railroad with
nothing wrong with it (ADR-0050, BUS.md). A reason about the link takes
precedence, and `layout` reads `power` alone either way.

`device/refused` is no device state at all, which is why it is the one
observed row nothing folds: it is the publisher's report on its own last
exchange, keyed by whatever it calls itself as `device/link` is, carrying the
``addr`` the refused command named where it had one and free text for the
reason. Each refusal overwrites the last, so nothing has to remember which
addresses are refusing — the table no translator holds — and a UI that wants a
per-device view builds it from the stream. What it catches is misconfiguration
— an address the hardware does not have, a value out of range, an aspect a
mast will not accept — which is common and otherwise entirely silent; what it
misses is hardware that answers and does not obey, which no protocol reports.
A refusal that is published happened, and one that is not published is no
evidence that none occurred: where a participant cannot attribute a refusal to
its own command it publishes nothing, and each translator's own doc says
which those are (ADR-0063, #463). `layout` does not read it — nothing
branches on it, and it is there for a person.

Separate from ``TOPICS`` rather than in it because ``TOPICS`` maps a whole
topic to its field order, and a device row's whole topic is not knowable until
a railroad is wired. What the two mappings share is the namespace: a name is
unique across both (tested).

BUS.md, *Device vocabulary*, carries the values each field takes. An
address is the string the drawing carries and the hardware answers to, with no
system level in front of it: whatever is wired subscribes the desired rows and
acts on the addresses it recognises, and one nobody answers to does no harm
(ADR-0059)."""


WIDGET_TOPICS: dict[str, Topic] = {
    "tc49/ui/state/text": Topic(()),
    "tc49/ui/state/toggle": Topic((), browser=True),
    "tc49/ui/button": Topic((), browser=True),
}
"""The rows of the drawing's widgets, under `ui` (ADR-0087). Keyed by the
topic without the widget's name, which is the one level past the key and is
typed in the drawing, unique within it: `tc49/ui/state/text/current` is the
text widget named `current`. A client builds the topic from the key and the
name.

No row carries a field. A widget payload is raw — not JSON control defines,
and no `at` — and control carries it without reading it: a text row is UTF-8
text the page shows as it arrives, rendering the ANSI SGR codes for bold, red,
amber and green and removing any other code; a toggle row is the toggle's on
payload or its off payload as typed in the drawing, and a page reads the
position by comparing the row with the two, a row matching neither, or no row,
showing neither; a button row is the payload typed for the button (ADR-0087
decision 4). So ``AT`` does not lead a widget's state row, and the trace, which runs only on the
in-process bus where no widget row is published, does not name one.

Any writer, on a state row too: the exception to rule 1 that ADR-0087
decision 3 makes, because a widget row is always the whole value and the last
one written is the right one. Two writers of one text row overwrite each
other, which is the writers' business. A text row carries no browser mark,
because no page writes one. A toggle row carries it, because a page writes the
position a person presses: the one state row with the mark (ADR-0087 decision
3), and the exception to ``INBOUND``'s rule below. A button row is an event and
carries the mark too: a page publishes it once per press, whatever the track
power, and nothing keeps it (ADR-0087 decisions 2 and 3)."""


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


AUTOMATIC = "automatic"
MANUAL = "manual"
DRIVINGS = (MANUAL, AUTOMATIC)
"""The closed set of ``driving`` on ``tc49/layout/state/driving`` and on the
``tc49/layout/driving_wanted`` gesture: the railroad's one **driving mode**
(ADR-0079): in `manual` people drive every train, and in `automatic` the
driver drives every train no throttle holds. The dispatcher
routes the same in both.

`manual` first, because it is where the railroad comes up and what an
unreadable state payload reads as: ``tc49.lib.payload.driving``. A gesture
naming anything else is dropped (``tc49.lib.payload.wanted_driving``), and
one is accepted at any power."""


ON = "on"
DRAINING = "draining"
OFF = "off"
"""The values of ``tc49/layout/state/power``: the layout's answer to whether a
train may move at all, and the one switch a person turns (ADR-0078). `on`
lets the dispatcher route; `draining` keeps the supply on while each moving
train stops and nothing new starts, until ``tc49/dispatch/state/moving`` reads
false and `layout` switches it off; `off` is the supply removed.

The same values on ``tc49/layout/power_wanted``, which is the command
direction of the one axis: the closed set goes wherever the field goes. A
plain `off` there is the emergency stop, applied at once in every state, and
`draining` the ordinary shutdown, answered from `on` only. A power command is
applied on arrival — there is no beat to quantise it against (#243) — and it
changes no lock and grants nothing, so it races with nothing the dispatcher is
deciding (ADR-0051).

The row the fold below reads is not one of them. ``SUPPLY`` is its own set of
two, and `draining` is the thing no publisher can report (ADR-0063)."""


POWERS = (ON, DRAINING, OFF)
"""The closed set of ``tc49/layout/state/power`` as a reader takes it:
``tc49.lib.payload.power`` reads each as itself and anything else as `off`."""


SUPPLY = (ON, OFF)
"""The two values of ``tc49/layout/state/device/track``: what the hardware
reports about the supply, and two where the row it folds into carries more.

A drain keeps the rails live, so the supply reads `on` through one and there
is nothing else it could truthfully read (ADR-0063). ``wanted/track`` carries
the same two: a translator is told to switch the supply, never to drain it.
``tc49.lib.payload.supply`` is the reader, and a frame outside this set falls
the way every unreadable state frame falls."""


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
(GLOSSARY.md, **detector**)."""


CLOSED = "closed"
THROWN = "thrown"
"""The two positions a person may ask a point for, ``position`` on
``tc49/dispatch/point_wanted``: the same two a way wants its points in on
``tc49/layout/align``. The gesture is read against them, so a word outside
the two is dropped there rather than carried on to a point (ADR-0068)."""


class Aspect(StrEnum):
    """The three values of ``aspect`` on ``tc49/dispatch/move_granted``, and
    of every entry in ``tc49/dispatch/state/aspects``: what a signal shows,
    read off how far ahead the dispatcher has locked (ADR-0025). A class and
    not three names, because `clear` is also an occupancy."""

    STOP = "stop"
    CAUTION = "caution"
    CLEAR = "clear"


class Refusal(StrEnum):
    """The three values of ``reason`` on ``tc49/dispatch/grant_refused``: the
    move was unsafe, a resource it needs is held by another train, or a
    transit it needs conflicts with one locked at the same connection. A
    class and not three names, because `held` is also a run."""

    UNSAFE = "unsafe"
    HELD = "held"
    TRANSIT_CONFLICT = "transit_conflict"


class Link(StrEnum):
    """The two values of ``link`` on
    ``tc49/layout/state/device/link/<id>``: whether a participant can reach
    the hardware it drives."""

    UP = "up"
    DOWN = "down"


def is_state_topic(topic: str) -> bool:
    """Whether a topic is a state topic, read off the path: state is marked
    structurally by a ``state`` level under the component, so the split is a
    property of the name and not a list to keep (BUS.md, rule 2).

    The mark is the **third** level and not the second from last, because a
    topic's name may go on past its own: an addressed device row is
    ``tc49/layout/state/wanted/point/5``, and reading backwards from
    the leaf would call that an event topic and drop its retained value
    (ADR-0043)."""
    levels = topic.split("/")
    return len(levels) > 3 and levels[2] == "state"


INBOUND = frozenset(topic for topic, row in TOPICS.items() if row.browser)
"""The topics a client writes: the page's write surface, and what a broker's
ACL would grant it were one built (ADR-0034, ADR-0059 decision 4). Read off
the rows' marks rather than off a prefix — a topic names the component that
responds to it, so the fifteen gestures sit under `schedule`, `dispatch` and
`layout` beside everything else those three answer, and only the mark says a
page may send them.

Event topics only. A page has concurrent instances — two tabs are two of
them — and concurrent writers may not write a state topic at all
(ADR-0035). So `browser=True` belongs on event rows, and a state row here must
never carry it. The one exception is outside ``TOPICS``: a toggle's row,
`tc49/ui/state/toggle/<name>` in ``WIDGET_TOPICS``, is a state row with the
mark, because it is always the whole value and the last one written is the
right one (ADR-0087 decision 3). It is a pattern the drawing completes, not a
whole topic, so it is not in this set; a page reads its mark off
``WIDGET_TOPICS``, as it does a button's, `tc49/ui/button/<name>`.

Gestures, never requests: `tc49/dispatch/request_submitted` carries no mark
and is refused inbound like any other unmarked topic, which is what makes the
scheduler's single-minter claim something the topic check enforces
(ADR-0036)."""


def leaf(topic: str) -> str:
    return topic.rsplit("/", 1)[-1]


LEAF_FIELDS: dict[str, tuple[str, ...]] = {
    leaf(topic): row.fields for topic, row in TOPICS.items()
}
