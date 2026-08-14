# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. This is a **single-context** repo.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the canonical glossary (block, terminal block, connection, transit, train, request, route, lock, tick).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

```
/
├── CONTEXT.md                              ← the glossary
├── docs/
│   ├── GOALS.md                            ← assets and operations
│   ├── MILESTONE-1.md                      ← scope: what is built first, what is not
│   ├── DISPATCH.md                         ← dispatch semantics, locking, metrics
│   ├── SAFETY.md                           ← the deadlock-freedom argument
│   ├── ARCHITECTURE.md                     ← modules, interfaces, trace, tests
│   ├── LAYOUT.md                           ← layout and scenario file formats
│   ├── BENCHMARKS.md                       ← layouts, workloads, sweep axes
│   └── adr/
│       ├── 0001-no-reversal-within-a-route.md
│       └── ...
├── layouts/                                ← the encoded railroads
└── scenarios/                              ← stock and request lists
```

Everything under `docs/` except `adr/` is spec prose, not glossary or decisions — read it for what the system does; read `CONTEXT.md` for what the words mean.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids — each entry lists its own _Avoid_ set (e.g. "connection", never "connector" or "node"; "transit", never "crossing"; "route" only for the request-level path).

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0001 (no reversal within a route) — but worth reopening because…_
