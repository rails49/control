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

`ADR-0026` holds only where the dispatcher locks `Incremental`. The strategy
is not on the bus, so the `View` carries no field for it and the caller that
knows it leaves that invariant out.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import cast

from tc49.lib.bus import Payload
from tc49.lib.inventory import ON, Aspect
from tc49.lib.layout import (
    Layout,
    block_of,
    connected_end,
    facing_ends,
    transit_ends,
)
from tc49.lib.payload import kept_allocation, kept_facing, moving, power, shown_aspects
from tc49.lib.roster import Roster

ALLOCATION = "tc49/dispatch/state/allocation"
ASPECTS = "tc49/dispatch/state/aspects"
MOVING = "tc49/dispatch/state/moving"
UNFIT = "tc49/dispatch/state/unfit"
FACING = "tc49/schedule/state/facing"
POWER = "tc49/layout/state/power"

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


def cross_app(invariant: Invariant) -> bool:
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
    locks = _fields(view.rows.get(ALLOCATION)).get("locks")
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
    listed = _fields(view.rows.get(ALLOCATION)).get("requests")
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
