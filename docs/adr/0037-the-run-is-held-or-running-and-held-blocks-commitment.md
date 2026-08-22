# The run is held or running, and held blocks commitment

A run has a state of its own, `tc49/dispatch/state/run`, retained and written
by the dispatcher — one writing role, like every other topic
([ADR-0035](0035-a-topic-has-one-writing-role.md)). Two values today, `held`
and `running`. A person moves it with `tc49/ui/run_wanted`, and while it is
`held` the dispatcher commits nothing: no route is chosen, no move granted,
no lock taken.

The bar it was built for is @iot49's: *"after power up, no trains should move
without operator intervention."* Nothing enforced it, and there was no gesture
with which a person could correct a placement either — the write surface was
`tc49/ui/request_wanted` and nothing else.

A **word and not a boolean**, because the ordinary-shutdown drain will add
`draining` as a third value here rather than inventing a state of its own
([#123](https://github.com/rails49/control/issues/123)). Not a
recovery-only flag: it is the run's general condition, and every view reads
it.

## A brake, not an emergency stop

The hold stops the dispatcher granting. It does **not** stop a move already
granted: at the moment of a hold a train can have an outstanding move, its
connection already aligned and `tc49/drive/cross` already sent, and nothing on
the bus can retract that. The driver is stateless and `tc49/drive/` carries
only `cross`.

So the buffered sensors are still applied at every boundary, held or not. An
outstanding move completes and releases its locks; a train that arrived does
not hold the block behind it for as long as the operator stands there.

The guarantee asked for lives one layer down. The hardware has a command to
turn track power on, and until it is given nothing moves whatever the software
believes: restoring power puts the driver in an idle state with power off.
That command is not this decision, and it is what makes a cold session coming
up `running` positively safe rather than merely tolerated — the rails are dead
until a person switches them on. What the hold adds is that the dispatcher
will not grant into a track that has come back live.

[#123](https://github.com/rails49/control/issues/123) called the drain and a
stop-everything button "the same primitive". The brake is shared; an emergency
stop is more, and it is not here.

## Held blocks commitment, not admission

Requests are accepted and queue up while held. `request_admitted` is still
published, and nothing on the rails can move whatever a scheduler is minting.
Nobody accrues refusals while held either — no launch is attempted — so the
aging key stays admission order and the queue drains in the order it
accumulated ([ADR-0012](0012-the-pending-scan-ages-by-refusal-count.md)).

This is deliberate and not an oversight. A timetable feeding a held run is a
railroad being loaded before it is started, and a person queuing work against
one at rest is watching it leave when they release it.

Blocking admission instead would also take a lock on the strength of a
placement nobody has confirmed, which is the very thing the hold exists to
prevent.

## Releasing only clears the flag

The next `tc49/layout/boundary` runs an ordinary grant phase. Granting from
the gesture handler would make the boundary no longer the sole trigger, and
would grant against a sensor buffer filled over part of a period — the one
thing the time model rules out
([ADR-0009](0009-layout-interface-owns-time.md),
[DISPATCH.md](../dispatcher/DISPATCH.md#time-model)).

The cost is up to one period between GO and the first wheel turning, against a
panel that says *running* the moment you press. That is the right trade: a
boundary is the dispatcher's whole notion of when, and a second entry point
into granting would be a second one.

## A held run puts every signal to stop

The same decision seen from the driver's end. An aspect answers "may the train
in this block leave via this end"
([ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)), and
while held the answer is no, at every end.

Leaving them alone would show `clear` over a railroad that is going nowhere,
and on the physical layout would leave lineside signals green over dead track
— which is exactly the audience ADR-0025 named as not being the automated
driver. Both transitions republish the topic.

This **qualifies ADR-0025 rather than superseding it.** The depth of the locks
ahead still decides which of the other two aspects shows; the hold is a gate
over the reading, so nothing about the locks has to be undone and put back.

## One gesture, one authority

`tc49/ui/placement_wanted` names a train and a block: where it actually
stands, said by the person who can see it. The **dispatcher alone** reads it,
and having accepted it publishes `tc49/dispatch/train_placed`, a past-tense
fact like every other dispatcher leaf. The scheduler follows that event and
never the gesture.

Two apps reading one payload would have to agree on every precondition, and
"is that block free" is knowledge only the dispatcher has. The picture would
split exactly where a real operator is working.

It is accepted only when the run is held, the train is known, the block exists
and is **free of every claim**, the train fits it, and the train has **no
request in flight**.

*Free* means both claims a route carries, not only the stronger one. A
resource is **committed** when it is on a route the dispatcher has chosen and
has not locked yet ([CONTEXT.md](../../CONTEXT.md#dispatch)), and that is a
claim. Under `FullRoute` the two sets coincide, a launch locking the whole
route; under `Incremental` a fixed route runs on ahead of its locks, and
reading the lock table alone would call those blocks free. Placing a train
into one strands the working that owns it — the route is fixed
([ADR-0002](0002-fixed-route-per-request.md)), the placed train is idle and
its standing lock is therefore a permanent obstacle
([SAFETY.md](../dispatcher/SAFETY.md)), and nothing cancels a request, so the
committed train is refused for the rest of the session. So the check reads the
committed routes and not just the lock table.
The last mirrors `tc49/ui/reversal_wanted` and adds a worse reason of its own:
on release the grant phase launches from the block the dispatcher believes the
train is in, so a pending request would silently depart from wherever the train
was just put, having been admitted against the old block. Anything else is
dropped in silence and to the trace — a gesture carries no id to address an
answer to
([ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

`train_placed` is the **ledger line for a placement**, in place of a
`lock_released` and a `lock_granted`. Those two would say a route gave a block
up and took another, which is not what happened: a hand lifted a locomotive.
The fact has its own leaf so a reader can tell the two apart.

**Facing is not part of placing.** The gesture names a train and a block; the
scheduler carries the end letter over, so `up_e.A` becomes `yard_w.A`. That is
arbitrary, because the layout is topological and there is nothing better to
derive from, and `tc49/ui/reversal_wanted` is already the correction. It keeps
the dispatcher clear of facing altogether
([ADR-0019](0019-facing-is-scheduler-state.md)), and it is the shape the
roster drag wants anyway
([ADR-0039](0039-a-train-may-be-off-the-layout.md)): a train dragged onto a
free block lands facing some way, and the operator turns it if it is wrong.

**Placement is resolved a train at a time**, not by editing a saved file.

**A placement clears whatever the train was crossing.** The crossing mark is
restored across a restart with no route behind it, as a placement hint
([#123](https://github.com/rails49/control/issues/123)) — which makes such a
train exactly the one a person has to say something about. Once they have, it
is standing in a block and crossing nothing, and the picture says so. Leaving
the hint would carry it out to every view and persist it again, and there is
no way to clear it by hand: affirming the block the dispatcher already
believes in is not accepted, that block not being free.

## Consequences

**Every session comes up running**, and states so from the dispatcher's
constructor as `state/allocation` already does: a joining client is served the
word rather than left to read one out of an absence
([ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md)). The
retained value is not adopted across a restart — the rails are dead until a
person switches them on, so there is nothing for a remembered `held` to
protect, and a run that came back up refusing to grant with no one at the
panel would be a fault that looks like a hang.

**The simulator is told when a hand moves a train.** It stands in for steel
that would simply be where it was left, so `train_placed` moves its placement
too; without it the next `cross` would vacate the block the train used to be
in. That stays inside the simulator app and on no topic of its own
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)).

**Nothing cancels a request**, and this decision gives that a sharp edge: hold
mid-run with a committed route standing and that train cannot be repositioned
until you release and let it finish. Named rather than solved.

**Taking a train off the layout is a separate decision**, bought by
[ADR-0039](0039-a-train-may-be-off-the-layout.md): the gesture here always
names a block, and a placement that said a train was gone is removal.
