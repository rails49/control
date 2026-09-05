# A request id is unique, not meaningful

**Amended under
[ADR-0059](0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
for [#437](https://github.com/rails49/control/issues/437):** the split below
is unchanged and has **moved inside the scheduler**. The panel no longer
mints anything — [ADR-0036](0036-the-scheduler-is-an-app-the-panel-is-a-view.md)
made the scheduler the one writer of requests and inherited both jobs into its
counter — so where the text below names the panel as the nonce-minter, read
the scheduler's gestures. A timetable keeps `<train>-N`, minted
deterministically in the file's order — for a person reading a trace against
the document they wrote, and for the unattended runs GOALS.md wants, rather
than for replay: **the harness does not take that path.** `bench/replay.py`
feeds a document's requests as drags, deliberately, so that no app is given a
scenario and every app keeps one placement path (#171, ADR-0030) — so a
replayed request is minted like any other gesture, `<train>-<nonce>-<n>` from
a nonce the scheduler process makes once at construction.

So byte-identical replay rests on two things, neither of them the timetable's
numbering. **Two runs of one document agree id for id** because the harness
**states** its nonce (`bench/runner.py`) instead of letting `secrets` mint
one, which costs nothing: the collision a nonce prevents needs a second
scheduler process, and a bench run is one from start to finish. **A run fed as
drags and the same run fed as a timetable** cannot agree on ids at all — one
shape carries a nonce and the other does not — so the test that compares those
two compares ids with the nonce taken out (`stable_ids`,
`tests/bench/test_replay.py`), the way it already drops the departure end a
gesture cannot state. Where the text below says the file scheduler's
determinism is what leaves replay untouched, read this. What forced the move is that
the scheduler and the dispatcher are separate processes now, so a supervisor
restarting the minter alone is ordinary: its counter starts at zero again
while the dispatcher still holds every id it has seen, and the next drag is
dropped at the top of admission and never answered — the failure below,
reproduced by a restart instead of a page reload. Nothing about
uniqueness-not-meaning changes.

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
