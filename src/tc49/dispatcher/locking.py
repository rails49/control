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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from tc49.dispatcher.routing import Route, candidates
from tc49.dispatcher.safety import safe
from tc49.lib.inventory import Refusal
from tc49.lib.layout import Layout

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
    obstacles: list[dict[str, str]]  # one {resource, holder} per blocked candidate


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


def congested(state: ReadOnlyState, train: str) -> frozenset[str]:
    """The congested blocks route selection steers around (#33): blocks
    locked by another train — idle holders included — and blocks on the
    committed remaining route of another active train. The committed part is
    what restores to `Incremental` the signal `FullRoute`'s up-front locks
    carry for free; a deterministic function of state, so ordering stays
    reproducible."""
    blocks = {
        resource
        for resource, holder in state.locks.items()
        if holder != train and "." not in resource
    }
    for other, active in state.active.items():
        if other != train:
            blocks.update(active.route.blocks[active.cur_index :])
    return frozenset(blocks)


class FullRoute:
    """The baseline: launch locks the entire route or refuses; grant walks
    the already-locked route with no further check."""

    def __init__(self, layout: Layout, k: int) -> None:
        self._layout = layout
        self._k = k

    def launch(
        self, req: Request, origin: str, depart: str, state: ReadOnlyState
    ) -> Launched | Refused | None:
        routes = candidates(
            self._layout,
            origin,
            depart,
            req.arrivals,
            state.roster[req.train],
            self._k,
            congested(state, req.train),
        )
        if not routes:
            return None
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

    def grant(self, train: str, state: ReadOnlyState) -> Move:
        active = state.active[train]
        i = active.cur_index
        return Move(
            active.route.blocks[i],
            active.route.transits[i],
            active.route.blocks[i + 1],
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
        routes = candidates(
            self._layout,
            origin,
            depart,
            req.arrivals,
            state.roster[req.train],
            self._k,
            congested(state, req.train),
        )
        if not routes:
            return None
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


def safety_view(
    state: ReadOnlyState, skip: str | None = None
) -> tuple[dict[str, str], dict[str, list[str]], list[str], dict[str, list[str]]]:
    """The safe() inputs for the current state, excluding `skip` (the train
    whose tentative position the caller supplies), if any.

    What a train holds ahead is read off the lock table rather than off the
    strategy's depth, so the check describes the state it is given whatever
    asked for it."""
    cur: dict[str, str] = {}
    rem: dict[str, list[str]] = {}
    held: dict[str, list[str]] = {}
    for train, active in state.active.items():
        if train != skip:
            cur[train] = active.route.blocks[active.cur_index]
            rem[train] = list(active.route.blocks[active.cur_index + 1 :])
            held[train] = [b for b in rem[train] if state.locks.get(b) == train]
    idle = [
        block
        for train, block in state.block_of.items()
        if train not in state.active and train != skip
    ]
    return cur, rem, idle, held


def _unsafe_obstacle(
    remaining: Sequence[str], state: ReadOnlyState, train: str
) -> tuple[str, str]:
    """Name the obstacle behind an unsafe verdict: the first remaining
    block another train holds, or — the shared-destination case, where
    nothing is locked yet — the block another active train is committed to
    parking on."""
    for block in remaining:
        holder = state.locks.get(block)
        if holder is not None and holder != train:
            return (block, holder)
    for other in sorted(state.active):
        dest = state.active[other].route.arrival_block
        if other != train and dest in remaining:
            return (dest, other)
    return (remaining[-1], state.locks.get(remaining[-1], ""))
