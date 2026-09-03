# The run is held or running, and held blocks commitment

A run has a state of its own, `tc49/dispatch/state/run`, retained and written
by the dispatcher — one writing role, like every other topic
([ADR-0035](0035-a-topic-has-one-writing-role.md)). Two values today, `held`
and `running`. A person moves it with `tc49/ui/run_wanted`, and while it is
`held` the dispatcher commits nothing: no route is chosen, no move granted,
no lock taken.

**Amended under
[ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md):**
"Releasing only clears the flag" below no longer holds. The boundary is gone,
so there is no beat for a release to wait for: releasing runs a sweep, and the
first wheel turns with the press. The argument that section makes against it —
that granting from the gesture handler adds a second entry point into granting
— is answered rather than overridden: a sweep is *the* entry point, run
wherever the lock table or the waiting set changes, and a release is one of
those changes. The decision this ADR records, that `held` commits nothing, is
untouched.

**Amended under
[ADR-0049](0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md):**
`placement_wanted`'s third precondition, that the train have no request in
flight, is gone. The gesture cancels the request and then places the train, so
"nothing cancels a request" below — and the sharp edge it gives that fact,
that a train under a committed route cannot be repositioned until you release
and let it finish — no longer holds. The other two preconditions, the held run
and the known train, stand, as does everything else this ADR decides.

**Amended for
[#242](https://github.com/rails49/control/issues/242):** a field whose values
are a closed set is an **enum**; this ADR calls it a *word*, the term
`CONTEXT.md` used until #242. Nothing below has been rewritten, so read *word*
as *enum* throughout.

**Amended for
[#294](https://github.com/rails49/control/issues/294):** "Two values today"
is three: `held`, `running` and `draining`. The drain the enum was kept open
for has landed, and it commits more than a hold and less than a release — it
admits, it goes on granting a train already moving, and it launches nothing,
ending when the dispatcher writes `held` itself. It is what
[ADR-0051](0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)'s
OFF asks for and waits on before it commands power off, that ADR having left
the value itself to this issue. The section *The drain is the third value*
below carries the three side by side. The name of this decision stands: the
run is still held or running when it is not draining, and `held` still blocks
commitment.

The bar it was built for is @iot49's: *"after power up, no trains should move
without operator intervention."* Nothing enforced it, and there was no gesture
with which a person could correct a placement either — the write surface was
`tc49/ui/request_wanted` and nothing else.

A **word and not a boolean**, because the ordinary-shutdown drain will add
`draining` as a third value here rather than inventing a state of its own
([#123](https://github.com/rails49/control/issues/123)). Not a
recovery-only flag: it is the run's general condition, and every view reads
it.

## The drain is the third value

`draining` is the ordinary way to turn a railroad off
([#294](https://github.com/rails49/control/issues/294)). An abrupt cut leaves
no point position trustworthy and can strand a train mid-transit; the drain is
what a person presses instead, and it gates **launching** rather than
admission:

| value | admits | launches | grants to a train already moving |
| --- | --- | --- | --- |
| `running` | yes | yes | yes |
| `draining` | yes | no | yes |
| `held` | yes | no | no |

This corrects #123's *"stop admitting"*: admission is cheap and reversible —
it takes no lock and moves no wheel — where launching is the commitment. The
queue therefore accumulates through a drain exactly as it does through a hold,
accruing no refusals, and a drain turned back releases into the order it
accumulated (ADR-0012).

**The dispatcher writes `held` itself** at the first moment no train is active
and none is crossing, and that transition is the drain's completion. It is
what the panel watches for before it publishes `power_wanted: off`
([ADR-0051](0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)),
so it has to be a value on the topic and not something a client infers from an
empty picture: after a completed drain nothing is crossing, nothing is
committed and every grant re-aligns, which is what makes the point positions
the cut loses cost nothing. A drain over a railroad with nothing under way
completes in the press that asked for it, a wait that could never end being
worse than no wait at all.

**Manual trains count by the same rule.** Every train moves only on a route
the dispatcher allocated with signals set to allow it, and *manual* names only
who turns the throttle, so the drain needs no notion of mode and none leaks in
([#207](https://github.com/rails49/control/issues/207)).

**A held run puts every signal to stop; a draining one does not.** The answer
to "may the train in this block leave via this end" is yes for the train the
drain is still granting, and a lineside signal at stop over a train that has
just been told to go is the same lie the hold refuses to tell, the other way
about.

`held` published while a drain is in progress **abandons** it, immediately and
without waiting for a train to finish: the hold asks for less than the drain
does, and a person who wants the railroad still now does not wait out a route.
`stopped` power is always honoured and is not a drain — it holds the run by
the path power always takes (ADR-0041) — and a `run_wanted` of `draining` is
dropped while the power is anything but `on`, for the reason a release is: a
drain grants the trains already under way, so over dead rails it asks for what
a release asks for.

A drain that a **wedged** train holds open forever — one whose outstanding
move no sensor will ever answer — is escaped by holding the run and taking
that train off the layout, which drops the request it was running
([ADR-0049](0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md),
[#237](https://github.com/rails49/control/issues/237)). The placement's
preconditions are untouched by the drain: a placement is judged against a
railroad that is standing still, and a draining one is not. A `cancel_wanted`
needs no held run and ends a drain wherever the request it retires was not
mid-move.

## A brake, not an emergency stop

The hold stops the dispatcher granting. It does **not** stop a move already
granted: at the moment of a hold a train can have an outstanding move, its
connection already aligned and `tc49/drive/move` already sent, and nothing on
the bus can retract that. The driver is stateless and `tc49/drive/` carries
only `move`.

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

[ADR-0039](0039-a-train-may-be-off-the-layout.md) later gave the gesture its
other direction: `block: null` takes the train **off the layout**, answered
by `train_removed`. Everything below holds for both.

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

**A run comes up held unless its own document stood its trains on the rails**,
and either way the constructor states it as `state/allocation` already does: a
joining client is served the word rather than left to read one out of an
absence
([ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md)).

A start whose document places every train has nothing for a hold to protect:
the rails are dead until a person switches them on, and a run that came up
refusing to grant with no one at the panel would be a fault that looks like a
hang. That start is the harness's — `tc49 bench` and `tc49 sweep`, built from
a scenario file
([#171](https://github.com/rails49/control/issues/171)) — and it is the one
this decision was written against, when it read "a cold session comes up
running".

A **restored** session is the hold's own case
([#154](https://github.com/rails49/control/issues/154)): the picture it
adopted says where the last session *believed* the railroad was, and the steel
has stood there unwatched since, long enough for a stalled train to have been
lifted out of a tunnel by hand
([CONTEXT.md](../../CONTEXT.md#interruptions)). Coming up running on the
strength of a picture nobody has looked at is the failure this decision exists
to prevent.

A cold session with an **empty layout** comes up held too
([ADR-0039](0039-a-train-may-be-off-the-layout.md)), and for a plainer reason
than either: a placement is honoured while held and dropped while running, so
a run that opened running would refuse the first gesture an operator makes on
it, and an empty layout has nothing else to offer them. That is every run an
operator starts, once a run is built from a railroad rather than from a
scenario (#171) — the hold is what lets them lay the railroad out.

The **retained word is not what decides it.** The file keeps every state
topic's last value, `state/run` among them
([#151](https://github.com/rails49/control/issues/151)), so a session cut
while running finds `running` waiting for it, and adoption overrides it.
Neither does it turn on whether the picture was in the end *taken*: where it
contradicts the scenario the document wins the placement whole, and the rails
do not go back to the document with it.

**The simulator is told when a hand moves a train.** It stands in for steel
that would simply be where it was left, so `train_placed` moves its placement
too; without it the next `move` would vacate the block the train used to be
in. That stays inside the simulator app and on no topic of its own
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)).

**Nothing cancels a request**, and this decision gives that a sharp edge: hold
mid-run with a committed route standing and that train cannot be repositioned
until you release and let it finish. Named rather than solved.

**Taking a train off the layout is a separate decision**, bought by
[ADR-0039](0039-a-train-may-be-off-the-layout.md): the gesture here always
names a block, and a placement that said a train was gone is removal.
