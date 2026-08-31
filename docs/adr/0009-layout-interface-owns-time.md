# The layout interface owns time

*(Amended under
[ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md):
the boundary event is gone, so owning time now means the run clock advances on
the events the layout interface publishes. No payload carries a timestamp; the
trace tap stamps each line with `time`. The decision itself — no app component
reads a clock — is unchanged.)*

*(Amended for #198: the boundary payload carries a second field, the
railroad's fast clock, minted by the same single writer so that no app has to
interpolate one — which is this page's rule, not an exception to it
([ADR-0044](0044-the-boundary-period-is-real-time-and-the-fast-clock-is-out-of-the-control-path.md)).)*

*(Amended for #118: the event is `tc49/layout/boundary` carrying a field
`boundary`, where this page first named it `tc49/layout/tick` carrying
`tick`. **Tick** stays the simulator's word for its own beat; the contract
every binding speaks is named for the boundary, per
[ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md). The
decision itself is unchanged.)*

The layout interface publishes the grant-boundary event
(`tc49/layout/boundary`, a deterministic counter); the four app components
only subscribe. That one event is also the grant boundary: the scheduler
releases due requests, the dispatcher grants over the sensors buffered since
the previous one, and reactions to boundary `N` are handled at `N+1`. In
milestone 1 the simulator advances it when the bus is quiescent — loop-owner
pacing, not a contract promise — and a hardware adapter later picks its own
cadence behind the same event: the publisher swaps, the contract doesn't.

Two alternatives were rejected. A **second event** alongside the boundary — a
beat-start/grant-now pair — buys tighter phase alignment only because the
milestone-1 loop owner can observe quiescence between the two, a crutch MQTT
cannot offer, and it reintroduces the same-boundary-causality habit the bus
contract exists to break. **Harness-owned time** (the old "each adapter owns
the loop") dissolves instead of generalizing: with components reacting to
events there is no loop to own, only a time source, and placing it anywhere
but the layout boundary would give an app component a clock — the thing "the
dispatcher never reads a clock" exists to prevent.

The boundary number rides in the payload because at-least-once delivery makes
a counted bare event double-advance on a duplicate. That argument is about
delivery and not about the simulator, which is why every binding numbers its
boundary. No other event carries a `boundary` field — the trace tap stamps.
See [SYSTEM.md](../SYSTEM.md#time).
