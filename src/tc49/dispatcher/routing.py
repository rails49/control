"""candidates(): the route chooser (DISPATCH.md, route selection).

Routes to every surviving arrival end are merged into one list, filtered to
those whose every block fits the train, ordered by transit count, then by how
many route blocks are congested (#33), then by lexicographically smallest
block-id sequence, and capped by the single `k` budget. Routes are simple
paths: no block or transit twice. The caller names the congested blocks, so
the ordering is a function of `(layout, state)` and stays deterministic.
"""

from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from tc49.lib.layout import Layout


@dataclass(frozen=True)
class Route:
    blocks: tuple[str, ...]  # origin .. arrival block
    transits: tuple[str, ...]  # qualified ids, one per block pair

    @property
    def arrival_block(self) -> str:
        return self.blocks[-1]

    def crossing_order(self) -> list[str]:
        """The resources beyond the origin, in the order crossed."""
        result: list[str] = []
        for transit, block in zip(self.transits, self.blocks[1:]):
            result += [transit, block]
        return result

    def interleaved(self) -> list[str]:
        """The alternating block/transit sequence, for the route_chosen event."""
        return [self.blocks[0], *self.crossing_order()]


def other_end(end: str) -> str:
    block, _, letter = end.rpartition(".")
    return f"{block}.{'B' if letter == 'A' else 'A'}"


def candidates(
    layout: Layout,
    origin: str,
    depart_end: str,
    arrivals: tuple[str, ...],
    train_length: int,
    k: int,
    congested: AbstractSet[str] = frozenset(),
) -> list[Route]:
    routes: list[Route] = []

    def extend(
        exit_end: str, blocks: tuple[str, ...], transits: tuple[str, ...]
    ) -> None:
        for transit, far_end in layout.transits_at(exit_end):
            far_block = far_end.rpartition(".")[0]
            if transit in transits or far_block in blocks:
                continue  # simple path
            if layout.blocks[far_block] < train_length:
                continue  # the train must fit every block of the route
            path = (blocks + (far_block,), transits + (transit,))
            if far_end in arrivals:
                routes.append(Route(*path))
            extend(other_end(far_end), *path)

    extend(depart_end, (origin,), ())
    routes.sort(
        key=lambda r: (
            len(r.transits),
            sum(block in congested for block in r.blocks[1:]),
            r.blocks,
        )
    )
    return routes[:k]
