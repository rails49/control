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
([ADR-0013](adr/0013-apps-are-deployment-units.md)). Today there are eight in
Python — store, scheduler, dispatcher, driver, simulator, layout, dccex-usb,
dccex — and one in the browser: `ui/`, which is **one** app, one page holding
one loaded railroad and a list of views of it
([ADR-0038](adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).

`layout` is the physical binding of the layout interface, and the core app the
hardware hangs under
([ADR-0043](adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md),
docs/layout/README.md). The `simulator` is the other binding of the same
contract and neither knows about the other, so a run has one of them: the bench
harness assembles the simulator, and a railroad with steel on it runs `layout`.

`dccex-usb` and `dccex` hang under `layout`. `dccex-usb` owns the command
station's serial device and serves it on a TCP port; it is an app by the same
rule as the rest — its own container, on the machine the device is plugged
into — and it is the one that meets neither the bus nor the store, having no
contract of ours to speak (docs/dccex_usb/README.md). `dccex` is the first
**translator**: it subscribes to the device vocabulary, turns it into the
command station's own language over that port, and publishes back the supply
and its own link (docs/dccex/README.md). Zero, one or more translators run,
per what is wired, and each recognises its own addresses so no ownership table
exists anywhere (ADR-0043).

Apps import `tc49.lib` and themselves, **never each other**. They meet only
over the event bus and the asset store's CRUD contract, so each one can be
read, tested and eventually deployed without the others.

[SYSTEM.md](SYSTEM.md) is the normative definition of those contracts;
`lib/` is its Python binding. A TypeScript UI gets a sibling language binding
of the same spec ([ADR-0014](adr/0014-python-apps-typescript-ui.md)), so
nothing an app depends on is defined only in Python.

`src/tc49/bench/` is not an app. It is the research harness, and the only code
that wires apps together. Top-level `bench/` is the fixture data it roots
itself at, and is not code at all.

## Package layout

```
src/tc49/
  lib/          the Python binding of SYSTEM.md's contracts
    bus.py        the bus every app is handed — the interface, and the
                  in-process binding of it: queued FIFO, run-to-completion,
                  prefix-filter subscriptions (SYSTEM.md#the-bus)
    mqtt.py       the other binding, over an MQTT broker — retained state
                  topics, a wall-time stamp, the network thread queueing and
                  `drain()` delivering (ADR-0059)
    bridge.py     the WebSocket relay of a live session — `tc49/#` out as
                  {topic, payload} frames, `request_submitted` in; deleted
                  with the in-process bus when a real broker arrives
    layout.py     Layout — blocks, connections, transits, conflict matrix
                  (expanded from `concurrent` by inversion), derived
                  terminal blocks
    roster.py     Model, Car, Train, Roster — a railroad's stock and the
                  installation's models (ADR-0045)
    stock.py      the validator that reads the roster and the catalogue into
                  those, beside the types because an app in its own process
                  reads a roster too and has no store to import
    documents.py  Documents — the layout, the roster and the catalogue read
                  off the store's HTTP face by name, retried while the store
                  is not up (ADR-0059 decision 5)
    scenario.py   Scenario, TrainSpec, RequestSpec — the harness's own
                  document, which no app reads (#171)
    inventory.py  the event inventory's leaf fields
    trace.py      the trace tap — canonical JSONL serialization, read/write

  store/        store.py    AssetStore — CRUD contract, YAML binding,
                            validate at get
                drawing.py  Drawing — the authored schematic and the
                            derivation of a layout from it (store/DRAWING.md)
                yamlfile.py save — writing a document back without
                            disturbing what is already in the file, which is
                            mostly comments (ADR-0018)
                server.py   the store's HTTP face: list, read a drawing
                            document, write one, and review one — red pins,
                            junctions, joints, the layout and why it is that
                            (ui/EDITOR.md); and the derived layout an app in
                            its own process reads (ADR-0059 decision 5)
                symbols.py  render() — the symbol library as the TypeScript
                            the editor draws against
                root.py     store_root() — where an installation's own
                            documents are: `~/tc49/`, or `--store`/
                            `TC49_STORE` (store/LAYOUT.md, #320)
                backup.py   Backup — git over that root, driven and not
                            owned: a commit coalesced on idle, a push on its
                            own timer, a restore refused over a dirty tree
                            (store/BACKUP.md, ADR-0053)
  scheduler/    scheduler.py  Scheduler — composes gestures into requests
                              and submits a timetable whole at the start of a
                              run, mechanical arrival-end expansion,
                              deterministic ids, exhausted state topic
                __main__.py   `python -m tc49.scheduler --broker … --railroad
                              … --store …`, the command line a container
                              runs: the railroad's documents off the store,
                              the broker, this app's own rows, then a drain
                              loop that ends on a signal (ADR-0059)
  dispatcher/   dispatch.py   Dispatcher — admission, queue, lock table,
                              sensor roles, grant sweep, align
                locking.py    LockingStrategy, FullRoute, Incremental
                routing.py    candidates(layout, origin, depart_end,
                              arrivals, train_length, k) — k-shortest over
                              every arrival end merged, DISPATCH.md's
                              ordering
                safety.py     safe()
                __main__.py   `python -m tc49.dispatcher --broker … --railroad
                              … --store …`, the command line a container
                              runs: the railroad's layout and roster off the
                              store, the broker, the picture the last process
                              left, then a drain loop that ends on a signal
                              (ADR-0059)
  driver/       Driver — move_granted → move
  simulator/    Simulator — the milestone-1 layout interface: a
                discrete-event engine that schedules each accepted move's
                sensors on fixed delays, owns the run clock, pacing and
                termination
  layout/       interface.py  LayoutInterface — the physical layout
                              interface: align before move, the near-end
                              check, nothing while the rails are dead, the
                              device vocabulary out, a block's two debounced
                              detectors folded into the occupancy events, and
                              the traction write, whose sign is the train's
                              facing composed with each car's orientation
                              (docs/layout/README.md)
  dccex_usb/    station.py  Station — the command station's serial device
                            mirrored on a TCP port: every byte fanned out to
                            every client, a client's bytes written whole
                framing.py  frame() — bytes in, whole `<…>` messages out
                __main__.py `python -m tc49.dccex_usb --device … --port …`,
                            the command line deploy/app.Dockerfile runs
  dccex/        translator.py  the translator between the device vocabulary
                               and the command station: the desired state out
                               over one connection to `dccex-usb`, the supply
                               and the link back (docs/dccex/README.md)
                commands.py    the mapping — one desired value in, the exact
                               bytes out, pure
                replies.py     the framing, and the two facts this app reads
                               out of what the station says

  bench/        runner.py   assemble the apps on one bus and run a scenario
                            to quiescence — the one wiring, shared by the
                            CLI and the tests
                session.py  the live session: one railroad at a time behind
                            the bridge, swapped by whoever joins
                replay.py   Replay — a scenario played onto a live run as
                            the gestures a person would make (#171)
                detector.py HandFed — a person's typed readings published as
                            the detector rows nothing publishes yet, on a
                            physical run alone (#315)
                cli.py      `tc49 bench <scenario>`; `tc49 sweep` takes no
                            arguments — the grid of BENCHMARKS.md is the
                            fixed research design; `tc49 layout show`;
                            `tc49 serve` runs the store's HTTP face;
                            `tc49 generate` rewrites every TypeScript
                            file the UI is handed rather than keeps by hand
                sweep.py    the seeded workload generator and the fixed grid
                metrics.py  metrics(trace) -> Metrics

ui/                         the layout editor: TypeScript, pnpm, Lit
                            (ADR-0014). Outside src/tc49/, which is Python.
                            src/symbols.generated.ts is written by
                            `tc49 generate` from store/drawing.py's symbol
                            library, and src/rejection.generated.ts from
                            lib/rejection.py's reason set; a test asserts
                            each is current
              src/model/    the document, the geometry, the editing session,
                            connection naming and the store client — no DOM,
                            and what the Vitest tests target
              src/render/   the artwork, hand-written per kind
              src/ui/       the Lit components: shell, palette, canvas,
                            netlist, properties, menu
              test/         the Vitest tests

bench/                      the harness's inputs, the store `tc49 bench`,
                            `tc49 sweep` and `tc49 layout show` root
                            themselves at. A session and the server read an
                            installation's own store instead (#320)
  layouts/                  <layout>.drawing.yaml — the drawn railroads,
                            the only committed topology; the store derives
                            each layout from its drawing
                            <layout>.roster.yaml — the trains it owns
  catalogue/                <model>.yaml — what a product is
  scenarios/<layout>/       <scenario>.scenario.yaml — the harness's placement
                            and request lists
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
  MILESTONE-2.md   scope: the physical layout, and what running decides
  SYSTEM.md        the apps and the contracts between them
  ARCHITECTURE.md  this page: repo organization and tests
  adr/             every decision, one numbered sequence
  dispatcher/      DISPATCH.md  SAFETY.md  INTERNALS.md
  store/           LAYOUT.md  DRAWING.md
  bench/           BENCHMARKS.md  METRICS.md
  ui/              EDITOR.md  PANEL.md  THROTTLE.md — a page per view
  layout/          README.md
  dccex_usb/       README.md
  dccex/           README.md
  agents/          how agent skills should consume this repo
  research/        background reading
```

An app gets a folder when it has internals worth writing down. `scheduler`,
`driver` and `simulator` have none: their whole behaviour is their footprint
in [SYSTEM.md](SYSTEM.md#component-footprints), and an empty folder would
suggest otherwise. `layout` has one because it is a second binding of a
footprint the simulator also implements, and what each does with the same
commands is its own. `dccex-usb` has one for the opposite reason — it has no
footprint there at all, so its page is the only place its behaviour is
written down. `dccex` has one for both reasons at once: its bus footprint is
the device vocabulary, and its page is the only place in the repository where
the command station's own syntax is written, product names staying out of the
normative documents.

**ADRs are not split by app.** They stay one numbered sequence in `adr/`,
because the numbering is a chronological record rather than a filing system,
and several ADRs decide contracts *between* apps and so have no single app to
live in. Each spec page links the ADRs that bind it.

## Tests

`tests/` mirrors `src/tc49/`: one package per app, plus `system/` for the
tests that drive the real assembly over the bus, with `harness.py`,
`brokers.py` — a real broker, for the apps that come up against one — and
`generate.py` shared at the top.

```
tests/
  harness.py  brokers.py  generate.py
  lib/         test_layout  test_bus  test_trace
  store/       test_store  test_drawing  test_server  test_symbols
  scheduler/   test_scheduler  test_main
  dispatcher/  test_routing  test_safety  test_incremental  test_aging
               test_main
  bench/       test_metrics  test_sweep  test_cli  test_benchmarks
  driver/      test_driver
  simulator/   test_move  test_power  test_placement  test_pacing  test_live
               test_reading
  layout/      test_align  test_move  test_aspects  test_power  test_reading
               test_occupancy  test_traction  test_mode  test_throttle
  dccex_usb/   test_framing  test_station
  dccex/       test_commands  test_replies  test_translator
  system/      test_skeleton  test_properties  test_safety_conditions
               test_app_boundaries
```

Every app has a test package. The two bindings of the layout interface each
have one because what they refuse — a stale command, a dead railroad — is
refused at the interface and has to be driven from there; for `layout` that
package is the whole of the app's cover, nothing assembling it, since a run has
one binding of the interface.

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
  [`bench/layouts/single-track-meet.drawing.yaml`](../bench/layouts/single-track-meet.drawing.yaml).
- `crossover-yard` — the double crossover of `image.png`, exercising partial
  transit concurrency; already drawn, at
  [`bench/layouts/crossover-yard.drawing.yaml`](../bench/layouts/crossover-yard.drawing.yaml).

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
   `FullRoute` completes, in no more boundaries", and **that is false** — the
   suite found it out, which is what the suite is for. Every form of the dominance
   claim falls to adversarial search: the completed sets can be incomparable,
   the counts can favour either side, and even when both strategies complete
   exactly the same set `Incremental` can be slower. The shrunk counterexample
   is committed as
   [`crossover-yard/route-blindness`](../bench/scenarios/crossover-yard/route-blindness.scenario.yaml)
   and asserted exactly in `tests/dispatcher/test_incremental.py`: two trains,
   no idle obstacle, no starvation, and `FullRoute` a transit faster (a
   boundary, in the units of the day).

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

   **This one is a property of the bindings rather than of the system.** It
   needs the simulator's deterministic beat and the in-process bus's queued
   FIFO, and it could not hold on a physical railroad, where the cadence comes
   from a clock and sensor arrival order is unspecified. Properties 1–3 survive
   that change of binding and this one does not, which a hardware effort should
   know before reading the suite
   ([ADR-0030](adr/0030-the-physical-railroad-is-the-normative-binding.md)).
   What does survive is what determinism is testing for: that a run is a pure
   function of its inputs — fixed transit delays, no RNG, one delivery order —
   and that arrival order picks only among grants that were all safe
   ([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).

**The library-core seam is pure functions only.** Direct unit tests cover
`safe()` on hand-built states, layout graph queries, route policies, and the
scheduler's arrival-end expansion. The six boundary conditions closing
[SAFETY.md](dispatcher/SAFETY.md) are scenario-shaped, so they run over the bus
as committed scenario YAML — the same harness and fixture format as shrunk
Hypothesis counterexamples, which is the practical payoff of generating
requests rather than layouts: a failure is a readable scenario file, not an
unpicturable random graph.
