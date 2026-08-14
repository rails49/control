# The layout interface owns time

The layout interface publishes the tick event (`tc49/layout/tick`, a
deterministic counter); the four app components only subscribe. The one tick
event is also the grant boundary: the scheduler releases due requests, the
dispatcher grants over the sensors buffered since the previous tick, and
reactions to tick `N` are handled at `N+1`. In milestone 1 the simulator
advances the tick when the bus is quiescent — loop-owner pacing, not a
contract promise — and a hardware adapter later picks its own cadence
behind the same event: the publisher swaps, the contract doesn't.

Two alternatives were rejected. A **separate boundary event** alongside the
tick — a tick-start/grant-now pair — buys tighter phase alignment only
because the milestone-1 loop owner can observe quiescence between the two, a
crutch MQTT cannot offer, and it reintroduces the same-tick-causality habit
the bus contract exists to break. **Harness-owned time** (the old "each
adapter owns the loop") dissolves instead of generalizing: with components
reacting to events there is no loop to own, only a time source, and placing
it anywhere but the layout boundary would give an app component a clock —
the thing "the dispatcher never reads a clock" exists to prevent.

The tick number rides in the payload because at-least-once delivery makes a
counted bare event double-advance on a duplicate; no other event carries a
tick field — the trace tap stamps. See [SYSTEM.md](../SYSTEM.md#time).
