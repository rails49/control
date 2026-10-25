# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. This is a **single-context** repo.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root — the canonical glossary (block, terminal block, connection, transit, train, request, route, lock).
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## What each doc holds

The organisation's
[ADR-0021](https://github.com/rails49/.github/blob/main/docs/adr/0021-each-fact-has-one-owner-and-the-glossary-is-glossary-md.md)
says what each kind of doc holds and that an accepted ADR does not change.
Where `docs/` files an app's pages: [ARCHITECTURE.md](../ARCHITECTURE.md#documentation-layout).

An issue that adds an ADR stating an invariant adds its function to `src/tc49/lib/invariants.py` ([ADR-0096](../adr/0096-invariants-are-stated-over-what-the-bus-shows-and-checked-in-tests.md)).

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids — each entry lists its own _Avoid_ set (e.g. "connection", never "connector" or "node"; "transit", never "crossing"; "route" only for the request-level path).

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0001 (no reversal within a route) — but worth reopening because…_
