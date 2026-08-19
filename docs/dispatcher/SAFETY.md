# Safety

How incremental locking stays deadlock-free. The algorithm choice is recorded
in [ADR-0003](../adr/0003-route-aware-bankers-safety-check.md) and justified
against the literature in the
[deadlock-avoidance survey](../research/deadlock-avoidance-survey.md);
terminology follows [CONTEXT.md](../../CONTEXT.md) and the dispatch model
[DISPATCH.md](DISPATCH.md).

## Two independent guarantees

Keeping these apart matters — the safety check is routinely misread as a
collision mechanism, and it is not one.

- **Collision safety** is the lock table. Blocks and transits are held
  exclusively; a train enters a resource only while holding it. This is what
  keeps two trains off the same track, and it holds regardless of what the
  safety check believes.
- **Deadlock freedom** is the safety check below. It never grants access to
  anything — it only vetoes grants that the lock table would otherwise make.

A consequence worth stating: a train mid-transit from `X` to `Y` holds
`{X, T, Y}`, and its lock on `X` is released on `block_vacated(X)` — the
sensor confirming the train has fully cleared it — never on
`block_occupied(Y)`. Real trains straddle the boundary; the release rule
handles that without the dispatcher knowing. In the simulator both events land
in the same tick's buffered set, so the two behave identically.

## State

- **Active** trains have a committed route: launched, not yet completed.
- **Idle** trains are all the rest — parked, whether or not a request for them
  is pending. An idle train holds the standing lock on its block and nothing in
  the dispatcher will move it, so *its block is permanently unavailable*.
- For an active train `t`: `cur(t)` is the block it occupies; if it is
  mid-transit, `cur(t)` is the block it is crossing *into*. `rem(t)` is the
  blocks of its route strictly after `cur(t)`, ending at `dest(t)`. `held(t)`
  is the blocks of `rem(t)` it has already locked.

`cur(t)` for a mid-transit train is its destination because "frozen" means
*stops as soon as it physically can*, and by Lemma 1 that is always the far
block. Its origin therefore counts as free. This is sound — the release is
guaranteed, not hoped for — and strictly more permissive than counting both.

`held(t)` is empty whenever a grant locks no further than `cur(t)`, which is
every grant a depth-one strategy makes. It is read off the lock table rather
than off the strategy's depth, so the check describes the state it is handed
whatever asked for it, and a strategy that reaches further ahead cannot make
the check optimistic by accident.

## The check

```
safe(state):
  # memoized over S ⊆ active — the set of trains assumed already finished
  frozen(t, S)   = ⋃ {{cur(u)} ∪ held(u) : u ∈ active, u ∉ S ∪ {t}}

  feasible(t, S) = every b in rem(t) satisfies
       b ∉ frozen(t, S)                         # frozen active trains:
                                                #   where they stand, and
                                                #   what they already hold
     ∧ b ∉ {dest(u) : u ∈ S}                    # finishers, parked
     ∧ b ∉ {cur(u) : u ∈ idle}                  # permanent obstacles

  safe_from(S) = (S == active)
              or ∃ t ∈ active \ S: feasible(t, S) ∧ safe_from(S ∪ {t})

  return safe_from(∅)
```

Transits do not appear: by Lemma 1 they are never held across a wait, so they
cannot participate in a circular wait. Transit conflicts are enforced as
instantaneous admissibility at the grant itself, not here.

Complexity is `O(2ⁿ · n · L)` for `n` active trains with remaining routes of
length `≤ L`. At model-railroad train counts this is a few thousand route
walks per event. If `n` ever grows past comfort, the polynomial — and more
conservative — orderings of Reveliotis et al. are the fallback; see the
survey's §2.

## When it runs

Tentatively apply the grant, evaluate `safe()` on the resulting state, and
commit the grant only if it holds. A refused train stays parked holding its
standing block lock, and is reconsidered at every subsequent grant phase.

- **Every incremental grant** (next transit + next block).
- **Every launch**, which is itself an allocation — see route selection below.
- **Never on release.** Freeing resources cannot invalidate a witness
  (Lemma 2), so a release needs no check.
- **Never under the full-route baseline**, which locks a whole route up front
  and is trivially deadlock-free: a train granted its entire route can always
  run it to completion.

## Route selection

Launching a request is safety-checked against candidate routes rather than a
single one, so a request can route *around* a blockage — or, since a request
names a set of arrival ends, *finish somewhere else* — instead of waiting for
it:

```
launch(req, k):
  for route in candidates(req, k):     # deterministic order
      if safe(state with req active on route):
          commit route; launch; return
  stay pending
```

`candidates(req, k)` yields at most `k` simple routes in the order fixed by the
dispatch policy — routes to **every** surviving arrival end merged into one
list, fewest transits, then fewest congested blocks, then a lexicographic
tie-break, and only routes whose every block fits the train
([DISPATCH.md](DISPATCH.md#route-selection)). `k` is one budget over that
merged list, not a budget per arrival end. The congestion count is a function
of the dispatcher's state and only reorders candidates; nothing in the safety
argument depends on the order routes are tried.

The route is fixed once chosen, so
[ADR-0002](../adr/0002-fixed-route-per-request.md) is untouched — and so is
everything above. Committing the route commits one arrival end with it, which
is why `dest(t)` in `feasible` is single-valued for every *active* train
however many ends its request named. The set exists only in the pending queue;
the safety check never sees it.

`k` is configurable and is a benchmark axis, not merely a cap: `k = 1` is a
pure single-route gate, larger `k` is route-around and finish-somewhere-else,
and the interesting question — what permissiveness actually buys in makespan —
is measured, not assumed.

How far the sweep usefully runs is a property of the railroad *and of the
request*, never of the algorithm. Two bounds hold on any layout: `k = 1` with a
single arrival end is a pure gate, since one arrival end reachable one way is
one candidate; and `k` past the number of candidates a request actually has
buys nothing. Where that ceiling falls is what varies — a layout with several
paths between two points raises it, one with a single path leaves `k` inert
however many arrival ends a request names.
[BENCHMARKS.md](../bench/BENCHMARKS.md#the-k-axis) works the ceiling out for the encoded
railroads and sweeps `k` only where it can bite.

## Why it is deadlock-free

**Lemma 1 (transit transience).** A train holding a transit also holds the
block at the far end: the two are granted atomically and entry requires both.
So it can always complete the crossing and release the transit without waiting
on any train. Every *waiting* train therefore waits while occupying only a
block, and any circular wait is a cycle of block-holders. Transits drop out of
the analysis.

**Lemma 2 (release monotonicity).** If a state is safe with witness ordering
`W`, any state reached by releasing resources is safe with the *same* `W`.
Feasibility only ever requires certain blocks to be unoccupied, and releases
only unoccupy blocks.

**Invariant — every reachable state is safe.** The empty dispatch is
trivially safe. Every transition is a checked grant (safe by construction), a
checked launch (likewise), or a physical advance and release (safe by
Lemma 2). By induction no unsafe state is reachable. A deadlocked state is
unsafe: in a circular wait no train can be first in any ordering, since each
needs a block held by a train frozen behind it. Hence no deadlock.

**Progress.** In any reachable state with an unfinished train, take a witness
ordering `t₁…tₖ`. Every block on `rem(t₁)` is free or held by `t₁` itself —
which is what `feasible(t₁, ∅)` establishes, `frozen` covering what the other
trains hold and not only where they stand — so
`t₁`'s next transit and block are grantable, and granting them preserves
safety — `t₁` remains the head of the same witness. The dispatcher re-examines
waiting trains at every grant phase, so the grant is eventually issued. Each advance
strictly decreases total remaining route length, a natural number, so every
active train reaches its destination.

**Liveness is conditional.** The above covers trains that are *active*. A
pending request whose every candidate route crosses an idle train's block will
never launch, because that block is permanently unavailable. So the guarantee
is:

> Every accepted request completes, **provided** every train blocking a
> pending request eventually receives a request of its own.

Discharging that proviso is the scheduler's job, not the dispatcher's.

## Boundary conditions

Each of these falls out of the definitions rather than being special-cased,
and each is worth a test.

- **Optimism about idle trains is unsound.** If `safe()` treated an idle
  train's block as free on the grounds that it will move eventually, it could
  advance a train into a position where the two later wedge each other — the
  cycle is manufactured by the optimism. Pessimism means the blocked train
  never launches, so it never gets into that position.
- **An arrival block held by an idle train is unroutable-to** until that train
  leaves. Two trains cannot park in one block, so this is correct rather than
  merely conservative. What arrival-end sets change is only how often it
  matters: the request is held back when *every* one of its arrival blocks is
  obstructed, not when one is.
- **Shared destinations.** Two active trains committed to the same block can
  never both appear in a witness ordering — the second finds the block parked
  on — so `safe()` refuses to launch the second while the first is active. Two
  *requests* whose arrival sets overlap are not shared destinations: each
  commits to one end at launch, and the second is free to commit to a different
  block. This is the throughput the sets were added for, and it is bought
  entirely in route selection — the check above is unchanged.
- **Completion is a non-event for the proof.** A train leaving the active set
  changes nothing, because `dest(u)` already modeled its block as permanently
  held; it simply becomes an idle obstacle under a different name.
- **Self-intersecting routes.** A route may revisit a block it released
  earlier. `feasible` handles this already: blocks are checked against *other*
  trains only.
- **Starvation is not deadlock.** The argument guarantees that some train
  always advances and that all active trains finish; it does not bound how
  long a particular train waits. That is measured by max per-request latency
  ([DISPATCH.md](DISPATCH.md)), and the aging rule on the pending scan (#34,
  [ADR-0012](../adr/0012-the-pending-scan-ages-by-refusal-count.md)) is the
  remedy — orthogonal to safety, since it only reorders which *safe* grants
  get issued and can never make an unsafe grant reachable.
