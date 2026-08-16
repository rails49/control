# Deadlock-Avoidance Survey

Resolves [#2](https://github.com/rails49/control/issues/2). Assesses known
deadlock-avoidance theory against the tc49 dispatch model and ends in a
recommended algorithm with a sketch of its deadlock-freedom argument.
Terminology follows [CONTEXT.md](../../CONTEXT.md); the model is defined in
[DISPATCH.md](../dispatcher/DISPATCH.md), [ADR-0001](../adr/0001-no-reversal-within-a-route.md),
and [ADR-0002](../adr/0002-fixed-route-per-request.md).

## 1. The model in resource-allocation terms

In the vocabulary of the resource-allocation literature, tc49's dispatcher is
a **sequential resource allocation system (RAS)** — Reveliotis and Lawley's
term for a set of processes each of which acquires and releases resources
along a *known, fixed sequence* [4][5]:

| tc49 term | RAS term |
| --- | --- |
| Train | Process |
| Block | Unit-capacity, non-preemptible, reusable resource |
| Transit | Resource with a compatibility relation (non-conflicting transits are shareable) |
| Route (fixed at start, ADR-0002) | The process's exact, ordered remaining resource sequence |
| Incremental lock (block + next transit + next block) | Incremental allocation |
| Request completion | Process termination — **but the train parks**, see O3 |

Four structural observations shape everything below.

**O1 — Transits are never held across a wait.** Incremental locking grants
the next transit and the next block *together*, and a train enters a transit
only after both are granted. A train occupying a transit therefore always has
somewhere to go: it completes the crossing into a block it already holds and
releases the transit. Consequence: *every wait in the system is a wait by a
train parked in a block*. Transits (and their conflict relation) constrain
which grants are admissible at an instant, but they can be ignored in the
safety/look-ahead analysis — only blocks can be held across a wait, so only
blocks can participate in a circular wait.

**O2 — No preemption.** A train cannot be forced to vacate a block: reversal
within a route is forbidden (ADR-0001) and there may be no free block to move
it to. This rules out the entire *detection-and-recovery* branch of the
literature (detect a deadlock, then roll a victim back): there is no rollback
operation. Deadlock must be *avoided*, never entered.

**O3 — Completion is parking, not exit.** In the FMS/OS literature a
finished process releases everything and leaves. Here a completed train
*permanently occupies its destination block* (until some future request,
which the dispatcher cannot assume). This breaks the monotonicity that makes
the classical Banker's greedy safety check complete (§2) and is the one place
where tc49 genuinely differs from the textbook setting.

**O4 — Exact future knowledge.** Fixed routes (ADR-0002) mean the avoidance
layer knows every train's exact remaining path — far stronger information
than the "maximum claims" the original Banker's algorithm assumes. This is
precisely the condition under which the FMS literature found Banker-style
checks to be *not* overly conservative [4].

Deadlock in this model is concretely: a set of trains, each parked in a block,
each needing as its next block one occupied by another train in the set (the
two-facing-blocks example in DISPATCH.md is the minimal instance). By O1,
nothing subtler than block-on-block circular wait can occur.

## 2. Banker's-style safety checks (Dijkstra / Habermann)

**Sources.** Dijkstra introduced the Banker's algorithm in *Cooperating
Sequential Processes* (EWD-123, 1965) [1] and gave the underlying mathematics
in EWD-623 [2]; Habermann generalized it to multiple resource types in
"Prevention of System Deadlocks" (CACM 12(7), 1969) [3]. The state of the art
for *route-aware* variants is the FMS work of Lawley, Reveliotis and Ferreira:
"Polynomial-Complexity Deadlock Avoidance Policies for Sequential Resource
Allocation Systems" (IEEE Trans. Automatic Control 42(10):1344–1357, 1997)
[5] and "The Application and Evaluation of Banker's Algorithm for
Deadlock-Free Buffer Space Allocation in Flexible Manufacturing Systems"
(Int. J. Flexible Manufacturing Systems 10:73–100, 1998) [4].

**Idea.** Grant a lock only if the *resulting* state is **safe**: there
exists an order in which all processes can run to completion. Waiting instead
of granting is always harmless (the state is unchanged), so maintaining the
invariant "every reachable state is safe" makes deadlock unreachable.

**Fit to this model — excellent.** The classical objection to Banker's — that
"maximum claims" over-approximate real behavior — evaporates under O4: the
check can simulate each train's *exact* remaining route. This is exactly the
adaptation Lawley et al. made for FMS buffer allocation and found to give
very good operational flexibility [4]. The safety test becomes: *does there
exist an ordering t₁, …, tₖ of the active trains such that each tᵢ can
traverse its remaining route, given that t₁…tᵢ₋₁ have completed (and are
parked at their destinations, per O3) and tᵢ₊₁…tₖ sit frozen in their current
blocks?* A single train's feasibility test is a walk down its remaining
route: every block on it must be currently free, held by the train itself, or
occupied only by trains that will have moved on/completed earlier in the
ordering; by O1, transits never need to be checked.

Two departures from the textbook algorithm matter:

1. *Greedy search is incomplete here.* The classical proof that the greedy
   check ("repeatedly pick any process that can finish; declare safe if all
   finish") is complete relies on completion only *freeing* resources. Under
   O3, completing train X parks it on dest(X), which may lie on train Y's
   remaining route — completing X early can destroy an ordering in which Y
   goes first. So the search must consider orderings. Safety for general RAS
   is NP-complete (Gold, "Deadlock Prediction: Easy and Difficult Cases",
   SIAM J. Computing 7(3):320–336, 1978 [6]; see also [5]), and O3 keeps
   tc49 out of the easy greedy case. The practical fix is a memoized search
   over subsets of completed trains: O(2ⁿ · n · L) for n active trains with
   remaining routes of length ≤ L. A model railroad runs a handful of trains
   (n ≲ 10), so this is a few thousand route walks per event — microseconds.
   If n ever grows, the polynomial (more conservative) orderings of [5] are
   the documented fallback.
2. *When to run it.* The check runs at two kinds of event: **route start**
   (starting a request is itself an allocation — and if several candidate
   routes exist, pick one whose start-state passes) and **every incremental
   lock grant** (next transit + next block). Releases never need a check
   (freeing resources cannot invalidate a witness ordering — see §7).

**Cost per event.** O(2ⁿ · n · L) worst case, tiny at model-railroad scale;
polynomial variants exist [5].

**Conservatism.** Low. The only feasible schedules it forbids are those with
no *sequential* completion witness even though some interleaved execution
might succeed — rare, and the price of a clean proof. Lawley et al. measured
route-aware Banker's as close to maximally permissive in FMS [4].

**Freedom argument shape.** Inductive invariant (all reachable states safe) +
progress (the head of the witness ordering can always move). Clean and short —
spelled out in §7.

## 3. Resource-allocation graphs and cycle detection

**Sources.** Coffman, Elphick and Shoshani, "System Deadlocks" (ACM Computing
Surveys 3(2):67–78, 1971) [7] — the four necessary conditions (mutual
exclusion, hold-and-wait, no preemption, circular wait) and the
resource-allocation/wait-for graph formalism.

**Idea.** Maintain a wait-for graph (train → train holding the block it
needs); a cycle among unit-capacity resources is a deadlock. Either *detect*
cycles and recover, or *avoid* by denying any grant/wait that closes a cycle.

**Fit — necessary concept, insufficient policy.**

- *Detection + recovery* is ruled out outright by O2: no preemption, no
  rollback. Detecting a deadlock in tc49 is detecting an unrecoverable
  failure.
- *Cycle-avoidance at grant time* ("deny the wait that closes a cycle") stops
  the deadlock's final step but not the states that make it inevitable. The
  literature calls these **restricted deadlocks** or unsafe states: no cycle
  exists yet, but every continuation reaches one (Fanti's zone-control work
  characterizes exactly this second-level phenomenon [10]). Minimal example:
  three trains headed pairwise into a two-block single-track section — the
  cycle only appears after moves that each look individually harmless.
  Denying cycle-closing waits converts the deadlock into a permanent stall
  one step earlier; it does not restore liveness.
- *Static prevention by resource ordering* (grab blocks in a fixed global
  order, breaking circular wait a priori) is incompatible with the model:
  routes run both directions through the same blocks, so no total order on
  blocks is consistent with all routes.

**Cost per event.** O(V+E) cycle check — the cheapest family surveyed.

**Verdict.** Not viable alone. The wait-for graph remains useful as
vocabulary for the freedom argument (what must never form is a block-on-block
circular wait, per O1) and optionally as a fast necessary-condition filter,
but the safety check of §2 subsumes it.

## 4. Deadlock avoidance in AGV systems

The closest literature: zone-controlled AGVs are trains in all but name —
unit-capacity zones (= blocks), guide-path networks, vehicles that cannot
climb over each other, incremental zone acquisition.

**Key sources.**

- Reveliotis, "Conflict Resolution in AGV Systems" (IIE Transactions
  32(7):647–659, 2000) [8]: zone control with routes extended *incrementally,
  one zone at a time*, each extension vetted by a RAS safety test — the
  Banker machinery of §2 transplanted to vehicles. Demonstrates that the
  grant-time safety-check architecture is the accepted design for exactly
  tc49's setting. (tc49 is actually *easier*: ADR-0002 fixes whole routes, so
  the check never has to quantify over routing alternatives.)
- Moorthy, Hock-Guan, Wing-Cheong and Chung-Piaw, "Cyclic Deadlock
  Prediction and Avoidance for Zone-Controlled AGV System" (Int. J.
  Production Economics 83(3):309–324, 2003) [9]: deployed at a container
  terminal; predicts cycle formation at zone-claim time from claimed/next
  zones and denies the closing claim. Fast and field-proven, but it is the
  cycle-avoidance policy of §3 — it handles the cycles it models and
  documents residual multi-step deadlocks as needing separate treatment.
- Fanti, "Event-based controller to avoid deadlock and collisions in
  zone-control AGVS" (Int. J. Production Research 40(6):1453–1478, 2002)
  [10]: digraph/coloured-Petri-net event controller; introduces the
  *restricted deadlock* notion and shows one-step cycle checks miss it —
  the strongest argument in this survey for a genuine safety (look-ahead)
  test rather than graph patching.
- Fanti and Zhou, "Deadlock Control Methods in Automated Manufacturing
  Systems" (IEEE Trans. SMC-A 34(1):5–22, 2004) [11]: survey organizing the
  field into digraph, automaton and Petri-net methods and the
  prevention/avoidance/detection taxonomy used here.
- Lehmann, Grunow and Günther, "Deadlock handling for real-time control of
  AGVs at automated container terminals" (OR Spectrum 28:631–657, 2006) [12]:
  industrial-scale confirmation that detection/recovery is only workable when
  vehicles *can* reverse — which tc49's trains (ADR-0001, O2) cannot.

**Fit — direct; this is where the recommendation comes from.** The AGV
literature converged on the same conclusion the structural analysis suggests:
with unit-capacity zones and no preemption, run a route-aware safety check on
every zone grant [8]; pure cycle prediction is cheaper but leaves gaps
[9][10]. tc49's fixed routes and no-reversal rules remove the complications
(routing flexibility, vehicle backtracking) that force the AGV papers into
their heavier machinery.

**Cost / conservatism.** As §2 (Reveliotis's test *is* a Banker variant);
Moorthy-style cycle prediction is O(V+E) but incomplete.

## 5. Petri-net approaches (siphons, supervisory control)

**Sources.** Ezpeleta, Colom and Martínez, "A Petri Net Based Deadlock
Prevention Policy for Flexible Manufacturing Systems" (IEEE Trans. Robotics
and Automation 11(2):173–184, 1995) [13] — the seminal S³PR result: deadlock
⇔ some *siphon* (a place set that, once empty of tokens, stays empty) becomes
unmarked; adding *monitor places* that keep every siphon marked yields an
offline, provably live net. For AGVs specifically: Yeh and Yeh, "Deadlock
prediction and avoidance based on Petri nets for zone-control AGV systems"
(Int. J. Production Research 33(12), 1995) [14] and Wu and Zhou's
(colored) resource-oriented Petri nets, e.g. "Resource-Oriented Petri Nets in
Deadlock Avoidance of AGV Systems" (Proc. IEEE ICRA 2001) [15] and *System
Modeling and Control with Resource-Oriented Petri Nets* (CRC Press, 2010)
[16].

**Fit — elegant theory, wrong deployment shape.**

- Siphon-based *prevention* [13] is an **offline structural synthesis**: it
  computes control places from the net of all process types. tc49's
  "process types" are routes, which are created per request against an
  arbitrary layout — the net changes with every request mix, so the
  synthesis would rerun online, and complete siphon enumeration is
  exponential in the net size. The resulting policy is also known to be more
  conservative than route-aware Banker's (monitors forbid all markings that
  *could* empty a siphon, including many safe ones).
- Supervisory control on the reachability graph (maximally permissive by
  construction) needs the state space including every train's route — the
  very explosion the event-driven, per-grant check avoids.
- Wu–Zhou CROPNs [15][16] are genuinely close (places = zones, tokens =
  vehicles, colors = routes) and would be attractive if tc49 wanted a single
  formalism for modeling *and* control; but the control policy they derive
  is again an avoidance check evaluated per move — equivalent power to §2 at
  higher formal overhead. Transit conflicts would need colored/weighted
  extensions on top.

**Where Petri nets still earn a place:** as a *verification* vehicle. The
recommended policy (§6) can be modeled as a net and its liveness
model-checked for particular layouts as a mechanized cross-check of the §7
argument, without putting a net in the dispatch loop.

**Cost per event.** Prevention: zero online cost (all offline) — but the
offline step doesn't fit per-request routes. Avoidance-style net policies:
comparable to §2.

**Conservatism.** Siphon/monitor prevention: the most conservative of the
viable families. Net-based avoidance: comparable to Banker's.

## 6. Railway zone/interlocking control practice

**Sources.** Interlocking principles and route/sectional release: "Principles
of Railway Interlocking" (railwaysignalling.eu) [17] and route-locking /
sectional-release circuit descriptions [18]; moving-block/CBTC state of the
art: Sels et al.-style literature is summarized in "Real-time railway traffic
management under moving-block signalling: a literature review and research
agenda" (Transportation Research Part C, 2024) [19].

**What practice does.** A signalled route is *locked end-to-end before the
signal clears* — mechanical/electronic route locking guarantees no
conflicting route can be set — and **sectional release** frees each track
section as the train clears it [17][18]. That is precisely tc49's
**full-route locking baseline** (lock everything up front, release behind the
train). Two lessons:

1. Interlocking solves *collision* safety, not deadlock: with full-route
   locking, deadlock-freedom is trivial (a train granted a route can always
   run it to completion), and real railways push the remaining
   deadlock/throughput problem up to human dispatchers and timetables
   (meet-pass planning on single track). Practice thus validates the baseline
   and confirms that incremental locking with a provable avoidance layer is a
   genuine research delta, not reinvention.
2. Sectional release is exactly the release-behind-the-train rule tc49
   already has; moving-block/CBTC [19] relaxes block granularity but not the
   allocation logic, so nothing there changes the analysis.

**Verdict.** Baseline confirmation and terminology, not an avoidance
algorithm.

## 7. Recommendation

**Adopt a route-aware Banker's safety check — the single-unit sequential-RAS
variant in the style of Lawley–Reveliotis–Ferreira [4][5] and Reveliotis's
AGV transplant [8] — adapted for park-at-destination completion (O3), run at
route start and at every incremental lock grant.**

Concretely, on each grant event (tentatively apply the grant, then test):

```
safe(state):
  # trains: active trains; each t has remaining route rem(t) (blocks only, per O1),
  # current block cur(t), destination dest(t).
  # Search for an ordering t1..tk such that each ti can finish given
  # earlier trains parked at their destinations and later trains frozen at cur().
  memo over S ⊆ trains (set of trains assumed completed):
    done(S)     = (S == trains)
    feasible(t,S) = every block b in rem(t) satisfies:
                      b not in {cur(u) : u ∉ S ∪ {t}}       # frozen trains
                      and b not in {dest(u) : u ∈ S}        # parked finishers
    safe-from(S) = done(S) or ∃ t ∉ S: feasible(t,S) and safe-from(S ∪ {t})
  return safe-from(∅)
```

Grant the lock iff `safe` holds on the post-grant state; otherwise the train
waits and the dispatcher re-evaluates it on the next release event. Transit
conflicts are enforced only as instantaneous admissibility at the grant
itself (O1 keeps them out of `safe`). Complexity O(2ⁿ·n·L), trivial for
model-railroad n; the polynomial policies of [5] are the escape hatch if n
grows. The same check vets route choice: at route start, prefer a candidate
route whose start-state is safe.

**Rejected alternatives, in one line each:**

- *Cycle detection/avoidance on the wait-for graph* (§3): misses restricted
  deadlocks [10]; detection-and-recovery impossible without preemption (O2).
- *Static resource ordering:* incompatible with bidirectional use of blocks.
- *Siphon-based Petri-net prevention* (§5): offline synthesis doesn't fit
  per-request routes; strictly more conservative than route-aware Banker's.
- *Supervisory control / reachability synthesis:* state explosion over
  route-bearing states; per-grant checking achieves the permissiveness
  without materializing the state space.
- *Full-route locking* (§6): already the benchmark baseline; trivially safe,
  low throughput — the yardstick the recommendation must beat on makespan.

## 8. Sketch of the deadlock-freedom argument

*Definitions.* A **state** is: each active train's current block, held locks,
and remaining route; plus completed trains parked at destinations. A state is
**safe** iff `safe(state)` above holds, i.e. there is a **witness ordering**
t₁…tₖ in which each train can traverse its remaining route to its destination
assuming its predecessors have finished (and parked) and its successors never
move.

**Lemma 1 (transit transience — O1).** A train holding a transit also holds
its next block (they are granted atomically, and entry requires both), so it
can always complete the crossing and release the transit without waiting on
any other train. Hence in every reachable state, every *waiting* train waits
while occupying only a block, and any circular wait is a cycle of
block-holders. Transits can therefore be excluded from `safe`.

**Lemma 2 (release monotonicity).** If a state is safe with witness ordering
W, any state obtained by releasing resources (a train moving forward into
locks it already holds, freeing the block behind; a transit freed on crossing
completion) is safe with the *same* W: feasibility of each tᵢ in W only
requires certain blocks to be unoccupied, and releases only unoccupy blocks.

**Invariant (all reachable states are safe).** *Base:* the empty dispatch
(no active trains) is trivially safe, and a request only starts when the
route-start check passes. *Step:* every transition is (a) a checked grant —
safe by construction of the check; (b) a physical advance/release — safe by
Lemma 2; or (c) a new request start — checked like a grant. By induction,
no unsafe (in particular, no deadlocked) state is reachable. A deadlocked
state is indeed unsafe: in a circular wait no train can be first in any
witness ordering, since each needs a block held by a frozen successor.

**Progress (no permanent stall).** Take any reachable state with at least one
unfinished train, and a witness ordering t₁…tₖ. Every block on rem(t₁) is
free or held/occupied by t₁ itself (all other trains are "later" in W).
In particular t₁'s next transit and next block are grantable, and granting
them preserves safety (t₁ remains a valid head of the same witness ordering,
and no other train's feasibility in W referenced those resources as free —
they were required free only for t₁, which still precedes them). The
dispatcher is event-driven and re-examines waiting trains on every
release/grant event, so this grant is eventually issued, t₁ advances, and by
Lemma 2 safety persists. Each advance strictly decreases the total remaining
route length, a natural number; by induction every active train — t₁ first,
then inductively the rest of W as resources free up — reaches its
destination. Hence: **no deadlock, and every accepted request whose
predecessors terminate is eventually completed.**

*Boundary conditions to carry into implementation and tests:*

- **Shared destinations.** Two active trains with the same destination block
  can never both appear in a witness ordering (the second finds the block
  parked-on), so `safe` automatically refuses to start the second until the
  first departs on a later request — the desired behavior, but worth a test.
- **Starvation vs. deadlock.** The argument guarantees *some* train always
  advances and all *current* trains finish; it does not by itself bound how
  long a particular waiting train starves while others are repeatedly
  granted. The per-request max-latency metric (DISPATCH.md) monitors this;
  an aging/priority rule on the grant queue is the standard remedy and is
  orthogonal to safety (it only reorders which safe grants are issued).
- **Self-intersecting routes.** A route may revisit a block it released
  earlier; `feasible` as written already treats it correctly (the block is
  checked against *other* trains only).

## 9. Comparison summary

| Family | Fit to fixed-route/no-reversal | Cost per grant event | Conservatism | Freedom argument |
| --- | --- | --- | --- | --- |
| Route-aware Banker's [4][5][8] | Excellent (O4 gives exact needs) | O(2ⁿ·n·L), n small; poly variants [5] | Low | Invariant + progress; short (§8) |
| Wait-for-graph cycle avoidance [7][9] | Partial — misses restricted deadlocks [10] | O(V+E) | Low but **unsound** as avoidance | None achievable alone |
| Detection + recovery [7][12] | Unusable — no preemption (O2) | — | — | — |
| Siphon/monitor prevention [13] | Poor — offline synthesis vs. per-request routes | 0 online, exponential offline | High | Structural liveness (per fixed net) |
| PN avoidance (CROPN) [14][15][16] | Good but equivalent to Banker's at higher overhead | ≈ Banker's | ≈ Banker's | Net liveness ≙ §8 |
| Full-route locking (railway practice) [17][18] | Trivially safe — the baseline | O(L) once per route | Maximal | Immediate |

## References

1. E. W. Dijkstra, *Cooperating Sequential Processes*, EWD-123, 1965.
   https://www.cs.utexas.edu/~EWD/transcriptions/EWD01xx/EWD123.html
2. E. W. Dijkstra, *The Mathematics Behind the Banker's Algorithm*, EWD-623,
   1977. https://www.cs.utexas.edu/~EWD/transcriptions/EWD06xx/EWD623.html
3. A. N. Habermann, "Prevention of System Deadlocks", *Communications of the
   ACM* 12(7):373–377, 1969. https://dl.acm.org/doi/10.1145/363156.363162
4. M. Lawley, S. Reveliotis, P. Ferreira, "The Application and Evaluation of
   Banker's Algorithm for Deadlock-Free Buffer Space Allocation in Flexible
   Manufacturing Systems", *Int. J. Flexible Manufacturing Systems*
   10:73–100, 1998. https://link.springer.com/article/10.1023/A:1007969601583
5. S. Reveliotis, M. Lawley, P. Ferreira, "Polynomial-Complexity Deadlock
   Avoidance Policies for Sequential Resource Allocation Systems", *IEEE
   Transactions on Automatic Control* 42(10):1344–1357, 1997.
   https://ieeexplore.ieee.org/document/633825
6. E. M. Gold, "Deadlock Prediction: Easy and Difficult Cases", *SIAM
   Journal on Computing* 7(3):320–336, 1978.
   https://epubs.siam.org/doi/10.1137/0207027
7. E. G. Coffman Jr., M. J. Elphick, A. Shoshani, "System Deadlocks", *ACM
   Computing Surveys* 3(2):67–78, 1971.
   https://dl.acm.org/doi/10.1145/356586.356588
8. S. A. Reveliotis, "Conflict Resolution in AGV Systems", *IIE
   Transactions* 32(7):647–659, 2000.
   https://www.tandfonline.com/doi/abs/10.1080/07408170008967423
9. R. L. Moorthy, W. Hock-Guan, N. Wing-Cheong, T. Chung-Piaw, "Cyclic
   Deadlock Prediction and Avoidance for Zone-Controlled AGV System", *Int.
   J. Production Economics* 83(3):309–324, 2003.
   https://www.sciencedirect.com/science/article/abs/pii/S0925527302003705
10. M. P. Fanti, "Event-based controller to avoid deadlock and collisions in
    zone-control AGVS", *Int. J. Production Research* 40(6):1453–1478, 2002.
    https://www.tandfonline.com/doi/abs/10.1080/00207540110118073
11. M. P. Fanti, M. Zhou, "Deadlock Control Methods in Automated
    Manufacturing Systems", *IEEE Transactions on Systems, Man, and
    Cybernetics — Part A* 34(1):5–22, 2004.
    https://ieeexplore.ieee.org/document/1259355
12. M. Lehmann, M. Grunow, H.-O. Günther, "Deadlock handling for real-time
    control of AGVs at automated container terminals", *OR Spectrum*
    28:631–657, 2006. https://link.springer.com/article/10.1007/s00291-006-0053-4
13. J. Ezpeleta, J. M. Colom, J. Martínez, "A Petri Net Based Deadlock
    Prevention Policy for Flexible Manufacturing Systems", *IEEE
    Transactions on Robotics and Automation* 11(2):173–184, 1995.
    https://ieeexplore.ieee.org/document/370500
14. M. Yeh, W. Yeh, "Deadlock prediction and avoidance based on Petri nets
    for zone-control automated guided vehicle systems", *Int. J. Production
    Research* 33(12), 1995.
    https://www.tandfonline.com/doi/abs/10.1080/00207549508904872
15. N. Wu, M. Zhou, "Resource-Oriented Petri Nets in Deadlock Avoidance of
    AGV Systems", *Proc. IEEE Int. Conf. on Robotics and Automation (ICRA)*,
    2001. https://ieeexplore.ieee.org/document/932531
16. M. Zhou, N. Wu, *System Modeling and Control with Resource-Oriented
    Petri Nets*, CRC Press, 2010.
    https://www.routledge.com/System-Modeling-and-Control-with-Resource-Oriented-Petri-Nets/Zhou-Wu/p/book/9781138115088
17. "Principles of Railway Interlocking", railwaysignalling.eu.
    https://www.railwaysignalling.eu/railway-interlocking-principles-railwaysignalling
18. "Route Locking Circuit — Railway Signalling", railwaysignallingconcepts.in.
    https://www.railwaysignallingconcepts.in/route-locking-circuit-railway-signalling/
19. "Real-time railway traffic management under moving-block signalling: a
    literature review and research agenda", *Transportation Research Part C*,
    2024. https://www.sciencedirect.com/science/article/pii/S0968090X2300428X
