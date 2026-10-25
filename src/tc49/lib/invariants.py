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

The rules over `layout`'s rows — traction, points, the track and who holds
a train — are here as well. ADR-0089's, that no throttle holds two trains,
holds since `layout` releases a throttle's train before it takes another
(#1050). One is not here: ADR-0085's "while `railroad` says `built:
false`, power does not come on" is not an invariant over the bus: the page
refuses ON, and `layout` answers it so a person can power an unfinished track
plan to test part of it (#889, #1049).

`ADR-0026` holds only where the dispatcher locks `Incremental`. The strategy
is not on the bus, so the `View` carries no field for it and the caller that
knows it leaves that invariant out.
"""

from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import cast

from tc49.lib.bus import Payload
from tc49.lib.inventory import (
    AUTOMATIC,
    DRAINING,
    MANUAL,
    OFF,
    ON,
    Aspect,
    device_topic,
    is_state_topic,
    split_device,
)
from tc49.lib.layout import (
    FACINGS,
    Layout,
    block_of,
    connected_end,
    end_letter,
    facing_ends,
    transit_ends,
)
from tc49.lib.payload import (
    Command,
    alignment,
    chosen,
    command,
    commanded_power,
    desired_position,
    desired_speed,
    driving,
    grant,
    granted_aspect,
    kept_allocation,
    kept_facing,
    link_up,
    moving,
    named_train,
    occupancy,
    placement,
    power,
    readable_id,
    shown_aspects,
    supply,
    taken,
    wanted_power,
    withdrawal,
)
from tc49.lib.roster import FORWARD, Roster

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
PLACEMENT_REFUSED = "tc49/dispatch/placement_refused"
REVERSAL_WANTED = "tc49/schedule/reversal_wanted"
BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"
POWER_WANTED = "tc49/layout/power_wanted"
ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
MOVE_WITHDRAWN = "tc49/layout/move_withdrawn"
RAILROAD = "tc49/layout/state/railroad"
DRIVING = "tc49/layout/state/driving"
TAKEN = "tc49/layout/state/taken"
WANTED_TRACTION = "tc49/layout/state/wanted/traction"
WANTED_POINT = "tc49/layout/state/wanted/point"
WANTED_TRACK = "tc49/layout/state/wanted/track"
DEVICE_TRACK = "tc49/layout/state/device/track"
DEVICE_LINK = "tc49/layout/state/device/link"

EVERY_TRACTION = f"{WANTED_TRACTION}/+"
EVERY_POINT = f"{WANTED_POINT}/+"
EVERY_LINK = f"{DEVICE_LINK}/+"
"""The addressed rows a rule reads, one per address, as the filter that
matches them all: a rule about traction reads every car's row."""

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


def _addresses(roster: Roster, train: str) -> tuple[tuple[str, str], ...]:
    """Each car of the train that has an address, with the way round it is
    coupled, in the train's order: what `layout` writes traction to
    (ADR-0045). `()` for a train the roster does not name."""
    made_up = roster.trains.get(train)
    return tuple(
        (coupled.car.addr, coupled.orientation)
        for coupled in (made_up.cars if made_up is not None else ())
        if coupled.car.addr is not None
    )


def _written(topic: str, payload: object) -> tuple[str, float] | None:
    """The address a `wanted/traction` row is for, from its topic, and the
    speed it asks for; None for any other topic, or a speed that cannot be
    read."""
    split = split_device(topic)
    if split is None or split[0] != WANTED_TRACTION:
        return None
    speed = desired_speed(payload)
    return None if speed is None else (split[1], speed)


def _traction(rows: Mapping[str, Payload]) -> dict[str, float]:
    """Every `wanted/traction` row's speed by address, each that cannot be
    read passed over."""
    return {
        written[0]: written[1]
        for topic, payload in rows.items()
        if (written := _written(topic, payload)) is not None
    }


def _dead(rows: Mapping[str, Payload]) -> bool:
    """Whether the hardware reports the supply off or any link down."""
    if DEVICE_TRACK in rows and supply(rows[DEVICE_TRACK]) == OFF:
        return True
    return any(
        not link_up(payload)
        for topic, payload in rows.items()
        if topic.startswith(f"{DEVICE_LINK}/")
    )


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


def adr_0022_points_set_for_the_crossing(view: View) -> list[str]:
    """While a train crosses a transit, every addressed point that transit
    needs is wanted at the position it needs
    ([ADR-0022](../../../docs/adr/0022-a-symbol-carries-its-hardware-address.md),
    with ADR-0031 and ADR-0068).

    The transit crossed and not every one held: a transit locked ahead of a
    train has had no `align` yet, which comes with its grant."""
    lines: list[str] = []
    for train, transit in sorted(_crossing(view).items()):
        name, _, way = transit.partition(".")
        connection = view.layout.connections.get(name)
        for point in connection.points.get(way, ()) if connection else ():
            wanted = desired_position(
                view.rows.get(device_topic(WANTED_POINT, point.addr))
            )
            if wanted != point.position:
                lines.append(
                    f"{train} crosses {transit} with point {point.addr}"
                    f" wanted {wanted or 'nowhere'}, not {point.position}"
                )
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


def adr_0063_power_follows_the_hardware(view: View) -> list[str]:
    """Power does not read `on` while `device/track` reads `off` or a
    `device/link` reads `down`
    ([ADR-0063](../../../docs/adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md),
    as amended by ADR-0078). `draining` is held over the fold until the drain
    ends (BUS.md, `state/power`), so it is not read as `on`."""
    if power(view.rows.get(POWER)) != ON or not _dead(view.rows):
        return []
    return ["power reads on while the hardware reports it off or a link down"]


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


def adr_0079_manual_untaken_stands(view: View) -> list[str]:
    """In `manual`, a placed train no throttle holds has traction 0 unless it
    is crossing, finishing the move it had when the railroad went to `manual`
    ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md),
    as amended by ADR-0081)."""
    if driving(view.rows.get(DRIVING)) != MANUAL:
        return []
    holders, crossing = taken(view.rows.get(TAKEN)), _crossing(view)
    speeds = _traction(view.rows)
    lines: list[str] = []
    for train in sorted(_trains(view)):
        if train in holders or train in crossing:
            continue
        running = {
            addr: speeds[addr]
            for addr, _orientation in _addresses(view.roster, train)
            if speeds.get(addr, 0.0) != 0.0
        }
        if running:
            lines.append(f"{train} stands in manual with no throttle at {running}")
    return lines


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


def adr_0089_one_train_a_throttle(view: View) -> list[str]:
    """No throttle id holds two trains
    ([ADR-0089](../../../docs/adr/0089-a-throttle-holds-one-train.md))."""
    held = Counter(taken(view.rows.get(TAKEN)).values())
    return [
        f"{throttle} holds {count} trains"
        for throttle, count in sorted(held.items())
        if count > 1
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
        "0022",
        "While a train crosses a transit, every addressed point that transit"
        " needs is wanted at the position it needs.",
        (ALLOCATION, EVERY_POINT),
        adr_0022_points_set_for_the_crossing,
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
        "0063",
        "Power does not read `on` while `device/track` reads `off` or a"
        " `device/link` reads `down`.",
        (POWER, DEVICE_TRACK, EVERY_LINK),
        adr_0063_power_follows_the_hardware,
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
        "0079",
        "In `manual`, a placed train no throttle holds has traction 0 unless"
        " it is crossing.",
        (DRIVING, TAKEN, EVERY_TRACTION, ALLOCATION),
        adr_0079_manual_untaken_stands,
    ),
    Invariant(
        "0080",
        "A request chained with `after` is listed after the request it follows.",
        (ALLOCATION,),
        adr_0080_after_follows,
    ),
    Invariant(
        "0089",
        "No throttle id holds two trains.",
        (TAKEN,),
        adr_0089_one_train_a_throttle,
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
class _Started:
    """A move whose traction `layout` has written, until it arrives."""

    into: str
    signs: dict[str, float]  # addr -> +1.0 or -1.0, the sign the move gives it


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

    What `layout` writes is followed as well. A `wanted/traction` row names
    an address and not a train, so a nonzero speed on a car of a train no
    throttle holds, with a `move` for that train heard and not yet driven,
    is that move's start; the roster says which cars a train has.
    """

    def __init__(
        self,
        layout: Layout,
        rows: Mapping[str, Payload] | None = None,
        roster: Roster | None = None,
    ):
        self.layout = layout
        self.roster = roster if roster is not None else Roster("", {})
        self.rows: dict[str, Payload] = {}
        self.occupied: dict[str, bool] = {}  # block -> its last reading
        self.trains: dict[str, str] = {}
        self.crossing: dict[str, str] = {}
        self.locks: dict[str, str] = {}
        self.requests: dict[str, str] = {}  # id -> train, until it ends
        self.listed: tuple[str, ...] = ()  # the last allocation's ids, in order
        self.routes: dict[str, tuple[str, ...]] = {}  # id -> route, once chosen
        self.moves: dict[str, _Move] = {}  # train -> its move not yet ended
        self.placing: dict[str, _Move] = {}  # train -> its move, while placed
        self.cancelled: set[str] = set()  # ids cancelled while a move ran
        self.turns: Counter[str] = Counter()  # facing changes a train is owed
        self.unexplained: list[str] = []  # readings since a drain was asked
        self.placed_over: dict[str, str] = {}  # a block left, to its holder
        self.awaited: dict[str, str] = {}  # end -> aspect a grant showed
        self.cut_wanted = False  # `power_wanted: off` since power changed
        self.drain_wanted = False  # `power_wanted: draining` likewise
        self.pressed: str | None = None  # the last `power_wanted` word, likewise
        self.granted: dict[str, tuple[str, str | None]] = {}  # train -> transit, aspect
        self.priced: dict[str, float] = {}  # aspect -> the speed its moves ran at
        self.aligned: set[str] = set()  # transits an `align` named, not yet driven
        self.commanded: dict[str, Command] = {}  # train -> a `move` not yet driven
        # train -> the transit and block of a `move` withdrawn before it came,
        # which `layout` drops when it does (#1080)
        self.withdrawn: dict[str, tuple[str, str]] = {}
        self.started: dict[str, _Started] = {}  # train -> the move driven, until in
        self.signs: dict[str, float] = {}  # addr -> its last nonzero speed, until 0
        self.resting: set[str] = set()  # addrs owed a 0 since `layout` came up
        self.starting: set[str] = set()  # topics owed an `off` since then
        self.cut = False  # the supply cut, until `power_wanted: on`
        self.removed: dict[str, str] = {}  # addr -> train taken off, owed a 0
        self.arrived: dict[str, str] = {}  # addr -> train at its sensor, owed a 0
        self.released: dict[str, str] = {}  # addr -> train let go of, owed a 0
        self.keeps: set[str] = set()  # trains let go of mid-move in automatic
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
                self.placing.pop(train, None)
                self.commanded.pop(train, None)
                self.withdrawn.pop(train, None)
                self.started.pop(train, None)
                self.keeps.discard(train)
                for addr, _orientation in _addresses(self.roster, train):
                    self.removed[addr] = train
        elif topic == PLACEMENT_WANTED:
            # A placement ends the train's move by hand, not on its readings,
            # and one the dispatcher refuses leaves it running (#1062).
            wanted = placement(payload)
            if wanted is not None:
                move = self.moves.pop(wanted.train, None)
                if move is not None:
                    self.placing[wanted.train] = move
        elif topic == PLACEMENT_REFUSED:
            train = named_train(payload)
            move = None if train is None else self.placing.pop(train, None)
            if train is not None and move is not None:
                self.moves[train] = move
        elif topic in ENDED:
            self._ended(readable_id(payload))
        elif topic == MOVE_WITHDRAWN:
            # `layout` took back a cancelled request's move nothing had
            # driven, so it ends on that answer and not on its readings
            # (#1068). One taken back before its `move` came drops that
            # `move` when it does, as `layout` drops it (#1080).
            withdrawn = withdrawal(payload)
            move = None if withdrawn is None else self.moves.get(withdrawn.train)
            if (
                withdrawn is not None
                and move is not None
                and move.transit == withdrawn.transit
                and move.into == withdrawn.into
                and move.id in self.cancelled
            ):
                train = withdrawn.train
                del self.moves[train]
                commanded = self.commanded.pop(train, None)
                if commanded is None or commanded.transit_id != withdrawn.transit:
                    self.withdrawn[train] = (withdrawn.transit, withdrawn.into)
                self.started.pop(train, None)
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
            self.pressed = wanted or self.pressed
            if wanted == OFF:
                self.cut_wanted = True
                self.keeps.clear()
            elif wanted == DRAINING:
                self.drain_wanted = True
                self.unexplained.clear()
            elif wanted == ON:
                self.cut = False
        elif topic == POWER:
            self.cut = self.cuts(payload) or (self.cut and power(payload) == OFF)
            self.cut_wanted = self.drain_wanted = False
            self.pressed = None
            self.starting.discard(POWER)
        elif topic == ALIGN:
            aligning = alignment(payload)
            if aligning is not None and aligning.transit_id is not None:
                self.aligned.add(aligning.transit_id)
        elif topic == MOVE:
            self._commanded(payload)
        elif topic == RAILROAD and payload != self.rows.get(RAILROAD):
            # A value the record already holds is the retained row handed to
            # a late subscriber, and not `layout` coming up.
            self.resting = {
                addr for addr, speed in _traction(self.rows).items() if speed != 0.0
            }
            self.starting = {POWER, WANTED_TRACK}
        elif topic == WANTED_TRACK:
            self.starting.discard(WANTED_TRACK)
        elif topic == TAKEN:
            self._let_go(payload)
        elif (written := _written(topic, payload)) is not None:
            self._wrote(*written)
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
        if occupied:
            # The arrival: the move's sensor, where `layout` stops the train.
            speeds = _traction(self.rows)
            for train, started in list(self.started.items()):
                if started.into == block:
                    del self.started[train]
                    for addr, _orientation in _addresses(self.roster, train):
                        if speeds.get(addr, 0.0) != 0.0:
                            self.arrived[addr] = train
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
        self.granted[granted.train] = (granted.transit, granted_aspect(payload))
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
        if placed is not None:
            self.withdrawn.pop(placed.train, None)
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
        self.placing.pop(train, None)
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

    def cuts(self, payload: object) -> bool:
        """Whether this `state/power` is the supply cut: `off` with
        `power_wanted: off` or `draining` the last word pressed, or ending a
        drain. Not `off` after `on` was pressed, nor from `on` with nothing
        pressed: that is the hardware reading the supply off, which no person
        asked for."""
        if power(payload) != OFF or POWER not in self.rows:
            return False
        was = power(self.rows[POWER])
        if was == OFF or self.pressed == ON:
            return False
        return self.pressed in (OFF, DRAINING) or was == DRAINING

    def under_way(self, train: str) -> bool:
        """Whether the train has a move granted that has not reached the
        block it enters."""
        move = self.moves.get(train)
        return move is not None and not move.arrived

    def starts(self, addr: str) -> list[tuple[str, Command]]:
        """The moves a nonzero speed on `addr` starts: each `move` heard and
        not yet driven, of a train no throttle holds whose cars carry `addr`.
        """
        holders = taken(self.rows.get(TAKEN))
        return [
            (train, commanded)
            for train, commanded in sorted(self.commanded.items())
            if train not in holders
            and any(each == addr for each, _ in _addresses(self.roster, train))
        ]

    def composed(self, train: str, near: str) -> dict[str, float] | None:
        """The sign each addressed car of `train` is given by a move departing
        through `near`: positive where the move is nose-first and the car
        `forward`, or propelled and `reverse` (ADR-0052). None where the
        facing does not name the block departed (ADR-0095)."""
        facing = (kept_facing(self.rows.get(FACING)) or {}).get(train)
        if (
            facing is None
            or end_letter(facing) not in FACINGS
            or block_of(facing) != block_of(near)
        ):
            return None
        nose_first = facing_ends(facing)[1] == near
        return {
            addr: 1.0 if (orientation == FORWARD) == nose_first else -1.0
            for addr, orientation in _addresses(self.roster, train)
        }

    def _commanded(self, payload: object) -> None:
        commanded = command(payload)
        if commanded is None:
            return
        withdrawn = self.withdrawn.pop(commanded.train, None)
        if withdrawn == (commanded.transit_id, commanded.into):
            return
        self.resting.clear()
        granted = self.granted.pop(commanded.train, None)
        if (
            granted is not None
            and granted[0] == commanded.transit_id
            and granted[1] is not None
            and commanded.speed is not None
        ):
            self.priced.setdefault(granted[1], commanded.speed)
        self.commanded[commanded.train] = commanded

    def _wrote(self, addr: str, speed: float) -> None:
        """A speed `layout` wrote on `addr`: whatever stop it owed is written,
        and a nonzero one starts each move it is the start of."""
        for owed in (self.removed, self.arrived, self.released):
            owed.pop(addr, None)
        self.resting.discard(addr)
        if speed == 0.0:
            self.signs.pop(addr, None)
            self.keeps -= {
                train
                for train in self.keeps
                if any(each == addr for each, _ in _addresses(self.roster, train))
            }
            return
        self.signs[addr] = speed
        for train, commanded in self.starts(addr):
            del self.commanded[train]
            self.aligned.discard(commanded.transit_id)
            ends = transit_ends(self.layout, commanded.into, commanded.transit_id)
            signs = None if ends is None else self.composed(train, ends[1])
            self.started[train] = _Started(commanded.into, signs or {})

    def _let_go(self, payload: object) -> None:
        """A `state/taken`: each train it no longer names was let go of, and
        in `automatic` is owed a 0 unless it is mid-move over live rails, when
        it keeps running (ADR-0081, ADR-0083)."""
        before, after = taken(self.rows.get(TAKEN)), taken(payload)
        self.keeps -= after.keys()
        if driving(self.rows.get(DRIVING)) != AUTOMATIC:
            return
        live = power(self.rows.get(POWER)) != OFF
        for train in sorted(before.keys() - after.keys()):
            addrs = [addr for addr, _orientation in _addresses(self.roster, train)]
            if addrs and live and self.under_way(train):
                self.keeps.add(train)
            else:
                self.released.update(dict.fromkeys(addrs, train))


@dataclass(frozen=True)
class HistoryInvariant:
    adr: str
    states: str
    reads: tuple[str, ...]
    # Called on each message, before `Record.observe`, and with `QUIET`.
    breaches: Callable[[Record, View, str, Payload], list[str]]


def _owed(owed: Mapping[str, str], why: str) -> list[str]:
    """One line per train with cars still owed a 0, which `why`."""
    trains: dict[str, list[str]] = {}
    for addr, train in sorted(owed.items()):
        trains.setdefault(train, []).append(addr)
    return [
        f"{train} {why} and {addrs} were never written 0"
        for train, addrs in sorted(trains.items())
    ]


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


def adr_0025_move_at_the_aspects_speed(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """The `move` that follows a grant carries the speed for the grant's
    aspect, the same for every grant of that aspect, and a grant at `stop`
    gets no `move`
    ([ADR-0025](../../../docs/adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md),
    as amended by ADR-0079). The speeds are configured on the driver and on
    no topic, so the first `move` of each aspect says what it is worth."""
    commanded = command(payload) if topic == MOVE else None
    granted = None if commanded is None else record.granted.get(commanded.train)
    if commanded is None or granted is None or granted[0] != commanded.transit_id:
        return []
    train, aspect = commanded.train, granted[1]
    if aspect == Aspect.STOP:
        return [f"{train} moves over {granted[0]} on a grant at stop"]
    priced = record.priced.get(aspect) if aspect is not None else None
    if commanded.speed is None or (priced is not None and commanded.speed != priced):
        return [f"{train} moves at {commanded.speed} on {aspect}, not {priced}"]
    return []


def adr_0031_no_traction_before_align(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """No traction is written for a move before the `align` naming its
    transit
    ([ADR-0031](../../../docs/adr/0031-the-layout-carries-the-points-a-transit-needs.md)).
    """
    written = _written(topic, payload)
    if written is None or written[1] == 0.0:
        return []
    return [
        f"{train} driven over {commanded.transit_id} before an align named it"
        for train, commanded in record.starts(written[0])
        if commanded.transit_id not in record.aligned
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


def adr_0047_traction_from_the_near_end(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """`layout` writes traction for a move only if the train stands at the
    transit's near end
    ([ADR-0047](../../../docs/adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
    """
    written = _written(topic, payload)
    if written is None or written[1] == 0.0:
        return []
    lines: list[str] = []
    for train, commanded in record.starts(written[0]):
        ends = transit_ends(view.layout, commanded.into, commanded.transit_id)
        near = None if ends is None else block_of(ends[1])
        standing = record.trains.get(train)
        if near is None or standing != near:
            lines.append(
                f"{train} driven over {commanded.transit_id} from {standing},"
                f" not its near end in {near}"
            )
    return lines


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


def adr_0052_sign_composed(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A car's traction is positive when the move is nose-first and the car
    is `forward`, or propelled and `reverse`, and negative otherwise
    ([ADR-0052](../../../docs/adr/0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md)).

    Read of the speeds a move gives a train no throttle holds: its start,
    and a speed given again before it arrives. A lever's sign is the
    person's."""
    written = _written(topic, payload)
    if written is None or written[1] == 0.0:
        return []
    addr, speed = written
    expected: list[tuple[str, float]] = []
    for train, commanded in record.starts(addr):
        ends = transit_ends(view.layout, commanded.into, commanded.transit_id)
        signs = None if ends is None else record.composed(train, ends[1])
        if signs is not None and addr in signs:
            expected.append((train, signs[addr]))
    if not expected:
        holders = taken(record.rows.get(TAKEN))
        expected = [
            (train, started.signs[addr])
            for train, started in sorted(record.started.items())
            if addr in started.signs and train not in holders
        ]
    return [
        f"{train}'s car {addr} is written {speed}, the move gives it {sign:+.0f}"
        for train, sign in expected
        if (speed > 0.0) != (sign > 0.0)
    ]


def adr_0052_no_traction_without_facing(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """An addressed train gets no traction from a move until facing names
    the block it departs
    ([ADR-0052](../../../docs/adr/0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md),
    as amended by ADR-0095)."""
    written = _written(topic, payload)
    if written is None or written[1] == 0.0:
        return []
    lines: list[str] = []
    for train, commanded in record.starts(written[0]):
        ends = transit_ends(view.layout, commanded.into, commanded.transit_id)
        if ends is not None and record.composed(train, ends[1]) is None:
            facing = (kept_facing(record.rows.get(FACING)) or {}).get(train)
            lines.append(f"{train} driven out of {block_of(ends[1])} facing {facing}")
    return lines


def adr_0054_traction_zeroed_at_start(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """When `layout` starts, every retained traction row is set to 0 before
    any move
    ([ADR-0054](../../../docs/adr/0054-the-railroad-comes-up-at-rest-and-points-replay.md)).
    `layout` starting is its `state/railroad`, the first thing it says."""
    if topic != MOVE or not record.resting:
        return []
    return [f"a move with {sorted(record.resting)} not zeroed since the start"]


def adr_0060_new_railroad_only_while_off(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """`railroad` names a new railroad only while power reads `off`, except
    on a box with none loaded yet
    ([ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
    """
    if topic != RAILROAD:
        return []
    was = _fields(record.rows.get(RAILROAD)).get("name")
    name = _fields(payload).get("name")
    if not was or not isinstance(name, str) or name in ("", was):
        return []
    stated = power(record.rows.get(POWER))
    if stated == OFF:
        return []
    return [f"{name} loaded over {was} with power {stated}"]


def adr_0062_drain_ends_at_a_stand(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """`layout` writes `wanted/track: off` only while `moving` reads
    `false`, unless `power_wanted: off` was pressed or `layout` is coming up
    ([ADR-0062](../../../docs/adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md),
    as amended by ADR-0078)."""
    if topic != WANTED_TRACK or commanded_power(payload) != OFF:
        return []
    if record.cut_wanted or WANTED_TRACK in record.starting:
        return []
    if not moving(record.rows.get(MOVING)):
        return []
    return ["wanted/track written off while moving"]


def adr_0069_removed_is_stopped(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """On `train_removed`, `layout` writes speed 0 for every addressed car of
    that train
    ([ADR-0069](../../../docs/adr/0069-a-train-comes-off-while-running-and-its-track-opens-when-it-reads-clear.md)).
    """
    if topic != QUIET:
        return []
    return _owed(record.removed, "was taken off")


def adr_0074_comes_up_off(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """The railroad comes up with power `off` and `wanted/track` `off`
    ([ADR-0074](../../../docs/adr/0074-a-person-commands-track-power-and-it-is-cut-when-layout-goes-silent.md),
    as amended by ADR-0078)."""
    if topic not in record.starting:
        return []
    said = power(payload) if topic == POWER else commanded_power(payload)
    return [] if said == OFF else [f"layout came up with {topic} {said}"]


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


def adr_0078_cut_leaves_the_railroad_at_rest(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """From the supply cut until `power_wanted: on`, `wanted/track` reads
    `off` and every traction row reads 0
    ([ADR-0078](../../../docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md),
    with ADR-0081). A cut is `off` after `power_wanted: off` or at the end
    of a drain; the hardware reading the supply off is not one."""
    if topic == POWER and record.cuts(payload):
        lines = [
            f"car {addr} reads {speed} as the supply is cut"
            for addr, speed in sorted(_traction(record.rows).items())
            if speed != 0.0
        ]
        track = record.rows.get(WANTED_TRACK)
        if track is not None and commanded_power(track) != OFF:
            lines.append(f"wanted/track reads {commanded_power(track)} as it is cut")
        return lines
    if not record.cut:
        return []
    written = _written(topic, payload)
    if written is not None and written[1] != 0.0:
        return [f"car {written[0]} written {written[1]} with the supply cut"]
    if topic == WANTED_TRACK and commanded_power(payload) == ON:
        return ["wanted/track written on with the supply cut"]
    return []


def adr_0079_holder_changes_by_release(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """The throttle holding a train never changes to another without a
    release
    ([ADR-0079](../../../docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
    """
    if topic != TAKEN:
        return []
    before, after = taken(record.rows.get(TAKEN)), taken(payload)
    return [
        f"{train} went from {before[train]} to {after[train]} with no release"
        for train in sorted(before.keys() & after.keys())
        if before[train] != after[train]
    ]


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


def adr_0081_arrival_stops_the_train(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """When a move `layout` drove reaches its sensor, `layout` writes 0 for
    the train whoever drives it
    ([ADR-0081](../../../docs/adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)):
    before any other speed on its cars."""
    written = _written(topic, payload)
    if written is not None and written[1] != 0.0 and written[0] in record.arrived:
        train = record.arrived[written[0]]
        return [f"{train}'s car {written[0]} written {written[1]} at its sensor"]
    if topic != QUIET:
        return []
    return _owed(record.arrived, "reached its sensor")


def adr_0081_release_in_automatic(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A train released in `automatic` gets 0 with no move outstanding or
    with dead rails; with a move outstanding and live rails it keeps a
    nonzero speed
    ([ADR-0081](../../../docs/adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md),
    with ADR-0083)."""
    written = _written(topic, payload)
    if written is not None:
        addr, speed = written
        if speed != 0.0 and addr in record.released:
            return [f"{record.released[addr]}'s car {addr} written {speed}"]
        return [
            f"{train} released mid-move and stopped"
            for train in sorted(record.keeps)
            if speed == 0.0
            and record.under_way(train)
            and any(each == addr for each, _ in _addresses(view.roster, train))
        ]
    if topic != QUIET:
        return []
    speeds = _traction(record.rows)
    return _owed(record.released, "was released") + [
        f"{train} released mid-move and left standing"
        for train in sorted(record.keeps)
        if record.under_way(train)
        and not any(
            speeds.get(addr, 0.0) != 0.0
            for addr, _orientation in _addresses(view.roster, train)
        )
    ]


def adr_0084_sign_changes_through_zero(
    record: Record, view: View, topic: str, payload: Payload
) -> list[str]:
    """A car's traction never changes sign without a 0 written in between
    ([ADR-0084](../../../docs/adr/0084-a-reverser-moves-only-with-the-lever-at-0.md),
    with ADR-0088)."""
    written = _written(topic, payload)
    if written is None or written[1] == 0.0:
        return []
    addr, speed = written
    last = record.signs.get(addr)
    if last is None or (last > 0.0) == (speed > 0.0):
        return []
    return [f"car {addr} went from {last} to {speed} with no 0 between"]


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
        "0025",
        "The `move` that follows a grant carries the speed for the grant's"
        " aspect, the same for every grant of that aspect, and a grant at"
        " `stop` gets no `move`.",
        (MOVE_GRANTED, MOVE),
        adr_0025_move_at_the_aspects_speed,
    ),
    HistoryInvariant(
        "0031",
        "No traction is written for a move before the `align` naming its" " transit.",
        (ALIGN, MOVE, EVERY_TRACTION, TAKEN),
        adr_0031_no_traction_before_align,
    ),
    HistoryInvariant(
        "0047",
        "No `move_granted` for a train the allocation lists as crossing.",
        (MOVE_GRANTED, ALLOCATION, LOCK_RELEASED, TRAIN_PLACED, TRAIN_REMOVED),
        adr_0047_no_grant_while_crossing,
    ),
    HistoryInvariant(
        "0047",
        "`layout` writes traction for a move only if the train stands at the"
        " transit's near end.",
        (MOVE, EVERY_TRACTION, TAKEN, ALLOCATION, TRAIN_PLACED, TRAIN_REMOVED),
        adr_0047_traction_from_the_near_end,
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
        "0052",
        "A car's traction is positive when the move is nose-first and the car"
        " is `forward`, or propelled and `reverse`, and negative otherwise.",
        (EVERY_TRACTION, MOVE, FACING, TAKEN, BLOCK_OCCUPIED, TRAIN_REMOVED),
        adr_0052_sign_composed,
    ),
    HistoryInvariant(
        "0052",
        "An addressed train gets no traction from a move until facing names"
        " the block it departs.",
        (EVERY_TRACTION, MOVE, FACING, TAKEN),
        adr_0052_no_traction_without_facing,
    ),
    HistoryInvariant(
        "0054",
        "When `layout` starts, every retained traction row is set to 0 before"
        " any move.",
        (RAILROAD, EVERY_TRACTION, MOVE),
        adr_0054_traction_zeroed_at_start,
    ),
    HistoryInvariant(
        "0060",
        "`railroad` names a new railroad only while power reads `off`, except"
        " on a box with none loaded yet.",
        (RAILROAD, POWER),
        adr_0060_new_railroad_only_while_off,
    ),
    HistoryInvariant(
        "0062",
        "`layout` writes `wanted/track: off` only while `moving` reads"
        " `false`, unless `power_wanted: off` was pressed or `layout` is"
        " coming up.",
        (WANTED_TRACK, MOVING, POWER_WANTED, RAILROAD),
        adr_0062_drain_ends_at_a_stand,
    ),
    HistoryInvariant(
        "0069",
        "On `train_removed`, `layout` writes speed 0 for every addressed car"
        " of that train.",
        (TRAIN_REMOVED, EVERY_TRACTION),
        adr_0069_removed_is_stopped,
    ),
    HistoryInvariant(
        "0074",
        "The railroad comes up with power `off` and `wanted/track` `off`.",
        (RAILROAD, POWER, WANTED_TRACK),
        adr_0074_comes_up_off,
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
        + (REQUEST_COMPLETED, PLACEMENT_WANTED, PLACEMENT_REFUSED),
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
        "0078",
        "From the supply cut until `power_wanted: on`, `wanted/track` reads"
        " `off` and every traction row reads 0.",
        (POWER, POWER_WANTED, WANTED_TRACK, EVERY_TRACTION),
        adr_0078_cut_leaves_the_railroad_at_rest,
    ),
    HistoryInvariant(
        "0079",
        "The throttle holding a train never changes to another without a" " release.",
        (TAKEN,),
        adr_0079_holder_changes_by_release,
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
    HistoryInvariant(
        "0081",
        "When a move `layout` drove reaches its sensor, `layout` writes 0 for"
        " the train whoever drives it.",
        (MOVE, EVERY_TRACTION, TAKEN, BLOCK_OCCUPIED, TRAIN_REMOVED),
        adr_0081_arrival_stops_the_train,
    ),
    HistoryInvariant(
        "0081",
        "A train released in `automatic` gets 0 with no move outstanding or"
        " with dead rails; with a move outstanding and live rails it keeps a"
        " nonzero speed.",
        (TAKEN, DRIVING, POWER, POWER_WANTED, EVERY_TRACTION)
        + (MOVE_GRANTED, BLOCK_OCCUPIED, LOCK_RELEASED, TRAIN_REMOVED),
        adr_0081_release_in_automatic,
    ),
    HistoryInvariant(
        "0084",
        "A car's traction never changes sign without a 0 written in between.",
        (EVERY_TRACTION,),
        adr_0084_sign_changes_through_zero,
    ),
)
