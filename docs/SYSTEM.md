# System

How the app is organized: four components — asset store, scheduler, dispatcher,
driver — plus the external **layout interface** and the **UI**, communicating
over an event bus and an asset CRUD contract. This page fixes those contracts. An implementer
of any one component should need this page and at most one internals doc
([dispatcher/INTERNALS.md](dispatcher/INTERNALS.md) for the dispatcher); nothing here requires
reading another component's internals. Terminology follows
[CONTEXT.md](../CONTEXT.md); the contract decisions are recorded in
[ADR-0008](adr/0008-bus-contract-is-the-mqtt-safe-intersection.md),
[ADR-0009](adr/0009-layout-interface-owns-time.md), and
[ADR-0010](adr/0010-asset-store-serves-coarse-read-only-documents.md).

## Overview

```
          ┌───────────────────── asset store ─────────────────────┐
          │   layout + scenario documents — read-only, snapshot   │
          └───────┬─────────────┬─────────────────────┬───────────┘
                  │             │                     │
          ┌───────┴───┐  ┌──────┴─────┐  ┌────────┐  ┌┴─────────────────┐
          │ scheduler │  │ dispatcher │  │ driver │  │ layout interface │
          └───────────┘  └────────────┘  └────────┘  └──────────────────┘
                ▲▼             ▲▼            ▲▼               ▲▼
          ═══════════════════════ bus: tc49/# ═══════════════════════════
                                     ▲▼
                                ┌────┴───┐
                                │   ui   │  gestures out, everything in
                                └────────┘
```

- **Scheduler** — turns the scenario's request list into request events,
  released at their `at` boundaries.
- **Dispatcher** — admits requests, chooses routes, grants moves
  deadlock-free; the research core ([DISPATCH.md](dispatcher/DISPATCH.md),
  [SAFETY.md](dispatcher/SAFETY.md)).
- **Driver** — turns each granted move into the command that moves the train;
  in the end state it reads the aspect it is handed and decides how fast
  ([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
- **Layout interface** — the boundary to whatever runs the track: sensor
  readings and the grant boundary come out, turnout and throttle commands go
  in. A simulator implements it in milestone 1, a hardware adapter later.
- **Asset store** — serves the layout and scenario documents; the one
  contract that is not the bus, because it answers queries and the bus
  refuses to.
- **UI** — the panel, and a throttle later: watches the bus and writes
  **gestures** under `tc49/ui/*`. A gesture is not a request — it names a
  train and where to put it, and the scheduler composes the request
  ([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)).

These are **roles, not implementations**. Each names a boundary any
implementer can stand behind unchanged: the simulator and a hardware adapter
publish the same layout topics, and a future scheduling UI or freight
generator publishes the same schedule topics the milestone-1 scheduler does.

One cycle of the machine: the layout interface publishes the boundary; the
scheduler releases the requests that have come due; the dispatcher runs its
grant phase over everything buffered since the previous one and publishes
granted moves, publishing `align` for each so the route is set before anything
moves; the driver turns the grant it sees into a `cross`; the layout interface
executes both and reports occupancy, which the dispatcher buffers for the next
boundary. The trace tap watches all of it.

## The bus

Components share a publish/subscribe bus carrying typed JSON events on named
topics. In milestone 1 the bus is an in-process object; MQTT is a later
drop-in transport. That substitution only works if nothing relies on what
MQTT cannot give, so the contract is exactly the **MQTT-safe intersection,
unsoftened** ([ADR-0008](adr/0008-bus-contract-is-the-mqtt-safe-intersection.md))
— even where the in-process implementation could trivially promise more.

The bus **promises**:

- **Per-topic FIFO** — events on one topic arrive in publish order (each
  topic has a single writer, below).
- **Fan-out** — every subscriber whose filter matches sees the event, each
  independently.
- **At-least-once mindset** — the bus may duplicate; consumers are
  idempotent.
- **Last-value state topics** — a state topic delivers its latest value to a
  late subscriber (retained-style).
- **MQTT topic grammar** — `/`-separated levels, `+` and `#` filters.

The bus **refuses** — each of these is deliverable in-process and refused
anyway, because relying on it would be a latent bug the day MQTT arrives:

- no synchronous request/reply,
- no delivery confirmation,
- no global or cross-topic ordering,
- no replay for late subscribers (state topics excepted, last value only),
- no unbounded queues.

Queries that need answers stay off the bus; the asset store's CRUD contract
exists for that.

**Topic rules.** Three rules bind the inventory below:

1. **Single writer** — exactly one **role** publishes on any topic, which
   upgrades the ordering promise to plain per-topic FIFO and makes ownership
   checkable by inspection. A role with concurrent instances — two browser
   tabs are two instances of `ui` — may write an **event** topic, provided no
   consumer depends on ordering across instances; it may never write a
   **state** topic, which is last-value-wins and so diverges exactly when its
   writers know different things
   ([ADR-0035](adr/0035-a-topic-has-one-writing-role.md)).
2. **Event and state topics are disjoint** — an event topic carries facts
   that happened and is never replayed; a state topic is last-value-wins.
   Every topic is declared as one or the other, and state is marked in the
   path (`.../state/<name>`), so the split is structural.
3. **Prefix-filter consumption** — each consumer subscribes with a small
   fixed set of `+`/`#` prefix filters under `tc49/`, never a list of
   individual topic names.

**Milestone-1 binding.** A single-threaded, queued-FIFO, run-to-completion
scheduler: `publish()` appends to one queue and returns; a loop drains it,
delivering each event to subscribers in subscription order; publishes made
inside a handler join the back of the queue. Delivery order is then a pure
function of publish and subscribe order — the byte-identical replay the test
suite requires ([ARCHITECTURE.md](ARCHITECTURE.md#tests)) — and the
breadth-first shape forecloses the same-boundary-causality habit the contract
refuses, since nested synchronous delivery would grant exactly what MQTT
never will.

**The retained values are durable.** Given a file, the binding loads it at
startup and rewrites the whole of it on every change to a `tc49/*/state/*`
value — a temporary file in the same directory, renamed over the target, so a
cut mid-write leaves the previous good copy intact. That is a **binding**
concern and not an app's, because it is what a broker already does with
retained messages: an app that comes back up finds its own value waiting on
its own state topic and adopts it, exactly as it would from a broker that
outlived it, and milestone 2 inherits the behaviour rather than deleting a
crutch. What is adopted is each app's own business, and it is selective —
placement and facing are; the dispatcher's queue is not, and no request id
ever resumes ([ADR-0033](adr/0033-a-request-id-is-unique-not-meaningful.md)).
With no file the bus opens none, so `bench` and `sweep` are untouched by
construction.

**Milestone-1 bridge.** Until the bus is a real broker, a browser reaches it
over a WebSocket relay ([ui/PANEL.md](ui/PANEL.md#implementation)): every
`tc49/#` event goes out to every client as one JSON frame,
`{"topic": …, "payload": …}`, and the inbound topics are the `tc49/ui`
leaves — `request_wanted`, `reversal_wanted`, `run_wanted` and
`placement_wanted` — whose frames are published as the events they name. That
set is the `ui` role's own, which is what a broker's ACL will grant a page
once the relay is gone, so it is read off the inventory rather than listed a
second time.
**A client names the scenario it wants in the socket path**,
`ws://host:port/<layout>/<scenario>`, and hears that railroad or none. The
relay outlives the assembly it relays: naming one it is not running rebuilds
behind it and closes whoever is still on the old path, and naming one that
does not exist is an error frame and a close with the running railroad
untouched. None of that is a topic, so the inbound set is unchanged and stays
equal to what the ACL will grant.
`tc49/schedule/request_submitted` is refused inbound like any other
topic: the browser writes gestures and never requests, which is what makes the
single-minter claim something the topic check enforces rather than an intention
([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)). Any other inbound frame — another topic, or not `{topic, payload}`
JSON — is answered with an `{"error": …}` frame and never reaches the bus.
The relay adds no topics and no payload fields: the frame is the event, so
the inventory below is its entire schema. When MQTT arrives the browser
speaks MQTT-over-WebSocket to the broker and the relay is deleted.

**On connect the relay sends each state topic's last value**, before any live
frame — the same frames it would have sent had the client been there, in the
same schema. This is the retained-style delivery the bus already promises a
late subscriber, and what a broker gives a client the moment it subscribes; a
relay that dropped it would be weaker than the contract it binds. It is not
the relay describing the run
([ADR-0032](adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).

**The relay checks the topic and never the payload.** Topic authorization is
what a broker enforces with an ACL and so survives the relay's deletion;
payload validation is not, so it belongs to the dispatcher at admission, which
never raises on anything arriving from the bus
([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

## Event inventory

Topics are `tc49/<role>/<leaf>`, **publisher-first**: the second segment
names the role that writes there — `layout`, `schedule`, `dispatch`, `drive`,
`ui` — so rule 1 is verifiable from the name alone, `tc49/layout/*` keeps its
meaning when hardware replaces the simulator, and a future UI gets
`tc49/dispatch/#` for free. Leaves are past-tense facts, with two exceptions:
the two commands are imperative (`align`, `cross` — past tense would
be a lie, the command precedes the crossing), and `boundary` is the sole noun
leaf, naming a beat rather than a change. `align` sits under `dispatch`
because the dispatcher writes it: setting the route is its responsibility, and
the driver moves locomotives
([ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md)).

**Adding a `tc49/ui` event row grants the browser write access to it.** The
inbound set is read off this table rather than listed a second time, so a new
`tc49/ui/<leaf>` event topic is writable from any page the day the row is
added, and that is the grant a broker's ACL will carry once the relay is gone
([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).
The default is deliberate: a topic under `ui` is one a person's page writes,
that being what the role means
([ADR-0035](adr/0035-a-topic-has-one-writing-role.md)). The human driver's
throttle is the case the default is right for
([#124](https://github.com/rails49/control/issues/124)): it arrives as a
`tc49/ui` leaf and is meant to be writable. A topic under `tc49/ui` that should
not be writable is misfiled, and belongs to the role that may write it.

| Topic | Kind | Publisher | Payload gist |
| --- | --- | --- | --- |
| `tc49/layout/boundary` | event | layout | deterministic counter |
| `tc49/layout/block_occupied` | event | layout | block |
| `tc49/layout/block_vacated` | event | layout | block |
| `tc49/layout/state/power` | state | layout | last-value word, `on`, `stopped` or `off` — whether a train may move at all ([ADR-0041](adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)) |
| `tc49/schedule/request_submitted` | event | scheduler | id, train, depart, dest ends |
| `tc49/schedule/state/exhausted` | state | scheduler | last-value flag |
| `tc49/schedule/state/facing` | state | scheduler | last-value map of train to the end it would depart through |
| `tc49/ui/request_wanted` | event | UI | train, dest ends — a request minus the id and depart the scheduler owns |
| `tc49/ui/reversal_wanted` | event | UI | train — turn it around where it stands, the scheduler flipping its facing and composing nothing |
| `tc49/ui/run_wanted` | event | UI | run (`held`, `running`) — hold the run or release it |
| `tc49/ui/placement_wanted` | event | UI | train, block — where a train actually stands, said by the person who can see it |
| `tc49/dispatch/request_admitted` | event | dispatcher | id, surviving dest ends, pruned |
| `tc49/dispatch/request_rejected` | event | dispatcher | id, reason (`no_fit`, `no_entry`, `unreachable`, `wrong_origin`, `unknown_train`, `unknown_block`, `malformed` — the set is `tc49.lib.rejection`, and the UI's copy of it is generated) |
| `tc49/dispatch/request_completed` | event | dispatcher | id |
| `tc49/dispatch/route_chosen` | event | dispatcher | id, route, k_tried |
| `tc49/dispatch/move_granted` | event | dispatcher | id, train, transit, into, aspect |
| `tc49/dispatch/grant_refused` | event | dispatcher | id, reason (`unsafe`, `held`, `transit_conflict`), obstacles `[{resource, holder}]` |
| `tc49/dispatch/lock_granted` | event | dispatcher | train, resources |
| `tc49/dispatch/lock_released` | event | dispatcher | train, resources |
| `tc49/dispatch/train_placed` | event | dispatcher | train, block — a placement accepted, the standing lock moved with it |
| `tc49/dispatch/state/run` | state | dispatcher | last-value word, `held` or `running` ([ADR-0037](adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)) |
| `tc49/dispatch/state/aspects` | state | dispatcher | last-value map of signalled block end to aspect |
| `tc49/dispatch/state/allocation` | state | dispatcher | last-value picture of the run: standing trains, the transit each crossing train is on, locks and holders, committed routes, live requests |
| `tc49/dispatch/state/disputed` | state | dispatcher | last-value pair of lists: trains standing in a block that reads clear, and blocks that read occupied with nothing claiming them. Empty unless the run is held ([#153](https://github.com/rails49/control/issues/153)) |
| `tc49/dispatch/align` | command | dispatcher | connection, transit, points `[{addr, position}]` |
| `tc49/drive/cross` | command | driver | train, connection, transit, into |

| Consumer | Filter(s) |
| --- | --- |
| Scheduler | `tc49/layout/boundary`, `tc49/dispatch/#` **and** `tc49/ui/#` |
| Dispatcher | `tc49/layout/#`, `tc49/schedule/request_submitted` **and** `tc49/ui/#` |
| Driver | `tc49/dispatch/move_granted` |
| Layout interface | `tc49/drive/+`, `tc49/dispatch/align` **and** `tc49/dispatch/train_placed` |
| Trace tap | `tc49/#` |

Two invariants the inventory must maintain:

- **Leaf names are globally unique** across all topics — the trace's `event`
  field is the leaf alone and depends on it.
- **Consumers subscribe by prefix filter only** (rule 3). Each filter names a
  role, as the scheduler's three do; a consumer needing a list of individual
  topics is a design smell. The count is not the invariant — the shape is.
  The layout interface is the one exception and stays one: it acts on a
  named command and on `train_placed`, and hearing the whole `dispatch` role
  would mean discarding most of it — and its quiescence rule counts the
  commands it was sent.

**Payload conventions.** Correlate by request id, don't repeat: lifecycle
events carry the id plus only what is *new* — `request_rejected` drops
`depart`/`dest` (recoverable from `request_submitted`), `request_admitted`
keeps surviving ends and `pruned` because those are new facts.
`lock_granted`/`lock_released` carry `train` rather than the id, since the
utilization metric groups by resource. `request_completed` carries no
latency — the dispatcher has no clock to compute one with; metrics derives
it from the trace's boundary stamps. `grant_refused` carries one
`{resource, holder}` entry per candidate route blocked — one entry when
advancing a fixed route, up to `k` at a launch — which is what lets the
stall report of [BENCHMARKS.md](bench/BENCHMARKS.md#termination) be derived rather
than stored.

Payloads are gists, not field schemas. Field-level schemas are deferred
until a second consumer exists.

## Time

**The layout interface owns time**
([ADR-0009](adr/0009-layout-interface-owns-time.md)). It publishes
`tc49/layout/boundary`; the four app components only ever subscribe, which
keeps every one of them clock-free — the dispatcher never learns which
boundary it is on. In milestone 1 the simulator advances only when the bus is
quiescent (queue drained); that is loop-owner pacing, not a bus-contract
promise. Advancing means: execute the pending commands, publish their sensor
events, **then** publish the boundary — a beat's sensors precede the boundary
itself, so the grant phase the boundary triggers finds them in its buffered
set. Publishing the boundary first would slip every grant by one. A hardware
adapter later picks its own cadence behind the same event: the publisher
swaps, the contract doesn't. The contract is named for what it needs, the
**boundary**; `tick` is the simulator's name for its own beat, and "one
transit per beat" is the simulator's behaviour rather than the model's time
([ADR-0027](adr/0027-the-tick-is-the-simulators-grant-boundary.md)).

**The boundary event is what the dispatcher grants on.** There is no second
event. On each boundary the scheduler releases requests that have come due,
the dispatcher runs its grant phase over the sensor events buffered since the
previous one ([DISPATCH.md](dispatcher/DISPATCH.md#time-model)), and the
driver takes granted moves forward. Under queued-FIFO delivery, everything
published in reaction to boundary `N` lands after the dispatcher has already
handled boundary `N`, so it is granted at `N+1` — the one-boundary skew the
dispatch model's no-same-boundary-handoff rule describes.

**The boundary carries its number; nothing else does.** The payload is a
plain deterministic counter minted by the topic's single writer — required by
the at-least-once mindset, since a bare boundary consumed by counting would
double-advance on a duplicate, while a numbered one makes duplicates
trivially ignorable. That argument is not the simulator's: every binding
numbers its boundary, a hardware adapter included. No other event carries a
boundary field: the trace tap stamps each recorded event with the latest
boundary number it has observed, deterministic in milestone 1 because the tap
sees everything in delivery order. The scheduler consumes the number (it is
how requests come due at their `at` boundary); counting a bus event is not
reading a clock.

## Asset store

The store holds the documents the run is built from, behind an abstract CRUD
contract ([ADR-0010](adr/0010-asset-store-serves-coarse-read-only-documents.md)).
The milestone-1 binding is a Python library over the YAML files of
[DRAWING.md](store/DRAWING.md) and [LAYOUT.md](store/LAYOUT.md); a future REST
binding slots under the same names and verbs without appearing in the contract.

- **Two coarse document types** — `drawing` and `scenario`, fetched and
  stored whole. Symbols, wires, trains, and requests live inside documents
  and are not independently addressable. A layout is **derived** from a
  drawing at `get` and is not a document type of its own
  ([ADR-0015](adr/0015-drawing-is-the-source-of-truth.md)), so a railroad has
  one committed description.
- **Names as ids** — `crossover-yard` for railroads, layout-qualified
  `crossover-yard/meet` for scenarios. Verbs: `get`, `put` (whole-document
  create-or-replace), `delete`, `list` (all layouts; scenarios of a layout).
  No partial update.
- **Components are read-only** — scheduler, dispatcher, driver, and the
  layout interface only `get`/`list`. Writes belong to authoring tools.
  Runtime truth is bus state, history is the trace; a scenario that mutates
  when run is a broken benchmark fixture.
- **Snapshot at startup** — assets are immutable for the duration of a run.
  The contract offers no change notification and no asset-change events
  exist on the bus; editing an asset means a new session. This is what makes
  read-only safe: a mid-run topology change would invalidate committed
  routes and locks.
- **The store validates, consumers derive** — `get` never returns an
  invalid document. Schema conformance and referential integrity (the
  scenario's layout exists, named blocks exist, connection endpoints are
  real block ends) are enforced at whichever verb a document enters through:
  `put` rejects invalid documents, and the milestone-1 YAML binding runs the
  same validator at `get`, because its documents are hand-authored files
  that never passed through `put`. The layout derived from a drawing goes
  through that validator too, as a safety net against derivation bugs. A mistyped end fails loudly at load, not
  as a `KeyError` mid-run.
  All derivation stays consumer-side: the conflict matrix by inversion
  ([ADR-0006](adr/0006-conflicts-declared-by-inversion.md)), terminal-block
  derivation, arrival-end expansion, fit pruning.

## Component footprints

Each component in terms of the contracts above: what it reads from the
store, what it subscribes to, what it publishes, and the responsibility that
justifies exactly that footprint.

### Scheduler

*Reads* the scenario and the layout. *Subscribes* `tc49/layout/boundary`,
`tc49/dispatch/#` and `tc49/ui/#`. *Publishes* `request_submitted` and the
`state/exhausted` and `state/facing` last-value topics.

The scheduler is the **one writer of requests**, and its sources are three: a
timetable released at its `at` boundaries, a person gesturing on the panel,
and a generator inventing traffic later — "three sources inside one
scheduler, not three publishers"
([ADR-0028](adr/0028-the-scheduler-knows-where-trains-stand.md),
[GOALS.md](GOALS.md#scheduling)). Which of them a session has is
configuration, not a rule: `tc49 live` runs with the timetable off while `at`
is still a boundary count
([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)).

A boundary count is the milestone binding of "at a stated time" and not the
model's answer, since a boundary count means nothing to a timetable once a
hardware adapter is picking the cadence
([MILESTONE-1.md](MILESTONE-1.md#scope)). From a scenario request the
scheduler performs only the *mechanical* arrival-end expansion
(`to: [yard_e]` → `yard_e.A, yard_e.B` — pure syntax, no layout needed); from
a **gesture** it supplies the two fields the gesture omits, the id and the
departure end. It mints each request's **id**, which is opaque to every
consumer and need only be unique
([ADR-0033](adr/0033-a-request-id-is-unique-not-meaningful.md)), from one
undivided counter in scenario order (`<train>-1`, `<train>-2`), which
byte-identical replay requires of it — a run carrying gestures makes no such
claim, and a benchmark run receives none. Never clock-derived.

It **holds facing**, which is scheduler state
([ADR-0019](adr/0019-facing-is-scheduler-state.md)): seeded from the
scenario's placement, carried forward from the entry end of each
`move_granted` and from a committed route's departure end, and published as a
last-value topic that every view reads to draw a train's direction arrow
([ADR-0032](adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
That upkeep is why it reads the layout: `move_granted` names a transit and the
block entered, not the end entered through, so which ends a transit joins has
to come from somewhere.

It **judges nothing**. All semantic checking — departure-end consistency,
`no_fit`/`no_entry` pruning, reachability — belongs to the dispatcher at
admission, leaving one feasibility authority instead of two; a gesture naming
a train that is not idle is composed and submitted like any other, and
answered `wrong_origin` or queued. What it cannot compose it **drops** — a
gesture is the first thing a browser writes and carries no id, so there is
nothing to address an answer to and the frame is already a line in the trace
([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).
Like the dispatcher, it never raises on a bus payload. When the last timetable
request is out it sets `exhausted`, the milestone-1 termination signal.
Where a **retained `state/facing` survived a restart** it adopts that in
place of the scenario's placement, a train the retained value does not name
falling back to it.

### Dispatcher

*Reads* the layout, and from the scenario its stock — train lengths for the
admission fit check, initial placement to seed the standing locks. Neither
fact can come off the bus: sensors are anonymous, so the lock table the
dispatcher recovers identity from must be seeded before the first sensor
event, and `request_submitted` carries no length. Where a **retained
`state/allocation` survived a restart** the placement comes from it instead —
its `trains` and `crossing`, adopted before the standing locks are published;
lengths stay the scenario's, and `locks` and `requests` are not adopted at
all, so the lock table is rebuilt one block per train and the queue comes
back empty. The placement is taken **per train**: a train the picture does
not name starts where the document says, and where that is the block the
picture stands another train in the contested block goes to the train with
nowhere else to stand. The other falls back to its own starting block, or —
both of its answers taken — comes up placed nowhere at all, which the
picture then shows as a train with no block
([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)). *Subscribes*
`tc49/layout/#`,
`tc49/schedule/request_submitted` and `tc49/ui/#`. *Publishes* the nine
`tc49/dispatch/*` events, plus `state/run`, `state/aspects`,
`state/disputed` and
`state/allocation` — the last its picture of the run, serialized from the
lock table on change, so a client that joins an idle railroad can draw it
([ADR-0032](adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).

**The run is held or running**, on `state/run`, stated from the constructor
so a joining client is served the word rather than left to read one out of an
absence. A cold session states `running`; one that came up on a restored
picture states `held`, that picture being where the last session believed the
railroad was rather than where it now stands. A person moves it with `tc49/ui/run_wanted`, and while it is `held`
the dispatcher **commits nothing**: the grant phase applies its buffered
sensors and stops, so no route is chosen, no move granted and no lock taken,
while admission goes on accepting and queuing. An outstanding move still
completes and releases its locks — the hold is a brake and not an emergency
stop, nothing on the bus retracting a `cross` already sent — and every
signalled end shows `stop` for as long as it lasts. Releasing sets the word
and nothing else; the next boundary grants
([ADR-0037](adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).

**The layout can hold it too.** `tc49/layout/state/power` arriving as anything
but `on` sets the word to `held`, by the path the gesture takes: nothing more
is committed, and no signalled end goes on showing `clear` over track with no
volts in it. Which of `stopped` and `off` it is changes nothing here. Power
returning to `on` releases nothing — the operator presses GO — and a
`run_wanted` of `running` is **dropped** while it is anything else, releasing
into dead rails being how the next train is stranded like the first. A hold is
honoured whatever the power is doing
([ADR-0041](adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).

**It alone reads `tc49/ui/placement_wanted`**, a person saying where a train
actually stands. Whether the block is free is knowledge only it has, so a
second reader would have to agree with it on every precondition. Accepted
while held, for a known train, into a block that exists, fits the train and is
free of every claim — no lock, and on no committed route, which under
`Incremental` are not the same set — and only where that train has no request
in flight; anything else is dropped in silence and to the trace. Having accepted, it moves the train's
standing lock and publishes `train_placed`, which the scheduler follows to
carry facing into the new block and the layout interface to move the steel
under it.

**While held it publishes what the detectors dispute**, on `state/disputed`:
the trains its placement stands in a block the layout reports clear, and the
blocks the layout reports occupied with nothing claiming them. On power-up
the detectors assert at once, anonymously, at the moment a restored placement
is least trustworthy, and naming the two contradictions turns walking the
whole railroad into checking a handful of trains. The set **resolves
nothing**, no sensor saying *which* train: a person ends each entry with a
`placement_wanted`, and it empties as they do. Only blocks the layout has
actually reported on take part. **Silence is not a clear reading**, and a
binding that reports no occupancy at all disputes nothing rather than
disputing the whole railroad. A train the picture says is crossing takes no
part either, standing in no block. Releasing the hold with entries
outstanding is allowed, the person deciding rather than the check, and
empties the set: a running dispatcher's placement is what its sensors have
just told it ([#153](https://github.com/rails49/control/issues/153)).

It is also the **sole payload authority**: a browser can publish anything on
an inbound topic, and after the relay is deleted nothing stands in front
of it, so the dispatcher never raises on a bus payload. A request naming a
train or a block that does not exist is answered `unknown_train` or
`unknown_block`; one carrying a readable id and otherwise not a request is
answered `malformed`; one with no readable id is dropped, there being nothing
to address an answer to, and is already in the trace by virtue of having been
published
([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

The dispatcher is the deep module and the research core; its semantics are
[DISPATCH.md](dispatcher/DISPATCH.md) and [SAFETY.md](dispatcher/SAFETY.md), its internals
[dispatcher/INTERNALS.md](dispatcher/INTERNALS.md). At this boundary it is **fully
asynchronous**: requests arrive as events and every fate is announced as an
event — `request_admitted`, `request_rejected` (at admission or at first
launch attempt), `request_completed` — with the request id as correlation
and idempotency key (duplicate request events are dropped). A request
stating a departure block its train is not standing in is one of those
fates, answered `wrong_origin` rather than raised, because the submitter
may be a browser
([ADR-0021](adr/0021-a-bad-request-is-answered-not-raised.md)). Sensor events
are **buffered until the boundary**, then treated as a set with the canonical
grant order applied to the whole of it, so grants are a pure function of the
buffered set, never of delivery order — and under MQTT a straggling sensor
is processed at the next boundary: a deferred grant, conservative and safe.
Every signalled block end's aspect goes on the last-value
`state/aspects` topic, republished whenever any of them changes: signal heads,
the panel and a person driving by eye are audiences that are not the automated
driver, and a late subscriber wants the whole picture rather than the next
change ([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
An end nothing ever leaves carries no signal and does not appear.

Granted moves are published one event each (`move_granted`), distinct from
the `lock_granted` ledger — the move is the driver's command; the ledger
feeds the utilization metric, and a `FullRoute` launch locks a whole route
in one grant while granting one move. At startup, having seeded its lock
table from the scenario, the dispatcher publishes each train's standing
lock as `lock_granted` — the trace must carry initial occupancy, or the
utilization metric is blind to idle trains.

### Driver

*Reads* nothing. *Subscribes* `tc49/dispatch/move_granted`. *Publishes*
`cross`.

The driver is a **stateless, layout-blind translator**: per granted move it
immediately publishes `cross`, the move itself, mirrored. Setting the route is
the dispatcher's, which publishes `align`
([ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md)), so a grant is
the driver's green signal. The grant now carries the aspect, and the driver
ignores it: turning an aspect into a speed needs `cross` to carry one and
transits to take time, which milestone 1 defers
([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md),
[MILESTONE-1.md](MILESTONE-1.md)). The move payload carries every field `cross` needs,
so the driver holds no state and reads no assets. It does
not subscribe to the boundary — the N+1 skew is the boundary's property, and
duplicating it here would land grants at N+2. The boundary stays real by
footprint, not thickness: a **human driver** drops in by consuming grants as
a display and publishing nothing (sensors remain the sole truth), and a
future realistic-driving component fattens the driver behind the same topic.

### Layout interface

*Reads* the layout and the scenario (initial train placement). *Subscribes*
`tc49/drive/+`, `tc49/dispatch/align` and `tc49/dispatch/train_placed`.
*Publishes* the boundary, the sensor events and `state/power`.

The layout interface is the app's edge: **commands in, observations out**,
plus ownership of time. Its outbound vocabulary is exactly what hardware can
implement — anonymous occupancy sensors, track power and the boundary; it never asserts
train identity, which detectors cannot honestly report (the dispatcher
recovers identity from its own lock table). Commands are **transit-level**: an
`align` names a connection and a transit, and carries the points that transit
needs as address-and-position pairs, so an adapter throws what it is told and
holds no table of its own. Those pairs are carried by the layout, derived from
the drawing's addresses
([ADR-0031](adr/0031-the-layout-carries-the-points-a-transit-needs.md)),
rather than kept by an adapter.

One **obligation** comes with them: the layout interface must not act on a
`cross` before the `align` naming the same transit. The two commands now have
two publishers, and the bus refuses cross-topic ordering, so nothing upstream
can promise the route is set before the train moves — but a train started onto
points that have not thrown is a collision, so the duty has to sit somewhere
and this is the only component that sees both. How it is held is the binding's
own business: the simulator gets it free by batching commands to its tick, a
hardware adapter pairs them. What stays private hardware configuration is the
control loop that executes a `cross` (throttle up, watch the detector, stop). The milestone-1 **simulator** applies `align` and
`cross` directly at the next tick, and owns pacing and termination: it stops
advancing when the scheduler is `exhausted` and a tick's cascade
produced no commands ([BENCHMARKS.md](bench/BENCHMARKS.md#termination)). That stop
rule is milestone-1 pacing, not bus contract — a hardware adapter never
terminates. Sensor events report moves only: initial occupancy is never
published — the dispatcher seeds its standing locks from the scenario, and
the occupancy topics are event topics, facts that happened, not state.

**Track power** is the one observation that is not a sensor: `state/power`
says whether a train may move at all, `on`, `stopped` or `off`. It is stated
from the binding's constructor, always, so a joining client is served the word
rather than left to read one out of an absence
([ADR-0032](adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
`stopped` is an emergency stop and `off` is the supply removed; they differ
for the person recovering and not for the dispatcher, which holds the run on
either ([ADR-0041](adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
Commanding power is not here: today the operator's ON is a physical action,
and an emergency stop worth the name is a hardwired contact rather than a
message. The milestone-1 **simulator** publishes `on` and never changes it,
simulated track being always live (ADR-0030).

`train_placed` is the one thing besides a `cross` that moves a train, and what
a binding does with it is its own business: the simulator stands in for steel
that would simply be where a hand left it, so it is told where the hand put
it. Not a command — nothing is buffered, and no boundary moves.

It comes with a **standing assumption** about the sensor stream, which
milestone 1 makes and does not yet enforce: every sensor event explains a move
the dispatcher granted. The dispatcher recovers train identity from its lock
table, so a `block_occupied` no grant accounts for — a hand putting a
locomotive on a detected block, or a train pushed while the power was off — is
not something it can read, and it raises rather than guessing. The simulator
publishes no sensors for a placement, which is what makes the gesture safe
today. A layout that detects occupancy will need the dispatcher told what an
unexpected sensor means, and that is still open: track power
([ADR-0041](adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md))
answers the observation and not the assert, so a `block_occupied` no grant
accounts for still raises at the next boundary. The **dispute check** is not
that answer either: it records every reading as it arrives, explained or not,
and compares — comparing commits nothing. What the *boundary* then does with a
reading no grant accounts for is the half still open.

### Asset store

*Serves* the CRUD contract above. It is not a bus participant: it publishes
nothing and subscribes to nothing, which is precisely why it exists as a
second contract — components need answers to queries, and the bus refuses
request/reply.

### Beyond milestone 1

The contracts above are what milestone 1 builds, and they are not final.
[GOALS.md](GOALS.md) describes the whole system; three decisions still grow
these contracts, and they are listed here so no footprint above is read as the
last word. A fourth has already landed: the scheduler reads the layout and
subscribes `tc49/dispatch/#`, spent early on holding facing rather than on a
generator ([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)).

| Growth | Why | Where |
| --- | --- | --- |
| `cross` carries a **speed** | the driver decides how fast; the layout interface keeps throttle-up-watch-the-detector-stop, where the braking curve and detector geometry live | same |
| The scheduler **invents traffic** | continual generated traffic has to name an idle train and a reachable destination, which is what it now reads the layout for; the dispatcher stays the single feasibility authority | [ADR-0028](adr/0028-the-scheduler-knows-where-trains-stand.md) |
| The boundary event's cadence comes from a **clock**, transits vary in length | `tick` is the simulator's beat behind the boundary, not the model's unit of time | [ADR-0027](adr/0027-the-tick-is-the-simulators-grant-boundary.md) |

None of the three adds a role, a writer, or a query — which is the point.
Every one lands on a topic that already exists or a state topic under a role
that already writes there, so the single-writer rule, the event/state split
and the prefix-filter rule survive without amendment.

The growth that did not manage this is worth naming, since the claim above was
once made of it too: taking a person's gesture off a page added the `ui` role,
a topic and an inbound path, and rule 1 had to be restated in terms of roles
rather than components to admit two browser tabs at all
([ADR-0035](adr/0035-a-topic-has-one-writing-role.md)). The event/state split
survived untouched, and did the diagnostic work.

Locking two blocks ahead instead of one
([ADR-0026](adr/0026-two-blocks-ahead-is-full-speed.md)) appears nowhere in
this table, because it is not a contract change at all: it is a parameter of
the incremental strategy behind the seam of
[ADR-0005](adr/0005-seam-at-locking-strategy.md).

## The trace

The trace is a **tap on the bus**: a subscriber to `tc49/#` that writes one
JSONL line per delivered event, in delivery order — deterministic under the
milestone-1 queued-FIFO bus. There is no bespoke trace channel; the events
the trace records are the same events the components exchange, so a future
UI subscribes to exactly what the trace already proves sufficient.

Each line is flat: `{"boundary": …, "event": …, …payload}`, with `event` set
to the topic's leaf (globally unique, per the inventory invariant) and
`boundary` stamped by the tap from the last boundary number it observed — `0`
for events delivered before the first boundary event, such as the startup
standing locks. Key order is canonical — `boundary`, `event`, then the event's
fields in inventory order — which is what makes the determinism property a
byte compare
([ARCHITECTURE.md](ARCHITECTURE.md#tests)). A payload field outside the
inventory fails loudly, which is a promise about what the **apps** write:
on the topics a client writes the tap records what it was given — the
inventory's fields in order, then anything else, and a payload that is not
an object under `payload` — since that line is the whole record of a frame
the dispatcher drops
([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

`metrics(trace)` stays a pure function of the trace, and the trace stays
**load-bearing**: every metric derives from recorded events — makespan from
`request_admitted`/`request_completed` stamps, latency likewise,
utilization from `lock_granted`/`lock_released` spans, parallelism from
`cross` commands per boundary, and the stall report from the last
`grant_refused` per never-completed request — so an event that stops being
emitted breaks a metric and fails a test rather than rotting quietly. The
derivations live in [bench/METRICS.md](bench/METRICS.md).
