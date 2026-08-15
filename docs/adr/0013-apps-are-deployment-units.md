# Apps are deployment units

An app is a unit that will run as its own container. Today there are five —
`store`, `scheduler`, `dispatcher`, `driver`, `simulator` — and each gets one
package in `src/tc49/` and one folder in `docs/`. A UI is expected to join
them. Apps import `tc49.lib` and themselves, never each other; they meet only
over the event bus and the store's CRUD contract, which are the interfaces
[SYSTEM.md](../SYSTEM.md) fixes.

The criterion is deliberately about deployment, not about size or about being
a tidy grouping. It answers "is this a new app?" the same way every time,
including for things that do not exist yet, and it stops the folder list
drifting into a taxonomy of topics. The four bus roles plus the store were
already named as components with contracts in
[SYSTEM.md](../SYSTEM.md#component-footprints); this decision says the file
tree should say so too, and that nothing else earns a folder.

`lib` is not an app and neither is `bench`. **`SYSTEM.md` is the normative
definition of the contracts; `lib` is its Python binding.** A TypeScript UI
gets a sibling binding of the same spec, so nothing an app depends on is
defined only in Python, and the two bindings answer to the spec rather than to
each other. `bench` is the research harness: it assembles the apps on one bus
and is the only code permitted to import more than one of them.

The rule forces the two coarse document types of
[ADR-0010](0010-asset-store-serves-coarse-read-only-documents.md) into `lib`.
`Scenario` had lived in the store, which meant the scheduler, dispatcher and
simulator all imported the store app to read a document type. The store owns
the binding and the validator that produce documents; the types themselves are
shared vocabulary and belong beside `Layout`.

Rejected: keeping the store's types where they were and carving out an
exception to the import rule. The exception would have covered exactly the app
most likely to be containerized first, which is where the rule needs to hold
hardest.

The boundary is checked by a test rather than left to review, because it is
the kind of rule that decays silently. See
[ARCHITECTURE.md](../ARCHITECTURE.md).
