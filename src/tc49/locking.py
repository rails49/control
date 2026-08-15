"""The locking seam: LockingStrategy and the FullRoute baseline (ADR-0005).

A strategy answers two questions against the dispatcher's live state:
``launch`` — commit a route for a pending request, locking whatever the
strategy's discipline requires; ``grant`` — advance an active train by one
move. Both mutate ``state.locks`` and report what they newly locked so the
dispatcher can publish the lock ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from tc49.layout import Layout
from tc49.routing import Route, candidates

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
