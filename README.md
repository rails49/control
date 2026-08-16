# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad.

This repo (eventually) implements the features described in the docs:

- [Goals](docs/GOALS.md) — assets (tracks, blocks, connections, stock) and the
  operations performed on them.
- [Milestone 1](docs/MILESTONE-1.md) — what is being built first, and what is
  deliberately out of scope.
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
- [Store](docs/store) — the [layout and scenario file
  formats](docs/store/LAYOUT.md) and the [drawing format and
  derivation](docs/store/DRAWING.md) that will replace hand-authored layouts;
  the encoded railroads live in [layouts/](layouts) and
  [scenarios/](scenarios).
- [Bench](docs/bench) — the [benchmark suite](docs/bench/BENCHMARKS.md) and
  the [metrics derivations](docs/bench/METRICS.md).
- [UI](docs/ui) — the [layout editor](docs/ui/EDITOR.md) and the [dispatch
  panel](docs/ui/PANEL.md), both design pages for the app to come.
