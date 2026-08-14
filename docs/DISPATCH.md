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

## Time model

The simulator uses synchronous discrete **ticks**: each tick, every moving
train completes one transit into its next block. Travel time within blocks is
ignored. An event-driven clock with real traversal times can replace ticks
later without changing the dispatcher.

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
3. **Transit concurrency** — connections declare which transits conflict, so
   e.g. a crossing accepts two trains simultaneously on its straight transits
   but only one on either crossing transit.

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

Benchmarks feed the dispatcher a fixed list of requests and report:

- **Makespan** (headline) — ticks from first arrival until the last request
  completes.
- **Per-request latency** — completion − arrival; mean and max (catches
  starvation).
- **Resource utilization** — fraction of ticks each block/transit is occupied
  or locked.
- **Trains moved per tick** — instantaneous parallelism.
