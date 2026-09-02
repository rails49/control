# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad.

**Status: alpha.** Interfaces, topics, and file formats change without notice,
and nothing here runs on a layout other than the author's yet. Published to
share the design, not to be installed. [MIT licensed](LICENSE).

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
- [Deploy](docs/DEPLOY.md) — the names, the certificate and the reverse
  proxy that puts the stack on the LAN, living in [deploy/](deploy).

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
- [Layout](docs/layout) — the [layout interface as a core
  app](docs/layout/README.md): the three rules a command meets, and the device
  vocabulary the hardware hangs under.
- [Station](docs/station) — the [command station mirror](docs/station/README.md):
  one process owns the USB device and serves it on TCP 2560, so the `dccex`
  translator, JMRI and hand-held throttles share one station.
- [DCC-EX](docs/dccex) — the [translator](docs/dccex/README.md) between the
  device vocabulary and the command station: the mapping a row at a time, the
  latched stop and the zeros that precede its release, and the only page here
  that writes the station's own syntax down.
- [UI](docs/ui) — one app with three views of the loaded railroad, the [layout
  editor](docs/ui/EDITOR.md), the [run view](docs/ui/PANEL.md) and the
  [throttle](docs/ui/THROTTLE.md) a person drives a train from, living in
  [ui/](ui).
