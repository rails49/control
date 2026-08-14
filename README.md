# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad.

This repo (eventually) implements the features described in the docs:

- [Goals](docs/GOALS.md) — assets (tracks, blocks, connections, stock) and the
  operations performed on them.
- [Dispatch](docs/DISPATCH.md) — finding, locking, and releasing routes;
  deadlock avoidance at high throughput is the research core.
- [Safety](docs/SAFETY.md) — the avoidance layer and why it is deadlock-free.
- [Architecture](docs/ARCHITECTURE.md) — module structure, the dispatcher
  interface, the event trace, and the test strategy.
- [Glossary](CONTEXT.md) — canonical terms; decisions in [docs/adr](docs/adr).
