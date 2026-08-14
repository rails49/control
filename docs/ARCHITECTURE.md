# Architecture

The module structure of the milestone-1 implementation: what the dispatcher's
interface is, how a backend drives it, what the event trace carries, and how it
is all tested. Terminology follows [CONTEXT.md](../CONTEXT.md); the dispatch
model is [DISPATCH.md](DISPATCH.md), the avoidance layer [SAFETY.md](SAFETY.md),
the file formats [LAYOUT.md](LAYOUT.md), and the suite that exercises it all
[BENCHMARKS.md](BENCHMARKS.md). The two seam decisions are recorded in
[ADR-0004](adr/0004-dispatcher-returns-commands.md) and
[ADR-0005](adr/0005-seam-at-locking-strategy.md).

## The dispatcher's interface

The dispatcher is the deep module of this codebase: routing, queueing, locking
and the safety check all sit behind two methods, and it holds no collaborators
at all.

```python
class Dispatcher:
    def __init__(self, layout: Layout, locking: LockingStrategy, k: int = 2): ...

    def submit(self, req: Request) -> Admission: ...
    def advance(self, sensors: Sequence[Sensor]) -> Step: ...
```

```python
@dataclass(frozen=True)
class Request:                  # (train, departure end, destination block)
    train: str
    depart: str                 # "<block>.A" | "<block>.B"
    dest: str                   # block id
    at: int                     # arrival tick

@dataclass(frozen=True)
class Sensor:                   # anonymous, per #4 — no train identity
    kind: Literal["block_occupied", "block_vacated"]
    block: str

@dataclass(frozen=True)
class Move:                     # a granted increment
    train: str
    transit: tuple[str, str]    # (connection, transit)
    into: str                   # block id

@dataclass(frozen=True)
class Step:
    moves: list[Move]
    events: list[TraceEvent]
```

`Move` is **data, not a call**. This is what makes the core hardware
independent: there is no backend protocol to implement, so the simulator and a
future DCC-EX driver consume the same values by different means, and a test
needs neither. The dispatcher never reads a clock and never calls out.

`advance` takes a tick's sensor events as a **batch**, not one at a time,
because [#4](https://github.com/iot49/tc49/issues/4) fixes grant order — active
trains by request arrival tick, then pending launches oldest-first — and that
order must not depend on the order sensors happen to fire.

## Who owns the loop

Each adapter does. The simulator's loop is exactly the three phases of #4:

```python
pending: list[Move] = []
for tick in count():
    for req in scenario.requests_at(tick):      # 1. admit
        trace.append(dispatcher.submit(req))
    sensors = world.apply(pending)              # 2. move + release
    step = dispatcher.advance(sensors)          # 3. grant
    trace.extend(step.events)
    pending = step.moves                        # take effect at tick+1
```

A DCC-EX driver replaces `world.apply` with throttle and turnout commands and
`sensors` with current-detector readings. Nothing else changes.

## The locking seam

```python
class LockingStrategy(Protocol):
    def launch(self, req: Request, state: State) -> Route | None: ...
    def grant(self, train: str, state: State) -> Grant | None: ...
```

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

## Event trace

One JSONL stream, one event per line, merged from both sides of the interface.
The dispatcher's events come back from `submit` and `advance`; the backend adds
its own.

From the dispatcher:

| Event | Fields |
| --- | --- |
| `request_admitted` | `train`, `depart`, `dest` |
| `request_rejected` | `train`, `depart`, `dest`, `reason` |
| `route_chosen` | `train`, `route`, `k_tried` |
| `grant_refused` | `train`, `reason` (`unsafe`, `held`, `transit_conflict`) |
| `lock_granted` | `train`, `resources` |
| `lock_released` | `train`, `resources` |
| `request_completed` | `train`, `latency` |

From the backend:

| Event | Fields |
| --- | --- |
| `block_occupied` | `block` |
| `block_vacated` | `block` |
| `train_moved` | `train`, `from`, `transit`, `to` |
| `run_stalled` | `pending`, `obstacles` |

`run_stalled` exists because metrics are a pure function of the trace, so the
stall diagnosis of [BENCHMARKS.md](BENCHMARKS.md#termination) cannot be read off
final state the trace never recorded.

Every event carries `tick` and `event`:

```json
{"tick": 0, "event": "request_admitted", "train": "freight_1", "depart": "yard_w.B", "dest": "yard_e"}
{"tick": 0, "event": "route_chosen", "train": "freight_1", "route": ["yard_w", "to_dn", "dn_w"], "k_tried": 1}
{"tick": 1, "event": "grant_refused", "train": "express_2", "reason": "unsafe"}
```

`grant_refused` and `route_chosen` are the reason the trace is worth having.
They are dispatcher-internal facts, and a benchmark that reports makespan
without them cannot explain *why* throughput was lost.

## Metrics

`metrics(trace) -> Metrics` is a pure function of the trace — nothing is
accumulated live. The four metrics of [DISPATCH.md](DISPATCH.md) all derive
from the vocabulary above: makespan from the first `request_admitted` to the
last `request_completed`, latency from `request_completed`, utilization from
`lock_granted`/`lock_released` spans, and parallelism by counting `train_moved`
per tick.

This is deliberate. It keeps the trace **load-bearing**: an event that stops
being emitted breaks a metric and fails a test, rather than leaving the trace to
rot quietly until a future UI discovers it is missing what it needs. It also
makes every metric testable against a hand-written trace, with no run required.

## Package layout

```
src/tc49/
  layout.py    Layout — blocks, connections, transits, conflict matrix
               (expanded from `concurrent` by inversion), derived terminal
               blocks, step()
  routing.py   candidates(layout, req, k) — k-shortest, DISPATCH.md's
               ordering and dedupe-by-resource-set
  scenario.py  Scenario — trains, requests, YAML loading (LAYOUT.md)
  dispatch.py  Dispatcher — submit/advance, queue, lock table, state
  locking.py   LockingStrategy, FullRoute, Incremental
  safety.py    safe()
  trace.py     TraceEvent types, JSONL read/write
  sim.py       Simulator — applies moves, emits sensors, owns the tick loop
  metrics.py   metrics(trace) -> Metrics
  cli.py       `tc49 bench` / `tc49 sweep`, a scenario as the single argument

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

pytest, with Hypothesis for the deadlock hunt. The generator produces **train
placements and request sequences over a fixed library of hand-written
layouts** — deadlock is a property of request interleaving, not of exotic
topology, so that is where the search pressure belongs. The library is chosen
to be adversarial:

- `facing-pair` — two facing blocks with no other connection, DISPATCH.md's
  minimal deadlock.
- `single-track-meet` — a passing loop that forces meet-pass decisions.
- `crossover-yard` — the double crossover of `image.png`, exercising partial
  transit concurrency; already written, at
  [`layouts/crossover-yard.layout.yaml`](../layouts/crossover-yard.layout.yaml).

Four properties:

1. **Safety invariant** — every reachable state satisfies `safe()`. Local, so it
   fails at the grant that broke it rather than at the deadlock much later.
2. **Quiescence oracle** — a quiesced run with pending requests is always
   attributable to a permanent obstacle, never to a circular wait
   ([SAFETY.md](SAFETY.md)). Anything else is a policy bug.
3. **Differential against the baseline** — `Incremental` completes every request
   set `FullRoute` completes, in no more ticks.
4. **Determinism** — repeated runs produce byte-identical traces, guarding the
   tie-break and grant-order promises of #3 and #4.

Shrunk counterexamples are committed as scenario YAML regression fixtures, which
is the practical payoff of generating requests rather than layouts: a failure is
a readable scenario file, not an unpicturable random graph.

The six boundary conditions closing [SAFETY.md](SAFETY.md) are each an example
test alongside these.
