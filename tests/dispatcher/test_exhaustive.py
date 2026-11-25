"""Every order in which sensors can read for two trains on a small railroad
(#1331, spec #1315).

The test keeps a model of the steel beside the lock table and drives the
table's transitions directly, with no bus. It visits every state reachable
from a case's placements once, keyed on the table together with the model,
and checks at each one that the table still describes the steel.

**The railroad.** `stub` is a terminal track: its A end is a buffer stop.
Its B end meets a turnout, whose two ways lead into `up` and `down` by their
A ends, and the B ends of `up` and `down` are joined, so the two make a loop.

        |[ stub ]=< points >=[ up   ]=\\
                            =[ down ]=/  loop

**The steel.** Each block is cut into seven pieces from A to B: the stretch
beyond the sensor at A, the sensor at A, three pieces between the sensors,
the sensor at B and the stretch beyond it. Each transit is one piece. A
sensor reads `occupied` while a train covers its piece, which is what a
truthful sensor gives (GOALS.md, **Tracks**). A train is the stretch of
pieces it covers, tail to head, and moves head first, one end one piece at a
time, covering between `lo` and `hi` pieces. A short train covers one or two
pieces, so it fits between a block's sensors; a long one covers four or five,
so it cannot, and it is still no longer than its block, sensor to sensor.

A train is driven as the dispatcher grants: its head goes as far as the far
sensor of the last block it was granted into, where `layout` stops it
(GOALS.md, **Driving**), and onto the stretch beyond only with a grant beyond.
It may stop anywhere short of that, so every relative speed of the two trains
is tried. A train given a route back out by the end its tail is towards runs
on the way it was going until it stops and turns, which is a step of its own:
`layout` holds such a move until the train has stopped.

**The steps.** From each state: a train's head or tail moving one piece on,
with the reading it causes taken by the table at once (`reading`, then
`opening`), and a run whose newest move ended at its route's last block
completing; a train stopping and turning; or any move the obstacle answer
allows: a route committed for a train with no run, from either end of its
block, with its first move granted as a launch does; or an active train's
next move. A move is granted without the increment beyond it and, where the
obstacle answer allows that too, with it, since the safety check may refuse
it.

**The checks, at every state:** each piece a train covers is locked to that
train, so nothing was released under it and no two trains cover one piece;
`broken()` returns nothing (ADR-0076); and a `clear` reading changed nothing
of any train but one whose move expected that sensor. A state with a fault is
counted and not gone on from.

**Left out:** the cases GOALS.md lists as not guarded, `unknown` sensors, the
deadlock check (#1331), and readings reaching the dispatcher later than the
steel gave them.
"""

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, replace
from functools import cache

import pytest

from tc49.dispatcher.table import (
    Effect,
    Move,
    MoveEnded,
    Route,
    Table,
    broken,
    committing,
    completing,
    granting,
    opening,
    placing,
    reading,
)
from tc49.lib.layout import Layout, block_of, opposite_end, transit_ends

RAILROAD = Layout.from_document(
    {
        "layout": "stub-and-loop",
        "blocks": {
            "stub": {"length": 1000},
            "up": {"length": 1000},
            "down": {"length": 1000},
        },
        "connections": {
            "points": {
                "transits": {
                    "to_up": ["stub.B", "up.A"],
                    "to_down": ["stub.B", "down.A"],
                }
            },
            "loop": {"transits": {"join": ["up.B", "down.B"]}},
        },
    }
)
TRANSITS = frozenset(
    f"{connection.name}.{transit}"
    for connection in RAILROAD.connections.values()
    for transit in connection.transits
)
SENSORS = frozenset(f"{block}.{end}" for block in RAILROAD.blocks for end in "AB")
CUTS = ("a", "A", "1", "2", "3", "B", "b")  # a block's pieces, from A to B


def pieces(block: str, towards: str) -> list[str]:
    """The block's pieces in the order a train heading for end `towards`
    covers them."""
    ordered = [f"{block}.{cut}" for cut in CUTS]
    return ordered if towards == f"{block}.B" else ordered[::-1]


def resources(piece: str) -> frozenset[str]:
    """What a train covering `piece` must hold a lock on, one of: the block,
    or the transit over the piece. The stretch beyond a sensor is the block's,
    and also each transit at that end's, since a tail past an exit sensor has
    left the block and is on the transit (GOALS.md, the reading table)."""
    if piece in TRANSITS:
        return frozenset([piece])
    block, _, cut = piece.partition(".")
    if cut in ("a", "b"):
        end = f"{block}.{cut.upper()}"
        return frozenset([block, *(t for t, _ in RAILROAD.transits_at(end))])
    return frozenset([block])


@dataclass(frozen=True)
class Steel:
    """Where one train is: the pieces it covers, tail to head; the pieces it
    may still run on to; the end of its block its head is heading for; and,
    once it has been given a route back out the way it is heading from, that
    route's pieces, for it to take once it has stopped and turned."""

    stretch: tuple[str, ...]
    ahead: tuple[str, ...]
    facing: str
    turning: tuple[str, ...] = ()


@dataclass(frozen=True)
class Case:
    """Two trains, each with the fewest and most pieces it covers, and where
    each is placed: the pieces it covers and the end it faces."""

    lengths: dict[str, tuple[int, int]]
    placed: dict[str, Steel]


SHORT, LONG = (1, 2), (4, 5)

State = tuple[Table, tuple[Steel, ...]]


def routes(origin: str) -> Iterator[Route]:
    """Every route out of `origin`, by either end, of two or three blocks
    with none twice."""

    def onward(
        blocks: tuple[str, ...], transits: tuple[str, ...], end: str
    ) -> Iterator[Route]:
        for transit, across in RAILROAD.transits_at(end):
            into = block_of(across)
            if into in blocks:
                continue
            route = Route((*blocks, into), (*transits, transit))
            yield route
            if len(route.blocks) < 3:
                yield from onward(route.blocks, route.transits, opposite_end(across))

    for end in (f"{origin}.A", f"{origin}.B"):
        yield from onward((origin,), (), end)


def entry(block: str, transit: str) -> str:
    ends = transit_ends(RAILROAD, block, transit)
    assert ends is not None
    return ends[0]


def turned(head: str, piece: str, facing: str) -> str:
    """The end of its block a train's head heads for once it has moved from
    `head` onto `piece`."""
    if piece in TRANSITS:
        return facing
    block, _, cut = piece.partition(".")
    if block_of(head) == block and head not in TRANSITS:
        before = CUTS.index(head.partition(".")[2])
        return f"{block}.B" if CUTS.index(cut) > before else f"{block}.A"
    return f"{block}.B" if cut == "a" else f"{block}.A"


@dataclass(frozen=True)
class Fault:
    check: str
    detail: str


def sensed(table: Table, sensor: str, occupied: bool, faults: list[Fault]) -> Table:
    """A settled reading taken as the dispatcher takes it: the reading, a run
    whose newest move ended at its last block completing, then residue
    opening. A clear reading that changes a train whose move did not expect
    it is a fault."""
    expecting = {
        train
        for train, following in table.following.items()
        for each in following
        if (each.exit == sensor and each.exit_read)
        or (each.entry == sensor and each.head_in)
    }
    new, effects = reading(table, sensor, occupied)
    if not occupied:
        for train in table.block_of:
            if train not in expecting and _of(table, train) != _of(new, train):
                faults.append(
                    Fault("clear", f"{sensor} clear changed {train}: {_of(new, train)}")
                )
    new = _ended(new, effects)
    return opening(new)[0]


def _of(table: Table, train: str) -> tuple[object, ...]:
    return (
        frozenset(r for r, holder in table.locks.items() if holder == train),
        table.block_of.get(train),
        table.active.get(train),
        table.crossing.get(train),
        table.occupied.get(train),
        table.following.get(train),
    )


def _ended(table: Table, effects: list[Effect]) -> Table:
    """`dispatch._request_over` without cancellation: a run whose newest move
    ended in its route's last block completes."""
    for effect in effects:
        if isinstance(effect, MoveEnded):
            active = table.active.get(effect.train)
            if (
                active is not None
                and active.outstanding is None
                and active.cur_index == len(active.route.blocks) - 1
            ):
                table = completing(table, effect.train)[0]
    return table


def placed(case: Case) -> tuple[State, list[Fault]]:
    """The case's trains placed, then every sensor read as the steel has it."""
    names = sorted(case.placed)
    table = Table(RAILROAD, {}, {}, {})
    for train in names:
        table = placing(table, train, block_of(case.placed[train].stretch[0]))[0]
    covered = {piece for steel in case.placed.values() for piece in steel.stretch}
    faults: list[Fault] = []
    for sensor in sorted(SENSORS):
        table = sensed(table, sensor, sensor in covered, faults)
    return (table, tuple(case.placed[train] for train in names)), faults


def steps(case: Case, state: State) -> Iterator[tuple[str, State, list[Fault]]]:
    """Every next step from `state`, each with what it found wrong on the
    way."""
    table, steel = state
    names = sorted(case.placed)
    for i, train in enumerate(names):
        lo, hi = case.lengths[train]
        each = steel[i]
        others = {p for j, s in enumerate(steel) if j != i for p in s.stretch}
        if len(each.stretch) < hi and each.ahead:
            piece = each.ahead[0]
            moved = Steel(
                (*each.stretch, piece),
                each.ahead[1:],
                turned(each.stretch[-1], piece, each.facing),
            )
            yield _moved(
                f"{train} head onto {piece}",
                table,
                steel,
                i,
                moved,
                piece,
                True,
                others,
            )
        if len(each.stretch) > lo:
            piece = each.stretch[0]
            moved = replace(each, stretch=each.stretch[1:])
            yield _moved(
                f"{train} tail off {piece}",
                table,
                steel,
                i,
                moved,
                piece,
                False,
                others,
            )
        if each.turning:
            yield f"{train} stops and turns", (
                table,
                (*steel[:i], _turned(each), *steel[i + 1 :]),
            ), []
    for i, train in enumerate(names):
        active = table.active.get(train)
        if active is None:
            yield from _launches(table, steel, i, train)
        elif (
            active.outstanding is None
            and active.cur_index < len(active.route.blocks) - 1
        ):
            yield from _grants(table, steel, i, train)


def _moved(
    label: str,
    table: Table,
    steel: tuple[Steel, ...],
    i: int,
    moved: Steel,
    piece: str,
    occupied: bool,
    others: set[str],
) -> tuple[str, State, list[Fault]]:
    faults: list[Fault] = []
    if piece in SENSORS and piece not in others:
        table = sensed(table, piece, occupied, faults)
    return label, (table, (*steel[:i], moved, *steel[i + 1 :])), faults


def _free(table: Table, train: str, *wanted: str) -> bool:
    return all(table.obstacle(resource, train) is None for resource in wanted)


def _aheads(table: Table, train: str, route: Route, i: int) -> list[list[str]]:
    """The increments beyond a move out of `route.blocks[i]` it may be
    granted with: none, and the next where the obstacle answer allows it."""
    if i + 1 >= len(route.transits):
        return [[]]
    beyond = [route.transits[i + 1], route.blocks[i + 2]]
    return [[], beyond] if _free(table, train, *beyond) else [[]]


def _launches(
    table: Table, steel: tuple[Steel, ...], i: int, train: str
) -> Iterator[tuple[str, State, list[Fault]]]:
    """Each route a train with no run may be given, launched as `_launch`
    does: committed with its first increment, and that move granted."""
    each = steel[i]
    origin = table.block_of[train]
    for route in routes(origin):
        first = [route.transits[0], route.blocks[1]]
        if not _free(table, train, *first):
            continue
        leaving = entry(origin, route.transits[0])
        path = (
            *pieces(origin, leaving),
            route.transits[0],
            *pieces(
                route.blocks[1], opposite_end(entry(route.blocks[1], route.transits[0]))
            )[:-1],
        )
        if each.facing == leaving:
            moved = _onto(each.stretch, path)
        else:
            moved = replace(each, turning=path)
        committed = committing(table, train, train, route, first)[0]
        for ahead in _aheads(committed, train, route, 0):
            move = Move(origin, route.transits[0], route.blocks[1], [], ahead)
            granted = granting(committed, train, move)[0]
            label = f"{train} launched {'-'.join(route.blocks)}" + (
                " with the increment beyond" if ahead else ""
            )
            yield label, (granted, (*steel[:i], moved, *steel[i + 1 :])), []


def _onto(stretch: tuple[str, ...], path: tuple[str, ...]) -> Steel:
    """A train covering `stretch`, heading along `path`, which starts in the
    block it stands in wholly: a train with no run stands in one block."""
    head = path.index(stretch[-1])
    assert path[head - len(stretch) + 1 : head + 1] == stretch, stretch
    block, _, cut = path[6].partition(".")
    return Steel(stretch, path[head + 1 :], f"{block}.{cut.upper()}")


def _turned(each: Steel) -> Steel:
    """A train given a route back out the way it came, once it has stopped:
    `layout` holds such a move until then (GOALS.md, **Driving**)."""
    return _onto(each.stretch[::-1], each.turning)


def _grants(
    table: Table, steel: tuple[Steel, ...], i: int, train: str
) -> Iterator[tuple[str, State, list[Fault]]]:
    """An active train's next move, as `Incremental.grant` makes it."""
    active = table.active[train]
    route, at = active.route, active.cur_index
    transit, into = route.transits[at], route.blocks[at + 1]
    if not _free(table, train, transit, into):
        return
    newly = [r for r in (transit, into) if table.locks.get(r) != train]
    each = steel[i]
    beyond = pieces(route.blocks[at], entry(route.blocks[at], transit))[-1]
    onward = (beyond, transit, *pieces(into, opposite_end(entry(into, transit)))[:-1])
    for ahead in _aheads(table, train, route, at):
        granted = granting(
            table, train, Move(route.blocks[at], transit, into, newly, ahead)
        )[0]
        moved = replace(each, ahead=(*each.ahead, *onward))
        label = f"{train} granted into {into}" + (
            " with the increment beyond" if ahead else ""
        )
        yield label, (granted, (*steel[:i], moved, *steel[i + 1 :])), []


def checked(case: Case, state: State) -> list[Fault]:
    """What the state breaks: a piece a train covers not locked to it, a piece
    two trains cover, and the table's own rules."""
    table, steel = state
    faults: list[Fault] = []
    covering: dict[str, str] = {}
    for train, each in zip(sorted(case.placed), steel):
        for piece in each.stretch:
            if piece in covering:
                faults.append(
                    Fault("steel", f"{train} and {covering[piece]} cover {piece}")
                )
            covering[piece] = train
            if not any(table.locks.get(r) == train for r in resources(piece)):
                faults.append(
                    Fault("steel", f"{train} covers {piece}, which it holds no lock on")
                )
    faults += [Fault("broken", line) for line in broken(table)]
    return faults


@dataclass
class Searched:
    visited: int
    fault: Fault | None
    sequence: list[str]


@cache
def search(name: str) -> Searched:
    """Every state reachable from the case's placements, breadth first, so
    the first fault found comes with the shortest sequence of steps that
    reaches it. A state with a fault is counted and not gone on from: what
    follows a table that no longer describes the steel is not asked about."""
    case = CASES[name]
    start, faults = placed(case)
    faults += checked(case, start)
    assert not faults, faults
    parent: dict[State, tuple[State, str] | None] = {start: None}
    found: tuple[Fault, list[str]] | None = None
    queue = deque([start])
    while queue:
        state = queue.popleft()
        for label, new, faults in steps(case, state):
            if new not in parent:
                parent[new] = (state, label)
                faults += checked(case, new)
                if not faults:
                    queue.append(new)
            if faults and found is None:
                found = (faults[0], [*_sequence(parent, state), label])
    if found is None:
        return Searched(len(parent), None, [])
    return Searched(len(parent), *found)


def _sequence(parent: dict[State, tuple[State, str] | None], state: State) -> list[str]:
    labels: list[str] = []
    while (came := parent[state]) is not None:
        state, label = came
        labels.append(label)
    return labels[::-1]


def _steel(*cuts: str, facing: str) -> Steel:
    return Steel(tuple(cuts), (), facing)


CASES = {
    "a short and a long train": Case(
        {"s": SHORT, "l": LONG},
        {
            "s": _steel("stub.2", facing="stub.B"),
            "l": _steel("up.A", "up.1", "up.2", "up.3", facing="up.B"),
        },
    ),
    "two short trains": Case(
        {"s": SHORT, "t": SHORT},
        {
            "s": _steel("stub.2", facing="stub.B"),
            "t": _steel("up.2", facing="up.B"),
        },
    ),
    "two long trains": Case(
        {"l": LONG, "m": LONG},
        {
            "l": _steel("stub.A", "stub.1", "stub.2", "stub.3", facing="stub.B"),
            "m": _steel("up.A", "up.1", "up.2", "up.3", facing="up.B"),
        },
    ),
    "a train placed beyond the sensor it leaves by": Case(
        {"s": SHORT, "l": LONG},
        {
            "s": _steel("stub.b", facing="stub.B"),
            "l": _steel("down.2", "down.3", "down.B", "down.b", facing="down.B"),
        },
    ),
}


REVERSING = pytest.mark.xfail(
    reason="#1336: a reversing move takes the tail rolling off the entry"
    " sensor as the train leaving its block",
    raises=AssertionError,
    strict=True,
)


@pytest.mark.parametrize(
    ("name", "visited"),
    [
        ("a short and a long train", 31033),
        ("two short trains", 35969),
        ("two long trains", 22709),
        ("a train placed beyond the sensor it leaves by", 31653),
    ],
)
def test_the_search_visits_every_state_once(name: str, visited: int) -> None:
    """The count, so a change that shrinks the search shows."""
    assert search(name).visited == visited


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("a short and a long train", marks=REVERSING),
        "two short trains",
        pytest.param("two long trains", marks=REVERSING),
        pytest.param("a train placed beyond the sensor it leaves by", marks=REVERSING),
    ],
)
def test_no_reading_order_releases_track_under_a_train(name: str) -> None:
    found = search(name)

    assert found.fault is None, "\n".join([str(found.fault), *found.sequence])
