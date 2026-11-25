"""candidates(): the route chooser (DISPATCH.md, route selection).

Routes to every surviving arrival end are merged into one list, filtered to
those whose every block fits the train and none beyond the origin is out of use
(#1152), ordered by transit count, then by how many route blocks are congested
(#33), then by lexicographically smallest block-id sequence, and capped by the
single `k` budget. Routes are simple paths: no block or transit twice. The caller
names the congested blocks and the blocks out of use, so the answer is a function
of `(layout, state)` and stays deterministic. While the railroad's settings say
`short_blocks` the caller passes it, and the fit filter is lifted: a route may
end in or pass through a block shorter than the train (#1287).
"""

from collections.abc import Set as AbstractSet

from tc49.dispatcher.table import Route
from tc49.lib.layout import Layout, block_of, opposite_end


def candidates(
    layout: Layout,
    origin: str,
    depart_end: str,
    arrivals: tuple[str, ...],
    train_length: int,
    k: int,
    congested: AbstractSet[str] = frozenset(),
    out_of_use: AbstractSet[str] = frozenset(),
    *,
    short_blocks: bool = False,
) -> list[Route]:
    routes: list[Route] = []

    def extend(
        exit_end: str, blocks: tuple[str, ...], transits: tuple[str, ...]
    ) -> None:
        for transit, end_across in layout.transits_at(exit_end):
            block_across = block_of(end_across)
            if transit in transits or block_across in blocks:
                continue  # simple path
            if not short_blocks and layout.blocks[block_across] < train_length:
                continue  # the train must fit every block of the route
            if block_across in out_of_use:
                continue  # left out before `k` is spent, so another is found
            path = (blocks + (block_across,), transits + (transit,))
            if end_across in arrivals:
                routes.append(Route(*path))
            extend(opposite_end(end_across), *path)

    extend(depart_end, (origin,), ())
    routes.sort(
        key=lambda r: (
            len(r.transits),
            sum(block in congested for block in r.blocks[1:]),
            r.blocks,
        )
    )
    return routes[:k]
