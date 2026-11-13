"""The locking seam: LockingStrategy and the FullRoute baseline (ADR-0005).

A strategy answers two questions against the dispatcher's live state:
``launch`` — commit a route for a pending request from the origin and
departure end the dispatcher hands it, locking whatever the strategy's
discipline requires; ``grant`` — advance an active train by one move. Both
return what to lock and write nothing: the state they are handed is
``ReadOnlyState``, and the dispatcher locks what they return and publishes
the lock ledger from it, so the dispatcher is the lock table's one writer
(#761).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from tc49.dispatcher.routing import Route, candidates
from tc49.dispatcher.safety import finishable, safe
from tc49.lib.inventory import Refusal
from tc49.lib.layout import Layout, block_of

if TYPE_CHECKING:
    from tc49.dispatcher.dispatch import Active, Request


@dataclass(frozen=True)
class Launched:
    route: Route
    k_tried: int  # candidates examined up to and including the committed one
    locked: list[str]  # resources newly locked, in crossing order


@dataclass(frozen=True)
class Refused:
    reason: str  # 'held' | 'transit_conflict' | 'unsafe'
    # One {resource, holder} per blocked candidate, or the one block out of use
    # that a launch names where no candidate is left to try (#1152).
    obstacles: list[dict[str, str]]


@dataclass(frozen=True)
class Move:
    from_block: str
    transit: str
    into: str
    locked: list[str]  # resources newly locked for this move; [] under FullRoute
    # The second increment, when it was obtained: a separate grant, published
    # as its own lock_granted so a grant stays one transit with its far block
    # (ADR-0029). Empty means it was not obtained, which is the `caution`
    # aspect rather than an error.
    ahead: list[str]


class ReadOnlyState(Protocol):
    """What a strategy reads of the dispatcher's `State`, and nothing it could
    write: `State` satisfies it as it is, and a strategy handed one cannot
    take a lock itself (#761)."""

    @property
    def layout(self) -> Layout: ...

    @property
    def roster(self) -> Mapping[str, int]: ...

    @property
    def locks(self) -> Mapping[str, str]: ...

    @property
    def block_of(self) -> Mapping[str, str]: ...

    @property
    def active(self) -> Mapping[str, Active]: ...

    @property
    def readings(self) -> Mapping[str, bool]: ...

    @property
    def occupied(self) -> Mapping[str, Sequence[str]]: ...

    @property
    def residue(self) -> AbstractSet[str]: ...

    @property
    def out_of_use(self) -> AbstractSet[str]: ...

    def reads_occupied(self, block: str) -> bool: ...

    def obstacle(self, resource: str, train: str) -> tuple[str, str, str] | None: ...


class LockingStrategy(Protocol):
    def launch(
        self, req: Request, origin: str, depart: str, state: ReadOnlyState
    ) -> Launched | Refused | None:
        """Try to launch; None means no candidate routes exist (unreachable).

        The departure end comes from the dispatcher rather than off the
        request: which end a train leaves by is admission's question and
        not the strategy's."""
        ...

    def grant(self, train: str, state: ReadOnlyState) -> Move | Refused:
        """The active train's next move, or why it must wait."""
        ...


def standing_still(state: ReadOnlyState) -> list[str]:
    """The blocks that read occupied and that nobody holds or that are
    residue, since nothing is granted into them until they read clear
    (ADR-0077), and the blocks out of use, until their sensors return (#1152):
    obstacles as permanent as an idle train's block."""
    occupied = {block_of(s) for s, reading in state.readings.items() if reading}
    return sorted(
        state.out_of_use
        | {
            block
            for block in occupied
            if block not in state.locks or block in state.residue
        }
    )


def congested(state: ReadOnlyState, train: str) -> frozenset[str]:
    """The congested blocks route selection steers around (#33): blocks
    locked by another train — idle holders included — blocks on the
    committed remaining route of another active train, and blocks that read
    occupied with nobody standing in them (ADR-0077) or are out of use. The
    committed part is what restores to `Incremental` the signal `FullRoute`'s
    up-front locks carry for free; a deterministic function of state, so
    ordering stays reproducible."""
    blocks = {
        resource
        for resource, holder in state.locks.items()
        if holder != train and "." not in resource
    }
    blocks.update(standing_still(state))
    for other, active in state.active.items():
        if other != train:
            blocks.update(active.route.blocks[active.cur_index :])
    return frozenset(blocks)


def _launchable(
    layout: Layout,
    k: int,
    req: Request,
    origin: str,
    depart: str,
    state: ReadOnlyState,
) -> list[Route] | Refused | None:
    """The routes a launch may try, or what it answers without trying one.

    None is unreachable, which the request is rejected for, and it is asked
    with the blocks out of use left in: a request a failed sensor stands in the
    way of has to wait, and not be rejected (#1152). So a train standing in a
    block out of use, and one every route of which crosses such a block, is
    refused `held`, naming the block, the first on the first route, and no
    holder (#1254).
    """
    length = state.roster[req.train]
    busy = congested(state, req.train)
    out = state.out_of_use
    routes = candidates(layout, origin, depart, req.arrivals, length, k, busy, out)
    if routes and origin not in out:
        return routes
    every = candidates(layout, origin, depart, req.arrivals, length, k, busy)
    if not every:
        return None
    block = next(b for b in every[0].blocks if b in out)
    return Refused(Refusal.HELD, [{"resource": block, "holder": ""}])


def _standing_refusal(train: str, state: ReadOnlyState) -> Refused | None:
    """Why an active train may not leave the block it stands in, where it is out
    of use: refused `held`, naming that block and no holder, whatever it holds
    beyond (#1152, #1254)."""
    active = state.active[train]
    block = active.route.blocks[active.cur_index]
    if block not in state.out_of_use:
        return None
    return Refused(Refusal.HELD, [{"resource": block, "holder": ""}])


class FullRoute:
    """The baseline: launch locks the entire route or refuses; grant walks
    the already-locked route, asking only that the block it moves into does
    not read occupied (ADR-0077)."""

    def __init__(self, layout: Layout, k: int) -> None:
        self._layout = layout
        self._k = k

    def launch(
        self, req: Request, origin: str, depart: str, state: ReadOnlyState
    ) -> Launched | Refused | None:
        routes = _launchable(self._layout, self._k, req, origin, depart, state)
        if routes is None or isinstance(routes, Refused):
            return routes
        reason = ""
        obstacles: list[dict[str, str]] = []
        for tried, route in enumerate(routes, start=1):
            blocking = next(
                (
                    found
                    for resource in route.crossing_order()
                    if (found := state.obstacle(resource, req.train)) is not None
                ),
                None,
            )
            if blocking is None:
                return Launched(route, tried, route.crossing_order())
            reason = reason or blocking[0]
            obstacles.append({"resource": blocking[1], "holder": blocking[2]})
        return Refused(reason, obstacles)

    def grant(self, train: str, state: ReadOnlyState) -> Move | Refused:
        standing = _standing_refusal(train, state)
        if standing is not None:
            return standing
        active = state.active[train]
        i = active.cur_index
        into = active.route.blocks[i + 1]
        blocking = state.obstacle(into, train)
        if blocking is not None:
            return Refused(
                blocking[0], [{"resource": blocking[1], "holder": blocking[2]}]
            )
        return Move(
            active.route.blocks[i],
            active.route.transits[i],
            into,
            locked=[],
            ahead=[],
        )


class Incremental:
    """Each grant locks the next transit plus block, gated by the
    route-aware banker's safety check, and then asks for one increment more.
    A launch tries up to `k` candidates and takes the first whose
    post-launch state is safe; transit concurrency is admissibility at the
    grant, never part of the deadlock check.

    The second increment is asked for and not required (ADR-0029): a train
    that gets it holds two blocks beyond where it stands and runs at
    `clear`, one that does not runs at `caution`. Refusing the move
    because the second increment was unavailable would make `caution`
    unreachable, which is the aspect it exists to express."""

    def __init__(self, layout: Layout, k: int) -> None:
        self._layout = layout
        self._k = k

    def launch(
        self, req: Request, origin: str, depart: str, state: ReadOnlyState
    ) -> Launched | Refused | None:
        routes = _launchable(self._layout, self._k, req, origin, depart, state)
        if routes is None or isinstance(routes, Refused):
            return routes
        reason = ""
        obstacles: list[dict[str, str]] = []
        for tried, route in enumerate(routes, start=1):
            increment = [route.transits[0], route.blocks[1]]
            blocking = next(
                (
                    found
                    for resource in increment
                    if (found := state.obstacle(resource, req.train)) is not None
                ),
                None,
            )
            if blocking is None:
                # The launch grants the first increment, and the first move
                # follows in the same phase — so the state to check is the
                # post-grant one: mid-transit, cur at the far block.
                cur, rem, idle, held = safety_view(state, skip=req.train)
                cur[req.train] = route.blocks[1]
                rem[req.train] = list(route.blocks[2:])
                held[req.train] = []  # the increment is cur; nothing beyond it
                if safe(cur, rem, idle, held):
                    return Launched(route, tried, increment)
                blocking = (
                    Refusal.UNSAFE,
                    *_unsafe_obstacle(route.blocks[1:], state, req.train),
                )
            reason = reason or blocking[0]
            obstacles.append({"resource": blocking[1], "holder": blocking[2]})
        return Refused(reason, obstacles)

    def grant(self, train: str, state: ReadOnlyState) -> Move | Refused:
        standing = _standing_refusal(train, state)
        if standing is not None:
            return standing
        active = state.active[train]
        i = active.cur_index
        transit, into = active.route.transits[i], active.route.blocks[i + 1]
        blocking = next(
            (
                found
                for resource in (transit, into)
                if (found := state.obstacle(resource, train)) is not None
            ),
            None,
        )
        if blocking is None:
            cur, rem, idle, held = safety_view(state, skip=train)
            cur[train] = into  # mid-transit: the far block (Lemma 1)
            rem[train] = list(active.route.blocks[i + 2 :])
            held[train] = []  # the increment is cur; nothing beyond it
            if safe(cur, rem, idle, held):
                # The move after a launch re-grants the increment the launch
                # already locked; report only what is newly locked.
                newly = [r for r in (transit, into) if state.locks.get(r) != train]
                # Asked as if the first increment were locked, which is what
                # it reads as: `obstacle` passes the train's own transits and
                # `safety_view` skips the train.
                ahead = self._reach_ahead(train, i, state)
                return Move(active.route.blocks[i], transit, into, newly, ahead)
            blocking = (
                Refusal.UNSAFE,
                *_unsafe_obstacle(active.route.blocks[i + 1 :], state, train),
            )
        return Refused(blocking[0], [{"resource": blocking[1], "holder": blocking[2]}])

    def _reach_ahead(self, train: str, i: int, state: ReadOnlyState) -> list[str]:
        """The second increment, asked for once the first is granted. Returns
        what it locked, or [] — obstructed, unsafe, or a route with nothing
        that far ahead. Never a refusal: the move has already been granted,
        and an empty answer is what the `caution` aspect reports.

        The safety check is the same one the first increment passed, with the
        train now standing at the far block and holding the one beyond it —
        an ordinary grant made early (ADR-0026), so an ordinary check."""
        route = state.active[train].route
        if i + 1 >= len(route.transits):
            return []  # the route ends within one block of here
        transit, into = route.transits[i + 1], route.blocks[i + 2]
        if any(state.obstacle(r, train) is not None for r in (transit, into)):
            return []
        cur, rem, idle, held = safety_view(state, skip=train)
        cur[train] = route.blocks[i + 1]
        rem[train] = list(route.blocks[i + 2 :])
        held[train] = [into]
        if not safe(cur, rem, idle, held):
            return []
        return [transit, into]


def state_view(
    state: ReadOnlyState, skip: str | None = None
) -> tuple[dict[str, str], dict[str, list[str]], list[str], dict[str, list[str]]]:
    """The safe() inputs for the current state with every active train in
    them, excluding `skip`, if any.

    What a train holds ahead is read off the lock table rather than off the
    strategy's depth, so the check describes the state it is given whatever
    asked for it. A block that reads occupied with nobody standing in it is
    an idle obstacle beside the idle trains' blocks, each block on an idle train's
    `occupied` list as well as the one it stands in (ADR-0077, #1171), and so is
    a block out of use. An active train standing in one is frozen where it stands, with
    what it holds: its route ahead may be free, and it goes nowhere until its
    sensor returns (#1152), so it is no train a finishing order can count on."""
    cur: dict[str, str] = {}
    rem: dict[str, list[str]] = {}
    held: dict[str, list[str]] = {}
    frozen: list[str] = []
    for train, active in state.active.items():
        if train != skip:
            at = active.route.blocks[active.cur_index]
            ahead = list(active.route.blocks[active.cur_index + 1 :])
            holding = [b for b in ahead if state.locks.get(b) == train]
            if at in state.out_of_use:
                frozen += [at, *holding]
            else:
                cur[train], rem[train], held[train] = at, ahead, holding
    idle: list[str] = []
    for train, standing in state.block_of.items():
        if train not in state.active and train != skip:
            behind = state.occupied.get(train, ())
            idle += [e for e in behind if e in state.layout.blocks and e != standing]
            idle.append(standing)
    idle += frozen
    idle += standing_still(state)
    return cur, rem, idle, held


def safety_view(
    state: ReadOnlyState, skip: str | None = None
) -> tuple[dict[str, str], dict[str, list[str]], list[str], dict[str, list[str]]]:
    """What a grant is checked against, excluding `skip` (the train whose
    tentative position the caller supplies), if any.

    The largest set of trains that can all finish is judged on the current
    state, with no train skipped. Any other train, unless it is the one asking,
    leaves the check and its blocks are idle obstacles: one stuck train stops
    only itself and those that need its blocks (#1150). The one asking is
    judged as ever, against that set and these obstacles.

    With every active train able to finish this is `state_view`, so
    `safe(*safety_view(state))` always holds. To ask whether a state is safe,
    use `state_view`. A train standing in a block out of use is already outside
    it, an idle obstacle (`state_view`)."""
    able = finishable(*state_view(state))
    cur, rem, idle, held = state_view(state, skip)
    for train in sorted(set(cur) - able):
        idle += [cur.pop(train), *held.pop(train)]
        del rem[train]
    return cur, rem, idle, held


def _unsafe_obstacle(
    remaining: Sequence[str], state: ReadOnlyState, train: str
) -> tuple[str, str]:
    """Name the obstacle behind an unsafe verdict: the first remaining
    block another train holds, or — the shared-destination case, where
    nothing is locked yet — the block another active train is committed to
    parking on, or the first remaining block that reads occupied with nobody
    standing in it or is out of use, holder "" where nobody holds it (ADR-0077,
    #1152). A block out of use names no holder, and neither does `train`'s own
    lock, as `State.obstacle` answers (#1254)."""
    for block in remaining:
        holder = state.locks.get(block)
        if holder is not None and holder != train:
            return (block, "" if block in state.out_of_use else holder)
    for other in sorted(state.active):
        dest = state.active[other].route.arrival_block
        if other != train and dest in remaining:
            return (dest, other)
    still = standing_still(state)
    for block in remaining:
        if block in still and (found := state.obstacle(block, train)) is not None:
            return (block, found[2])
    holder = state.locks.get(remaining[-1], "")
    return (remaining[-1], "" if holder == train else holder)
