# Facing is scheduler state, not dispatcher state

Drag scheduling on the [panel](../ui/PANEL.md) names a train and a destination;
the departure end of the resulting request has to come from somewhere. It comes
from **facing** ([CONTEXT.md](../../CONTEXT.md#stock)): the end of its block a
parked train would leave through nose-first, declared in the scenario at
placement and thereafter fully determined, since routes are strict
pass-throughs — a train faces away from the end it entered through. The
panel-scheduler holds that state and submits `depart` accordingly. The
dispatcher never learns facing exists: requests carry `depart` exactly as
before, and no bus payload changes.

The alternative was dispatcher-enforced facing — reject a request whose
departure end contradicts which way the train stands. The dispatcher could
maintain it (it chooses the routes facing is derived from), but doing so adds
per-train stock state to a component that deliberately knows nothing about
stock beyond lengths, to enforce a constraint the submitter can enforce for
free. Under [ADR-0016](0016-the-panel-is-a-scheduler.md) there is exactly one
submitter per run, and it is the component that already knows the facing.

The consequence worth recording is the deliberate no: **facing is a scheduler
discipline, not a system invariant.** The dispatcher will happily route a
train out its tail end if a scheduler asks — file scenarios keep that freedom,
and nothing on the bus can tell the difference. This complements
[ADR-0007](0007-requests-name-a-set-of-arrival-ends.md), which made how a
train *finishes* expressible in the request; facing settles how it *starts*,
one level up, in the scheduler that composes the request. Deliberate reversal
at rest — the one event that changes facing outside a route — is a future
scheduler gesture, again invisible to the dispatcher.
