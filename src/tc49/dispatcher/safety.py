"""safe(): the route-aware banker's safety check (SAFETY.md, ADR-0003).

A state is safe when some ordering of the active trains lets each traverse
its exact remaining route, with earlier trains parked on their destinations
and later trains frozen in place. Idle trains are permanent obstacles. The
search is memoized over subsets of finishers — exponential in active
trains, microseconds at model-railroad counts; the polynomial orderings of
Reveliotis et al. are the documented fallback.

Transits do not appear: by Lemma 1 they are never held across a wait.
Transit conflicts are instantaneous admissibility at the grant, not here.
"""

from collections.abc import Iterable, Mapping, Sequence


def safe(
    cur: Mapping[str, str],
    rem: Mapping[str, Sequence[str]],
    idle: Iterable[str],
    held: Mapping[str, Sequence[str]],
) -> bool:
    """`cur`: each active train's occupied block — for a mid-transit train
    the block it is crossing *into* (its origin counts as free, Lemma 1).
    `rem`: the blocks of its route strictly after `cur`, ending at its
    destination; empty for a train arriving at its destination.
    `idle`: the blocks held by idle trains.
    `held`: the blocks of `rem` it has already locked, which a frozen train
    blocks just as it blocks `cur` — it stands in one and holds the rest."""
    active = frozenset(cur)
    idle_blocks = frozenset(idle)
    dest = {t: (rem[t][-1] if rem[t] else cur[t]) for t in active}
    memo: dict[frozenset[str], bool] = {}

    def feasible(t: str, done: frozenset[str]) -> bool:
        frozen = {b for u in active - done - {t} for b in (cur[u], *held[u])}
        parked = {dest[u] for u in done}
        return all(
            b not in frozen and b not in parked and b not in idle_blocks for b in rem[t]
        )

    def safe_from(done: frozenset[str]) -> bool:
        if done == active:
            return True
        if done not in memo:
            memo[done] = any(
                feasible(t, done) and safe_from(done | {t})
                for t in sorted(active - done)
            )
        return memo[done]

    return safe_from(frozenset())
