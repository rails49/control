# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad.

This repo (eventually) implements the features described in the docs:

- [Goals](docs/GOALS.md) — assets (tracks, blocks, connections, stock) and the
  operations performed on them.
- [Milestone 1](docs/MILESTONE-1.md) — what is being built first, and what is
  deliberately out of scope.
- [System](docs/SYSTEM.md) — the components and the contracts between them:
  the event bus and its inventory, time, and the asset store.
- [Dispatch](docs/DISPATCH.md) — finding, locking, and releasing routes;
  deadlock avoidance at high throughput is the research core.
- [Safety](docs/SAFETY.md) — the avoidance layer and why it is deadlock-free.
- [Architecture](docs/ARCHITECTURE.md) — dispatcher internals, metrics
  derivations, package layout, and the test strategy.
- [Layout files](docs/LAYOUT.md) — the layout and scenario YAML formats; the
  encoded railroads live in [layouts/](layouts) and [scenarios/](scenarios).
- [Benchmarks](docs/BENCHMARKS.md) — the layouts, workloads, sweep axes, and
  what the numbers mean.
- [Glossary](CONTEXT.md) — canonical terms; decisions in [docs/adr](docs/adr).
