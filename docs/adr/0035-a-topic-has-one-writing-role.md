# A topic has one writing role, not one writer

*(Amended under
[ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md):
"the dispatcher buffers sensor events to the grant boundary" below is gone —
a reading applies where it lands. The conclusion is unchanged and the ground
under it is now firmer: every grant is `safe()`-checked before it commits, so
arrival order picks among options that were all safe. Sensors were never the
case this rule is about in any event — the layout interface is one instance,
and the concurrent-instance role is the panel, whose gestures are independent
of one another.)*

Rule 1 of [SYSTEM.md](../SYSTEM.md#the-bus) said *exactly one component
publishes on any topic*. Read literally that forbids two browser tabs, which
are two components of one role, and it is the rule
[ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md) records
the panel breaking: two tabs on one session were two holders of facing and two
writers of `tc49/schedule/state/facing`.

The rule is restated:

> Exactly one **role** publishes on any topic. A role with concurrent
> instances may write an **event** topic, provided no consumer depends on
> ordering across instances. It may never write a **state** topic.

## What the rule buys, and which half is at stake

Two things, and only one of them is touched.

**Ownership by inspection is untouched.** Topics are publisher-first, so the
second segment names the writing role and the question "who may write here?"
is answered by reading the name. That stays exactly true with many instances:
`tc49/ui/#` is written by the `ui` role and by nothing else, and the broker ACL
that will enforce it after the relay is deleted is one line either way.

**Ordering across instances is given up, and nothing consumes it.** Per-topic
FIFO survives per instance — one panel's two gestures still arrive in order,
which is the only ordering an operator can perceive. Across instances there is
no order to promise and no reader to disappoint: the dispatcher buffers sensor
events to the grant boundary and applies its canonical order to the whole
buffered set, "never of delivery order"
([DISPATCH.md](../dispatcher/DISPATCH.md#time-model)), each gesture is
independent of every other, and the request id is minted by the app that
receives them rather than by the instances that send them
([ADR-0033](0033-a-request-id-is-unique-not-meaningful.md)).

Byte-identical replay is unaffected. A benchmark run has one instance of every
role and no browser at all.

## The state clause is the diagnosis

The last sentence of the rule is not a caveat, it is the whole finding. A state
topic is last-value-wins, so two instances of one role do not merely interleave:
they overwrite each other, and they do it exactly when one knows something the
other does not. That is the facing bug in one line, and the amended rule
forbids it on its face — where the original rule condemned the tab count and
therefore condemned the wrong thing.

So *the scheduler was in the browser* is not the disease. Multi-instance
**state** is. A role whose instances hold nothing cannot diverge, and
[ADR-0036](0036-the-scheduler-is-an-app-the-panel-is-a-view.md) is what makes
the panel such a role.

## Rejected

**A client level in the topic — `tc49/ui/<client>/request_wanted`.** This keeps
rule 1 literally true and costs, on the face of it, one segment. It was refused
because the segment has to be filled by a browser-minted nonce, which puts an
unbounded space of client-named topics in an inventory whose whole virtue is
that it is a table someone can read, turns the ACL from a line into a pattern,
and buys per-client ordering that the paragraph above shows nobody consumes.

**Reopening the namespaced ids of
[ADR-0016](0016-the-panel-is-a-scheduler.md).** It is not reopened. That
proposal partitioned one topic between two different *roles* by a convention in
the payload, which is precisely what defeats ownership by inspection. Here the
role count stays one and only the instance count moves, so the property that
rejection was protecting is the property this ADR leaves intact.
