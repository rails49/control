# The bus contract is the MQTT-safe intersection

Components communicate over a pub/sub bus whose contract promises only what
MQTT can also deliver — per-topic single-publisher FIFO, fan-out,
at-least-once with idempotent consumers, last-value state topics — and
refuses everything MQTT refuses: synchronous request/reply, delivery
confirmation, global or cross-topic ordering, replay for late subscribers,
unbounded queues. The milestone-1 bus is an in-process, single-threaded,
queued-FIFO scheduler that could trivially deliver every one of the refused
guarantees, and refuses them anyway.

The rejected alternative was to let the in-process implementation's actual
behavior be the contract and tighten later. Its failure mode points the
wrong way: every softening a component comes to rely on — a same-tick
reply, an ordering across topics, a synchronous admission answer — is
invisible in-process and becomes a latent bug the day MQTT arrives, exactly
when the system is hardest to debug. Refusing up front costs a little
awkwardness now (queries must go to the asset store's CRUD contract, which
exists for that) and buys a transport swap that changes no component.

The queued-FIFO delivery model is itself part of the milestone-1 binding,
not the contract: it is what makes delivery order a pure function of publish
and subscribe order, so the determinism property can be a byte compare.
See [SYSTEM.md](../SYSTEM.md#the-bus).
