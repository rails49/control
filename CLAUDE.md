# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad. See
[README.md](README.md) for the doc map; the research core is deadlock-free,
high-throughput dispatch ([docs/dispatcher/DISPATCH.md](docs/dispatcher/DISPATCH.md)).

## Apps

`src/tc49/` has one package per app, where an app is a unit that will run as
its own container: `store`, `scheduler`, `dispatcher`, `driver`, `simulator`.
Apps import `tc49.lib` and themselves, never each other; they meet over the
event bus and the store's CRUD contract. `bench/` is the research harness, not
an app, and is the only code that wires apps together. `tests/` mirrors the
same structure. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[ADR-0013](docs/adr/0013-apps-are-deployment-units.md).

## Agent skills

### Issue tracker

Issues live as GitHub issues in `iot49/tc49`, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root plus `docs/adr/`. See `docs/agents/domain.md`.
