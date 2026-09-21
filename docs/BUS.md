# Bus

The contract the components meet over: what the bus promises, every topic and
every payload, the stamp that orders a state topic, and the device vocabulary
the hardware under the layout interface speaks. This page is normative. A
component is implemented from it and from [SYSTEM.md](SYSTEM.md), which holds
the overview, the store's CRUD contract, each component's footprint and the
trace.

Every topic here names a `control` component as its writer, so the definition
lives in this repository; a project that shares the bus is a client of this
railroad rather than a co-owner of the contract
([ADR-0006 in `rails49/.github`](https://github.com/rails49/.github/blob/main/docs/adr/0006-the-bus-contract-is-controls-and-travels-when-something-reads-it.md)).
The first reader outside this repository takes a copy with the commit
recorded, and the contract gains a machine-readable inventory at that point,
not before.

`tc49.lib.bus` and `tc49.lib.mqtt` are this repository's binding of the page —
the interface an app is handed, and its two transports. A binding in another
language implements this page rather than porting Python:
`ui/src/model/trace.ts` already is one. The decisions behind the contract are
[ADR-0008](adr/0008-bus-contract-is-the-mqtt-safe-intersection.md) and
[ADR-0009](adr/0009-layout-interface-owns-time.md). Terminology follows
[CONTEXT.md](../CONTEXT.md).

## The bus

Components talk to each other by publishing JSON events on named topics and
subscribing to the topics they care about. The bus has **two bindings and
neither supersedes the other**: a deployed app is a client of an MQTT broker,
one broker to a railroad, and the bench harness wires its apps on a Python
object inside one process. Each exists for one use — the broker because an app
is its own container and hardware speaks the bus from off the box, the
in-process object because byte-identical replay is what the harness is for
([ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 1).

That both are one bus rests on the contract promising only what MQTT also
promises, even where the in-process binding could easily do more
([ADR-0008](adr/0008-bus-contract-is-the-mqtt-safe-intersection.md)). Nothing
below distinguishes the two; where a binding shows through, it is named.

The bus promises:

- **Order from one publisher** — events that one writer sends on one topic
  are delivered in the order it sent them. Nothing more is promised: no order
  between two writers, and none between two topics. Each topic has a single
  writer, below. MQTT promises no more either, and rather less than it looks:
  a broker keeps a topic ordered per publisher and per QoS while it is
  configured to, and not across that publisher's reconnect or a
  retransmission with more than one message in flight.
- **Fan-out** — every subscriber whose subscription matches the topic gets the
  event, independently of the others.
- **At-least-once delivery** — the bus may deliver the same event twice, so a
  consumer must handle a repeat without changing its answer.
- **State topics keep their last value** — a subscriber that connects late is
  given the most recent value published on a state topic. MQTT calls these
  retained messages.
- **MQTT topic names** — levels separated by `/`, with `+` and `#` as
  wildcards in a subscription.

The bus does not offer the following. Each would be easy to add in process,
and is left out because code that came to depend on it would break the day
MQTT arrives:

- no request that returns an answer,
- no confirmation that an event was delivered,
- no ordering between one topic and another,
- no replay of past events to a late subscriber, apart from the last value on
  a state topic,
- no queue that grows without limit.

A component that needs an answer to a question does not use the bus. The asset
store answers questions, and exists for that reason.

**A state topic does not depend on that order.** A state topic keeps the last
message published on it, so a pair the wire hands over backwards would leave
the *older* value standing for good — the track reading dead while it is
live, or a signal showing aspects the railroad has moved on from. Every state
payload therefore carries a **stamp**, `at`, the run clock's reading when the
value was published, and every consumer of one keeps the later stamp and
ignores the earlier, whoever published it: equal replaces, and an unstamped
value is accepted and clears the held stamp so that ordering restarts from
the next stamped one. Nothing is raised either way.

The **binding stamps, not the app**: the thing that publishes reads the clock,
so no app component reads one (ADR-0009), and an `at` a caller supplied is
replaced by the one publishing it. No event payload carries a stamp and none
needs one — a detector reports a level, so a repeat re-asserts what a consumer
holds, and a request is keyed by a unique id, so duplicates drop.

`at` orders messages **within one run and says nothing across a restart**. On
the in-process binding the clock is seconds since the run started and resets
to zero every time, so a stamp carried out of the last run would beat every
genuine report the new one makes for as long as the old run was long; on the
broker it is wall time, processes sharing no run clock (ADR-0059 decision 1).
Either way what a restart adopts is a starting assumption, and the first real
report supersedes it (ADR-0030).

**Four rules govern the topics listed in the next section.**

1. **Single writer.** For the events a component emits and its state topics,
   the component the topic names is the only writer — `layout`, `schedule` or
   `dispatch`, a component rather than a particular process. With a single
   writer, that writer's own order is the topic's order, and a reader can see
   which component is responsible for a topic by reading the topic's name.

   A topic that carries **requests to** its component is the other way
   around: one responder, any number of writers — that is what it is for.
   Two browser tabs both send gestures, and the scheduler and a page both
   submit requests. Several writers may publish on an event topic, as long
   as no consumer depends on which of them published first. They must not
   publish on a state topic. A state topic keeps only the last message, and
   a publisher has to supply the whole value, so a writer that knows about
   one train replaces what another knew about the rest
   ([ADR-0035](adr/0035-a-topic-has-one-writing-role.md)).
2. **A topic is either an event topic or a state topic, never both.** An event
   topic reports something that happened, and is never replayed. A state topic
   holds a current value, of which only the last one published survives. Every
   topic is declared as one or the other, and a state topic says so in its name
   (`tc49/<component>/state/<name>[/<address>…]`). The mark is where it is
   rather than where the name ends, because a name may go on past it: a device
   row carries its address as trailing levels
   ([ADR-0043](adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)),
   and `tc49/layout/state/wanted/point/<addr>` is a state topic like
   any other.
3. **Prefix-filter consumption.** Each consumer subscribes with a small fixed
   set of prefix filters under `tc49/`, written with `+` and `#`, rather than
   naming individual topics.
4. **Any source.** The bus does not authenticate a publisher: a topic's name
   says who answers it, not who can write it. A request addressed to a
   component discloses its source nowhere — not in the topic, not in the
   payload — so a responder never reads, infers, or depends on who sent one.
   A consumer therefore validates
   every payload it reads and never raises on one — a payload proves nothing
   about its sender
   ([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md),
   [ADR-0035](adr/0035-a-topic-has-one-writing-role.md)). What a failed read
   is worth is the consumer's own rule: an answer where the payload carries an
   id, a drop where it does not, and `state/power` failing towards `off`
   ([#181](https://github.com/rails49/control/issues/181)).

   **A recorder on a bus where every publisher is in the same process may
   fail loudly.** The rule exists because anything at all can publish on a
   shared bus, so a consumer cannot trust what arrives. An instrument reading
   a bus inside one process has no such publishers: everything on it is our
   own code, a payload outside the inventory there is our own bug, and
   failing on it is an assertion rather than a fault. That is the trace tap
   (`lib/trace.py`), which runs in `bench` and in the suite and nowhere else
   ([#421](https://github.com/rails49/control/issues/421)).

   **A recorder that watches a broker may not**, and must record what it can.
   The moment an instrument reads a bus anything can publish on, the reason
   for the exception is gone and the rule binds it like every other consumer.

**The inventory is open.** A new topic, a new *optional* field on an existing
payload, or a new value in an enum whose readers declare a fallback
(CONTEXT.md) is a compatible change: one communication issue
(docs/agents/issue-tracker.md), and a consumer built before it keeps working,
because a consumer ignores fields it does not recognize. Removing, renaming
or repurposing a field or a topic, or making an optional field required,
breaks consumers and needs the stronger argument. A field can leave and come
back the same way: `at` was dropped from the request and returns, if it does,
as one communication issue once its requirements are understood — a different
field from the stamp every state payload carries, which says when a value was
published rather than when a request wants its train to run. An added
field still changes the trace, so recorded fixtures regenerate — a cost each
addition pays, not breakage.

**How the in-process binding works.** One thread and one queue. `publish()`
adds the event to the queue and returns. A loop takes events off the front and
delivers each one to its subscribers, in the order they subscribed. An event
published inside a handler goes to the back of the queue, so it is delivered
after everything already waiting.

Delivery order therefore depends only on the order of publishes and
subscribes, which is what makes a replayed run produce a byte-identical trace
([ARCHITECTURE.md](ARCHITECTURE.md#tests)). It also means an event published
while another is being handled is never delivered before that handling has
finished: MQTT would never deliver it any sooner.

**The last value of a state topic survives one app's restart.** It is the
broker that holds it: a state topic is published retained, so an app coming
back up finds its own last value waiting on its own topic. Whether to use it
is each app's own decision, and they differ: the dispatcher takes back its
train placement and the scheduler its facing, the dispatcher's queue is not
restored, and no request id ever resumes
([ADR-0033](adr/0033-a-request-id-is-unique-not-meaningful.md)).

Nothing survives the **broker's** own restart. `persistence false`
(`deploy/mosquitto.conf`) is deliberate: a retained speed that outlived a
power cut is a train that moves when the broker comes back, and the railroad
comes up at rest instead
([ADR-0054](adr/0054-the-railroad-comes-up-at-rest-and-points-replay.md),
[ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 3). The in-process binding keeps its retained values in memory and
loses them with the process, which is what leaves `bench` and `sweep`
unaffected.

**Reaching the bus from a browser.** A page is a client of the broker like
any other, over the broker's own WebSocket listener, reached on the app's own
origin as `/mqtt` through the proxy in front of it
([ui/PANEL.md](ui/PANEL.md#implementation), [DEPLOY.md](DEPLOY.md)). It
subscribes `tc49/#` and publishes the browser-writable rows. There is no
relay, no frame format of its own and no railroad in a path: one broker runs
one railroad, and a view reads which from `tc49/layout/state/railroad`
([ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 4).

**A socket from a page on another origin is refused.** A handshake carrying an
`Origin` header is answered 403 before the upgrade, and no socket exists,
unless the origin's host is the router's own host. A handshake with no
`Origin` is a native client and goes through, as it does at the store's face,
and a native client on 1883 does not pass this way at all. A WebSocket has no
preflight, so this check is the whole of what stands between a page somebody's
browser visits and the gestures above. Mosquitto has no `Origin` setting, so
the rule is stated in front of it as a proxy middleware on `/mqtt`
(`deploy/routes/*/site.yaml`) rather than in an app
([ADR-0056](adr/0056-the-browsers-way-onto-the-bus-refuses-a-foreign-origin.md),
[ADR-0042](adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)).

**Which topics a page publishes on is convention, not enforcement.** With
anonymous clients a broker cannot tell a page from an app, and the LAN is
already the trust boundary, so nothing checks the topic of an inbound publish.
What a page may write is the inventory's browser mark, and what a page must
not write it does not: `tc49/dispatch/request_submitted` is the scheduler's,
so "only the scheduler writes requests" rests on the app boundary rather than
on a check
([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md),
[ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 4). Payload checking is unchanged and belongs where it always did:
the dispatcher, when it admits a request, which never raises on anything that
arrives from the bus
([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

## Event inventory

A topic is named `tc49/<component>/<leaf>`: `layout`, `schedule` or
`dispatch`. The component comes first because it is the component that
**declares** the topic — the events it emits, and the requests it responds
to. Naming topics this way means rule 1 can be checked by reading the name,
`tc49/layout/*` keeps its meaning when hardware replaces the simulator, and a
UI that wants everything the dispatcher says subscribes to `tc49/dispatch/#`.

A leaf names something that has happened, in the past tense. The two
commands, `align` and `move`, are the exception: they are imperative, because
a command is sent before what it asks for happens. They sit under `layout`
because the layout interface is what responds to them; setting the route is
still the dispatcher's job, and moving locomotives the driver's, which is who
sends each — a fact the names no longer carry (rule 4,
[ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md)).

**A row marked `browser` is one any page may publish on.** The list of
topics a client may publish on is read off this table's mark rather than
written down a second time, so marking a row widens the browser's write
surface the day the mark lands, and the mark is the permission a broker's ACL
would carry were one built
([ADR-0034](adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md),
[ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 4).
Today the mark sits on exactly the ten gesture rows. The throttle a person
drives with ([#207](https://github.com/rails49/control/issues/207)), the
track power a person commands
([ADR-0051](adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)),
the railroad a person loads
([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md))
and the firmware a person writes to the command station
([ADR-0065](adr/0065-the-app-that-owns-the-device-flashes-it.md))
are five of them, under `layout`, which is the component that responds to
them. Whether a row carries the mark is an ACL decision, made when the row
lands.

**Writer** is the component the name already states for everything a
component emits. On a request row it is `any`: one responder, any number of
writers (rule 1), and `any (browser)` is the mark above.

| Topic | Kind | Writer | Meaning |
| --- | --- | --- | --- |
| `tc49/layout/state/railroad` | state | layout | the railroad this broker runs ([ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)) |
| `tc49/layout/railroad_wanted` | event | any (browser) | load this railroad, the apps staying up ([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)) |
| `tc49/layout/block_occupied` | event | layout | a detector saw a block fill |
| `tc49/layout/block_vacated` | event | layout | a block is empty: both its ends read clear, or the move this app carried out named it the block behind a train now fully into the block ahead ([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)) |
| `tc49/layout/power_wanted` | event | any (browser) | give the track power, stop every locomotive, or remove the supply ([ADR-0051](adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)) |
| `tc49/layout/state/power` | state | layout | whether a train may move at all ([ADR-0041](adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)) |
| `tc49/layout/align` | command | any | set the route: throw these points |
| `tc49/layout/move` | command | any | take the train across, this fast |
| `tc49/layout/mode_wanted` | event | any (browser) | a train is driven automatically, or by a person |
| `tc49/layout/throttle_wanted` | event | any (browser) | how fast a person is driving a train |
| `tc49/layout/state/mode` | state | layout | who drives each train |
| `tc49/layout/firmware_wanted` | event | any (browser) | flash the command station with this build ([ADR-0065](adr/0065-the-app-that-owns-the-device-flashes-it.md)) |
| `tc49/schedule/request_wanted` | event | any (browser) | a gesture: the request minus the id and depart the scheduler owns |
| `tc49/schedule/reversal_wanted` | event | any (browser) | turn a train around where it stands |
| `tc49/schedule/state/exhausted` | state | scheduler | the timetable has run dry |
| `tc49/schedule/state/facing` | state | scheduler | the run each train would make across its block |
| `tc49/dispatch/request_submitted` | event | any | a request, composed and released |
| `tc49/dispatch/run_wanted` | event | any (browser) | hold the run, release it, or drain it |
| `tc49/dispatch/placement_wanted` | event | any (browser) | where a train actually is ([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)) |
| `tc49/dispatch/cancel_wanted` | event | any (browser) | end a train's request without arriving ([ADR-0049](adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)) |
| `tc49/dispatch/request_admitted` | event | dispatcher | admission accepted it, with what survived pruning |
| `tc49/dispatch/request_rejected` | event | dispatcher | admission refused it, and why |
| `tc49/dispatch/request_completed` | event | dispatcher | the train arrived |
| `tc49/dispatch/request_cancelled` | event | dispatcher | the request ended without arriving, and why |
| `tc49/dispatch/route_chosen` | event | dispatcher | the route a launch fixed |
| `tc49/dispatch/move_granted` | event | dispatcher | one transit authorised |
| `tc49/dispatch/grant_refused` | event | dispatcher | a grant blocked, and by what |
| `tc49/dispatch/lock_granted` | event | dispatcher | resources claimed for a train |
| `tc49/dispatch/lock_released` | event | dispatcher | resources released |
| `tc49/dispatch/train_placed` | event | dispatcher | a placement accepted, the standing lock moved with it |
| `tc49/dispatch/train_removed` | event | dispatcher | a train taken off the layout |
| `tc49/dispatch/state/run` | state | dispatcher | held, running or draining, and whether anything is moving ([ADR-0037](adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md), [ADR-0062](adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)) |
| `tc49/dispatch/state/aspects` | state | dispatcher | every signalled end's aspect |
| `tc49/dispatch/state/allocation` | state | dispatcher | the run's whole picture |
| `tc49/dispatch/state/disputed` | state | dispatcher | where the detectors contradict the placement ([#153](https://github.com/rails49/control/issues/153)) |

| Consumer | Filter(s) |
| --- | --- |
| Scheduler | `tc49/dispatch/#` **and** `tc49/schedule/#` |
| Dispatcher | `tc49/layout/#` **and** `tc49/dispatch/#` |
| Driver | `tc49/dispatch/move_granted` |
| Layout interface | `tc49/layout/align`, `tc49/layout/move`, `tc49/layout/power_wanted`, `tc49/layout/railroad_wanted`, `tc49/layout/state/power`, `tc49/dispatch/train_placed` / `train_removed`, `tc49/dispatch/state/aspects`, `tc49/dispatch/state/run`, `tc49/schedule/state/facing` **and** `tc49/layout/state/device/#` |
| Translator | `tc49/layout/state/wanted/#`, **and** `tc49/layout/state/railroad` where it publishes sensors |
| Command station mirror | `tc49/layout/firmware_wanted` |
| Trace tap | `tc49/#` |

The **command station mirror** is the app that owns the station's USB device
and serves it on a TCP port, and the one row it responds to is the flash
gesture: writing the station's flash means owning the port, so the process
holding it is the only thing that can hand the device over
([ADR-0065](adr/0065-the-app-that-owns-the-device-flashes-it.md)). It reads
nothing else on the bus — not the run, not the supply, not the railroad — and
what it publishes is `device/refused/<id>` where it will not flash. Its other
side is not the bus at all
([docs/dccex_usb/README.md](dccex_usb/README.md)).

Every app but the layout interface and the mirror also subscribes
`tc49/layout/state/railroad`, and acts on one thing only: a name other than
the one it is running, which is a railroad being loaded under it (ADR-0060,
above). A translator does so where it reads the store: one publishing
`device/sensor` reads the names the hardware knows those sensors by out of
the drawing, and those are a railroad's (ADR-0063, below). One that reads
nothing does not, hardware needing no layout — and the mirror reads no
document at all, a cable being no railroad's. The layout interface does not
either, being the row's writer: it follows
`tc49/layout/railroad_wanted` instead, which is the gesture it answers. The
binding of it that drives hardware reads back its own
`tc49/layout/state/power` for the precondition on that gesture; a binding that
drives none has no precondition and answers with the rails live, having no
steel that could disagree with the drawing just loaded (ADR-0060 as amended).

Two things the inventory has to keep true:

- **A leaf name is unique across all topics.** The trace records the leaf
  alone in its `event` field, so two topics sharing a leaf could not be told
  apart there.
- **A consumer subscribes by prefix filter, not by list** (rule 3), and
  ignores what a filter brings that it does not answer. A component's own
  filter now matches its own announcements: the dispatcher's `tc49/layout/#`
  brings it the two commands, its `tc49/dispatch/#` everything it publishes
  itself, and the scheduler's `tc49/dispatch/#` brings `request_submitted`,
  its own included. Ignoring an unrecognized leaf is rule 4 doing its
  ordinary work. The layout interface is the one exception to the
  prefix-filter shape and stays the only one. It names the topics it acts
  on — the two commands, the power a person presses, the two placement facts
  and the dispatcher's aspects — because a `tc49/layout/#` filter would hand
  it back its own sensors and its own device writes, and subscribing to the
  whole of `dispatch` would mean discarding most of what it heard. Its one
  prefix filter is `tc49/layout/state/device/#`, the observed half of the
  vocabulary below, which is a filter of the ordinary shape: the addresses
  under it are a railroad's wiring and cannot be listed.

**What a payload carries.** Events are tied together by the request id, and
no event repeats what another has already said. An event in a request's life
carries the id and only what is *new*: `request_rejected` leaves out `depart`
and `dest`, which a reader can take from `request_submitted`, while
`request_admitted` carries the surviving ends and `pruned`, which are new.

`lock_granted` and `lock_released` carry `train` rather than the id, because
the utilization metric groups by resource. `request_completed` carries no
latency: the dispatcher has no clock to measure one, so metrics works it out
from the time stamps the trace carries. `grant_refused` carries one
`{resource, holder}` entry for each candidate route that was blocked, which is
one entry when a fixed route advances and up to `k` at a launch. That is what
lets the stall report of
[BENCHMARKS.md](bench/BENCHMARKS.md#termination) be derived from the trace
rather than stored.

### Payload schemas

Every payload is a JSON object. The listings give each topic's fields in the
trace's canonical key order, which `tc49.lib.inventory` fixes. Every **state**
topic's payload leads with `at`, the stamp the bus above describes, and no
event payload carries one; it is stated once here rather than repeated on
every state row below. Every field is
**required unless marked *optional***; an enum's values are the field's whole
vocabulary, and which way an unreadable one falls is declared with it
(CONTEXT.md). Names are strings throughout: a **train** as the roster names
it, a **block** as the layout names it, a **block end** as `<block>.<A|B>`,
and a **transit** either qualified as `<connection>.<transit>` or split into
its two names, as each topic states.

#### `layout`

- `tc49/layout/state/railroad` — `name`: the railroad, as the store lists it.
  One broker runs one railroad, so every other row here is about that one and
  a view reads this to know which
  ([ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
  decision 2, as amended by
  [ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
  Written by whichever binding of the layout interface is running, from its
  constructor, that being the one app bound to a railroad: the name is the
  layout's own, and a drawing is filed under the name it declares, so there is
  no second place for it to be told from. A view reads it, loads that railroad
  from the store and subscribes the flat topic tree.
  **Every app follows it.** A name other than the one an app is running is a
  railroad being loaded while the apps run: the app built on the last one
  stops answering, the retained rows it owns are **cleared**, and it is built
  again on the new one — a cold start that happens without a restart
  (ADR-0060, `lib/loading.py`). Clearing rather than republishing, because a
  desired speed for a locomotive the new railroad does not have, or occupancy
  for a block end it does not have, is a row nothing would ever republish and
  a page opened afterwards would read as current. A railroad the store cannot
  give is said on stderr and not taken: the app goes on running the one it
  has (ADR-0050). `tests/system/test_reload.py` holds this for every app.
- `tc49/layout/railroad_wanted` — browser-writable — `railroad`: the railroad
  to load, as the store lists it. The gesture behind the row above: a person
  chooses which railroad the apps run **while they run**, so creating one
  from the app is possible and a box wired to steel can carry more than one
  track plan over its life
  ([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
  Whichever binding of the layout interface is running answers it, that being
  the one app bound to a railroad and the writer of the state row; every other
  app follows the **state** row and never this, as the scheduler follows
  `train_placed` and never `placement_wanted`. One writing role (ADR-0035),
  one responder (rule 4).
  **Track power off is the precondition.** It is answered only where
  `tc49/layout/state/power` reads `off`, and dropped otherwise — a refusal
  with nowhere to go, this app answering nothing, and the picker is what says
  why while the track has power (ADR-0034).
  With the power off nothing moves and no turnout throws, and the
  person who turns it back on is the one confirming the rails match the
  drawing just loaded (ADR-0051, the operator as the backstop). Nothing here
  orchestrates a shutdown — turning the power off is a gesture a person
  already has, and the layout interface never writes `off` of its own accord.
  A railroad the store cannot give is refused the same way and the running
  one is unchanged. On the simulator the rails are always live, so this is
  always refused there: a power cut is a physical act and simulating one
  would be the branch ADR-0030 keeps out of every app.
- `tc49/layout/block_occupied`, `tc49/layout/block_vacated` — `block`: the
  block a detector reported on. Anonymous: no train field, because a detector
  cannot name one. A detector reports a **level**, so a repeated reading
  re-asserts what a consumer already holds and at-least-once delivery needs
  no counter; the physical order is occupied then vacated, the head into the
  next block before the tail clears the last
  ([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
- `tc49/layout/power_wanted` — browser-writable — `power`: enum `on`,
  `stopped` or `off`, the same closed set `state/power` below carries; any
  other value is dropped. `layout` is what answers it, and it answers by
  writing `tc49/layout/state/wanted/track` — never by a page reaching a
  translator directly (ADR-0051). A plain `off` is **guarded**: it is applied
  where `tc49/dispatch/state/run` reads `held` with `moving` false, and where
  `layout` holds no run at all, and it is dropped with its reason to the trace
  where the run reads `running` or `draining` or something is moving
  ([ADR-0062](adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)).
  `on` and `stopped` are applied in every run state.
- `tc49/layout/state/power` — `power`: enum `on`, `stopped` or `off`. An
  unreadable payload reads as `off`: dropping it would mean *not* holding the
  run, over track whose state could not be read. `on` and `off` are folded
  from `device/track` and the links; `stopped` is `layout`'s own, published on
  writing `wanted/track: stopped` and held over the fold until a
  `power_wanted: on` clears it, no hardware being able to report an emergency
  stop (ADR-0063).
- `tc49/layout/align` — `connection`; `transit`: bare name within the
  connection; `points`: list of `{addr, position}`, `position` enum `closed`
  or `thrown`; `[]` where nothing needs throwing.
- `tc49/layout/move` — `train`; `connection`; `transit`: bare name, the
  grant's qualified transit split; `into`: the block entered; `speed`: a
  magnitude, `0.0` … `1.0`, the fraction of that locomotive's maximum to run
  this move at. Not a decoder step and not a scale speed, and unsigned —
  which way the train goes along the track is the layout interface's, which
  holds the geometry and the way round the locomotive stands
  ([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
- `tc49/layout/mode_wanted` — browser-writable — `train`: the train to hand
  over or take back, or `null` for **every** train; `mode`: enum `automatic`
  or `manual`; any other value is dropped, and so is the whole gesture, the
  train's mode staying where it was. `null` with `manual` skips the trains
  `layout` is driving — one mid-transit under a grant would otherwise run on
  past the block it was sent to — and takes the rest
  ([#436](https://github.com/rails49/control/issues/436)).
- `tc49/layout/throttle_wanted` — browser-writable — `train`; `speed`: a
  number in −1.0 … 1.0, the fraction of that train's maximum, `0.0` being
  stop, signed for which way the train runs along its own length — positive
  nose-first. Which locomotive the speed reaches, and which way round it
  stands, is `layout`'s, which reads the roster.
- `tc49/layout/state/mode` — `modes`: map of train to enum `automatic` or
  `manual`. `automatic` is the resting value, so a train the map does not
  name is `automatic` and an unreadable entry leaves that train without a
  mode rather than being read as one.
- `tc49/layout/firmware_wanted` — browser-writable — `tag`: the release tag
  to write to the command station, `v5.6.4-rails49.1` and the like. The
  firmware is built elsewhere, against the station's own source; what this
  gesture does is make writing a released build onto the box something the
  running system does, rather than something a person does from a checkout
  ([ADR-0065](adr/0065-the-app-that-owns-the-device-flashes-it.md)). The app
  that holds the station's device answers it and nothing else subscribes:
  writing flash means owning the port, so the app holding it is the only one
  that can hand the device over. Under `layout` because hardware hangs under
  the layout interface (ADR-0043).
  **A tag and never a source.** The payload names no repository and no URL:
  the LAN is the trust boundary and carries no authentication on purpose
  ([ADR-0042](adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)),
  so a payload that named where to fetch from would let anyone on the wifi
  have the station fetch and run an arbitrary binary. A tag can only choose
  among builds already published to the one place the responder is
  configured to look, and that place is a flag on that app. `latest` is no
  legal value either: it names a different build depending on when it is
  read, and the point of the gesture is to be able to say afterwards what
  was written.
  **Never retained**, which is rule 2 and no exception to it. It is spelled
  out here because this is the row where breaking that rule costs a command
  station: a retained flash request reflashes the station every time the
  responder reconnects to the broker — every restart, every deploy, every
  blip.
  **There is no reply**, no correlation id and no outcome topic. The flash
  is a desired half and what happened is read off the observed half:
  `tc49/layout/state/device/link/<id>` goes `down` with the link while the
  station is being written and comes back up when it answers again, carrying
  the `build` the station now reports — which is where a client sees whether
  the tag it asked for is the build that answered — and a failure is published
  on `tc49/layout/state/device/refused/<id>`, whose `addr` is already optional
  for a refusal that named no address.
  **The client sequences it**, as the panel sequences a plain `off`
  (ADR-0051, ADR-0062): flashing resets the station, so the rails drop and
  every throttle on the port disconnects, and the guarantee that this is not
  done under a moving train lives in the client written to honour it. A
  control requires `tc49/dispatch/state/run` at `held` and
  `tc49/layout/state/device/track` at `off` before it publishes. The
  responder checks neither and knows nothing about runs: reading the
  dispatcher's state is the coupling the app holding the device has never
  had.

#### `schedule`

The ten browser-writable rows — the two here, the three under `dispatch`
and the five under `layout` above — are where rule 4 bites hardest: each
payload is read defensively, and one that fails the read is dropped.

- `tc49/schedule/request_wanted` — browser-writable — `train`; `dest`: list,
  each entry a block or a block end, a bare block meaning either end.
- `tc49/schedule/reversal_wanted` — browser-writable — `train`.
- `tc49/schedule/state/exhausted` — `exhausted`: boolean, `true` once the
  last timetable request has gone out.
- `tc49/schedule/state/facing` — `facing`: map of train to the run it would
  make across its block, `<block>.A-to-B` or `<block>.B-to-A`; a train facing
  `<block>.A-to-B` would depart through that block's B end (CONTEXT.md,
  **Facing**). The bare end letter this value once carried is refused rather
  than read, a retained row written by an older build losing that train's
  facing rather than turning it round.

#### `dispatch`

- `tc49/dispatch/request_submitted` — `id`: opaque unique string
  ([ADR-0033](adr/0033-a-request-id-is-unique-not-meaningful.md)); `train`;
  `depart`: the block end the train departs through; `dest`: list of arrival
  block ends, at least one.
- `tc49/dispatch/run_wanted` — browser-writable — `run`: enum `held`,
  `running` or `draining`; any other value is dropped.
- `tc49/dispatch/placement_wanted` — browser-writable — `train`; `block`:
  block name, or `null` for off the layout. The key's presence is
  load-bearing: a payload without `block` fails the read, while an explicit
  `null` is a positive statement
  ([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)).
- `tc49/dispatch/cancel_wanted` — browser-writable — `train`. The gesture
  names no request: it ends whatever that train has, pending or active, and
  a train with nothing in flight is dropped like any other gesture the
  dispatcher cannot act on
  ([ADR-0049](adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)).
- `tc49/dispatch/request_admitted` — `id`; `dest`: the arrival ends that
  survived pruning; `pruned`: list of `{end, reason}`, `reason` one of
  `no_fit`, `no_entry`, `unreachable`.
- `tc49/dispatch/request_rejected` — `id`; `reason`: enum `malformed`,
  `unknown_train`, `unknown_block`, `no_origin`, `wrong_origin`, `no_fit`,
  `no_entry`, `unreachable` — the set is `tc49.lib.rejection`, and the UI's
  copy of it is generated.
- `tc49/dispatch/request_completed` — `id`.
- `tc49/dispatch/request_cancelled` — `id`; `reason`: enum `revoked`,
  `removed`, `displaced` — the set is `tc49.lib.cancellation`. `revoked` is
  the gesture that names the request's own end, and the other two are the
  two directions of a placement that retired it.
- `tc49/dispatch/route_chosen` — `id`; `route`: list alternating block and
  transit names, starting and ending on a block, a single block for the
  degenerate already-there case; `k_tried`: integer, candidate routes
  examined, `0` for the degenerate case.
- `tc49/dispatch/move_granted` — `id`; `train`; `transit`: qualified
  `<connection>.<transit>`; `into`: the block entered; `aspect`: enum `stop`,
  `caution` or `clear`
  ([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
- `tc49/dispatch/grant_refused` — `id`; `reason`: enum `unsafe`, `held` or
  `transit_conflict`; `obstacles`: list of `{resource, holder}` — the block
  or transit that blocked a candidate, and the train holding it.
- `tc49/dispatch/lock_granted`, `tc49/dispatch/lock_released` — `train`;
  `resources`: list of blocks and transits.
- `tc49/dispatch/train_placed` — `train`; `block`.
- `tc49/dispatch/train_removed` — `train`.
- `tc49/dispatch/state/run` — `run`: enum `held`, `running` or `draining`; a
  reader drops an unreadable value (CONTEXT.md). The dispatcher writes
  `draining` when it is asked for and writes `held` itself when the drain
  completes ([#294](https://github.com/rails49/control/issues/294)).
  `moving`: boolean, true while any train is active or crossing — the same
  test the drain's completion makes — and false otherwise. It is orthogonal
  to `run` and not a fourth value of it: a held run can be moving, because a
  move already granted runs to its sensor, and a running run with nothing
  granted is not. The row is republished when `moving` changes with the run
  word standing, and `layout` reads the pair to decide a plain `off`
  ([ADR-0062](adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)).
- `tc49/dispatch/state/aspects` — `aspects`: map of signalled block end to
  aspect. An end nothing ever leaves does not appear.
- `tc49/dispatch/state/disputed` — `trains`: sorted list of trains standing
  in a block that reads clear; `blocks`: sorted list of blocks reading
  occupied with nothing claiming them. Both empty unless the run is held.
- `tc49/dispatch/state/allocation` — `trains`: map of train to standing
  block; `crossing`: map of crossing train to its transit; `locks`: map of
  resource to holding train; `requests`: list of
  `{id, train, depart, dest, route}` in admission order, `route` *optional*
  — present once the route is committed.

## Time

**The layout interface owns time**
([ADR-0009](adr/0009-layout-interface-owns-time.md),
[ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)):
the run clock advances on the events it publishes, and the app components
stay clock-free — the dispatcher grants on the events that arrive, never on
a beat, and never learns what time it is.

**Time is the scheduler's responsibility.** A schedule says "this train,
every workday at 7:00"; the scheduler posts the request that morning. The
dispatcher's contract carries no time, and a simulator that wants timed
submissions owns that timing itself, inside the `simulator` app
(ADR-0047). Milestone 1 needs none of it: a timetable goes in whole at the
start of a run, and the queue does the staggering.

**No event payload carries a timestamp.** Time on the record is observation:
the trace tap stamps each line with `time`, seconds since the run started
— simulated in batch, wall live — and no event, request or grant carries one,
so no app can read one or come to depend on it. A **state** payload carries
`at`, and does not breach that rule: it is stamped by the binding that
publishes rather than by an app, it says the order two values of one topic
were published in and nothing about the hour of the day, and it is read by
that comparison alone.

**The fast clock has no carrier.** It is the railroad's operating time: the
wall clock with a start time and a multiplier, both railroad configuration, so
anything that wants it derives it. Nothing in the control path reads it — it
feeds scheduling and scenery, never dispatch and never safety, so a train that
is late is late and nothing follows from it
([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
Until a session clock derived from that configuration arrives, the UI shows
the last event's time.

## Device vocabulary

What passes between `layout` and the hardware under it, in two halves: one
retained state topic per device naming what that device should do, and one
naming what it is observed to do. Every row has a single writer (rule 1) —
`layout` for a desired row, and for an observed one the one thing that answers
for that address — and whatever recognises an address acts on it while
everything else ignores it, so no ownership table exists anywhere and an
address nothing answers to does no harm, as a packet nobody picks up does
([ADR-0043](adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
The rows are `tc49.lib.inventory.DEVICE_TOPICS`. What each translator does
with them, and where one cannot, is
[layout/DEVICES.md](layout/DEVICES.md).

**What `layout` asks of the hardware.** Four of the five are written today —
`wanted/point` on each `align`, `wanted/signal` on each aspect the dispatcher
shows, `wanted/track` on each press of the power (#287), and `wanted/traction`
on each `move` it acts on and again on the arrival, its sign composed from the
train's facing and the way round each car is coupled
([#296](https://github.com/rails49/control/issues/296)). `wanted/function` has
no writer: a function press has no gesture to arrive on and is nobody's until a
throttle asks. Its `value` is a **boolean** and not a word out of a catalogue:
a function is one bit on the wire wherever it was checked, and setting a
volume or a brightness is decoder configuration, a different capability that
would be a different row
([ADR-0063](adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)). All five are **subscribed** by a translator, which acts on the
addresses it recognises and holds no table of the ones it does not
([#289](https://github.com/rails49/control/issues/289)).

| Topic | Payload | Values |
| --- | --- | --- |
| `tc49/layout/state/wanted/traction/<addr>` | `addr`, `speed` | `speed` a number in −1.0 … 1.0 |
| `tc49/layout/state/wanted/function/<addr>/<number>` | `addr`, `function`, `value` | `function` the function number as a string; `value` a **boolean** |
| `tc49/layout/state/wanted/point/<addr>` | `addr`, `position` | `position` `closed` or `thrown` |
| `tc49/layout/state/wanted/signal/<addr>` | `addr`, `aspect` | `aspect` `stop`, `caution` or `clear` |
| `tc49/layout/state/wanted/track` | `power` | `power` `on`, `stopped` or `off` |

The address is **trailing levels rather than a leaf**, so a row is named by the
topic above it and the payload repeats the address as `addr`, which is what
lets a trace line read on its own. The trace's `event` for one of these is that
key past `tc49/layout/state/` — `wanted/traction`, `wanted/point` — two levels
where every other row's name is one, because the observed half of the
vocabulary answers for the same devices and `point` alone would not say which
half a line records.

**An address names no system.** It is the string the drawing carries and the
hardware answers to, and the topic carries it as trailing levels with nothing
in front of them — a decoder answers to the number it was programmed with
whoever sends the packet, and a turnout answers to the accessory number it is
wired to
([ADR-0045](adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md),
[ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)).
Whatever is wired subscribes these rows and acts on the addresses it
recognises, holding no table of the ones it does not, and an address nobody
answers to does no harm. Two systems that number a point alike both act, and
that is the deployer's addressing to fix and not a topic level.

**`track` carries no address.** Power districts are a hardware-level fact and
do not reach the bus: there is one railroad-wide desired power, and a
translator maps it onto however many districts its hardware has. Above the
layout interface the railroad-wide answer stays `tc49/layout/state/power`,
unchanged; `device/track` below it is what one translator reads off its own
hardware, and how the two meet is `layout`'s, as the fold from sensors into
`block_occupied` and `block_vacated` is.

**Speed is a fraction, never a decoder step.** The sign is direction along the
track and the magnitude is the fraction of that locomotive's maximum; `0.0` is
stop. Steps, speed tables and every wire protocol stay inside a translator
(ADR-0043).

**What the hardware reports back.** The observed half, written by whatever
watches or drives the thing addressed — a detector for a sensor, a translator
for the addresses it drives — and never by `layout`, which reads these rows
rather than writing them.

| Topic | Payload | Values |
| --- | --- | --- |
| `tc49/layout/state/device/sensor/<block>.<end>` | `addr`, `occupancy`, `reason` | `occupancy` `occupied`, `clear` or `unknown`; `reason` *optional*, free text, only with `unknown` |
| `tc49/layout/state/device/point/<addr>` | `addr`, `position` | `position` `closed` or `thrown` |
| `tc49/layout/state/device/track` | `power`, `reason` | `power` `on` or `off`; `reason` *optional*, free text |
| `tc49/layout/state/device/link/<id>` | `id`, `link`, `detail`, `build` | `link` `up` or `down`; `detail` *optional*, free text; `build` *optional*, free text |
| `tc49/layout/state/device/refused/<id>` | `id`, `addr`, `detail` | `addr` *optional*, absent where the refusal had no address; `detail` free text |

The address rules are the desired half's, and `link` and `refused` are the two
rows whose address comes back under a name of its own: each is keyed by
whatever the publisher calls itself, and the payload repeats that as `id`
rather than as `addr`, there being no device at the far end of it.

**The link's `id` is the publisher's own.** It appears in no drawing, no
configuration and no list of ours, and nothing but `layout` reads the row. It
is a key rather than nothing at all because one railroad may have several
participants, and the second's `up` would otherwise erase the first's `down`.
`layout` folds `state/power` to `off` for any id it has heard say `down` and
never waits for an id it has not heard, so nothing must announce itself for
the railroad to come up
([ADR-0058](adr/0058-hardware-meets-the-bus-and-a-translator-is-only-for-hardware-that-cannot.md)).
A publisher may set an MQTT last will of `down` on its own row, which
[ADR-0040](adr/0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md)
permits as a faster signal no safety property depends on (ADR-0059).

**`build` is what the far end says it is running.** The identifier the
hardware reports for its firmware, free text and optional, on the row that
already reads the thing: a publisher calls the link `up` on what the hardware
answered back, and what it answered names the build
([ADR-0065](adr/0065-the-app-that-owns-the-device-flashes-it.md)). The build
identifier alone and never the whole banner it was read out of — a banner's
shape is one vendor's, where this row is device-neutral and another publisher
reports whatever its own hardware calls its build. Optional for two reasons,
both ordinary: a link that is `down` has no build to report, and hardware that
reports no build at all is common. Nothing branches on it and `layout` does not
read it; what reads it is a client that asked for a build on
`tc49/layout/firmware_wanted` and wants to see whether the build it asked for
is the build that answered, which is the whole of that verification path — a
desired half and an observed half, no correlation id and no reply.

**The supply is `on` or `off`.** The observed row carries no emergency stop
where the desired one does, and that asymmetry is the vocabulary's own: what
the railroad may be **asked** for is not bounded by what a sensor can answer.
An emergency stop leaves the rails live — which is what tells it apart from
cutting the supply, and is physical rather than a modelling choice — so under
one the supply reads `on`, and that is the truth about the supply rather than
a gap in what a publisher can report
([ADR-0063](adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)).
Whether the railroad is standing under an emergency stop is
`tc49/layout/state/power`, which keeps all three values and gets that one from
`layout`'s own command rather than from this row. A `device/track` frame
stating a third value is refused like any other value outside the closed set,
and reads `off` with them.

**`reason` on the supply is for the participant that cannot reach it**:
`{power: off, reason: "…"}`, so a person reads why the railroad is dark
without a second row to find. Free text and optional, on the same terms as
the sensor's — nothing branches on it, and a supply that reads `off` with no
reason is no less `off`.

**A sensor is addressed by the block end it watches**, `<block>.<end>`, one
topic per sensor, and never by a camera's own identifier
([#194](https://github.com/rails49/control/issues/194)). The topic is that on
every railroad, so a trace is comparable between installations. **The drawing
carries the name the hardware knows each sensor by**, one per block end and
defaulting to `<block>.<end>`, and whoever publishes the row reads it from the
store: a camera can be told what to call itself, and a system whose sensors
are named by that system and whose protocol requires the name cannot be
([ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md),
[ADR-0063](adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)).
The name stays out of the payload: the row is retained, so a name published
before a drawing edit would sit on the broker contradicting the drawing, and
one place for it is what keeps it from drifting. Nothing above the layout
interface learns detector geometry either way (ADR-0043). Never a
whole-railroad map either: a map would make one camera the single writer of
every sensor on the railroad, and a second camera could then not join without
overwriting the first one's view, which is the reason
[ADR-0035](adr/0035-a-topic-has-one-writing-role.md) gives for one writing
role per state topic.

**A publisher that reads the store follows the railroad.** The names are a
railroad's, so it subscribes `tc49/layout/state/railroad` and builds them
again when another railroad is named, like every other app that reads the
store
([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
It remains a translator — no ownership table, acting on the addresses it
recognises, importing no app but `tc49.lib` and itself — and it now has a
railroad identity, where a translator was configured by its command line
alone. One that reads nothing still does not follow the row, hardware needing
no layout
([ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
decision 5): the rule narrows rather than gaining an exception.

**A detector publishes a level change and nothing else** — no heartbeat, no
periodic restatement, no map on a timer. Retention is what a late subscriber
gets, so there is **no state-inquiry request**, the same answer the topics
above give and for the same reason: a feature nothing needs is overhead.
`unknown` is a value and not an absence. The camera knows *why* it cannot say
— no model, not calibrated, drift — and `reason` carries that for a person to
read, while a consumer treats `unknown` as no information about that end.

**`link` is where a broken link becomes observable.** A participant that knows
it cannot reach its hardware says so as observed state like any other, so a UI
can say the command station is unreachable instead of the railroad merely
looking idle, and goes on saying so while the failure lasts
([ADR-0050](adr/0050-broken-hardware-is-reported-never-worked-around.md)).
That is where verifying the link belongs: at runtime, with a person present
who can act on it, and not in a test suite that would need a powered layout to
pass. A translator publishes `device/point` only where its
hardware actually reports a position, a commanded one never being echoed back
as a measured one (ADR-0043); on this railroad turnouts have no feedback
([ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md)), so the
translator driving them writes none, a faked reply being worse than silence.

**`refused` is the publisher's report on its own last exchange**, and not a
state of any device: the hardware refused a command or could not parse it, and
whoever sent that command says so, keyed by whatever it calls itself. It
carries the `addr` the command named where it had one and free text for the
reason, and each refusal overwrites the last, so nothing remembers which
addresses are refusing — that is the table no translator holds, and a UI that
wants a per-device view builds it from the stream. What it catches is
misconfiguration: an address the hardware does not have, a value out of range,
an aspect a mast will not accept, which is common and otherwise entirely
silent. What it misses is hardware that answers and does not obey, which no
protocol reports and this row does not pretend to
([ADR-0063](adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md),
[#463](https://github.com/rails49/control/issues/463)). A refusal that is
published happened, and one that is not published is no evidence that none
occurred: where a participant cannot attribute a refusal to its own command it
publishes nothing, and [layout/DEVICES.md](layout/DEVICES.md) says which those
are. `layout` does not subscribe it. It is for a UI, for a person to read, and
nothing branches on it.

Two of the observed rows are published today, both by a translator:
`device/track` and `device/link`, which are two of the three `layout` reads
and the two `state/power` is folded from. The third is `device/sensor`, whose
publisher is a detector and lives outside this repository — until one does, a
person supplies the readings a physical run has no other source of, typing
them a line at a time on the writing role a detector holds, at a client of the
broker like the camera that will replace it
([#315](https://github.com/rails49/control/issues/315),
[#379](https://github.com/rails49/control/issues/379),
[bench/detector.py](../src/tc49/bench/detector.py)); `device/point` and
`device/refused` are declared and written by nobody, the second being each
translator's own implementation issue. Folding a block's two sensors into
`block_occupied` and `block_vacated` is `layout`'s own work, and so is the
**settling time** a new level is held for before it is acted on — a number
private to that app, on no topic, so nothing above the layout interface is
told there is a debounce at all
([layout/README.md](layout/README.md)).

Every row of both halves is state rather than command because that is what
makes the extra hop safe under at-least-once delivery: a replayed message
carries the value that is already current, and a translator coming up finds
the retained value waiting (ADR-0043).

