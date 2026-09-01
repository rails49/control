# The scheduler is an app, the panel is a view

The scheduler becomes an app in the sense of
[ADR-0013](0013-apps-are-deployment-units.md), running beside the dispatcher
rather than inside a page. It holds facing and mints request ids. The panel
stops being a scheduler and becomes a view that emits **gestures** on
`tc49/ui/request_wanted`:

```
tc49/ui/request_wanted   {"train": "ic5", "dest": ["claro_3.A", "claro_3.B"]}
```

That is a `request_submitted` minus the two fields the scheduler owns — no
`id`, because the scheduler is the single minter again, and no `depart`,
because facing is scheduler state
([ADR-0019](0019-facing-is-scheduler-state.md)) and the drag never named a
departure end anyway. The scheduler composes the request and publishes it; the
dispatcher judges it exactly as before.

This is the end state [GOALS.md](../GOALS.md) and
[ADR-0028](0028-the-scheduler-knows-where-trains-stand.md) already describe —
a timetable, a generator and a person are "three sources inside one scheduler,
not three publishers" — and it is
[ADR-0016](0016-the-panel-is-a-scheduler.md)'s rejected alternative bought.
0016 priced it at "a topic, a role, and an inbound path on a component that
currently has none, to buy something exclusivity gives later for free". The
invoice arrived: exclusivity gives one writer per *component*, and a browser
tab can be opened twice
([ADR-0035](0035-a-topic-has-one-writing-role.md)).

## The gesture rides the bus

Not HTTP, though the store already has an HTTP face and such a path would
survive the relay's deletion untouched. Three reasons, in order of weight.

**The trace is load-bearing.** The tap subscribes `tc49/#` and every metric
derives from recorded events. A gesture arriving over HTTP is invisible to it,
and "the events the trace records are the same events the components exchange"
would stop being true at the one place a person enters the system.

**The HTTP line is drawn at queries.** The store is a second contract because
it answers them and the bus refuses to
([ADR-0010](0010-asset-store-serves-coarse-read-only-documents.md)). A gesture
asks nothing: its answer is a `request_submitted` appearing on the bus, which
every view sees rather than only the tab that dragged.

**A synchronous answer is a liability.** With two operators a request's fate is
public, and the panel already renders the run's requests rather than its own.

The role is `ui` and not `panel` because [GOALS.md](../GOALS.md) has a person
driving as well as a person dispatching; a throttle is a second leaf under the
same role. The leaf keeps the name ADR-0016 coined and refused, so the reversal
reads as one.

## A gesture is not a request

A request is an order with an id, a departure end and a set of arrival ends
([CONTEXT.md](../../CONTEXT.md#dispatch)). A gesture has none of those. It names
a train and where to put it, and the scheduler turns it into a request — which
is why the panel's write surface can be authorized as a topic and still carry
none of the authority a request carries.

**What the scheduler cannot compose, it drops.** A non-dict payload, a missing
`train` or `dest`, a `dest` that is a string, a `train` it holds no facing for:
each is dropped, silently, and is a line in the trace by virtue of having been
published. This is
[ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)'s
own reasoning one component upstream — a gesture never carries an id, so every
uncomposable gesture is exactly the null-id case that ADR already answers by
dropping, and a `gesture_refused` topic would be broadcast and uncorrelatable,
which is the objection that ADR raised against a null-id rejection. **The
scheduler never raises on a bus payload**, on the same terms and for the same
reason as the dispatcher: after the relay is deleted, nothing stands in front
of it.

Silence is tolerable because the panel renders the roster from the run and
assets are a snapshot at startup, so the roster cannot change mid-session and
an honest panel cannot name a train the scheduler does not hold. What is left
is stale pages and buggy clients. A train that is not *idle* is a different
matter and is not dropped: the scheduler has its facing, so it composes and
submits, and the dispatcher answers `wrong_origin` or queues it. The scheduler
still judges nothing.

## Facing keeps its topic, and gains readers

ADR-0032 closed by predicting that a server-side scheduler "deletes this topic
when it lands". That is wrong, and correcting it is part of this decision.
`tc49/schedule/state/facing` is not state only its writer reads: the panel
**renders** facing as the direction arrow on a block, and a train that has
never moved has no other source for one. What lands here is not a deletion but
a promotion — from a topic a page published to itself, to an ordinary state
topic with one writing role and every view reading it.

**Holding facing requires the layout.** `move_granted` carries
`(id, train, transit, into, aspect)` and not the end the train entered through,
so "a train faces away from the end it entered through" is not computable from
the event alone; it needs to know which ends the transit joins. The scheduler
therefore reads the layout and subscribes `tc49/dispatch/#`, which is
[ADR-0028](0028-the-scheduler-knows-where-trains-stand.md)'s growth spent early
— for facing rather than for a generator. A request whose `depart` contradicts
facing is legal, ADR-0019 having made facing a scheduler discipline rather than
a system invariant; the grant is still where the scheduler reads it, since such
a request is a train **propelled**, and the move that lands it is what says so.

*(Amended for [#295](https://github.com/rails49/control/issues/295): the
scheduler also followed `route_chosen`, taking a committed route's departure
end as the train's facing. That wrote the plan rather than the train, and said
a train departing against facing had turned around while nothing touched it.
It no longer reads that leaf, and `move_granted` is the whole of what moves an
arrow.)*

Adding an `entry` field to `move_granted` instead was rejected: it puts a field
on the dispatcher's busiest event for one consumer's benefit, against the
payload convention that an event carries only what is new.

## Consequences

**Exclusivity dissolves into a session's source list.** ADR-0016 made "the file
scheduler or the panel, never both" a rule because two schedulers meant two
writers and two minters. With one scheduler app that reason is gone, and which
sources a session has becomes configuration. `tc49 live` keeps the timetable
off for now: a scenario's `at` is still a tick number, so releasing it into a
two-second wall clock would dump a timetable on an operator in the first
minute. That is worth turning on once `at` is a fast-clock time
([#118](https://github.com/rails49/control/issues/118)), and it is then a flag
rather than a redesign.

**One id counter, undivided.** Per-source counters would keep a timetable's ids
stable against an operator's gestures, and were rejected: an id that tells you
who minted it is a shape, and ADR-0033 says no consumer reads the shape. The
determinism it would protect cannot be lost — a benchmark run wires no bridge
and receives no gestures.

**The page keeps no scheduler state.** The per-page id nonce of ADR-0033 and
the scenario-seeded placement of ADR-0032 are both deleted: placement comes
from `tc49/dispatch/state/allocation`, facing from `tc49/schedule/state/facing`,
and both are retained by apps that are always running, so the cold-start branch
in the panel has no case left to serve. The panel still reads the scenario for
one thing — which drawing to render — because nothing retained says which
railroad a session runs, and inventing a topic that does would be the bridge
describing the run, which
[#67](https://github.com/rails49/control/issues/67) refused.

**The browser loses the schedule role.** The relay's one inbound topic becomes
`tc49/ui/request_wanted`, and `tc49/schedule/request_submitted` is refused
inbound like any other. The single-minter claim stops being an intention and
becomes something the topic check enforces.

Deliberate reversal at rest — the other gesture that changes facing, parked by
ADR-0019 — is left to its own issue. The plumbing is now trivial; the gesture
is not, since the drag vocabulary has already spent the obvious motion on
cancelling.
