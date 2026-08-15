# Python for the apps, TypeScript for the UI

The five apps stay Python. The UI, when it arrives, is TypeScript. The two meet
as language bindings of the contracts [SYSTEM.md](../SYSTEM.md) fixes
([ADR-0013](0013-apps-are-deployment-units.md)).

Python keeps the apps for three reasons. Hypothesis carries the
deadlock-freedom properties of [SAFETY.md](../dispatcher/SAFETY.md) in
`tests/system/test_properties.py`, and is stronger at stateful generation and
shrinking than its TypeScript counterparts. The sweep of
[BENCHMARKS.md](../bench/BENCHMARKS.md) emits JSONL for later analysis, which
the Python notebook ecosystem serves better. And the apps already exist: about
2,000 lines under `pyright` strict with 2,400 lines of tests, so a rewrite
buys no feature.

Rejected: TypeScript everywhere. Its attraction was a typed bus, where a
discriminated union on topic makes an illegal payload unrepresentable. That is
an argument about schemas rather than languages. Python types nothing at the
boundary today (`lib/bus.py` declares `Payload = dict[str, Any]`, and the
store takes `dict[str, Any]`), but a schema types the boundary in both
languages, and also survives MQTT and a REST store.

The cost is field-level payload schemas, generated into each language rather
than written twice. The event inventory of [SYSTEM.md](../SYSTEM.md#event-inventory)
already defers those "until a second consumer exists", and a TypeScript UI is
that second consumer, so this decision calls the cost in rather than adding it.

One consequence for ADR-0013: sibling bindings "answer to the spec rather than
to each other" holds by itself for a milestone binding, where only one exists,
but needs a mechanism for a language binding, where several do. The schema is
that mechanism.
