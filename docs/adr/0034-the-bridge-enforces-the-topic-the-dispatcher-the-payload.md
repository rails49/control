# The bridge enforces the topic, the dispatcher the payload

**Extended by
[ADR-0036](0036-the-scheduler-is-an-app-the-panel-is-a-view.md).** The line
below is unchanged and now falls one component further upstream: the browser's
one inbound topic is `tc49/ui/request_wanted`, so the **scheduler** is the
first app to touch a frame a browser wrote, and it never raises on a bus
payload either. A gesture carries no id at all, which makes every unreadable
one the null-id case this ADR already answers by dropping it to the trace.

[ADR-0021](0021-a-bad-request-is-answered-not-raised.md) made a *readable* bad
request an answer rather than a crash, and left the rest open: a payload the
dispatcher cannot read at all still raised out of a bus handler and still ended
the run. Whether that belonged to the bridge or to admission was named there as
a separate contract change. This is it.

Every one of these ends a live session today, because the bridge publishes the
client payload with no shape check: a `train` the session does not have, a
`dest` naming a block the layout does not have, a missing `depart`, a `dest`
that is a string rather than a list of ends. The first needs no malice — the
panel is told nothing about which scenario the session runs, so an operator can
open a drawing whose trains it does not have, drag one, and stop the railroad.

**The bridge checks the topic. The dispatcher checks the payload.** That line
is drawn by what survives the migration. The bridge is scaffolding: when the
bus becomes a real broker the browser speaks MQTT-over-WebSocket to it and
`lib/bridge.py` is deleted. Refusing an inbound frame on a topic that is not
`request_submitted` survives that deletion, because topic authorization is
exactly what a broker enforces with an ACL. Payload validation does not survive
it: a broker carries any JSON published to a topic the client may write. So
anything taught to the bridge about payloads would have to be rebuilt in the
dispatcher on migration day, and until then would hide the fact that the
dispatcher is unprotected.

The dispatcher therefore **never raises on a payload from the bus**. Admission
grows two referential reasons alongside `no_fit`, `no_entry`, `unreachable` and
`wrong_origin` — `unknown_train` and `unknown_block`, both facts only the
dispatcher holds — and one structural reason, `malformed`, for a payload that
carries a readable id and is not otherwise a request.

**A payload with no readable id is dropped.** Every rejection is addressed by
id; the panel looks the request up by it. A frame with no id has nothing to
address an answer to, and it is already a JSONL line in the trace by virtue of
having been published, since the tap subscribes `tc49/#` — so dropping it is
not losing it, and a client bug stays diagnosable. Publishing
`request_rejected` with a null id was rejected: it is uncorrelatable by
construction and it is *broadcast*, so the moment there are two operators every
panel is shown a rejection none of them can attribute.

Validating at the bridge instead was rejected on the migration argument above,
and on [#67](https://github.com/rails49/control/issues/67)'s: knowing that a
train is not in this session is knowledge about the run, and a bridge holding
the roster is a second authority beside the dispatcher. Splitting the two —
structure at the bridge, reference at admission — was rejected for the same
reason in half measure: it buys a tidier reason set at admission and leaves the
structural half with no home after the bridge is gone.

[ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md) shrinks
what is left. Once a joining panel learns the roster from the run's retained
state rather than from an operator-picked scenario, `unknown_train` stops being
reachable by an honest operator. What remains is stale pages, races and buggy
clients — which is the population these reasons are for.
