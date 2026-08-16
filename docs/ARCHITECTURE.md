# Architecture

How the repository is organized and how it is tested. The contracts *between*
apps — bus, event inventory, time, asset store, footprints — are
[SYSTEM.md](SYSTEM.md)'s and are not repeated here. Each app's internals are
its own page: the dispatcher's are
[dispatcher/INTERNALS.md](dispatcher/INTERNALS.md), the metrics derivations
[bench/METRICS.md](bench/METRICS.md). Terminology follows
[CONTEXT.md](../CONTEXT.md).

## Apps

An **app** is a unit that will run as its own container
([ADR-0013](adr/0013-apps-are-deployment-units.md)). Today there are five:
store, scheduler, dispatcher, driver, simulator. A UI is expected later.

Apps import `tc49.lib` and themselves, **never each other**. They meet only
over the event bus and the asset store's CRUD contract, so each one can be
read, tested and eventually deployed without the others.

[SYSTEM.md](SYSTEM.md) is the normative definition of those contracts;
`lib/` is its Python binding. A TypeScript UI gets a sibling language binding
of the same spec ([ADR-0014](adr/0014-python-apps-typescript-ui.md)), so
nothing an app depends on is defined only in Python.

`bench/` is not an app. It is the research harness, and the only code that
wires apps together.

## Package layout

```
src/tc49/
  lib/          the Python binding of SYSTEM.md's contracts
    bus.py        the in-process bus — queued FIFO, run-to-completion,
                  prefix-filter subscriptions (SYSTEM.md#the-bus)
    layout.py     Layout — blocks, connections, transits, conflict matrix
                  (expanded from `concurrent` by inversion), derived
                  terminal blocks
    scenario.py   Scenario, TrainSpec, RequestSpec — the other coarse
                  document type of ADR-0010
    inventory.py  the event inventory's leaf fields
    trace.py      the trace tap — canonical JSONL serialization, read/write

  store/        store.py    AssetStore — CRUD contract, YAML binding,
                            validate at get
                drawing.py  Drawing — the authored schematic and the
                            derivation of a layout from it (store/DRAWING.md)
                convert.py  to_drawing — the conversion of a layout
                            document into the drawing that derives it,
                            which is how the railroads were migrated
                server.py   the store's HTTP face: list, read a drawing
                            document, write one, derive, explain — what the
                            editor talks to (ui/EDITOR.md)
  scheduler/    Scheduler — releases scenario requests at their `at` ticks,
                mechanical arrival-end expansion, deterministic ids,
                exhausted state topic
  dispatcher/   dispatch.py   Dispatcher — admission, queue, lock table,
                              buffered sensors, grant phase
                locking.py    LockingStrategy, FullRoute, Incremental
                routing.py    candidates(layout, origin, depart_end,
                              arrivals, train_length, k) — k-shortest over
                              every arrival end merged, DISPATCH.md's
                              ordering
                safety.py     safe()
  driver/       Driver — move_granted → align + cross
  simulator/    Simulator — the milestone-1 layout interface: applies
                commands, emits sensors, publishes the tick, owns pacing
                and termination

  bench/        runner.py   assemble the apps on one bus and run a scenario
                            to quiescence — the one wiring, shared by the
                            CLI and the tests
                cli.py      `tc49 bench <scenario>`; `tc49 sweep` takes no
                            arguments — the grid of BENCHMARKS.md is the
                            fixed research design
                sweep.py    the seeded workload generator and the fixed grid
                metrics.py  metrics(trace) -> Metrics

ui/                         the layout editor: TypeScript, pnpm, Lit
                            (ADR-0014). Outside src/tc49/, which is Python.
                            src/symbols.generated.ts is generated from
                            store/drawing.py's symbol library

layouts/                    <layout>.drawing.yaml — the drawn railroads,
                            the only committed topology; the store derives
                            each layout from its drawing
scenarios/<layout>/         <scenario>.scenario.yaml — stock and requests
benchmarks/expected/        <name>.json — golden numbers, asserted in pytest
out/                        sweep JSONL, gitignored
```

Each app package's `__init__.py` names its public entry point, so `runner.py`
imports from the app rather than from a module inside it. Tests that exercise
an app's internals import those by module, which is what makes the difference
visible.

The document types live in `lib/`, not in the store, because the scheduler,
dispatcher and simulator all read them. The store owns the binding and the
validator that produce them, not the types themselves.

Routing sits outside `Layout` so that `Layout` stays a data structure rather
than growing a policy. The [layout-format
prototype](https://github.com/rails49/control/tree/prototype/layout-format/prototype/layout-format)
had `route()` as a method, which was right for a throwaway and wrong here:
route choice is a pluggable policy per #3, and the layout should not know
about it. That is also why `routing.py` belongs to the dispatcher while
`layout.py` is shared.

## Documentation layout

`docs/` follows the same split. The top level is what is true of the repo or
of the system as a whole; an app's implementation details go in a subfolder
named for its package in `src/tc49/`.

```
docs/
  GOALS.md         assets and the operations on them
  MILESTONE-1.md   scope: what is built first, what is not
  SYSTEM.md        the apps and the contracts between them
  ARCHITECTURE.md  this page: repo organization and tests
  adr/             every decision, one numbered sequence
  dispatcher/      DISPATCH.md  SAFETY.md  INTERNALS.md
  store/           LAYOUT.md  DRAWING.md
  bench/           BENCHMARKS.md  METRICS.md
  ui/              EDITOR.md  PANEL.md — design pages for the app to come
  agents/          how agent skills should consume this repo
  research/        background reading
```

An app gets a folder when it has internals worth writing down. `scheduler`,
`driver` and `simulator` have none: their whole behaviour is their footprint
in [SYSTEM.md](SYSTEM.md#component-footprints), and an empty folder would
suggest otherwise.

**ADRs are not split by app.** They stay one numbered sequence in `adr/`,
because the numbering is a chronological record rather than a filing system,
and several ADRs decide contracts *between* apps and so have no single app to
live in. Each spec page links the ADRs that bind it.

## Tests

`tests/` mirrors `src/tc49/`: one package per app, plus `system/` for the
tests that drive the real assembly over the bus, with `harness.py` and
`generate.py` shared at the top.

```
tests/
  harness.py  generate.py
  lib/         test_layout  test_bus  test_trace
  store/       test_store  test_drawing  test_convert
  scheduler/   test_scheduler
  dispatcher/  test_routing  test_safety  test_incremental  test_aging
  bench/       test_metrics  test_sweep  test_cli  test_benchmarks
  system/      test_skeleton  test_properties  test_boundaries
               test_app_boundaries
```

`driver` and `simulator` have no test package: neither has a test of its own,
and both are covered only through the assembly tests.

`test_app_boundaries` checks the import rule above by parsing each app's
modules and reading off what they import. The rule is the kind that decays
silently — one convenient import and two containers are welded together with
nothing failing — so it is checked rather than reviewed. `bench` is exempt,
being the code that assembles the apps.

pytest, with Hypothesis for the deadlock hunt. **All four properties drive
the real assembly over the in-process bus**: each generated case wires
scheduler, dispatcher, driver, and simulator together and interacts only by
publishing and observing events, so the bus contract itself gets thousands
of adversarial runs for free. The single-threaded, no-I/O bus keeps
Hypothesis throughput acceptable.

The generator produces **train placements and request sequences over a fixed
library of drawn railroads** — deadlock is a property of request
interleaving, not of exotic topology, so that is where the search pressure
belongs. Arrival-end *sets* are part of what it draws, and they shrink toward
singletons, so a counterexample reduces to the tightest request that still
deadlocks. The library is chosen to be adversarial:

- `facing-pair` — two facing blocks with no other connection, DISPATCH.md's
  minimal deadlock.
- `single-track-meet` — a passing loop that forces meet-pass decisions, at
  [`layouts/single-track-meet.drawing.yaml`](../layouts/single-track-meet.drawing.yaml).
- `crossover-yard` — the double crossover of `image.png`, exercising partial
  transit concurrency; already drawn, at
  [`layouts/crossover-yard.drawing.yaml`](../layouts/crossover-yard.drawing.yaml).

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
   ([SAFETY.md](dispatcher/SAFETY.md)). Anything else is a policy bug.
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
   and asserted exactly in `tests/dispatcher/test_incremental.py`: two trains,
   no idle obstacle, no starvation, and `FullRoute` a tick faster.

   The mechanism was that locking a whole route up front is not merely
   conservative but **informative**, and route selection is what consumes the
   information. `FullRoute` locked the first train's whole route, so the second
   train's launch found its lexicographically-first candidate blocked and fell
   through to a candidate on the other line. `Incremental` locked only the
   first increment, so that candidate still looked clear, both trains committed
   to the same line, and one waited. Congestion-aware costing (#33) closed the
   gap: committed routes now enter the route ordering directly
   ([DISPATCH.md](dispatcher/DISPATCH.md#route-selection)), so both strategies
   steer the second train to the other line and finish the scenario together,
   asserted in `test_incremental.py`, with the scenario kept as the regression
   fixture. The dominance claim itself stays withdrawn: nothing here was a
   safety defect — both strategies stay deadlock-free — and the throughput
   claim belongs to the measured benchmark workloads, not to arbitrary ones.
4. **Determinism** — each scenario runs twice in one test and the two trace
   byte streams are asserted identical in memory, guarding the tie-break,
   grant-order, and canonical-serialization promises. No trace files are
   committed: the committed goldens are the metrics numbers in
   `benchmarks/expected/` plus scenario YAML fixtures, so the event
   inventory can evolve without fixture churn.

**The library-core seam is pure functions only.** Direct unit tests cover
`safe()` on hand-built states, layout graph queries, route policies, and the
scheduler's arrival-end expansion. The six boundary conditions closing
[SAFETY.md](dispatcher/SAFETY.md) are scenario-shaped, so they run over the bus
as committed scenario YAML — the same harness and fixture format as shrunk
Hypothesis counterexamples, which is the practical payoff of generating
requests rather than layouts: a failure is a readable scenario file, not an
unpicturable random graph.
