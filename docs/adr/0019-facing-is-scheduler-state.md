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

*(Amended for #145: "fully determined" was one case short. A train entering a
terminal block faces away from the end it came in through and there is no such
end, so the pass-through rule named a wall and every request the scheduler
then composed was rejected `unreachable`. Facing on a terminal block is its
one connected end, whatever the pass-through rule or the scenario says, and
the store refuses a placement declaring otherwise. This is a third rule for
what facing **is**, not a third event that changes it: nothing new happens on
the bus, and the dispatcher still learns nothing.)*

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

That last sentence is why facing cannot ride the dispatcher's retained
picture: a derived entry end is silent about a train that has never moved and
wrong after any reversal. The scheduler therefore publishes facing on its own
last-value topic, which keeps this ADR intact rather than amending it
([ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md)).

## Facing is a fact about the stock, not about the plan

*(Added for [#295](https://github.com/rails49/control/issues/295).)* The
scheduler once wrote facing twice: once when the dispatcher announced the route
it had committed to, from that route's departure end, and again when the first
move of the route was granted. The first of those was the plan and not the
train. Where a request departs the end its train already faces the two writes
agree and the eager one is redundant; where it departs the **other** end —
which a request may state, this ADR having made facing a discipline rather than
an invariant — the eager one records that the train turned around while nothing
touched it. Facing changes only by the geometry of a move the train actually
made, or by a deliberate reversal at rest. Choosing a route is neither, and the
scheduler no longer reads `route_chosen`.

What the move's geometry says now has two cases rather than one. A train that
left nose-first faces away from the end it entered through, as before. A train
that was **propelled** — pushed out of the end its nose points away from, which
is exactly the disagreement above — enters the next block tail-first, so its
nose points *at* the end it came in by. Which of the two happened is read
rather than remembered: for a move out of block `origin` over `transit`, the
train left nose-first exactly when `end_crossed(layout, origin, transit)` is
the end its facing points at. Routes are strict pass-throughs
([ADR-0001](0001-a-route-is-a-strict-pass-through.md)), so every move of one
route gets the same answer and nothing has to be carried between them.

Nothing on the bus changes, and the dispatcher still learns nothing: it keeps
its own record of the end the route it chose leaves a train facing, and resolves
a chained request against that. This mattered while facing fed an arrow on a
screen and matters more once `layout` reads the same value to decide which way
a locomotive's wheels turn — a wrong arrow is then a train driven backwards
down the track.
