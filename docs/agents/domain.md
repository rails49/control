# Domain docs

How the skills use a repository's domain docs is the organisation's
[domain.md](https://github.com/rails49/.github/blob/main/docs/agents/domain.md). This file holds what control adds.

- Each `GLOSSARY.md` entry lists its own _Avoid_ set: "connection", never
  "connector" or "node"; "transit", never "crossing"; "route" only for the
  request-level path.
- Where `docs/` files an app's pages:
  [ARCHITECTURE.md](../ARCHITECTURE.md#documentation-layout).
- An issue that adds an ADR stating an invariant adds its function to
  `src/tc49/lib/invariants.py`
  ([ADR-0096](../adr/0096-invariants-are-stated-over-what-the-bus-shows-and-checked-in-tests.md)).
