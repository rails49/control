# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. This is a **single-context** repo.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the canonical glossary (block, terminal block, connection, transit, train, request, route, lock, tick).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Top level is repo-wide; each app's implementation details sit in its own subfolder, named for the app package in `src/tc49/`.

```
/
├── CONTEXT.md                              ← the glossary
├── docs/
│   ├── GOALS.md                            ← assets and operations
│   ├── MILESTONE-1.md                      ← scope: what is built first, what is not
│   ├── SYSTEM.md                           ← the apps and the contracts between them
│   ├── ARCHITECTURE.md                     ← repo organization, app boundaries, tests
│   ├── adr/
│   │   ├── 0001-no-reversal-within-a-route.md
│   │   └── ...
│   ├── dispatcher/
│   │   ├── DISPATCH.md                     ← dispatch semantics, locking
│   │   ├── SAFETY.md                       ← the deadlock-freedom argument
│   │   └── INTERNALS.md                    ← state, the locking seam
│   ├── store/
│   │   └── LAYOUT.md                       ← layout and scenario file formats
│   └── bench/
│       ├── BENCHMARKS.md                   ← layouts, workloads, sweep axes
│       └── METRICS.md                      ← how each number is derived
├── layouts/                                ← the encoded railroads
└── scenarios/                              ← stock and request lists
```

Everything under `docs/` except `adr/` is spec prose, not glossary or decisions — read it for what the system does; read `CONTEXT.md` for what the words mean.

ADRs are **not** split by app: they are one numbered sequence in `docs/adr/`, and several of them decide contracts between apps rather than anything inside one.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids — each entry lists its own _Avoid_ set (e.g. "connection", never "connector" or "node"; "transit", never "crossing"; "route" only for the request-level path).

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0001 (no reversal within a route) — but worth reopening because…_
