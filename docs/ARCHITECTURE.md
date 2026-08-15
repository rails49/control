# Architecture

Implementation architecture one level beneath [SYSTEM.md](SYSTEM.md): the
dispatcher's internals, the metrics derivations, the package layout, and the
test strategy. The contracts *between* components — bus, event inventory,
time, asset store, footprints — are SYSTEM.md's and are not repeated here.
Terminology follows [CONTEXT.md](../CONTEXT.md); the dispatch model is
[DISPATCH.md](DISPATCH.md), the avoidance layer [SAFETY.md](SAFETY.md), the
file formats [LAYOUT.md](LAYOUT.md), and the suite that exercises it all
[BENCHMARKS.md](BENCHMARKS.md). The two seam decisions are recorded in
[ADR-0004](adr/0004-dispatcher-returns-commands.md) and
[ADR-0005](adr/0005-seam-at-locking-strategy.md).

## The dispatcher's internals

The dispatcher is the deep module of this codebase: routing, queueing,
locking and the safety check all sit behind the bus footprint of
[SYSTEM.md](SYSTEM.md#dispatcher), and it holds no collaborators — it reads
its layout and stock snapshot at startup ([SYSTEM.md](SYSTEM.md#dispatcher))
and thereafter only consumes and publishes events. Its state is the pending-request queue, the lock table, the set of
active routes, and the sensor events buffered since the last tick.

`Request`, `Route`, `Move` and friends survive as internal dataclasses — the
in-memory forms of what travels the bus as JSON. The wire vocabulary is the
event inventory; these types are private to the implementation and the
tests, which is why field-level schemas could be deferred.

## The locking seam

```python
class LockingStrategy(Protocol):
    def launch(self, req: Request, origin: str, state: State) -> Launched | Refused | None: ...
    def grant(self, train: str, state: State) -> Move | Refused: ...
```

`Launched` carries the committed route, `k_tried`, and the resources newly
locked; `Refused` carries the reason and one `{resource, holder}` obstacle
per blocked candidate — the payload of `grant_refused`. `None` from
`launch` means no candidate route exists (the request is rejected
`unreachable`). Strategies mutate `state.locks` and report what they
locked, so the dispatcher can publish the lock ledger.

Two adapters, both real from day one:

- **`FullRoute`** — the baseline. `launch` locks every block and transit of the
  route or returns `None`; `grant` walks the already-locked route with no check.
  Trivially deadlock-free, low throughput, and the yardstick the research core
  must beat on makespan.
- **`Incremental`** — the research core. `launch` tries up to `k` candidate
  routes and takes the first whose post-launch state is safe; `grant` gates the
  next transit-plus-block on the same check.

`safe()` is a plain function in `safety.py`, not a protocol. The polynomial
fallback of [SAFETY.md](SAFETY.md) would be a second function and a parameter
if anyone ever wants it — see [ADR-0005](adr/0005-seam-at-locking-strategy.md)
for why the seam is here and not there.

## Metrics

`metrics(trace) -> Metrics` is a pure function of the trace — nothing is
accumulated live, and no component computes a metric at runtime. Everything
derives from the tapped events of [SYSTEM.md](SYSTEM.md#the-trace):

- **Makespan** — first `request_admitted` stamp to last `request_completed`
  stamp.
- **Per-request latency** — `request_completed` stamp minus the request's
  `at` tick, correlated by id; mean and max.
- **Utilization** — `lock_granted`/`lock_released` spans per resource, as a
  fraction of the whole run: tick 0 through the trace's final tick. Standing
  locks are in the trace from the dispatcher's startup emission
  ([SYSTEM.md](SYSTEM.md#dispatcher)), so idle trains count.
- **Parallelism** — `cross` commands per tick.
- **Stall report** — for each request admitted but never completed when the
  trace ends, the last `grant_refused` for its id names the obstacles: which
  train (`holder`), which block (`resource`), how many candidates were
  blocked (the list's length).

This is deliberate. It keeps the trace **load-bearing**: an event that stops
being emitted breaks a metric and fails a test, rather than leaving the trace
to rot quietly until a future UI discovers it is missing what it needs. It
also makes every metric testable against a hand-written trace, with no run
required.

## Package layout

```
src/tc49/
  bus.py        the in-process bus — queued FIFO, run-to-completion,
                prefix-filter subscriptions (SYSTEM.md#the-bus)
  store.py      asset store — CRUD contract, YAML binding, validate at put
  layout.py     Layout — blocks, connections, transits, conflict matrix
                (expanded from `concurrent` by inversion), derived terminal
                blocks
  routing.py    candidates(layout, origin, depart_end, arrivals,
                train_length, k) — k-shortest over every arrival end
                merged, DISPATCH.md's ordering
  scheduler.py  Scheduler — releases scenario requests at their `at` ticks,
                mechanical arrival-end expansion, deterministic ids,
                exhausted state topic
  dispatch.py   Dispatcher — admission, queue, lock table, buffered
                sensors, grant phase
  locking.py    LockingStrategy, FullRoute, Incremental
  safety.py     safe()
  driver.py     Driver — move_granted → align + cross
  sim.py        Simulator — the milestone-1 layout interface: applies
                commands, emits sensors, publishes the tick, owns pacing
                and termination
  trace.py      the trace tap — canonical JSONL serialization, read/write
  runner.py     assemble the components on one bus and run a scenario to
                quiescence — the one wiring, shared by the CLI and the tests
  metrics.py    metrics(trace) -> Metrics
  sweep.py      the seeded workload generator and the fixed grid
  cli.py        `tc49 bench <scenario>`; `tc49 sweep` takes no arguments —
                the grid of BENCHMARKS.md is the fixed research design

layouts/                    <layout>.layout.yaml — the durable railroads
scenarios/<layout>/         <scenario>.scenario.yaml — stock and requests
benchmarks/expected/        <name>.json — golden numbers, asserted in pytest
out/                        sweep JSONL, gitignored
```

Routing sits outside `Layout` so that `Layout` stays a data structure rather
than growing a policy. The [layout-format
prototype](https://github.com/iot49/tc49/tree/prototype/layout-format/prototype/layout-format)
had `route()` as a method, which was right for a throwaway and wrong here —
route choice is a
pluggable policy per #3, and the layout should not know about it.

## Tests

pytest, with Hypothesis for the deadlock hunt. **All four properties drive
the real assembly over the in-process bus**: each generated case wires
scheduler, dispatcher, driver, and simulator together and interacts only by
publishing and observing events — so the bus contract itself gets thousands
of adversarial runs for free. The single-threaded, no-I/O bus keeps
Hypothesis throughput acceptable.

The generator produces **train placements and request sequences over a fixed
library of hand-written layouts** — deadlock is a property of request
interleaving, not of exotic topology, so that is where the search pressure
belongs. Arrival-end *sets* are part of what it draws, and they shrink toward
singletons, so a counterexample reduces to the tightest request that still
deadlocks. The library is chosen to be adversarial:

- `facing-pair` — two facing blocks with no other connection, DISPATCH.md's
  minimal deadlock.
- `single-track-meet` — a passing loop that forces meet-pass decisions, at
  [`layouts/single-track-meet.layout.yaml`](../layouts/single-track-meet.layout.yaml).
- `crossover-yard` — the double crossover of `image.png`, exercising partial
  transit concurrency; already written, at
  [`layouts/crossover-yard.layout.yaml`](../layouts/crossover-yard.layout.yaml).

Four properties:

1. **Safety invariant** — every reachable state satisfies `safe()`. The bus
   drives, the assertion peeks: the test holds the dispatcher it
   constructed, and after each grant event re-evaluates the library `safe()`
   on the dispatcher's live state. Local, so it fails at the grant that
   broke it rather than at the deadlock much later — and it duplicates no
   dispatcher bookkeeping in test code and puts no committed-routes-on-the-
   wire requirement on the event inventory.
2. **Quiescence oracle** — a quiesced run with pending requests is always
   attributable to a permanent obstacle, never to a circular wait
   ([SAFETY.md](SAFETY.md)). Anything else is a policy bug.
3. **Differential against the baseline** — the same harness run twice with the
   locking strategy swapped, so the baseline gets the same oracle the research
   core does: both quiesce, and whatever either leaves behind is a permanent
   obstacle rather than a wedge.

   This property was first stated as "`Incremental` completes every request set
   `FullRoute` completes, in no more ticks", and **that is false** — the suite
   found it out, which is what the suite is for. Every form of the dominance
   claim falls to adversarial search: the completed sets can be incomparable,
   the counts can favour either side, and even when both strategies complete
   exactly the same set `Incremental` can be slower. The shrunk counterexample
   is committed as
   [`crossover-yard/route-blindness`](../scenarios/crossover-yard/route-blindness.scenario.yaml)
   and asserted exactly in `tests/test_incremental.py`: two trains, no idle
   obstacle, no starvation, and `FullRoute` a tick faster.

   The mechanism was that locking a whole route up front is not merely
   conservative but **informative**, and route selection is what consumes the
   information. `FullRoute` locked the first train's whole route, so the second
   train's launch found its lexicographically-first candidate blocked and fell
   through to a candidate on the other line. `Incremental` locked only the
   first increment, so that candidate still looked clear, both trains committed
   to the same line, and one waited. Congestion-aware costing (#33) closed the
   gap: committed routes now enter the route ordering directly
   ([DISPATCH.md](DISPATCH.md#route-selection)), so both strategies steer the
   second train to the other line and finish the scenario together — asserted
   in `test_incremental.py`, with the scenario kept as the regression fixture.
   The dominance claim itself stays withdrawn: nothing here was a safety
   defect — both strategies stay deadlock-free — and the throughput claim
   belongs to the measured benchmark workloads, not to arbitrary ones.
4. **Determinism** — each scenario runs twice in one test and the two trace
   byte streams are asserted identical in memory, guarding the tie-break,
   grant-order, and canonical-serialization promises. No trace files are
   committed: the committed goldens are the metrics numbers in
   `benchmarks/expected/` plus scenario YAML fixtures, so the event
   inventory can evolve without fixture churn.

**The library-core seam is pure functions only.** Direct unit tests cover
`safe()` on hand-built states, layout graph queries, route policies, and the
scheduler's arrival-end expansion. The six boundary conditions closing
[SAFETY.md](SAFETY.md) are scenario-shaped, so they run over the bus as
committed scenario YAML — the same harness and fixture format as shrunk
Hypothesis counterexamples, which is the practical payoff of generating
requests rather than layouts: a failure is a readable scenario file, not an
unpicturable random graph.
