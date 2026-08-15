# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad. See
[README.md](README.md) for the doc map; the research core is deadlock-free,
high-throughput dispatch ([docs/dispatcher/DISPATCH.md](docs/dispatcher/DISPATCH.md)).

## Apps

An **app** is a unit that will run as its own container: `store`, `scheduler`,
`dispatcher`, `driver`, `simulator`, and a `ui` later. Each gets one package in
`src/tc49/`. Apps import `tc49.lib` and themselves, **never each other**; they
meet over the event bus and the store's CRUD contract.

`docs/SYSTEM.md` is the normative definition of those contracts and `lib/` is
its Python binding, so a TypeScript UI gets a sibling binding rather than
chasing Python. `bench/` is the research harness, not an app, and is the only
code that wires apps together. `tests/` mirrors the same structure;
`tests/system/test_app_boundaries.py` enforces the import rule.

`docs/` splits the same way: repo-wide pages at the top level, an app's
implementation details in a subfolder named for its package. ADRs are the
exception — one numbered sequence in `docs/adr/`, never split by app.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[ADR-0013](docs/adr/0013-apps-are-deployment-units.md).

## Landing work

History is linear: no merge commits, no PRs. Open an issue, commit to `main`
in reviewable steps referencing it, push, close the issue. Keep mechanical
moves in their own commit so renames stay legible in the diff.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `iot49/tc49`, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root plus `docs/adr/`. See `docs/agents/domain.md`.
