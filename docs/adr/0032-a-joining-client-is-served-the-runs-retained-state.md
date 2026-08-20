# A joining client is served the run's retained state

**Corrected in part by
[ADR-0036](0036-the-scheduler-is-an-app-the-panel-is-a-view.md).** The last
paragraph below predicts that a server-side scheduler deletes
`tc49/schedule/state/facing`. It does not: the panel *renders* facing as a
block's direction arrow, so the topic has readers that are not its writer, and
what the move changes is that its single writer is now an app rather than
whichever tab was open. Everything else stands, including the reading of the
two-tab problem as a single-writer violation — 0035 restates the rule so that
it names multi-instance *state* rather than the tab count.

A browser that connects to a running session sees nothing until the next event
moves. Event topics are never replayed
([ADR-0008](0008-bus-contract-is-the-mqtt-safe-intersection.md)), so a panel
joining an idle railroad — the normal state when an operator walks up to it —
cannot draw the locks, the committed routes or the trains, because all of that
arrived as events before it connected. The panel worked around this by seeding
placement from the scenario document, which says where the railroad *started*
and is wrong the moment anything has run. That staleness is what
[ADR-0021](0021-a-bad-request-is-answered-not-raised.md) had to answer with
`wrong_origin`.

**The dispatcher publishes its picture as a state topic**,
`tc49/dispatch/state/allocation`: where each train stands, what is locked and
to whom, the committed routes, and the live requests. It is serialized from
the lock table when any of it changes, exactly as
`tc49/dispatch/state/aspects` already is
([ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)) — a
projection published beside its source, not a second copy maintained in
parallel. Live requests are in it because the panel renders a committed route
from the request that owns it, so a snapshot without them draws no routes.

**The bridge forwards retained last-values to a client on connect.** This is
not the bridge describing the run, which [#67](https://github.com/rails49/control/issues/67)
refused and this ADR does not reopen. It is the bridge ceasing to be *weaker*
than the contract it binds: the bus promises that a state topic delivers its
latest value to a late subscriber, a real broker delivers retained messages to
a client the moment it subscribes, and the relay today drops them because it
subscribed once at construction and holds no backlog. A browser speaking
MQTT-over-WebSocket to the broker would get them. The relay still adds no
topics and no payload fields; it forwards frames it would have forwarded had
the client been there.

**Facing is retained by the scheduler**, on `tc49/schedule/state/facing`.
[ADR-0019](0019-facing-is-scheduler-state.md) stands untouched: facing is
scheduler state, the dispatcher never learns it exists, and the scheduler
writes its own topic under the single-writer rule. The scenario still declares
initial facing at placement, now only for a cold start with no retained value.

Putting facing in the dispatcher's snapshot was rejected. The dispatcher could
derive an entry end from routes it granted, but that is silent about a train
that has never moved and wrong after a reversal at rest — the one gesture
ADR-0019 says changes facing outside a route and stays invisible to the
dispatcher. Carrying it anyway would not amend that ADR at the edges; it would
delete it.

**Rejoining is not recovery.** Three failures look alike and are not. A client
reconnecting has lost nothing — the dispatcher is running and holds the truth,
and that is the one this ADR addresses. A restart loses the lock table while
the rails stay as they were. A power cut on the layout loses it too and makes
what was believed *suspect*, because a stalled locomotive gets lifted out of
the tunnel by hand; sensors are anonymous, so that one ends with a person
confirming placement whatever is persisted. Continuous persistence is worth
having for the second and third. It is not what a reloaded page needs, and
making the page wait for it would buy a dependency on a durable store to solve
a problem the running dispatcher can already answer.

The scheduler writing a topic only it reads is the price of the panel being a
scheduler in the browser ([ADR-0016](0016-the-panel-is-a-scheduler.md)). Two
tabs on one session are two schedulers, two holders of facing and two writers
of that topic, which is a single-writer violation the retained value makes
visible rather than causes. The scheduler as a server-side app is what
[ADR-0028](0028-the-scheduler-knows-where-trains-stand.md) and
[GOALS.md](../GOALS.md) already describe, and it deletes this topic when it
lands. Until then facing has no other holder.
