"""The locking seam: LockingStrategy and the FullRoute baseline (ADR-0005).

A strategy answers two questions against the dispatcher's live state:
``launch`` — commit a route for a pending request, locking whatever the
strategy's discipline requires; ``grant`` — advance an active train by one
move. Both mutate ``state.locks`` and report what they newly locked so the
dispatcher can publish the lock ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from tc49.layout import Layout
from tc49.routing import Route, candidates
from tc49.safety import safe

if TYPE_CHECKING:
    from tc49.dispatch import Request, State


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


class LockingStrategy(Protocol):
    def launch(
        self, req: Request, origin: str, state: State
    ) -> Launched | Refused | None:
        """Try to launch; None means no candidate routes exist (unreachable)."""
        ...

    def grant(self, train: str, state: State) -> Move | Refused:
        """The active train's next move, or why it must wait."""
        ...


def resolve_depart(depart: str, origin: str) -> str:
    """A bare end letter (chained request) resolves against the origin."""
    return depart if "." in depart else f"{origin}.{depart}"


class FullRoute:
    """The baseline: launch locks the entire route or refuses; grant walks
    the already-locked route with no further check."""

    def __init__(self, layout: Layout, k: int) -> None:
        self._layout = layout
        self._k = k

    def launch(
        self, req: Request, origin: str, state: State
    ) -> Launched | Refused | None:
        routes = candidates(
            self._layout,
            origin,
            resolve_depart(req.depart, origin),
            req.arrivals,
            state.train_lengths[req.train],
            self._k,
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
                locked = route.crossing_order()
                for resource in locked:
                    state.locks[resource] = req.train
                return Launched(route, tried, locked)
            reason = reason or blocking[0]
            obstacles.append({"resource": blocking[1], "holder": blocking[2]})
        return Refused(reason, obstacles)

    def grant(self, train: str, state: State) -> Move:
        active = state.active[train]
        i = active.cur_index
        return Move(
            active.route.blocks[i],
            active.route.transits[i],
            active.route.blocks[i + 1],
            locked=[],
        )


class Incremental:
    """Each grant locks only the next transit plus block, gated by the
    route-aware banker's safety check. A launch tries up to `k` candidates
    and takes the first whose post-launch state is safe; transit
    concurrency is instantaneous admissibility at the grant, never part of
    the deadlock check."""

    def __init__(self, layout: Layout, k: int) -> None:
        self._layout = layout
        self._k = k

    def launch(
        self, req: Request, origin: str, state: State
    ) -> Launched | Refused | None:
        routes = candidates(
            self._layout,
            origin,
            resolve_depart(req.depart, origin),
            req.arrivals,
            state.train_lengths[req.train],
            self._k,
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
                cur, rem, idle = _safety_view(state, skip=req.train)
                cur[req.train] = route.blocks[1]
                rem[req.train] = list(route.blocks[2:])
                if safe(cur, rem, idle):
                    for resource in increment:
                        state.locks[resource] = req.train
                    return Launched(route, tried, increment)
                blocking = (
                    "unsafe",
                    *_unsafe_obstacle(route.blocks[1:], state, req.train),
                )
            reason = reason or blocking[0]
            obstacles.append({"resource": blocking[1], "holder": blocking[2]})
        return Refused(reason, obstacles)

    def grant(self, train: str, state: State) -> Move | Refused:
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
            cur, rem, idle = _safety_view(state, skip=train)
            cur[train] = into  # mid-transit: the far block (Lemma 1)
            rem[train] = list(active.route.blocks[i + 2 :])
            if safe(cur, rem, idle):
                # The move after a launch re-grants the increment the launch
                # already locked; report only what is newly locked.
                newly = [r for r in (transit, into) if state.locks.get(r) != train]
                state.locks[transit] = train
                state.locks[into] = train
                return Move(active.route.blocks[i], transit, into, newly)
            blocking = (
                "unsafe",
                *_unsafe_obstacle(active.route.blocks[i + 1 :], state, train),
            )
        return Refused(blocking[0], [{"resource": blocking[1], "holder": blocking[2]}])


def _safety_view(
    state: State, skip: str
) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """The safe() inputs for the current state, excluding `skip` (the train
    whose tentative position the caller supplies)."""
    cur: dict[str, str] = {}
    rem: dict[str, list[str]] = {}
    for train, active in state.active.items():
        if train != skip:
            cur[train] = active.route.blocks[active.cur_index]
            rem[train] = list(active.route.blocks[active.cur_index + 1 :])
    idle = [
        block
        for train, block in state.block_of.items()
        if train not in state.active and train != skip
    ]
    return cur, rem, idle


def _unsafe_obstacle(
    remaining: Sequence[str], state: State, train: str
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
