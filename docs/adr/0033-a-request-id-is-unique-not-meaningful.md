# A request id is unique, not meaningful

A request id is an idempotency key and a correlation key. Both want one thing
from it — that no two requests share one — and neither reads it. It was
nevertheless specified by its *shape*, `<train>-1`, `<train>-2`, …, and that
shape acquired a third reader: the panel parsed the ordinal back out to
advance its own counter, because the counter lives in the page and a reload
starts it at one again.

That reader is where the shape stopped being decoration. A reloaded panel
re-mints an id the dispatcher has in its seen set, the duplicate is dropped at
the top of admission before any check runs, and no `request_admitted` and no
`request_rejected` ever comes back — the marker sits in "requested" for good.
Which is [#73](https://github.com/rails49/control/issues/73)'s own
reproduction: reload the panel, drag the train again.

**Uniqueness is the whole contract.** The file scheduler keeps `<train>-N`,
minted deterministically in scenario order, so byte-identical replay is
untouched. The panel mints `<train>-<page>-<n>`, unique by construction from a
per-page nonce. Nothing parses either, and the panel's catch-up parse is
deleted along with the collision it existed to prevent.

A nonce is not clock-derived, which is what
[SYSTEM.md](../SYSTEM.md#the-bus) forbids, but it is not deterministic either.
That costs nothing here: [ADR-0016](0016-the-panel-is-a-scheduler.md) makes
panel runs and file-scheduler runs mutually exclusive and says plainly that
panel runs make no reproducibility claim, "since a human clicking is not a
reproducible benchmark". Replay runs the file scheduler. The nonce reaches
only the runs that never claimed determinism.

Two alternatives were rejected.

**Have the dispatcher answer duplicates**, with a `duplicate` rejection reason,
so a collision is visible rather than silent. This inverts the reason the seen
set exists. The bus contract has an explicit at-least-once mindset — it may
duplicate, and consumers are idempotent — so a redelivered frame would produce
a `request_rejected` the first delivery did not, and a panel would paint a
rejection over a request that is running perfectly well. Idempotency that
answers is not idempotency.

**Have the scheduler retain a watermark**, a last-value map of train to highest
ordinal, read back on rejoin. It keeps one id shape everywhere and is
symmetric with the state topics
[ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md) adds —
and that ADR does retain facing this way, so the machinery is paid for either
way. It was still rejected: uniqueness by construction beats uniqueness by
remembering, and remembering fails where construction does not. Two browser
tabs on one session are two minters resuming from the same number, and every
id they mint collides.

The consequence worth recording is that the id is now **opaque to every
consumer**. A future minter — a freight generator, a timetable, a second
operator's page — needs agreement from nobody about its shape, only that what
it mints is its own. Readability in a trace is a courtesy the shapes above
happen to keep, not a promise anything may depend on.
