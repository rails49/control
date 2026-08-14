# Dispatch

The dispatcher accepts requests from the scheduler and tries to satisfy them in
the shortest time possible. It is **online** — it commits to decisions without
knowing future requests — and is the research core of this project: deadlock
avoidance at high throughput. Terminology follows [CONTEXT.md](../CONTEXT.md).

## Semantics

- **Admission** — a request is rejected only if it is topologically
  unroutable: no route exists on an empty layout, or the train does not fit
  the destination block. All other requests are accepted and queued.
- **Fixed routes** — a route is chosen when the train starts moving and never
  changed; only its locks are incremental
  ([ADR-0002](adr/0002-fixed-route-per-request.md)).
- **No reversal** — routes are strict pass-throughs; terminal blocks occur
  only as endpoints ([ADR-0001](adr/0001-no-reversal-within-a-route.md)).
- **Event-driven** — the dispatcher reacts to events such as *train arrived
  at block* and never reads a clock, so the simulator and real hardware drive
  it the same way.

### Requests

A request is `(train, departure end, destination block, arrival tick)`. The
train is named explicitly — its origin block follows from where it stands — and
the departure end fixes the first transit. The *arrival* end is unconstrained:
which way round a train finishes is the scheduler's concern, resolved by
reversal at rest between requests.

A request whose destination is the train's current block is accepted with an
empty route and completes immediately, at latency 0. Treating it as degenerate
rather than as an error keeps the admission rule free of special cases.

A request may be pending for a train that is already active on an earlier
request; chained workings make this routine. It needs no mechanism — an active
train is not idle, so its next request simply cannot launch yet.

### Route selection

The route chooser is a **pluggable strategy**, so congestion-aware costing can
drop in later behind the same interface. Milestone 1's chooser:

1. Consider only routes whose every block fits the train.
2. Order by transit count — which is tick count, since every transit costs one
   tick regardless of length.
3. Break ties on the lexicographically smallest block-id sequence, so repeated
   runs are bit-identical.
4. **Dedupe by resource set.** Two candidates that lock the same blocks and the
   same transits are one option spelled two ways, and emitting both burns the
   `k` budget of [SAFETY.md](SAFETY.md)'s route selection while offering the
   dispatcher no genuine alternative. On Gotthard this is not hypothetical:
   a route entering the destination track at `A` and one entering at `B` differ
   only in the final transit, and while the junction is fully exclusive either
   transit excludes the same movements. See
   [BENCHMARKS.md](BENCHMARKS.md#the-k-axis).

### Queue discipline

Greedy, in arrival order. On every resource-releasing event the dispatcher
scans pending requests oldest-first and launches each whose conditions hold,
skipping the rest that round. The ordering key is an explicit policy point —
priority classes could replace arrival order without touching the safety core —
but milestone 1 ships arrival order only.

Starvation is possible and is **measured**, not prevented: max per-request
latency is the detector, and an aging rule is the standard remedy if the
benchmarks call for one. Starvation is not deadlock; see
[SAFETY.md](SAFETY.md).

### Launch and completion

Occupancy is a **standing lock** — every train always holds the lock on the
block it stands in, moving or parked, requested or not. Launching is therefore
not "taking a lock on the train's own block"; it is the safety layer granting
the request's first increment: the first transit plus the second block under
incremental locking, or the whole route under the full-route baseline.

**The queue does not filter on destination occupancy.** A request whose
destination is occupied is scanned like any other; whether it launches is the
safety check's answer, not the queue's. The two cases differ: an *idle*
occupant is a permanent obstacle and the launch is refused until it leaves, an
*active* occupant that has begun moving no longer counts as holding the block
([SAFETY.md](SAFETY.md#state)). Keeping that distinction out of the queue is
what keeps the avoidance layer the single place deadlock is reasoned about.

A request completes on the tick its final transit finishes: the trailing
transit and origin block release, and the train parks holding only its standing
lock. Latency is completion tick − arrival tick.

## Time model

The simulator uses synchronous discrete **ticks**: each tick, every moving
train completes one transit into its next block. Travel time within blocks is
ignored, and so is transit length — the long return loop and a station ladder
both cost one tick. An event-driven clock with real traversal times can replace
ticks later without changing the dispatcher.

**Each tick has three phases, in order:**

1. **Admit** — requests whose arrival tick is `n` are admitted and queued.
2. **Move + release** — every train holding a granted increment completes its
   transit, emitting `block_occupied(new)` and `block_vacated(old)`, and
   atomically releases its origin block and the transit.
3. **Grant** — the dispatcher reacts to those events and grants. Grants take
   effect at tick `n+1`.

Event and reaction stay within one tick, so the dispatcher's causality never
crosses a tick boundary.

**Lock footprint.** A train moving from `X` through `T` into `Y` holds
`{X, T, Y}` for the move and releases `X` and `T` atomically on arrival. `T`
and `Y` are granted together, which is what makes a transit never held across a
wait — the premise the whole deadlock argument rests on.

**Grant order** — within phase 3, active trains first (by request arrival tick,
tie-break train id), then pending launches oldest-first. Draining work in
progress before admitting new holders favours makespan and mirrors the progress
argument of [SAFETY.md](SAFETY.md): advancing the head of the witness ordering
is always safe, while launching adds a resource holder. Because `advance` takes
a whole tick's sensor events as a batch, this order never depends on the order
sensors happen to fire.

**No same-tick handoff.** A lock released in phase 2 of tick `n` is grantable in
phase 3 of tick `n`, but the grantee does not move until tick `n+1`. A convoy
therefore starts with a one-tick stagger and then flows at one block per train
per tick — the backward-propagating start wave real trains have. Minimum
latency is one tick per transit.

**Sensors are anonymous.** The backend reports only `block_occupied(block)` and
`block_vacated(block)`, with no train identity — exactly what a DCC-EX current
detector can produce. The dispatcher recovers identity from its own lock table,
which already records the grantee of every block. This is what lets the
simulator and real hardware drive the dispatcher the same way.

## Locking

1. **Full-route locking** (baseline) — lock every block and transit of a route
   before the train moves; unlock each behind the train. Trivially
   deadlock-free, low throughput. Serves as the benchmark yardstick.
2. **Incremental locking** (research core) — lock only what the train needs to
   advance: usually its current block plus the next transit and block.
   High throughput, but naive incremental locking deadlocks — e.g. two trains
   entering a section of two facing blocks with no other connections between
   them each wait forever for the other to depart. The deadlock-avoidance
   layer that prevents this is the central problem; see
   [SAFETY.md](SAFETY.md).
3. **Transit concurrency** — a connection declares which pairs of its transits
   are `concurrent`; every other pair conflicts
   ([ADR-0006](adr/0006-conflicts-declared-by-inversion.md)). A crossing that
   declares its two straight transits concurrent therefore accepts two trains
   at once on them, but only one on either crossing transit. Transits are also
   self-exclusive, so head-on use is excluded without declaring anything. A
   grant succeeds when the transit is unlocked and no currently-locked transit
   at that connection conflicts with it — an instantaneous admissibility test
   at the grant, not part of the deadlock check.

   ![Crossing connector](image.png)

## Research

The [survey](research/deadlock-avoidance-survey.md) assessed known theory
against this model — banker's-style safety checks (applicable because routes
are fixed), resource-allocation graphs and cycle detection, deadlock avoidance
in AGV systems, Petri-net approaches, and railway zone control. The resulting
choice is a route-aware banker's safety check
([ADR-0003](adr/0003-route-aware-bankers-safety-check.md)); the check itself
and its deadlock-freedom argument are in [SAFETY.md](SAFETY.md).

## Metrics

Benchmarks feed the dispatcher a fixed list of requests and report the four
metrics below; the suite that produces them is [BENCHMARKS.md](BENCHMARKS.md),
and each metric is computed as a pure function of the event trace
([ARCHITECTURE.md](ARCHITECTURE.md#metrics)).

- **Makespan** (headline) — ticks from first arrival until the last request
  completes.
- **Per-request latency** — completion − arrival; mean and max (catches
  starvation).
- **Resource utilization** — fraction of ticks each block/transit is occupied
  or locked.
- **Trains moved per tick** — instantaneous parallelism.
