# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad.

This repo (eventually) implements the features described in the docs:

- [Goals](docs/GOALS.md) — the end state: assets (tracks, blocks, connections,
  stock) and the three operations performed on them — scheduling, dispatching,
  driving.
- [Milestone 1](docs/MILESTONE-1.md) — reached: what the first slice built, and
  what is deliberately still out of scope.
- [System](docs/SYSTEM.md) — the apps and the contracts between them: the
  event bus and its inventory, time, and the asset store.
- [Architecture](docs/ARCHITECTURE.md) — how the repository is organized and
  how it is tested.
- [Glossary](CONTEXT.md) — canonical terms; decisions in [docs/adr](docs/adr).

Each app's implementation details live beside it:

- [Dispatcher](docs/dispatcher) — [dispatch](docs/dispatcher/DISPATCH.md)
  (finding, locking, and releasing routes),
  [safety](docs/dispatcher/SAFETY.md) (why it is deadlock-free), and
  [internals](docs/dispatcher/INTERNALS.md).
- [Store](docs/store) — the [drawing format and
  derivation](docs/store/DRAWING.md), the only committed topology, and the
  [derived layout, the roster and the harness's scenario
  file](docs/store/LAYOUT.md) it feeds; the drawn railroads and their rosters
  live in [layouts/](layouts) and the harness's scenarios in
  [scenarios/](scenarios).
- [Bench](docs/bench) — the [benchmark suite](docs/bench/BENCHMARKS.md) and
  the [metrics derivations](docs/bench/METRICS.md).
- [UI](docs/ui) — one app with two views of the loaded railroad, the [layout
  editor](docs/ui/EDITOR.md) and the [run view](docs/ui/PANEL.md), living in
  [ui/](ui).
