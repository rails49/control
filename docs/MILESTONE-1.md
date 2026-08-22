# Milestone 1

What was built first, and — more usefully — what was not. [GOALS.md](GOALS.md)
describes the whole system; this page fixes the boundary of its first slice.

**Reached.** Everything under *Deliverable* is in the tree and green under
`scripts/check.sh`. The boundary is what stays live: the scope below says what
this slice deliberately does not do, and a row stops binding only when an issue
moves it, as one already has.

## Deliverable

The system of [SYSTEM.md](SYSTEM.md) — the components wired over the
in-process bus — plus a benchmark harness. Where each part landed:

- The **dispatcher** of [DISPATCH.md](dispatcher/DISPATCH.md), with both locking
  strategies real from day one — full-route locking as the baseline yardstick,
  incremental locking with the route-aware safety check of
  [SAFETY.md](dispatcher/SAFETY.md) as the research core: `dispatcher/locking.py`,
  over the state of `dispatcher/dispatch.py`.
- The **scheduler** and **driver** — thin but real bus components: the
  scheduler composes a person's gestures into requests and releases a
  timetable's at their `at` boundaries, the driver translates each granted
  move into layout commands:
  `scheduler/scheduler.py` and `driver/driver.py`, the latter stateless.
- The **simulator**, implementing the layout interface: executes commands,
  reports occupancy, publishes the boundary, and owns pacing and termination:
  `simulator/sim.py`.
- The **asset store** in its milestone-1 binding — the Python library over
  the YAML files of [DRAWING.md](store/DRAWING.md) and
  [LAYOUT.md](store/LAYOUT.md): `store/`.
- A **pytest suite** — the four Hypothesis properties over the real assembly
  on the bus (`tests/system/test_properties.py`), the boundary-condition
  examples (`tests/system/test_safety_conditions.py`, one scenario per
  condition), and golden-number assertions on the named scenarios
  (`tests/bench/test_benchmarks.py`).
- A **benchmark CLI** that takes a scenario — the harness's own file, which
  names its layout ([LAYOUT.md](store/LAYOUT.md)) — prints the four
  metrics of [DISPATCH.md](dispatcher/DISPATCH.md#metrics), and can dump the structured
  event trace ([BENCHMARKS.md](bench/BENCHMARKS.md)): `tc49 bench <scenario> --trace`.

**Done** meant an implementing agent could build all of that without hitting an
open decision. Nothing on the list is stubbed.

## Toolchain

Python throughout, with `uv` for versions and environments — run things with
`uv run`. Ruff, Black and Pyright for lint, format and type-check.

## Scope

The core is **independent of the layout's hardware**, and milestone 1 built
only that core. Of [GOALS.md](GOALS.md)'s three operations, dispatching is the
whole subject; the other two are real components kept to the minimum that
exercises it:

- **Scheduling** is a person's drags, and a fixed request list the harness
  reads from a scenario file for a benchmark run, released by the scheduler of
  [SYSTEM.md](SYSTEM.md#scheduler) — which reads the layout, but only to keep
  facing, and invents nothing
  ([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)). There
  is no arrival process and no continual-arrivals scheduler. A request's `at`
  is a **boundary count**, and that is the milestone binding rather than the
  model: [GOALS.md](GOALS.md#scheduling) says a request comes due at a stated
  time, read off the fast clock, and a boundary count is not a time — a
  hardware adapter picks its own cadence, so counting beats tells a timetable
  nothing. A counted `at` is the same shape of simplification as one transit
  per tick ([ADR-0027](adr/0027-the-tick-is-the-simulators-grant-boundary.md)).
- **Driving** is the stateless translator of [SYSTEM.md](SYSTEM.md#driver),
  with the simulator advancing each train one transit per tick. A train has no
  speed here and reads no signal: the grant it is handed is the whole of what
  it is told.

**A run begins from a railroad**: its drawing, the trains its roster says it
owns, and a person who puts them on the layout
([#171](https://github.com/rails49/control/issues/171)). It comes up with an
empty layout and **held**, which is what lets the placing happen
([ADR-0037](adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md),
[ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)) — there is nothing to
do on one but place trains and press GO. A scenario is the harness's file, not
a run's: `tc49 bench` builds a batch run from one, and `tc49 live --scenario`
replays one as the gestures a person would make.

## Rigor bar

Deadlock freedom is established by a **convincing written argument** — the one
in [SAFETY.md](dispatcher/SAFETY.md), with each of its boundary conditions backed by a
test and its safety invariant checked by a Hypothesis property. Formal or
mechanized verification is out of scope.

## Out of scope

Each of these was ruled out deliberately, not overlooked, and each still binds
unless its row says otherwise:

| Not in milestone 1 | Why |
| --- | --- |
| A physical layout behind the layout interface | a later effort ([GOALS.md](GOALS.md)); the transit-level command vocabulary of [SYSTEM.md](SYSTEM.md#layout-interface) is the hook |
| MQTT transport, out-of-process deployment | the bus contract is already MQTT-safe ([ADR-0008](adr/0008-bus-contract-is-the-mqtt-safe-intersection.md)); the in-process bus is the milestone binding |
| A real scheduler with continual arrivals | requests are a fixed batch or a person's gestures here; the end-state scheduler *generates* traffic, which is what its layout knowledge is ultimately for ([ADR-0028](adr/0028-the-scheduler-knows-where-trains-stand.md)) |
| A driver that obeys the aspect | the dispatcher publishes `stop`/`approach`/`clear`, on the grant and on a last-value topic, and the driver ignores it: acting on it needs a speed on `cross` and transits that take time ([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)) |
| Trains that have a speed | one transit per tick, and a tick is the simulator's boundary rather than the model's unit of time ([ADR-0027](adr/0027-the-tick-is-the-simulators-grant-boundary.md)) |
| Braking distance | an open subject even in the end state, with a working answer and no decision ([GOALS.md](GOALS.md#driving)) |
| A request due at a *time* | `at` is a boundary count here; the fast clock a timetable is written against is end-state work ([GOALS.md](GOALS.md#scheduling)) |
| Human driving | the simulator drives |
| UI / visualization | the event trace was the hook for a future one. **Since crossed**: `ui/` ships the [layout editor](ui/EDITOR.md) and the [dispatch panel](ui/PANEL.md), and the scheduler moved out of the browser to serve them ([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)) |
| Mechanized deadlock-freedom proof | argument only, per the rigor bar above |
| Mid-route rerouting | [ADR-0002](adr/0002-fixed-route-per-request.md) |
| Request priorities (express > local) | the pluggable queue-ordering key of [DISPATCH.md](dispatcher/DISPATCH.md#queue-discipline) preserves the upgrade path |
| Transit durations proportional to length | every transit costs one tick, so makespan is a boundary count; on a physical railroad they vary by construction ([ADR-0027](adr/0027-the-tick-is-the-simulators-grant-boundary.md)), so revisit here only if makespan realism becomes a question |
| An aging / anti-starvation rule | starvation is measured by max latency first; add a rule only if the benchmarks show one is needed |
| Guaranteeing an obstructing train eventually gets a request | a **scheduler obligation** the dispatcher's liveness is explicitly conditional on ([SAFETY.md](dispatcher/SAFETY.md)); the dispatcher neither detects nor resolves it — the harness only names it and reports the run `stalled` |
