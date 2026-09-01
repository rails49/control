# Dispatch

The dispatcher accepts requests from the scheduler — as events on the bus
([SYSTEM.md](../SYSTEM.md#dispatcher)) — and tries to satisfy them in
the shortest time possible. It is **online** — it commits to decisions without
knowing future requests — and is the research core of this project: deadlock
avoidance at high throughput. Terminology follows [CONTEXT.md](../../CONTEXT.md).

## Semantics

- **Three endings** — a request ends by arrival, by rejection before
  admission, or by cancellation: a person ending it outright, or a person
  saying where the train actually is and the placement retiring it under them
  ([ADR-0049](../adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)).
- **Admission** — a request is rejected if no arrival end survives: none
  is a block the train fits, none is an end any route can enter through, or
  none is reachable from the origin — settled where the request arrives, or,
  where an earlier one of the same train is still pending, at the first launch
  attempt. A request stating a departure block its train is not standing in
  is rejected too, as is a payload the dispatcher cannot read as a request at
  all. All other requests are accepted and queued.
- **Fixed routes** — a route is chosen when the train starts moving and never
  changed; only its locks are incremental
  ([ADR-0002](../adr/0002-fixed-route-per-request.md)).
- **No reversal** — routes are strict pass-throughs; terminal blocks occur
  only as endpoints ([ADR-0001](../adr/0001-no-reversal-within-a-route.md)).
- **Event-driven** — the dispatcher reacts to bus events and never reads a
  clock — it never learns what time it is
  ([SYSTEM.md](../SYSTEM.md#time)) — so a simulator and a physical layout drive
  it the same way.
- **Signalled** — how far the dispatcher has locked ahead of a train is what
  the signal it faces shows. The aspect is published on the grant and on a
  last-value topic carrying every signalled end, and it is the driver's only
  input once the driver acts on it. A signal is at `stop` unless a block
  beyond it is locked, which follows from the locks rather than being a rule
  of its own
  ([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).

### Requests

A request is `(train, departure end, arrival ends)`. The
train is
named explicitly — its origin block follows from where it stands — and the
departure end fixes the first transit. The **arrival ends** are a set, and any
one of them satisfies the request; the dispatcher commits to one when it
chooses the route ([ADR-0007](../adr/0007-requests-name-a-set-of-arrival-ends.md)).

Both ends name the end the train **crosses**: `claro_1.B` as a departure means
it leaves through `B`, and `airolo_2.A` as an arrival means it enters through
`A` and comes to rest with its leading end toward `B`. The arrival end is
therefore the end of the route's final transit, and constraining it is how a
scheduler says which way round the train must finish — a fact the reversing
loop makes real, since turning a train costs a second request rather than
being free.

Naming both ends of one block says "either way round" and is exactly the
looser request this model had before. Naming ends on several blocks says the
thing a station actually offers: more than one track will take this train.

**Admission is decided in two stages**, because the two halves of the old rule
need different information:

- At admission — on receipt of the request event — arrival ends are pruned if
  the block cannot fit the train, or if the end appears in no connection — a
  terminal block's dead end, which no route can ever enter through. Both are
  facts about the layout and the train, so both are decidable the moment the
  request arrives. A stated departure block is checked here too, against where
  the train actually stands: every feasibility check is the dispatcher's,
  whatever the scheduler happens to know
  ([ADR-0028](../adr/0028-the-scheduler-knows-where-trains-stand.md)).
  A disagreement rejects the request with reason `wrong_origin` rather than
  raising, since the submitter may be a stale browser
  ([ADR-0021](../adr/0021-a-bad-request-is-answered-not-raised.md)). A request
  naming no block, as a chained one does, can state no disagreement.
  The stated block is no longer a routing input — what the train leaves by is
  settled below — so this check now does one thing only: it is a **staleness
  assertion**, catching a panel that composed against an out-of-date position.
  This stage is also where the payload is **read**, rather than trusted:
  anything at all can be published on the inbound topic and after the relay
  is deleted nothing stands in front of the dispatcher, so a train the
  session does not have is answered `unknown_train`, a departure or arrival
  block the layout does not have `unknown_block`, and a payload carrying a
  readable id that is otherwise not a request `malformed`. One with no
  readable id is dropped — every rejection is addressed by id, and the frame
  is a line in the trace by virtue of having been published
  ([ADR-0034](../adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).
- Arrival ends not reachable from the origin are pruned wherever the origin
  is known, which is everywhere except behind a request of the same train
  that is **still pending**. Behind an **active** route the origin is known:
  a route is fixed once chosen
  ([ADR-0002](../adr/0002-fixed-route-per-request.md)), so the block it
  arrives at and the end it leaves the train facing are both settled and a
  drag on a moving train is answered as it is asked. That is
  sound because reachability is a pure function of layout, origin, departure
  end, arrival ends and train length: route selection prunes only on fit and
  on the simple-path rule, congestion enters solely as a sort key and `k`
  only caps the list, so nothing between admission and the launch can change
  the answer. **Reachability waits for the launch attempt only when a
  predecessor is still pending** — so `request_rejected` can also be
  published at the first launch attempt, and rejection is not purely an
  admission-time answer. The departure block is re-checked there for the same
  reason, so `wrong_origin` is not an admission-only answer either: a request
  whose train ran no route at all — its work ahead having been degenerate, or
  refused — has only the block it stated, and one that has gone stale while
  it waited is refused rather than routed from.

Either stage rejects the request if it empties the set. The admission stage
records what it dropped, with reasons, on `request_admitted`
([SYSTEM.md](../SYSTEM.md#event-inventory)) — that is where an authoring
slip shows up, so a mistyped end is visible when it is made instead of
silently narrowing the experiment. The launch stage records nothing unless it rejects,
because a prune that leaves candidates standing changes nothing observable: the
chooser simply has fewer routes to order, and `route_chosen`'s `k_tried`
already says how many it examined.

**A request queued behind another does not state its own departure end.** It
was composed against the block its train stood in at the time of asking, and
where the train will really depart from is a choice the dispatcher had not
yet made — so a stated block that turns out not to be the origin is not an
authoring slip to refuse but an end to replace. The dispatcher reads the
replacement off the route the train arrives on: routes are strict
pass-throughs ([ADR-0001](../adr/0001-no-reversal-within-a-route.md)), so a
train that entered through one end leaves by the other, or by a terminal
block's one connected end where that would be a wall — `lib`'s rule, the same
one the scheduler asks of facing. A bare end letter states no block, cannot
go stale, and keeps resolving against whatever origin the launch finds.

This is not the dispatcher holding facing, which
[ADR-0019](../adr/0019-facing-is-scheduler-state.md) declined. It is the
dispatcher applying its own no-reversal rule to a route it chose itself: for
a train that arrived on a dispatcher route the departure end is a fact about
**the route**, not about **the train**. A train that has never moved is idle
and states a real end, and a reversal at rest cannot slip in between the two
— the pending scan runs in the same grant phase that applies the completion.

A request naming the train's current block is accepted with an empty route,
whichever end that arrival names. Whether a request is degenerate is decided
at the **first launch attempt** — it depends on the origin block, which for a
request queued behind a pending one is unknown until the predecessor
completes, and an end in the origin block is therefore never pruned for
reachability. The launch commits an empty route and completes in the same sweep,
moving nothing and locking nothing, so the request's latency is next to
nothing. An empty route has no
final transit for the end to constrain, and the dispatcher holds no facing to
check it against — facing is scheduler state it never sees
([ADR-0019](../adr/0019-facing-is-scheduler-state.md)) — so this is the one
case where the arrival end is vacuous. Treating it as degenerate rather than as an error
keeps the admission rule free of special cases.

A request may be pending for a train that is already active on an earlier
one; chaining makes this routine. It needs no mechanism — an active train is
not idle, so its next simply cannot launch yet.

### Route selection

The route chooser is a **pluggable strategy**. Milestone 1 shipped a pure
topology ordering; #33 made it congestion-aware. The chooser:

1. Consider routes to **every** surviving arrival end, merged into one list.
   The arrival ends are unordered and equally acceptable, so the ordering below
   decides between them; the request states no preference among them.
2. Consider only routes whose every block fits the train.
3. Order by transit count — which under the simulator is travel time, since
   every transit costs the same fixed delays regardless of length.
4. Break ties on congestion: the number of route blocks beyond the origin that
   are locked by another train — idle holders included — or lie on the
   committed remaining route of another active train.
5. Break remaining ties on the lexicographically smallest block-id sequence,
   so repeated runs are bit-identical.

`k` is a single budget over that merged list, not a budget per arrival end, so
it keeps its plain meaning: how many alternatives a launch may try before
staying pending.

Step 4 is what keeps equidistant candidates from concentrating. Arrival ends
on parallel tracks of one station tend to tie at step 3 — a station is reached
by the same line whichever of its tracks the train ends on — and before #33
the lexicographic tie-break alone decided which `k` got tried, so every train
tried the same smallest-id tracks first. That bias was measured twice: as the
`route-blindness` counterexample (ARCHITECTURE.md, property 3) and as an
outright stall of `gotthard-v0/saturation` authored at `|dest| = 6`
([BENCHMARKS.md](../bench/BENCHMARKS.md#the-k-axis)).

The congestion count is a function of the dispatcher's live state, so the
ordering is `(layout, state)` and stays deterministic: the tested
byte-identical-traces property is untouched. The committed-route part of the
count is what restores to `Incremental` the signal `FullRoute`'s up-front
locks gave the next launch for free: under `FullRoute` a committed route is
locked and already counted, under `Incremental` only the first increment is.
Congestion is a tie-break, never an additive cost, so a congested shorter
route still outranks a clear longer one; steering around congestion onto
longer routes stays `k`'s job.

There is no dedupe rule. An earlier draft deduped candidates by resource set,
on the grounds that a route entering the destination at `A` and one entering at
`B` were one option spelled twice. Under arrival-end sets they are two
different answers the caller explicitly asked for — and the rule could never
have fired as written anyway, since a simple route is determined by its
resource set.

### Queue discipline

Greedy, with aging. At **every** grant phase the dispatcher scans pending
requests and launches each whose conditions hold, skipping the rest that
round. Unconditionally: the first launch of a run follows an admission, not a
release, so a scan gated on released resources would never start the batch
workload. Skipping a scan when nothing was released *and* nothing was
admitted since the previous phase is a valid optimization, not a semantic
rule.

The scan order is most-refused first, admission order among equals (#34;
[ADR-0012](../adr/0012-the-pending-scan-ages-by-refusal-count.md) records why
plain arrival order starved through-traffic). Aging gives a starved request
first claim on whatever just freed. The refusal count is dispatcher state,
never wall-clock, so the order stays deterministic; a train's chained
requests keep their order for free, since an untried later one has no
refusals and a later seq. The ordering key remains an explicit policy point:
it only chooses which *safe* launch is tried first, and could change again
without touching the safety core.

Starvation is thereby bounded in practice, not prevented in principle: max
per-request latency remains the detector. Starvation is not deadlock; see
[SAFETY.md](SAFETY.md).

### Launch and completion

Occupancy is a **standing lock** — every train always holds the lock on the
block it stands in, moving or parked, requested or not. Launching is therefore
not "taking a lock on the train's own block"; it is the safety layer granting
the request's first increment: the first transit plus the second block under
incremental locking, with the increment beyond it asked for as the train
starts moving, or the whole route under the full-route baseline.

**The queue does not filter on arrival occupancy.** A request whose arrival
blocks are occupied is scanned like any other; whether it launches is the
safety check's answer, not the queue's. The two cases differ: an *idle*
occupant is a permanent obstacle and the launch is refused until it leaves, an
*active* occupant that has begun moving no longer counts as holding the block
([SAFETY.md](SAFETY.md#state)). Keeping that distinction out of the queue is
what keeps the avoidance layer the single place deadlock is reasoned about.
With a set of arrival ends the refusal is rarer but unchanged in kind: the
launch waits only when *every* candidate is refused, not merely the first.

A request completes as its final transit finishes: the trailing transit and
origin block release, and the train parks holding only its standing lock.
Latency is completion time − arrival time.

A request **cancelled** ends the same way and short of the arrival: everything
its train holds is released except the block it stands in, and the train parks
holding only its standing lock wherever along the route it had got to
([ADR-0049](../adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)).
A cancellation that lands while a move is outstanding is deferred to the
sensors that end that move — nothing on the bus retracts a `move` already
sent — and nothing further is granted in the meantime. It contributes no
latency: there is no arrival to measure to.

## Time model

The dispatcher grants on **the events that arrive**
([ADR-0047](../adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)):
there is no grant beat, no sensor buffer and no clock — a simulator and a
physical railroad drive it the same way, each pacing its own sensor stream.

**A reading applies where it lands.** A detector reports a level, so a
repeated reading re-asserts what the dispatcher already holds and is an
at-least-once no-op. A change splits the move's two facts by role:
`block_occupied` records where the train arrived, and `block_vacated` —
which follows it, the tail clearing after the head arrives — releases the
origin block and the transit, ends the move and completes the request.
Between the two the train is between blocks and takes no further grant.
Every grant is `safe()`-checked before it commits, so arrival order picks
among options that were all safe and never reaches an unsafe state; under a
future MQTT transport a straggling sensor delays a grant, conservative and
safe, never an unsafe one.

**The sweep is the grant phase**, run where the lock table or the waiting
set changes: a request admitted, a vacate releasing what a move held, the
run released. A sweep covers the active trains and the whole pending queue,
so a refused train is reconsidered exactly when the resource it waited on
frees, and every pending request accrues a refusal in the same sweep — no
backstop timer, and the aging order unchanged
([ADR-0012](../adr/0012-the-pending-scan-ages-by-refusal-count.md)).

**A held run commits nothing.** While `tc49/dispatch/state/run` is `held` a
sensor still applies where it lands: an outstanding move completes and
releases its locks, and no route is chosen, no move granted and no lock
taken until a person releases it. Admission is untouched, so the queue
accumulates and — nobody having accrued a refusal meanwhile — drains in the
order it accumulated. Releasing runs a sweep, so the press itself grants
([ADR-0037](../adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
The layout holds it too: `tc49/layout/state/power` arriving as anything but
`on` sets `run` to `held` by the same path, and a release is dropped until
it is back
([ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).

**A draining run launches nothing.** `draining` is the third value of the
same topic and the ordinary way to turn a railroad off, an abrupt cut
leaving no point position trustworthy and stranding whatever was mid-transit.
The gate is on **launching** and not on admission — admission is cheap and
reversible, launching is the commitment:

| value | admits | launches | grants to a train already moving |
| --- | --- | --- | --- |
| `running` | yes | yes | yes |
| `draining` | yes | no | yes |
| `held` | yes | no | no |

So the sweep's grant pass still covers the active trains, each running to the
end of the route it is on, and the pending queue is passed over untouched —
accruing no refusals, exactly as under a hold, so a drain turned back releases
into the order the queue accumulated. Every end a granted train is leaving by
still shows its aspect: the answer to "may this train leave" is yes, and a
signal at stop over a train that has just been told to go would be the hold's
lie the other way about.

**The drain completes when no train is active.** The dispatcher writes `held`
itself at the first moment no train is active and none is crossing, and that
transition is the drain's completion — what the panel watches for before it
cuts track power
([ADR-0051](../adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)).
It is read at the end of every sweep, a sweep being what runs wherever a
train can have stopped being active, so a drain over a railroad with nothing
under way ends in the press that asked for it. Manual trains count by the
same rule and need no rule of their own: every train moves on a route the
dispatcher allocated, and *manual* names only who turns the throttle
([#207](https://github.com/rails49/control/issues/207)).

`held` published while a drain is in progress **abandons** it, at once and
without waiting for a train to finish, and `stopped` power is always honoured
and is not a drain. `running` resumes launching. A drain a wedged train would
hold open forever is escaped the same way anything that train holds is: hold
the run, take the train off the layout, and the request it was running goes
with it
([ADR-0049](../adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md),
[#294](https://github.com/rails49/control/issues/294)).

That value is the one state topic the dispatcher consumes, so it is the one
place a **stamp** is compared here: a supply that went off and came back on,
delivered backwards, would otherwise leave the dispatcher holding the run
over live track — or worse, running over dead track. The later `at` wins and
the earlier value is ignored, quietly and with the frame on the trace like
any other (SYSTEM.md, the bus;
[#240](https://github.com/rails49/control/issues/240)). The sensor leaves
beside it are compared against nothing: a detector reports a level, so a
repeat re-asserts what the dispatcher already holds, and the readings of one
boundary are sorted before they are acted on — vacated first, then occupied
— so a grant never depends on delivery order at all
([ADR-0047](../adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
A request is keyed by a unique id and a duplicate is dropped, which is the
same independence bought a different way
([ADR-0033](../adr/0033-a-request-id-is-unique-not-meaningful.md)).

**A reading no grant explains holds it too**
([ADR-0048](../adr/0048-an-unexplained-reading-holds-the-run.md)). The
dispatcher recovers train identity from its lock table, so a `block_occupied`
with nothing claiming the block, or a `block_vacated` of a block it believes a
train stands in, says the table has stopped describing the steel — a hand
putting a locomotive down, a train pushed while the supply was off, a detector
asserting on dirt. The run holds by the path power takes, and nothing is
guessed: occupancy is anonymous, so there is no train to place. It does not
raise, a payload never being a reason to leave the bus (SYSTEM.md, rule 4).

**A held run also asks the detectors.** The sensor readings the layout has
reported are compared against the placement, and the two contradictions — a
train standing in a block that reads clear, a block reading occupied with
nothing claiming it — go out on `tc49/dispatch/state/disputed` for a person to
walk. Comparing commits nothing, and a reading that explains no granted move
is the check's whole subject: it is also what held the run, so the reading
that stopped the railroad is the entry the person is sent to. They place what
they find and press GO — a block reading clear again releases nothing, exactly
as power returning releases nothing. Blocks nothing has reported on take no
part, so a layout binding that publishes no occupancy disputes nothing
([#153](https://github.com/rails49/control/issues/153)).

**Lock footprint.** A train moving from `X` through `T` into `Y` holds
`{X, T, Y}` for the move and releases `X` and `T` atomically on arrival. `T`
and `Y` are granted together, which is what makes a transit never held across a
wait — the premise the whole deadlock argument rests on.

**Grant order** — within a sweep, active trains first (by request arrival
order, tie-break train id), then pending launches in the aging order of the
queue discipline above.
Draining work in progress before admitting new holders favours makespan and
mirrors the progress argument of [SAFETY.md](SAFETY.md): advancing the head of
the witness ordering is always safe, while launching adds a resource holder.

**Handoff follows the vacate.** A lock a move held is released by the
`block_vacated` that ends it, and the sweep that vacate triggers is where the
waiting train is granted — a convoy flows as each tail clears the block
behind it, the backward-propagating start wave real trains have. Minimum
latency is the travel time of the route's transits; the degenerate request's
launch-and-complete is the zero-transit case.

**Sensors are anonymous.** The layout interface reports only
`block_occupied(block)` and `block_vacated(block)`, with no train identity —
the least a block-occupancy sensor can be asked to produce. The dispatcher
recovers identity from its own lock table, which already records the grantee of
every block. This is what lets a simulator and a physical layout drive the
dispatcher the same way.

## Locking

1. **Full-route locking** (baseline) — lock every block and transit of a route
   before the train moves; unlock each behind the train. Trivially
   deadlock-free, low throughput. Serves as the benchmark yardstick.
2. **Incremental locking** (research core) — lock what the train needs to
   advance, its current block plus the next transit and block, and then ask
   for the transit and block after that. It runs at **depth two**, because one
   block ahead is only enough to move slowly enough to stop at the next signal
   and two is what buys full speed, and it never asks for a third
   ([ADR-0026](../adr/0026-two-blocks-ahead-is-full-speed.md)). The second
   increment is **asked for, not required**: obstructed or unsafe, the move
   happens anyway and the train runs at `caution` instead of `clear`
   ([ADR-0029](../adr/0029-a-lock-held-ahead-is-a-block-the-check-must-see.md)).
   Refusing the move on its account would leave `caution` with nothing to
   describe. A lookahead lock is an ordinary grant made early, so
   [ADR-0003](../adr/0003-route-aware-bankers-safety-check.md)'s check answers
   it unchanged — but it is told what a train holds ahead of where it stands,
   which is the one thing depth makes the safety layer's business. The
   baseline above is the same idea at unbounded depth.
   High throughput, but naive incremental locking deadlocks — e.g. two trains
   entering a section of two facing blocks with no other connections between
   them each wait forever for the other to depart. The deadlock-avoidance
   layer that prevents this is the central problem; see
   [SAFETY.md](SAFETY.md).
3. **Transit concurrency** — a connection declares which pairs of its transits
   are `concurrent`; every other pair conflicts
   ([ADR-0006](../adr/0006-conflicts-declared-by-inversion.md)). A crossing that
   declares its two straight transits concurrent therefore accepts two trains
   at once on them, but only one on either crossing transit. Transits are also
   self-exclusive, so head-on use is excluded without declaring anything. A
   grant succeeds when the transit is unlocked and no currently-locked transit
   at that connection conflicts with it — an instantaneous admissibility test
   at the grant, not part of the deadlock check.

   ![Crossing connector](../image.png)

## Research

The [survey](../research/deadlock-avoidance-survey.md) assessed known theory
against this model — banker's-style safety checks (applicable because routes
are fixed), resource-allocation graphs and cycle detection, deadlock avoidance
in AGV systems, Petri-net approaches, and railway zone control. The resulting
choice is a route-aware banker's safety check
([ADR-0003](../adr/0003-route-aware-bankers-safety-check.md)); the check itself
and its deadlock-freedom argument are in [SAFETY.md](SAFETY.md).

## Metrics

Benchmarks feed the dispatcher a fixed list of requests and report the four
metrics below; the suite that produces them is [BENCHMARKS.md](../bench/BENCHMARKS.md),
and each metric is computed as a pure function of the event trace
([bench/METRICS.md](../bench/METRICS.md)).

- **Makespan** (headline) — simulated seconds from the first arrival until
  the last request completes.
- **Per-request latency** — completion − arrival; mean and max (catches
  starvation).
- **Resource utilization** — fraction of the run each block/transit is
  occupied or locked, over the whole of it (the start through the trace's
  last stamp).
- **`move` commands per simulated minute** — throughput.
