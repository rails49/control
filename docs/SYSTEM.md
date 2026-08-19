# System

How the app is organized: four components — asset store, scheduler, dispatcher,
driver — plus the external **layout interface**, communicating over an event
bus and an asset CRUD contract. This page fixes those contracts. An implementer
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
```

- **Scheduler** — turns the scenario's request list into request events,
  released at their `at` ticks.
- **Dispatcher** — admits requests, chooses routes, grants moves
  deadlock-free; the research core ([DISPATCH.md](dispatcher/DISPATCH.md),
  [SAFETY.md](dispatcher/SAFETY.md)).
- **Driver** — turns each granted move into the command that moves the train.
- **Layout interface** — the boundary to whatever runs the track: sensor
  readings and the tick come out, turnout and throttle commands go in. A
  simulator implements it in milestone 1, a hardware adapter later.
- **Asset store** — serves the layout and scenario documents; the one
  contract that is not the bus, because it answers queries and the bus
  refuses to.

These are **roles, not implementations**. Each names a boundary any
implementer can stand behind unchanged: the simulator and a hardware adapter
publish the same layout topics, and a future scheduling UI or freight
generator publishes the same schedule topics the milestone-1 scheduler does.

One cycle of the machine: the layout interface publishes the tick; the
scheduler releases the requests that have come due; the dispatcher runs its
grant phase over everything buffered since the previous tick and publishes
granted moves, publishing `align` for each so the route is set before anything
moves; the driver turns the grant it sees into a `cross`; the layout interface
executes both and reports occupancy, which the dispatcher buffers for the next
tick. The trace tap watches all of it.

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

1. **Single writer** — exactly one component publishes on any topic, which
   upgrades the ordering promise to plain per-topic FIFO and makes ownership
   checkable by inspection.
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
breadth-first shape forecloses the same-tick-causality habit the contract
refuses, since nested synchronous delivery would grant exactly what MQTT
never will.

**Milestone-1 bridge.** Until the bus is a real broker, a browser reaches it
over a WebSocket relay ([ui/PANEL.md](ui/PANEL.md#implementation)): every
`tc49/#` event goes out to every client as one JSON frame,
`{"topic": …, "payload": …}`, and the one inbound topic is
`tc49/schedule/request_submitted`, whose frame is published as the event it
names. Any other inbound frame — another topic, or not `{topic, payload}`
JSON — is answered with an `{"error": …}` frame and never reaches the bus.
The relay adds no topics and no payload fields: the frame is the event, so
the inventory below is its entire schema. When MQTT arrives the browser
speaks MQTT-over-WebSocket to the broker and the relay is deleted.

## Event inventory

Topics are `tc49/<role>/<leaf>`, **publisher-first**: the second segment
names the role that writes there — `layout`, `schedule`, `dispatch`, `drive`
— so rule 1 is verifiable from the name alone, `tc49/layout/*` keeps its
meaning when hardware replaces the simulator, and a future UI gets
`tc49/dispatch/#` for free. Leaves are past-tense facts, with two exceptions:
the two commands are imperative (`align`, `cross` — past tense would
be a lie, the command precedes the crossing), and `tick` is the sole noun
leaf, naming a beat rather than a change. `align` sits under `dispatch`
because the dispatcher writes it: setting the route is its responsibility, and
the driver moves locomotives
([ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md)).

| Topic | Kind | Publisher | Payload gist |
| --- | --- | --- | --- |
| `tc49/layout/tick` | event | layout | deterministic counter |
| `tc49/layout/block_occupied` | event | layout | block |
| `tc49/layout/block_vacated` | event | layout | block |
| `tc49/schedule/request_submitted` | event | scheduler | id, train, depart, dest ends |
| `tc49/schedule/state/exhausted` | state | scheduler | last-value flag |
| `tc49/dispatch/request_admitted` | event | dispatcher | id, surviving dest ends, pruned |
| `tc49/dispatch/request_rejected` | event | dispatcher | id, reason (`no_fit`, `no_entry`, `unreachable`, `wrong_origin`) |
| `tc49/dispatch/request_completed` | event | dispatcher | id |
| `tc49/dispatch/route_chosen` | event | dispatcher | id, route, k_tried |
| `tc49/dispatch/move_granted` | event | dispatcher | id, train, transit, into |
| `tc49/dispatch/grant_refused` | event | dispatcher | id, reason (`unsafe`, `held`, `transit_conflict`), obstacles `[{resource, holder}]` |
| `tc49/dispatch/lock_granted` | event | dispatcher | train, resources |
| `tc49/dispatch/lock_released` | event | dispatcher | train, resources |
| `tc49/dispatch/align` | command | dispatcher | connection, transit, points `[{addr, position}]` |
| `tc49/drive/cross` | command | driver | train, connection, transit, into |

| Consumer | Filter(s) |
| --- | --- |
| Scheduler | `tc49/layout/tick` |
| Dispatcher | `tc49/layout/+` **and** `tc49/schedule/request_submitted` |
| Driver | `tc49/dispatch/move_granted` |
| Layout interface | `tc49/drive/+` **and** `tc49/dispatch/align` |
| Trace tap | `tc49/#` |

Two invariants the inventory must maintain:

- **Leaf names are globally unique** across all topics — the trace's `event`
  field is the leaf alone and depends on it.
- **Consumers subscribe by prefix filter only** (rule 3). The dispatcher's
  two filters are the accepted maximum; a consumer needing a list of
  individual topics is a design smell.

**Payload conventions.** Correlate by request id, don't repeat: lifecycle
events carry the id plus only what is *new* — `request_rejected` drops
`depart`/`dest` (recoverable from `request_submitted`), `request_admitted`
keeps surviving ends and `pruned` because those are new facts.
`lock_granted`/`lock_released` carry `train` rather than the id, since the
utilization metric groups by resource. `request_completed` carries no
latency — the dispatcher has no clock to compute one with; metrics derives
it from the trace's tick stamps. `grant_refused` carries one
`{resource, holder}` entry per candidate route blocked — one entry when
advancing a fixed route, up to `k` at a launch — which is what lets the
stall report of [BENCHMARKS.md](bench/BENCHMARKS.md#termination) be derived rather
than stored.

Payloads are gists, not field schemas. Field-level schemas are deferred
until a second consumer exists.

## Time

**The layout interface owns time**
([ADR-0009](adr/0009-layout-interface-owns-time.md)). It publishes
`tc49/layout/tick`; the four app components only ever subscribe, which keeps
every one of them clock-free — the dispatcher never learns what tick it is.
In milestone 1 the simulator advances the tick only when the bus is quiescent
(queue drained); that is loop-owner pacing, not a bus-contract promise.
Advancing means: execute the pending commands, publish their sensor events,
**then** publish the tick — a tick's sensors precede the tick itself, so the
grant phase the tick triggers finds them in its buffered set. Publishing the
tick first would slip every grant by a tick. A
hardware adapter later picks its own cadence behind the same event: the
publisher swaps, the contract doesn't.

**The tick event is the grant boundary.** There is no separate boundary
event. On each tick the scheduler releases requests that have come due, the
dispatcher runs its grant phase over the sensor events buffered since the
previous tick ([DISPATCH.md](dispatcher/DISPATCH.md#time-model)), and the driver takes
granted moves forward. Under queued-FIFO delivery, everything published in
reaction to tick `N` lands after the dispatcher has already handled tick `N`,
so it is granted at tick `N+1` — the one-tick skew the dispatch model's
no-same-tick-handoff rule describes.

**The tick carries its number; nothing else does.** The payload is a plain
deterministic counter minted by the topic's single writer — required by the
at-least-once mindset, since a bare tick consumed by counting would
double-advance on a duplicate, while a numbered one makes duplicates
trivially ignorable. No other event carries a tick field: the trace tap
stamps each recorded event with the latest tick number it has observed,
deterministic in milestone 1 because the tap sees everything in delivery
order. The scheduler consumes the number (it is how requests come due at
their `at` tick); counting a bus event is not reading a clock.

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

*Reads* the scenario. *Subscribes* `tc49/layout/tick`. *Publishes*
`request_submitted` and the `state/exhausted` last-value topic.

The scheduler is **layout-blind and tick-only**. It releases the scenario's
requests at their `at` ticks, performing only the *mechanical* arrival-end
expansion (`to: [yard_e]` → `yard_e.A, yard_e.B` — pure syntax, no layout
needed), and mints each request's **id deterministically in scenario order**
(e.g. `<train>-1`, `<train>-2`) — never clock-derived, since byte-identical
replay forbids clock-derived fields anywhere on the bus. All semantic
checking — departure-end consistency, `no_fit`/`no_entry` pruning,
reachability — belongs to the dispatcher at admission, leaving one
feasibility authority instead of two. Completions and rejections are noise
to it in milestone 1: the scenario is a fixed schedule. That thinness is
deliberate — this scheduler is the honest template for a future scheduling
UI or freight generator: publish intents, let the dispatcher judge. When its
last request is out it sets `exhausted`, the milestone-1 termination signal.

### Dispatcher

*Reads* the layout, and from the scenario its stock — train lengths for the
admission fit check, initial placement to seed the standing locks. Neither
fact can come off the bus: sensors are anonymous, so the lock table the
dispatcher recovers identity from must be seeded before the first sensor
event, and `request_submitted` carries no length. *Subscribes*
`tc49/layout/+` and
`tc49/schedule/request_submitted`. *Publishes* the eight `tc49/dispatch/*`
events.

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
are **buffered until the tick**, then treated as a set with the canonical
grant order applied to the whole of it, so grants are a pure function of the
buffered set, never of delivery order — and under MQTT a straggling sensor
is processed at the next boundary: a deferred grant, conservative and safe.
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
the driver's green signal. The move payload carries every field `cross` needs,
so the driver holds no state and reads no assets. It does
not subscribe to the tick — the tick+1 skew is the boundary's property, and
duplicating it here would land grants at N+2. The boundary stays real by
footprint, not thickness: a **human driver** drops in by consuming grants as
a display and publishing nothing (sensors remain the sole truth), and a
future realistic-driving component fattens the driver behind the same topic.

### Layout interface

*Reads* the layout and the scenario (initial train placement). *Subscribes*
`tc49/drive/+` and `tc49/dispatch/align`. *Publishes* the tick and the sensor
events.

The layout interface is the app's edge: **commands in, observations out**,
plus ownership of time. Its outbound vocabulary is exactly what hardware can
implement — anonymous occupancy sensors and the tick; it never asserts train
identity, which detectors cannot honestly report (the dispatcher recovers
identity from its own lock table). Commands are **transit-level**: an `align`
names a connection and a transit, and carries the points that transit needs as
address-and-position pairs, so an adapter throws what it is told and holds no
table of its own. The transit-to-turnout-positions table is built from the
drawing ([ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md)) rather
than kept by an adapter. What stays private hardware configuration is the
control loop that executes a `cross` (throttle up, watch the detector, stop). The milestone-1 **simulator** applies `align` and
`cross` directly at the next tick, and owns pacing and termination: it stops
advancing ticks when the scheduler is `exhausted` and a tick's cascade
produced no commands ([BENCHMARKS.md](bench/BENCHMARKS.md#termination)). That stop
rule is milestone-1 pacing, not bus contract — a hardware adapter never
terminates. Sensor events report moves only: initial occupancy is never
published — the dispatcher seeds its standing locks from the scenario, and
the occupancy topics are event topics, facts that happened, not state.

### Asset store

*Serves* the CRUD contract above. It is not a bus participant: it publishes
nothing and subscribes to nothing, which is precisely why it exists as a
second contract — components need answers to queries, and the bus refuses
request/reply.

## The trace

The trace is a **tap on the bus**: a subscriber to `tc49/#` that writes one
JSONL line per delivered event, in delivery order — deterministic under the
milestone-1 queued-FIFO bus. There is no bespoke trace channel; the events
the trace records are the same events the components exchange, so a future
UI subscribes to exactly what the trace already proves sufficient.

Each line is flat: `{"tick": …, "event": …, …payload}`, with `event` set to
the topic's leaf (globally unique, per the inventory invariant) and `tick`
stamped by the tap from the last tick number it observed — `0` for events
delivered before the first tick event, such as the startup standing locks.
Key order is
canonical — `tick`, `event`, then the event's fields in inventory order —
which is what makes the determinism property a byte compare
([ARCHITECTURE.md](ARCHITECTURE.md#tests)).

`metrics(trace)` stays a pure function of the trace, and the trace stays
**load-bearing**: every metric derives from recorded events — makespan from
`request_admitted`/`request_completed` stamps, latency likewise,
utilization from `lock_granted`/`lock_released` spans, parallelism from
`cross` commands per tick, and the stall report from the last
`grant_refused` per never-completed request — so an event that stops being
emitted breaks a metric and fails a test rather than rotting quietly. The
derivations live in [bench/METRICS.md](bench/METRICS.md).
