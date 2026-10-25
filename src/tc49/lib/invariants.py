"""The invariants: what an ADR says the bus shows, read off the retained values
(ADR-0096).

An **invariant** reads only what the bus shows, never an app's internal state,
so it describes the railroad rather than the code and holds through a rewrite
of the app that keeps it (GLOSSARY.md, **Invariant**). Each one here is a
function named for the ADR that states it, `adr_<nnnn>_<short_name>`, and the
module is the list of which ADRs state invariants: an issue that adds an ADR
stating one adds its function to `INVARIANTS`.

A function takes a `View` — the retained rows, the loaded drawing and its
roster — and answers one line per breach, `[]` where it holds. Like every
reader of a payload it never raises (BUS.md, rule 4): a row that cannot be
read is read as the readers in `tc49.lib.payload` read it, and a name the
drawing does not hold is a breach where the rule is about the drawing and is
passed over where it is not.

When one is checked is the caller's, and `cross_app` is what it decides by:
an invariant over one app's rows holds after every message, one over several
apps' only once nothing is left to deliver (ADR-0096, decision 3). Nothing
here runs on the railroad: the property suite and the stateful tests call
these (decision 4).

A **history invariant** reads what the messages so far have said as well: a
`Record` kept by observing each one, since some of what a rule is about — a
block's occupancy, for one — is only ever an event (ADR-0096, decision 1). Its
function is handed the record, the view and the message, before the record
observes it, and once with `QUIET` when nothing is left to deliver, which is
where a rule that one message is followed by another is breached. One over
several apps' topics is checked only where every subscriber sees one order
(decision 3).

`ADR-0026` holds only where the dispatcher locks `Incremental`. The strategy
is not on the bus, so the `View` carries no field for it and the caller that
knows it leaves that invariant out.
"""

from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import cast

from tc49.lib.bus import Payload
from tc49.lib.inventory import DRAINING, OFF, ON, Aspect, is_state_topic
from tc49.lib.layout import (
    Layout,
    block_of,
    connected_end,
    facing_ends,
    transit_ends,
)
from tc49.lib.payload import (
    chosen,
    grant,
    granted_aspect,
    kept_allocation,
    kept_facing,
    moving,
    named_train,
    occupancy,
    placement,
    power,
    readable_id,
    shown_aspects,
    wanted_power,
)
from tc49.lib.roster import Roster

ALLOCATION = "tc49/dispatch/state/allocation"
ASPECTS = "tc49/dispatch/state/aspects"
MOVING = "tc49/dispatch/state/moving"
UNFIT = "tc49/dispatch/state/unfit"
FACING = "tc49/schedule/state/facing"
POWER = "tc49/layout/state/power"
DISPUTED = "tc49/dispatch/state/disputed"
ROUTE_CHOSEN = "tc49/dispatch/route_chosen"
MOVE_GRANTED = "tc49/dispatch/move_granted"
LOCK_GRANTED = "tc49/dispatch/lock_granted"
LOCK_RELEASED = "tc49/dispatch/lock_released"
TRAIN_PLACED = "tc49/dispatch/train_placed"
TRAIN_REMOVED = "tc49/dispatch/train_removed"
REQUEST_COMPLETED = "tc49/dispatch/request_completed"
REQUEST_CANCELLED = "tc49/dispatch/request_cancelled"
REQUEST_REJECTED = "tc49/dispatch/request_rejected"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REVERSAL_WANTED = "tc49/schedule/reversal_wanted"
BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"
POWER_WANTED = "tc49/layout/power_wanted"

ENDED = (REQUEST_COMPLETED, REQUEST_CANCELLED, REQUEST_REJECTED)
"""The three ways a request ends without a placement (ADR-0049)."""

WRITERS = ("tc49/dispatch/", "tc49/schedule/", "tc49/layout/")
"""The prefix each writing app's topics carry: the dispatcher's, the
scheduler's and `layout`'s (BUS.md, rule 1)."""


@dataclass(frozen=True)
class View:
    """What an invariant reads: the retained values — `bus.last_values` — and
    the drawing and roster the run was built on, which no row carries."""

    rows: Mapping[str, Payload]
    layout: Layout
    roster: Roster


@dataclass(frozen=True)
class Invariant:
    adr: str  # "0093"
    states: str  # the rule, one plain sentence
    reads: tuple[str, ...]  # the topics it reads
    breaches: Callable[[View], list[str]]  # one line per breach; [] when it holds


def cross_app(invariant: "Invariant | HistoryInvariant") -> bool:
    """True when `reads` names topics of more than one writing app: tc49/dispatch/ is
    the dispatcher's, tc49/schedule/ the scheduler's, tc49/layout/ layout's (BUS.md, rule 1).
    """
    writers = {
        prefix
        for topic in invariant.reads
        for prefix in WRITERS
        if topic.startswith(prefix)
    }
    return len(writers) > 1


# -- reading the rows ---------------------------------------------------------


@dataclass(frozen=True)
class _Request:
    """One entry of the allocation's `requests`, as far as it can be read."""

    id: str
    train: str
    dest: tuple[str, ...]
    after: str | None
    route: tuple[str, ...] | None  # interleaved block, transit, block, ...


def _fields(payload: object) -> dict[str, object]:
    return cast(dict[str, object], payload) if isinstance(payload, dict) else {}


def _trains(view: View) -> dict[str, str]:
    kept = kept_allocation(view.rows.get(ALLOCATION))
    return kept.trains if kept is not None else {}


def _crossing(view: View) -> dict[str, str]:
    kept = kept_allocation(view.rows.get(ALLOCATION))
    return kept.crossing if kept is not None else {}


def _locks(view: View) -> dict[str, str]:
    """The allocation's lock table, resource to holder, an entry at a time as
    `kept_allocation` reads its two maps."""
    return _locks_in(view.rows.get(ALLOCATION))


def _locks_in(allocation: object) -> dict[str, str]:
    locks = _fields(allocation).get("locks")
    if not isinstance(locks, dict):
        return {}
    return {
        resource: holder
        for resource, holder in cast(dict[object, object], locks).items()
        if isinstance(resource, str) and isinstance(holder, str)
    }


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        return None
    return tuple(cast(list[str], items))


def _requests(view: View) -> list[_Request]:
    """The allocation's requests in list order, each one that cannot be read
    passed over."""
    return _requests_in(view.rows.get(ALLOCATION))


def _requests_in(allocation: object) -> list[_Request]:
    listed = _fields(allocation).get("requests")
    if not isinstance(listed, list):
        return []
    read: list[_Request] = []
    for entry in cast(list[object], listed):
        fields = _fields(entry)
        rid, train, after = fields.get("id"), fields.get("train"), fields.get("after")
        dest = _strings(fields.get("dest"))
        if not isinstance(rid, str) or not isinstance(train, str) or dest is None:
            continue
        read.append(
            _Request(
                rid,
                train,
                dest,
                after if isinstance(after, str) else None,
                _strings(fields.get("route")),
            )
        )
    return read


def _unfit(view: View) -> list[str]:
    """The trains `state/unfit` lists."""
    listed = _fields(view.rows.get(UNFIT)).get("trains")
    if not isinstance(listed, list):
        return []
    return [
        train
        for entry in cast(list[object], listed)
        if isinstance(train := _fields(entry).get("train"), str)
    ]


@dataclass(frozen=True)
class _Journey:
    """A started request's route, split, with where its train is recorded."""

    train: str
    blocks: tuple[str, ...]
    transits: tuple[str, ...]
    standing: int  # index into `blocks` of the block the train is recorded in


def _journeys(view: View) -> Iterator[_Journey]:
    """Every started request whose train is recorded in a block of its route.
    A route alternates block and transit, from the block it starts in to the
    one it arrives in (BUS.md, `state/allocation`)."""
    trains = _trains(view)
    for request in _requests(view):
        route = request.route
        if route is None or len(route) % 2 == 0:
            continue
        blocks, transits = route[0::2], route[1::2]
        recorded = trains.get(request.train)
        if recorded in blocks:
            yield _Journey(request.train, blocks, transits, blocks.index(recorded))


def _locked_ahead(locks: Mapping[str, str], journey: _Journey, index: int) -> int:
    """How many blocks of the route past `index` are locked to its train,
    counted until the first that is not."""
    depth = 0
    for block in journey.blocks[index + 1 :]:
        if locks.get(block) != journey.train:
            break
        depth += 1
    return depth


def _known_transit(layout: Layout, transit: str) -> bool:
    connection, _, name = transit.partition(".")
    held = layout.connections.get(connection)
    return held is not None and name in held.transits


# -- the invariants -----------------------------------------------------------


def adr_0001_pass_through(view: View) -> list[str]:
    """A route enters each block by one end and leaves by the other, so a
    terminal block is only first or last on a route
    ([ADR-0001](../../../docs/adr/0001-no-reversal-within-a-route.md))."""
    lines: list[str] = []
    for request in _requests(view):
        route = request.route
        if route is None:
            continue
        blocks, transits = route[0::2], route[1::2]
        for i, block in enumerate(blocks[1:-1], start=1):
            if block in view.layout.terminal_blocks:
                lines.append(f"{request.id} passes through terminal block {block}")
            entered = transit_ends(view.layout, block, transits[i - 1])
            left = transit_ends(view.layout, block, transits[i])
            if entered is None or left is None:
                lines.append(f"{request.id} has a transit that misses {block}")
            elif entered[0] == left[0]:
                lines.append(f"{request.id} enters and leaves {block} by {left[0]}")
    return lines


def adr_0006_no_conflicting_transits(view: View) -> list[str]:
    """No two trains hold transits that conflict: a pair not listed
    `concurrent` at their connection
    ([ADR-0006](../../../docs/adr/0006-conflicts-declared-by-inversion.md))."""
    held = sorted(
        (resource, holder)
        for resource, holder in _locks(view).items()
        if _known_transit(view.layout, resource)
    )
    lines: list[str] = []
    for i, (one, by) in enumerate(held):
        for other, also in held[i + 1 :]:
            if by != also and view.layout.conflicts(one, other):
                lines.append(f"{one} held by {by} conflicts with {other} of {also}")
    return lines


def adr_0007_route_ends_at_an_arrival(view: View) -> list[str]:
    """A started request's route ends at one of the arrival ends the request
    named ([ADR-0007](../../../docs/adr/0007-requests-name-a-set-of-arrival-ends.md)).
    """
    lines: list[str] = []
    for request in _requests(view):
        route = request.route
        if route is None or len(route) < 3:
            continue
        ends = transit_ends(view.layout, route[-1], route[-2])
        arrival = ends[0] if ends is not None else None
        if arrival not in request.dest:
            lines.append(
                f"{request.id} arrives by {arrival}, not one of {list(request.dest)}"
            )
    return lines


def adr_0019_terminal_facing(view: View) -> list[str]:
    """A train standing in a terminal block faces that block's one connected
    end ([ADR-0019](../../../docs/adr/0019-facing-is-scheduler-state.md)).

    A crossing train stands in no block, and a facing naming another block is
    not one held for the block the train stands in, so neither is read."""
    facing = kept_facing(view.rows.get(FACING)) or {}
    crossing = _crossing(view)
    lines: list[str] = []
    for train, block in sorted(_trains(view).items()):
        held = facing.get(train)
        if (
            block not in view.layout.terminal_blocks
            or train in crossing
            or held is None
            or block_of(held) != block
        ):
            continue
        connected = connected_end(view.layout, f"{block}.A")
        if facing_ends(held)[1] != connected:
            lines.append(f"{train} in terminal {block} faces {held}, not {connected}")
    return lines


def adr_0026_two_blocks_ahead(view: View) -> list[str]:
    """Under `Incremental`, no train holds more than two blocks beyond the
    block it is recorded in
    ([ADR-0026](../../../docs/adr/0026-two-blocks-ahead-is-full-speed.md))."""
    locks = _locks(view)
    lines: list[str] = []
    for journey in _journeys(view):
        ahead = [
            block
            for block in journey.blocks[journey.standing + 1 :]
            if locks.get(block) == journey.train
        ]
        if len(ahead) > 2:
            lines.append(f"{journey.train} holds {ahead} ahead")
    return lines


def adr_0029_block_with_its_transit(view: View) -> list[str]:
    """A block held ahead of a train is held together with the transit that
    leads into it
    ([ADR-0029](../../../docs/adr/0029-a-lock-held-ahead-is-a-block-the-check-must-see.md)).
    """
    locks = _locks(view)
    lines: list[str] = []
    for journey in _journeys(view):
        for i in range(journey.standing + 1, len(journey.blocks)):
            block, transit = journey.blocks[i], journey.transits[i - 1]
            if locks.get(block) == journey.train and locks.get(transit) != (
                journey.train
            ):
                lines.append(f"{journey.train} holds {block} ahead without {transit}")
    return lines


def adr_0039_unplaced_has_no_facing(view: View) -> list[str]:
    """A train that is not placed has no facing
    ([ADR-0039](../../../docs/adr/0039-a-train-may-be-off-the-layout.md))."""
    facing = kept_facing(view.rows.get(FACING)) or {}
    trains = _trains(view)
    return [
        f"{train} faces {held} and is not placed"
        for train, held in sorted(facing.items())
        if train not in trains
    ]


def adr_0062_moving_while_crossing(view: View) -> list[str]:
    """`moving` is true exactly while some train is crossing
    ([ADR-0062](../../../docs/adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md),
    as narrowed by #844)."""
    shown = moving(view.rows.get(MOVING))
    crossing = sorted(_crossing(view))
    if shown == bool(crossing):
        return []
    return [f"moving reads {str(shown).lower()} with {crossing or 'none'} crossing"]


def adr_0071_placed_where_it_fits(view: View) -> list[str]:
    """Every placed train stands in a block of the loaded drawing that is long
    enough for it
    ([ADR-0071](../../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)).
    A train the roster does not hold has no length to fit."""
    lengths = view.roster.lengths()
    lines: list[str] = []
    for train, block in sorted(_trains(view).items()):
        length = view.layout.blocks.get(block)
        if length is None:
            lines.append(f"{train} stands in {block}, which the drawing has not")
        elif train in lengths and lengths[train] > length:
            lines.append(f"{train} of {lengths[train]} stands in {block} of {length}")
    return lines


def adr_0071_unfit_is_not_placed(view: View) -> list[str]:
    """A train listed on `unfit` is not placed
    ([ADR-0071](../../../docs/adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)).
    """
    trains = _trains(view)
    return [
        f"{train} is unfit and placed in {trains[train]}"
        for train in _unfit(view)
        if train in trains
    ]


def adr_0076_placed_holds_its_block(view: View) -> list[str]:
    """A placed train holds the lock on the block it stands in
    ([ADR-0076](../../../docs/adr/0076-a-broken-lock-table-holds-the-run.md))."""
    locks = _locks(view)
    return [
        f"{train} stands in {block}, which is locked to {locks.get(block, 'nobody')}"
        for train, block in sorted(_trains(view).items())
        if locks.get(block) != train
    ]


def adr_0076_crossing_is_placed(view: View) -> list[str]:
    """A crossing train is placed
    ([ADR-0076](../../../docs/adr/0076-a-broken-lock-table-holds-the-run.md))."""
    trains = _trains(view)
    return [
        f"{train} is crossing {transit} and not placed"
        for train, transit in sorted(_crossing(view).items())
        if train not in trains
    ]


def adr_0080_after_follows(view: View) -> list[str]:
    """A request chained with `after` is listed after the request it follows
    ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
    """
    requests = _requests(view)
    place = {request.id: i for i, request in enumerate(requests)}
    return [
        f"{request.id} follows {request.after} and is listed before it"
        for i, request in enumerate(requests)
        if request.after is not None and place.get(request.after, -1) > i
    ]


def _aspect_of(depth: int) -> str:
    if depth >= 2:
        return Aspect.CLEAR
    return Aspect.CAUTION if depth else Aspect.STOP


def adr_0093_aspects_along_the_locks(view: View) -> list[str]:
    """With power `on`, the exit signal of every block from the one a train is
    recorded in to its last locked block shows `clear` with two or more blocks
    beyond locked, `caution` with one, `stop` with none; every other end shows
    `stop`
    ([ADR-0093](../../../docs/adr/0093-every-signal-along-a-trains-locked-blocks-shows-its-aspect-and-a-passed-signal-shows-stop.md)).
    """
    if power(view.rows.get(POWER)) != ON:
        return []
    shown = shown_aspects(view.rows.get(ASPECTS))
    if shown is None:
        return ["no aspects are shown"]
    expected = {end: str(Aspect.STOP) for end in view.layout.end_connection}
    locks = _locks(view)
    for journey in _journeys(view):
        last = journey.standing + _locked_ahead(locks, journey, journey.standing)
        for i in range(journey.standing, min(last + 1, len(journey.transits))):
            ends = transit_ends(view.layout, journey.blocks[i], journey.transits[i])
            if ends is not None:
                expected[ends[0]] = _aspect_of(_locked_ahead(locks, journey, i))
    return [
        f"{end} shows {shown.get(end, 'nothing')}, not {expected.get(end, 'stop')}"
        for end in sorted(expected.keys() | shown.keys())
        if shown.get(end, Aspect.STOP) != expected.get(end, Aspect.STOP)
    ]


def adr_0093_stop_without_power(view: View) -> list[str]:
    """While power is not `on`, every signal shows `stop`
    ([ADR-0093](../../../docs/adr/0093-every-signal-along-a-trains-locked-blocks-shows-its-aspect-and-a-passed-signal-shows-stop.md),
    with [ADR-0078](../../../docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
    """
    stated = power(view.rows.get(POWER))
    if stated == ON:
        return []
    shown = shown_aspects(view.rows.get(ASPECTS)) or {}
    return [
        f"{end} shows {aspect} with power {stated}"
        for end, aspect in sorted(shown.items())
        if aspect != Aspect.STOP
    ]


INVARIANTS: tuple[Invariant, ...] = (
    Invariant(
        "0001",
        "A route enters each block by one end and leaves by the other, so a"
        " terminal block is only first or last on a route.",
        (ALLOCATION,),
        adr_0001_pass_through,
    ),
    Invariant(
        "0006",
        "No two trains hold transits that conflict (a pair not listed"
        " `concurrent` at their connection).",
        (ALLOCATION,),
        adr_0006_no_conflicting_transits,
    ),
    Invariant(
        "0007",
        "A started request's route ends at one of the arrival ends the request"
        " named.",
        (ALLOCATION,),
        adr_0007_route_ends_at_an_arrival,
    ),
    Invariant(
        "0019",
        "A train standing in a terminal block faces that block's one connected" " end.",
        (FACING, ALLOCATION),
        adr_0019_terminal_facing,
    ),
    Invariant(
        "0026",
        "Under `Incremental`, no train holds more than two blocks beyond the"
        " block it is recorded in.",
        (ALLOCATION,),
        adr_0026_two_blocks_ahead,
    ),
    Invariant(
        "0029",
        "A block held ahead of a train is held together with the transit that"
        " leads into it.",
        (ALLOCATION,),
        adr_0029_block_with_its_transit,
    ),
    Invariant(
        "0039",
        "A train that is not placed has no facing.",
        (FACING, ALLOCATION),
        adr_0039_unplaced_has_no_facing,
    ),
    Invariant(
        "0062",
        "`moving` is true exactly while some train is crossing.",
        (MOVING, ALLOCATION),
        adr_0062_moving_while_crossing,
    ),
    Invariant(
        "0071",
        "Every placed train stands in a block of the loaded drawing that is"
        " long enough for it.",
        (ALLOCATION,),
        adr_0071_placed_where_it_fits,
    ),
    Invariant(
        "0071",
        "A train listed on `unfit` is not placed.",
        (UNFIT, ALLOCATION),
        adr_0071_unfit_is_not_placed,
    ),
    Invariant(
        "0076",
        "A placed train holds the lock on the block it stands in.",
        (ALLOCATION,),
        adr_0076_placed_holds_its_block,
    ),
    Invariant(
        "0076",
        "A crossing train is placed.",
        (ALLOCATION,),
        adr_0076_crossing_is_placed,
    ),
    Invariant(
        "0080",
        "A request chained with `after` is listed after the request it follows.",
        (ALLOCATION,),
        adr_0080_after_follows,
    ),
    Invariant(
        "0093",
        "With power `on`, the exit signal of every block from the one a train"
        " is recorded in to its last locked block shows `clear` with two or"
        " more blocks beyond locked, `caution` with one, `stop` with none;"
        " every other end shows `stop`.",
        (ASPECTS, ALLOCATION, POWER),
        adr_0093_aspects_along_the_locks,
    ),
    Invariant(
        "0093",
        "While power is not `on`, every signal shows `stop`.",
        (ASPECTS, POWER),
        adr_0093_stop_without_power,
    ),
)


# -- the record of the messages -----------------------------------------------

QUIET = ""
"""The topic a history invariant is handed once nothing is left to deliver: a
rule that one message is followed by another is breached when the bus goes
quiet without it."""


@dataclass(frozen=True)
class _Move:
    """A move granted and not yet ended."""

    id: str
    transit: str
    into: str
    origin: str | None  # the block it leaves, read off the drawing
    left: bool = False  # the origin has read clear since the grant
    arrived: bool = False  # the block entered has read occupied since


def _held(payload: object) -> tuple[str, list[str]] | None:
    """The train and resources a `lock_granted` or `lock_released` names."""
    fields = _fields(payload)
    train, resources = fields.get("train"), _strings(fields.get("resources"))
    if not isinstance(train, str) or resources is None:
        return None
    return train, list(resources)


def _disputed(payload: object) -> tuple[list[str], list[str]] | None:
    """The trains and blocks a `state/disputed` value lists."""
    fields = _fields(payload)
    trains, blocks = _strings(fields.get("trains")), _strings(fields.get("blocks"))
    if trains is None or blocks is None:
        return None
    return list(trains), list(blocks)


class Record:
    """What the messages so far have said, kept by observing every one.

    It starts from the retained rows and keeps them as it hears them, so a
    `View` over `rows` is the bus as an observer of these messages saw it.
    The lock table, the placements and the crossing trains are the last
    allocation's, carried forward by every event that moves them, since the
    allocation follows the events of a sweep rather than leading them.
    Which blocks read occupied is folded from `block_occupied` and
    `block_vacated`, which no retained row holds.
    """

    def __init__(self, layout: Layout, rows: Mapping[str, Payload] | None = None):
        self.layout = layout
        self.rows: dict[str, Payload] = {}
        self.occupied: dict[str, bool] = {}  # block -> its last reading
        self.trains: dict[str, str] = {}
        self.crossing: dict[str, str] = {}
        self.locks: dict[str, str] = {}
        self.requests: dict[str, str] = {}  # id -> train, until it ends
        self.listed: tuple[str, ...] = ()  # the last allocation's ids, in order
        self.routes: dict[str, tuple[str, ...]] = {}  # id -> route, once chosen
        self.moves: dict[str, _Move] = {}  # train -> its move not yet ended
        self.cancelled: set[str] = set()  # ids cancelled while a move ran
        self.turns: Counter[str] = Counter()  # facing changes a train is owed
        self.unexplained: list[str] = []  # readings since a drain was asked
        self.placed_over: dict[str, str] = {}  # a block left, to its holder
        self.awaited: dict[str, str] = {}  # end -> aspect a grant showed
        self.cut_wanted = False  # `power_wanted: off` since power changed
        self.drain_wanted = False  # `power_wanted: draining` likewise
        for topic, payload in (rows or {}).items():
            self.rows[topic] = payload
            if topic == ALLOCATION:
                self._allocation(payload)

    def observe(self, topic: str, payload: Payload) -> None:
        if topic == ALLOCATION:
            self._allocation(payload)
        elif topic in (BLOCK_OCCUPIED, BLOCK_VACATED):
            block = occupancy(payload)
            if block is not None:
                self._read(block, topic == BLOCK_OCCUPIED)
        elif topic == ROUTE_CHOSEN:
            found = chosen(payload)
            if found is not None:
                self.routes.setdefault(found.id, found.route)
        elif topic == MOVE_GRANTED:
            self._granted(payload)
        elif topic == LOCK_GRANTED:
            held = _held(payload)
            if held is not None:
                self.locks.update(dict.fromkeys(held[1], held[0]))
        elif topic == LOCK_RELEASED:
            self._released(payload)
        elif topic == TRAIN_PLACED:
            self._placed(payload)
        elif topic == TRAIN_REMOVED:
            train = named_train(payload)
            if train is not None:
                self.trains.pop(train, None)
                self.crossing.pop(train, None)
                self.moves.pop(train, None)
        elif topic == PLACEMENT_WANTED:
            # A placement ends the train's move by hand, not on its readings.
            wanted = placement(payload)
            if wanted is not None:
                self.moves.pop(wanted.train, None)
        elif topic in ENDED:
            self._ended(readable_id(payload))
        elif topic == CANCEL_WANTED:
            rid = readable_id(payload)
            if any(move.id == rid for move in self.moves.values()):
                self.cancelled.add(cast(str, rid))
        elif topic == REVERSAL_WANTED:
            train = named_train(payload)
            if train is not None:
                self.turns[train] += 1
        elif topic == FACING:
            old = kept_facing(self.rows.get(FACING)) or {}
            new = kept_facing(payload) or {}
            for train in old.keys() & new.keys():
                if old[train] != new[train] and self.turns[train] > 0:
                    self.turns[train] -= 1
        elif topic == ASPECTS:
            self.awaited.clear()
        elif topic == POWER_WANTED:
            wanted = wanted_power(payload)
            if wanted == OFF:
                self.cut_wanted = True
            elif wanted == DRAINING:
                self.drain_wanted = True
                self.unexplained.clear()
        elif topic == POWER:
            self.cut_wanted = self.drain_wanted = False
        if is_state_topic(topic):
            self.rows[topic] = payload

    def _allocation(self, payload: object) -> None:
        kept = kept_allocation(payload)
        if kept is not None:
            self.trains, self.crossing = dict(kept.trains), dict(kept.crossing)
        self.locks = _locks_in(payload)
        listed = _requests_in(payload)
        self.requests = {request.id: request.train for request in listed}
        self.listed = tuple(request.id for request in listed)
        self.routes = {
            request.id: request.route or self.routes[request.id]
            for request in listed
            if request.route is not None or request.id in self.routes
        }
        self.placed_over.clear()

    def _read(self, block: str, occupied: bool) -> None:
        """A reading, which changes something only where it changes the level
        (BUS.md, a detector reports a level)."""
        if self.occupied.get(block) == occupied:
            return
        self.occupied[block] = occupied
        for train, move in self.moves.items():
            if not occupied and move.origin == block:
                self.moves[train] = replace(move, left=True)
            elif occupied and move.into == block:
                self.moves[train] = replace(move, arrived=True)
        if power(self.rows.get(POWER)) != ON:
            return
        if occupied and block not in self.locks:
            self.unexplained.append(f"{block} reads occupied and nothing claims it")
        if not occupied:
            for train, standing in sorted(self.trains.items()):
                move = self.moves.get(train)
                if standing == block and (move is None or move.origin != block):
                    self.unexplained.append(
                        f"{train}'s block {block} reads clear with no move leaving it"
                    )

    def _granted(self, payload: object) -> None:
        granted, rid = grant(payload), readable_id(payload)
        if granted is None or rid is None:
            return
        ends = transit_ends(self.layout, granted.into, granted.transit)
        origin = None if ends is None else block_of(ends[1])
        self.moves[granted.train] = _Move(rid, granted.transit, granted.into, origin)
        self.crossing[granted.train] = granted.transit
        self.turns[granted.train] += 1
        aspect = granted_aspect(payload)
        if ends is not None and aspect is not None:
            shown = shown_aspects(self.rows.get(ASPECTS)) or {}
            if shown.get(ends[1], Aspect.STOP) != aspect:
                self.awaited[ends[1]] = aspect

    def _released(self, payload: object) -> None:
        held = _held(payload)
        if held is None:
            return
        train, resources = held
        for resource in resources:
            if self.locks.get(resource) == train:
                del self.locks[resource]
            if self.placed_over.get(resource) == train:
                del self.placed_over[resource]
        if self.crossing.get(train) in resources:
            del self.crossing[train]
        move = self.moves.get(train)
        if move is not None and move.transit in resources:
            del self.moves[train]

    def _placed(self, payload: object) -> None:
        placed = placement(payload)
        if placed is None or placed.block is None:
            return
        train, block = placed.train, placed.block
        before = self.trains.get(train)
        if before is not None:
            holder = self.locks.get(before)
            if holder == train:
                del self.locks[before]
            elif holder is not None:
                self.placed_over[before] = holder
        self.locks[block] = train
        self.trains[train] = block
        self.crossing.pop(train, None)
        self.moves.pop(train, None)
        self.turns[train] += 1

    def _ended(self, rid: str | None) -> None:
        if rid is None:
            return
        self.requests.pop(rid, None)
        self.routes.pop(rid, None)
        self.cancelled.discard(rid)
        for train, move in list(self.moves.items()):
            if move.id == rid:
                del self.moves[train]


@dataclass(frozen=True)
class HistoryInvariant:
    adr: str
    states: str
    reads: tuple[str, ...]
    # Called on each message, before `Record.observe`, and with `QUIET`.
    breaches: Callable[[Record, View, str, Payload], list[str]]


# -- the history invariants ---------------------------------------------------


def adr_0002_route_is_fixed(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """Once a request has a route, the route does not change until the
    request ends
    ([ADR-0002](../../../docs/adr/0002-fixed-route-per-request.md))."""
    stated: list[tuple[str, tuple[str, ...]]] = []
    if topic == ROUTE_CHOSEN:
        found = chosen(payload)
        if found is not None:
            stated.append((found.id, found.route))
    elif topic == ALLOCATION:
        stated = [
            (request.id, request.route)
            for request in _requests_in(payload)
            if request.route is not None
        ]
    return [
        f"{rid} was routed {list(record.routes[rid])} and is now {list(route)}"
        for rid, route in stated
        if record.routes.get(rid, route) != route
    ]


def adr_0019_facing_turns_on_a_move(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A train's facing changes only when it makes a move, is turned at rest
    or is placed, never when a route is chosen
    ([ADR-0019](../../../docs/adr/0019-facing-is-scheduler-state.md))."""
    if topic != FACING:
        return []
    old = kept_facing(record.rows.get(FACING)) or {}
    new = kept_facing(payload) or {}
    return [
        f"{train} turned from {old[train]} to {new[train]} with no move"
        for train in sorted(old.keys() & new.keys())
        if old[train] != new[train] and record.turns[train] == 0
    ]


def adr_0025_grant_shows_its_aspect(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A grant's aspect equals the aspect `aspects` shows at the end the move
    leaves by
    ([ADR-0025](../../../docs/adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md),
    with ADR-0093): the one already shown, or the next one shown."""
    if topic != ASPECTS:
        return []
    shown = shown_aspects(payload) or {}
    return [
        f"{end} shows {shown.get(end, Aspect.STOP)}, a grant from it {aspect}"
        for end, aspect in sorted(record.awaited.items())
        if shown.get(end, Aspect.STOP) != aspect
    ]


def adr_0047_no_grant_while_crossing(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """No `move_granted` for a train the allocation lists as crossing
    ([ADR-0047](../../../docs/adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
    """
    granted = grant(payload) if topic == MOVE_GRANTED else None
    if granted is None or granted.train not in record.crossing:
        return []
    crossing = record.crossing[granted.train]
    return [f"{granted.train} granted {granted.transit} while crossing {crossing}"]


def adr_0048_unexplained_drains(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """With power `on`, a block reading occupied that nothing claims, or a
    placed train whose block reads clear with no move to explain it, is
    followed by `power_wanted: draining`
    ([ADR-0048](../../../docs/adr/0048-an-unexplained-reading-holds-the-run.md),
    as amended by ADR-0078)."""
    if topic != QUIET:
        return []
    return [f"{line}, and no drain was asked" for line in record.unexplained]


def adr_0048_disputed_lists_contradictions(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """`disputed` lists exactly the placed trains whose block reads clear and
    the occupied blocks nothing claims, and is empty unless power reads `off`
    ([ADR-0048](../../../docs/adr/0048-an-unexplained-reading-holds-the-run.md),
    as amended by ADR-0080)."""
    if topic != QUIET or DISPUTED not in record.rows:
        return []
    listed = _disputed(record.rows[DISPUTED])
    if listed is None:
        return ["disputed cannot be read"]
    expected: tuple[list[str], list[str]] = ([], [])
    if power(record.rows.get(POWER)) == OFF:
        expected = (
            sorted(
                train
                for train, block in record.trains.items()
                if train not in record.crossing and record.occupied.get(block) is False
            ),
            sorted(
                block
                for block, occupied in record.occupied.items()
                if occupied and block not in record.locks
            ),
        )
    if listed == expected:
        return []
    return [f"disputed lists {listed}, not {expected}"]


def adr_0049_placed_has_no_request(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """When `train_placed` or `train_removed` is published, the train has no
    request left in the allocation
    ([ADR-0049](../../../docs/adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)).
    """
    if topic not in (TRAIN_PLACED, TRAIN_REMOVED):
        return []
    train = named_train(payload)
    return [
        f"{train} is {topic.rsplit('_', 1)[-1]} with {rid} left"
        for rid, holder in sorted(record.requests.items())
        if holder == train
    ]


def adr_0049_no_grant_after_cancel(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A request cancelled while its move is outstanding gets no further
    grant
    ([ADR-0049](../../../docs/adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)).
    """
    rid = readable_id(payload) if topic == MOVE_GRANTED else None
    if rid is None or rid not in record.cancelled:
        return []
    return [f"{rid} was granted a move after it was cancelled"]


def adr_0062_drain_ends_at_a_stand(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A drain ends in `off` only while `moving` reads `false`; only
    `power_wanted: off` cuts at once
    ([ADR-0062](../../../docs/adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md),
    as amended by ADR-0078)."""
    if topic != POWER or POWER not in record.rows or power(payload) != OFF:
        return []
    was = power(record.rows[POWER])
    drained = was == DRAINING or (was == ON and record.drain_wanted)
    if not drained or record.cut_wanted or not moving(record.rows.get(MOVING)):
        return []
    return [f"power went from {was} to off while moving"]


def adr_0077_not_into_occupied(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """No move is granted into, and no lock taken on, a block that reads
    occupied, whoever holds it
    ([ADR-0077](../../../docs/adr/0077-a-train-is-not-sent-into-a-block-that-reads-occupied-and-a-move-ends-on-both-readings.md)).
    """
    if topic == MOVE_GRANTED:
        granted = grant(payload)
        if granted is not None and record.occupied.get(granted.into):
            return [
                f"{granted.train} granted into {granted.into}, which reads occupied"
            ]
    elif topic == LOCK_GRANTED:
        held = _held(payload)
        if held is not None:
            return [
                f"{held[0]} locked {resource}, which reads occupied"
                for resource in held[1]
                if record.occupied.get(resource)
            ]
    return []


def adr_0077_move_ends_on_both_readings(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A move ends (origin and transit released, request completed) only once
    its origin reads clear and its arrival block reads occupied, in either
    order
    ([ADR-0077](../../../docs/adr/0077-a-train-is-not-sent-into-a-block-that-reads-occupied-and-a-move-ends-on-both-readings.md)).
    """
    ending: list[tuple[str, _Move]] = []
    if topic == LOCK_RELEASED:
        held = _held(payload)
        move = None if held is None else record.moves.get(held[0])
        if held is not None and move is not None and move.transit in held[1]:
            ending.append((held[0], move))
    elif topic == REQUEST_COMPLETED:
        rid = readable_id(payload)
        ending = [(t, move) for t, move in record.moves.items() if move.id == rid]
    lines: list[str] = []
    for train, move in ending:
        if move.origin is not None and not move.left:
            lines.append(f"{train}'s move ended before {move.origin} read clear")
        if not move.arrived:
            lines.append(f"{train}'s move ended before {move.into} read occupied")
    return lines


def adr_0077_placement_releases_its_own(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A placement releases the train's previous block only if the train held
    it
    ([ADR-0077](../../../docs/adr/0077-a-train-is-not-sent-into-a-block-that-reads-occupied-and-a-move-ends-on-both-readings.md)).
    """
    if topic != ALLOCATION:
        return []
    locks = _locks_in(payload)
    return [
        f"{block} of {holder} was released by a placement"
        for block, holder in sorted(record.placed_over.items())
        if locks.get(block) != holder
    ]


def adr_0078_nothing_commits_without_power(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """While power reads `draining` or `off`, no route is chosen and no move
    granted
    ([ADR-0078](../../../docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
    """
    if topic not in (ROUTE_CHOSEN, MOVE_GRANTED):
        return []
    stated = power(record.rows.get(POWER))
    if stated == ON:
        return []
    return [f"{topic.rsplit('/', 1)[-1]} {readable_id(payload)} with power {stated}"]


def adr_0080_listed_by_priority(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A new request goes in after every waiting request of the same or
    higher priority
    ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
    A train the roster does not hold has no priority to compare."""
    if topic != ALLOCATION:
        return []
    trains = view.roster.trains
    requests = _requests_in(payload)
    lines: list[str] = []
    for i, new in enumerate(requests):
        if new.id in record.listed or new.route is not None or new.train not in trains:
            continue
        key = trains[new.train].priority_key
        lines += [
            f"{new.id} is listed before {waiting.id}"
            for waiting in requests[i + 1 :]
            if waiting.id in record.listed
            and waiting.route is None
            and waiting.train in trains
            and trains[waiting.train].priority_key <= key
        ]
    return lines


def adr_0080_placed_into_a_free_block(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A train is placed only into a free block: no train placed there, no
    lock on it, on no active train's remaining route, its own residue excepted
    ([ADR-0080](../../../docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md),
    ADR-0069)."""
    placed = placement(payload) if topic == TRAIN_PLACED else None
    if placed is None or placed.block is None:
        return []
    train, block = placed.train, placed.block
    lines: list[str] = []
    holder = record.locks.get(block)
    if holder is not None and (holder != train or record.trains.get(train) == block):
        lines.append(f"{train} placed into {block}, which {holder} holds")
    for rid, route in sorted(record.routes.items()):
        mover = record.requests.get(rid)
        if mover is None or mover == train:
            continue
        blocks = route[0::2]
        standing = record.trains.get(mover)
        ahead = blocks[blocks.index(standing) :] if standing in blocks else blocks
        if block in ahead:
            lines.append(f"{train} placed into {block}, on the route of {rid}")
    return lines


HISTORY_INVARIANTS: tuple[HistoryInvariant, ...] = (
    HistoryInvariant(
        "0002",
        "Once a request has a route, the route does not change until the"
        " request ends.",
        (ALLOCATION, ROUTE_CHOSEN, *ENDED),
        adr_0002_route_is_fixed,
    ),
    HistoryInvariant(
        "0019",
        "A train's facing changes only when it makes a move, is turned at rest"
        " or is placed, never when a route is chosen.",
        (FACING, MOVE_GRANTED, REVERSAL_WANTED, ROUTE_CHOSEN, TRAIN_PLACED),
        adr_0019_facing_turns_on_a_move,
    ),
    HistoryInvariant(
        "0025",
        "A grant's aspect equals the aspect `aspects` shows at the end the move"
        " leaves by.",
        (MOVE_GRANTED, ASPECTS),
        adr_0025_grant_shows_its_aspect,
    ),
    HistoryInvariant(
        "0047",
        "No `move_granted` for a train the allocation lists as crossing.",
        (MOVE_GRANTED, ALLOCATION, LOCK_RELEASED, TRAIN_PLACED, TRAIN_REMOVED),
        adr_0047_no_grant_while_crossing,
    ),
    HistoryInvariant(
        "0048",
        "With power `on`, a block reading occupied that nothing claims, or a"
        " placed train whose block reads clear with no move to explain it, is"
        " followed by `power_wanted: draining`.",
        (BLOCK_OCCUPIED, BLOCK_VACATED, ALLOCATION, MOVE_GRANTED, LOCK_GRANTED)
        + (LOCK_RELEASED, TRAIN_PLACED, POWER, POWER_WANTED),
        adr_0048_unexplained_drains,
    ),
    HistoryInvariant(
        "0048",
        "`disputed` lists exactly the placed trains whose block reads clear and"
        " the occupied blocks nothing claims, and is empty unless power reads"
        " `off`.",
        (DISPUTED, ALLOCATION, POWER, BLOCK_OCCUPIED, BLOCK_VACATED)
        + (LOCK_GRANTED, LOCK_RELEASED, TRAIN_PLACED),
        adr_0048_disputed_lists_contradictions,
    ),
    HistoryInvariant(
        "0049",
        "When `train_placed` or `train_removed` is published, the train has no"
        " request left in the allocation.",
        (TRAIN_PLACED, TRAIN_REMOVED, ALLOCATION, *ENDED),
        adr_0049_placed_has_no_request,
    ),
    HistoryInvariant(
        "0049",
        "A request cancelled while its move is outstanding gets no further" " grant.",
        (CANCEL_WANTED, MOVE_GRANTED, LOCK_RELEASED, *ENDED),
        adr_0049_no_grant_after_cancel,
    ),
    HistoryInvariant(
        "0062",
        "A drain ends in `off` only while `moving` reads `false`; only"
        " `power_wanted: off` cuts at once.",
        (POWER, MOVING, POWER_WANTED),
        adr_0062_drain_ends_at_a_stand,
    ),
    HistoryInvariant(
        "0077",
        "No move is granted into, and no lock taken on, a block that reads"
        " occupied, whoever holds it.",
        (MOVE_GRANTED, LOCK_GRANTED, BLOCK_OCCUPIED, BLOCK_VACATED),
        adr_0077_not_into_occupied,
    ),
    HistoryInvariant(
        "0077",
        "A move ends (origin and transit released, request completed) only once"
        " its origin reads clear and its arrival block reads occupied, in either"
        " order.",
        (BLOCK_OCCUPIED, BLOCK_VACATED, MOVE_GRANTED, LOCK_RELEASED)
        + (REQUEST_COMPLETED, PLACEMENT_WANTED),
        adr_0077_move_ends_on_both_readings,
    ),
    HistoryInvariant(
        "0077",
        "A placement releases the train's previous block only if the train held" " it.",
        (TRAIN_PLACED, ALLOCATION, LOCK_RELEASED),
        adr_0077_placement_releases_its_own,
    ),
    HistoryInvariant(
        "0078",
        "While power reads `draining` or `off`, no route is chosen and no move"
        " granted.",
        (ROUTE_CHOSEN, MOVE_GRANTED, POWER),
        adr_0078_nothing_commits_without_power,
    ),
    HistoryInvariant(
        "0080",
        "A new request goes in after every waiting request of the same or"
        " higher priority.",
        (ALLOCATION,),
        adr_0080_listed_by_priority,
    ),
    HistoryInvariant(
        "0080",
        "A train is placed only into a free block: no train placed there, no"
        " lock on it, on no active train's remaining route, its own residue"
        " excepted.",
        (TRAIN_PLACED, ALLOCATION, ROUTE_CHOSEN, LOCK_GRANTED, LOCK_RELEASED) + ENDED,
        adr_0080_placed_into_a_free_block,
    ),
)
