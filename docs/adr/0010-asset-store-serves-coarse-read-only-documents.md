# The asset store serves coarse read-only documents

The asset store holds two document types — `layout` and `scenario` — keyed
by name, with `get`/`put`/`delete`/`list` on whole documents. App components
are read-only and snapshot their assets at startup; assets are immutable for
the run, and no asset-change events exist on the bus. The store validates at
`put` (schema and referential integrity), so a `get` never returns an
invalid document; all derivation — conflict matrix, terminal blocks,
arrival-end expansion, fit pruning — stays consumer-side.

Fine-grained resources (blocks, trains, requests as addressable entities)
were rejected because every current consumer uses a document whole; the
fine-grained surface has exactly one hypothetical caller, the out-of-scope
layout editor. Runtime writes were rejected on the failure mode: a mid-run
topology change invalidates committed routes and locks the dispatcher
reasons about, and a scenario that mutates when run is a broken benchmark
fixture. Runtime truth is bus state and history is the trace; when runtime
stock mutation is genuinely needed (car drops changing a train's length) it
arrives as a runtime writer or a checkpoint document type in a future
effort, not as a softening of this rule.

The milestone-1 binding is a Python library over the YAML files of
[LAYOUT.md](../store/LAYOUT.md); a REST binding later slots under the same names
and verbs. See [SYSTEM.md](../SYSTEM.md#asset-store).
