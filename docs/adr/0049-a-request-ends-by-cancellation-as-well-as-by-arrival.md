# A request ends by cancellation as well as by arrival

Resolves [#244](https://github.com/rails49/control/issues/244);
[#271](https://github.com/rails49/control/issues/271) executes it. It
supersedes [#237](https://github.com/rails49/control/issues/237), whose case
is one of the three reasons below.

A request ends by **arrival**, by **rejection** before admission, or by
**cancellation**. The third did not exist. Everything the dispatcher holds for
a train — its route, its locks, its place in the queue — was reachable only by
running the train to where the request said it was going.

On the layout that is the wrong answer to an ordinary evening. A locomotive
stalls on a dirty rail, a coupling drops a cut of cars, somebody changes their
mind about where a train should go. The person walks over, picks the
locomotive up or pushes it clear, and the railroad has to be told. Until this
decision the only thing that could tell it was a session restart: the train
went on holding every block of a route it would never run, and every train
waiting on those blocks waited with it
([ADR-0040](0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md),
*safe but wedged*).

## The gesture names a train

`tc49/dispatch/cancel_wanted` carries `train` and nothing else. It is
browser-writable, like the four gestures beside it, and it is read by the
dispatcher alone.

**Not by request id.** A person looks at a train, not at an id: the id is the
scheduler's mint and the dispatcher's correlation key, and it appears on a
page only as something to display
([ADR-0033](0033-a-request-id-is-unique-not-meaningful.md)). A gesture that
had to carry one would make the panel keep a request table in order to end a
request, and it would still have to answer what happens when the id names
work that has already finished. Naming the train asks the question the person
is actually asking, and the dispatcher already knows which request that is.

So it ends **everything that train has**: the active request and every one
still queued behind it. A train's chained requests run in order and from each
other's arrival blocks, so leaving one queued behind a cancelled predecessor
would run it from an origin the cancellation just unfixed.

A train with nothing in flight is **dropped**, in silence and to the trace,
exactly as an unknown train is. The gesture carries no id, so there is nothing
to address an answer to
([ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

**It needs no held run.** Cancelling ends one train's work; requiring the hold
first would stop every other train on the railroad to let one go, and the
person cancelling is usually standing beside a train that has already stopped.
The hold is a brake on new commitment
([ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md)),
and this is not a new commitment.

The answer is `tc49/dispatch/request_cancelled`, `{id, reason}`, with the
reason from a set of three: `revoked`, `removed`, `displaced`. The scheduler,
the metrics and the panel all read it, so the names live in one place
(`tc49.lib.cancellation`) exactly as the rejection reasons do.

## One release path

A cancelled request gives up **every resource its train holds except the block
it stands in**, as one `lock_released`.

The exception is not an optimisation. Every parked train holds the lock on the
block it stands in — that standing lock is what keeps the next train out of an
occupied block ([SAFETY.md](../dispatcher/SAFETY.md)) — so releasing it would
leave a locomotive in a block the dispatcher believes free. What goes is
everything the request took beyond it: under `FullRoute` a launch locks
`crossing_order()`, every transit and every block to the end of the route, and
those are the blocks the wedge was made of.

The sweep runs where the lock table moves
([ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)),
so what a cancellation frees is offered to whoever was refused for it, on the
spot.

`_seen_ids` is **not pruned**. A cancelled id stays used for the session: an
id is unique and not meaningful, and a resubmission of one is the duplicate it
looks like (ADR-0033).

## A move already sent cannot be taken back

Nothing on the bus retracts a `move`. The layout interface is executing it,
the train is between two blocks, and there is no command that stops a
locomotive — `move` has no speed field, `tc49/layout/state/power` is read-only,
and the emergency stop is a hardwired contact. Adding one is not this
decision's, and none of the three answers below needs it.

So a cancellation that lands while a move is outstanding is **deferred**: the
request is marked, `_grant` gives it nothing further, and it retires when
`block_vacated` says the move it was already making is over. The train runs
into the block it was granted and stops there, which is where it was going to
stop anyway, and the release happens with the sensors rather than under them.

That is a real end and not an open one: the block it is running into is
locked to it, the sensors are coming, and the retirement publishes
`request_cancelled` in place of `request_completed` — the train did not
arrive, and the metrics must not read it as though it had.

## A placement is a cancellation too

`tc49/dispatch/placement_wanted` had three preconditions, one of which was
that the train have no request in flight (ADR-0037). It has two now: the
gesture **cancels first and places second**.

The old rule protected something real. On release the grant phase launches
from where the dispatcher believes the train is, so a request admitted against
the old block would silently depart from the new one. Cancelling protects it
better: there is no request left to depart from anywhere.

And the refusal was in the way of the very case a placement is for. Under
`FullRoute` the train's own launch holds every block of its route, so a person
saying *the train is actually here* — pointing at a block on that route, which
is where a stalled train is — was refused by the freeness check for a claim
belonging to the request they were ending. That is
[#237](https://github.com/rails49/control/issues/237)'s case, and it is why
cancelling first is what makes the placement possible rather than merely
permitted.

Ordering, and it is contract: `request_cancelled` precedes `train_placed` and
`train_removed`, so both of those facts always describe a train with no
request. A reader of either never has to ask whether something still wants the
train.

Two reasons rather than one, because the two directions leave the railroad in
different places: `removed` is off the layout holding nothing, `displaced` is
standing in a block and holding it. A placement cancels its **own** train's
request and never another's, so a block claimed by somebody else is still a
block a placement is refused.

## What it does not do

- **It stops no locomotive.** See above; there is no such command, and adding
  one is out of scope.
- **It prunes no id**, and it resumes none.
- **It does not re-submit.** The scheduler drops a cancelled request and its
  destination; a destination that is still wanted is asked for again with
  `request_wanted`. Re-asking on the person's behalf would compose the work
  they just ended.
- **It invents no fault vocabulary.** A cancellation says a request ended, not
  why the railroad could not finish it. Why is what the person saw, and the
  trace records the gesture.

## What it rules on

- **Amends ADR-0037.** `placement_wanted`'s third precondition is gone, and
  with it the sharp edge that ADR named and did not solve: "hold mid-run with
  a committed route standing and that train cannot be repositioned until you
  release and let it finish". You cancel and reposition. Everything else that
  ADR decides — that `held` commits nothing, that a granted move is not
  retractable, that `train_placed` is the ledger line for a placement —
  stands.
- **Amends ADR-0040.** "Safe but wedged is the deliberate outcome" stays true
  of a train whose detector never fires: the dispatcher still sees no sensor
  event, and the block stays locked. It stops being the *only* outcome — the
  recourse was hold plus a placement, and the placement now takes the request
  with it, so the wedge ends where the person is standing instead of at the
  next restart. Legs 2 and 3 of that ADR, the transit bound and the power
  relay, are untouched.
- **Completes ADR-0047.** That ADR wrote "a move ends by arrival, or by
  cancellation: an agent revokes the permission and the request is deleted",
  and then said cancellation was contract surface that existed nowhere. It
  exists here.
- **ADR-0033 stands.** No id resumes, and a cancelled one is spent.
- **ADR-0039 stands** and gains its sharpest case: taking a train off the
  layout is one gesture in two directions, and now it works on a train that
  is in the middle of something.
