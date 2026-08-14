# Milestone 1

What is being built first, and — more usefully — what is not. [GOALS.md](GOALS.md)
describes the whole system; this page fixes the boundary of its first slice.

## Deliverable

The system of [SYSTEM.md](SYSTEM.md) — the components wired over the
in-process bus — plus a benchmark harness:

- The **dispatcher** of [DISPATCH.md](DISPATCH.md), with both locking
  strategies real from day one — full-route locking as the baseline yardstick,
  incremental locking with the route-aware safety check of
  [SAFETY.md](SAFETY.md) as the research core.
- The **scheduler** and **driver** — thin but real bus components: the
  scheduler releases the scenario's fixed request list at its `at` ticks, the
  driver translates each granted move into layout commands.
- The **simulator**, implementing the layout interface: executes commands,
  reports occupancy, publishes the tick, and owns pacing and termination.
- The **asset store** in its milestone-1 binding — the Python library over
  the YAML files of [LAYOUT.md](LAYOUT.md).
- A **pytest suite** — the four Hypothesis properties over the real assembly
  on the bus, the boundary-condition examples, and golden-number assertions
  on the named scenarios.
- A **benchmark CLI** that takes a `(layout, scenario)` pair, prints the four
  metrics of [DISPATCH.md](DISPATCH.md#metrics), and can dump the structured
  event trace ([BENCHMARKS.md](BENCHMARKS.md)).

**Done** when an implementing agent can build all of that without hitting an
open decision.

## Toolchain

Python throughout, with `uv` for versions and environments — run things with
`uv run`. Ruff, Black and Pyright for lint, format and type-check.

## Scope

The core is **independent of the layout's hardware**, and milestone 1 builds
only that core. Of [GOALS.md](GOALS.md)'s three operations, dispatching is the
whole subject; the other two are real components kept to the minimum that
exercises it:

- **Scheduling** is a fixed request list read from a scenario file, released
  by the layout-blind scheduler of [SYSTEM.md](SYSTEM.md#scheduler). There is
  no arrival process and no continual-arrivals scheduler.
- **Driving** is the stateless translator of [SYSTEM.md](SYSTEM.md#driver),
  with the simulator advancing each train one transit per tick.

## Rigor bar

Deadlock freedom is established by a **convincing written argument** — the one
in [SAFETY.md](SAFETY.md), with each of its boundary conditions backed by a
test and its safety invariant checked by a Hypothesis property. Formal or
mechanized verification is out of scope.

## Out of scope

Each of these was ruled out deliberately, not overlooked:

| Not in milestone 1 | Why |
| --- | --- |
| A physical layout behind the layout interface | a later effort ([GOALS.md](GOALS.md)); the transit-level command vocabulary of [SYSTEM.md](SYSTEM.md#layout-interface) is the hook |
| MQTT transport, out-of-process deployment | the bus contract is already MQTT-safe ([ADR-0008](adr/0008-bus-contract-is-the-mqtt-safe-intersection.md)); the in-process bus is the milestone binding |
| A real scheduler with continual arrivals | requests are a fixed batch here |
| Human driving | the simulator drives |
| UI / visualization | the event trace is the hook for a future one |
| Mechanized deadlock-freedom proof | argument only, per the rigor bar above |
| Mid-route rerouting | [ADR-0002](adr/0002-fixed-route-per-request.md) |
| Request priorities (express > local) | the pluggable queue-ordering key of [DISPATCH.md](DISPATCH.md#queue-discipline) preserves the upgrade path |
| Transit durations proportional to length | every transit costs one tick, so makespan is a tick count; revisit only if makespan realism becomes a question |
| An aging / anti-starvation rule | starvation is measured by max latency first; add a rule only if the benchmarks show one is needed |
| Guaranteeing an obstructing train eventually gets a request | a **scheduler obligation** the dispatcher's liveness is explicitly conditional on ([SAFETY.md](SAFETY.md)); the dispatcher neither detects nor resolves it — the harness only names it and reports the run `stalled` |
