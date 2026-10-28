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
The first reader outside this repository is `rails49/dccex`'s translator,
which imports this repository's package with the commit in its lock file
([its ADR-0014](https://github.com/rails49/dccex/blob/main/docs/adr/0014-the-translator-is-on-the-bus-through-controls-package.md)).
The inventory below is machine-readable as `tc49.lib.inventory`, which it
reads.

`tc49.lib.bus` and `tc49.lib.mqtt` are this repository's binding of the page —
the interface an app is handed, and its two transports. A binding in another
language implements this page rather than porting Python:
`ui/src/model/trace.ts` already is one. The decisions behind the contract are
[ADR-0008](adr/0008-bus-contract-is-the-mqtt-safe-intersection.md) and
[ADR-0009](adr/0009-layout-interface-owns-time.md). Terminology follows
[GLOSSARY.md](../GLOSSARY.md).

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

   A widget's state row under `ui` is the exception: any writer may publish
   on it. A widget row is always the whole value, so no writer supplies only
   part of it, and the last one written is the right one
   ([ADR-0087](adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md) decision 3).
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
([Payload schemas](#payload-schemas)) is a compatible change: one
communication issue (docs/agents/issue-tracker.md), and a consumer built
before it keeps working, because a consumer ignores fields it does not
recognize. Removing, renaming or repurposing a field or a topic, or making an
optional field required, breaks consumers and needs the stronger argument. A
field can leave and come back the same way: `at` was dropped from the request
and returns, if it does, as one communication issue once its requirements are
understood — a different field from the stamp every state payload carries,
which says when a value was published rather than when a request wants its
train to run. An added field still changes the trace, so recorded fixtures
regenerate — a cost each addition pays, not breakage.

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
the rule is stated in front of it as a router and middleware on `/mqtt` rather
than in an app
([ADR-0056](adr/0056-the-browsers-way-onto-the-bus-refuses-a-foreign-origin.md),
[ADR-0042](adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)):
as labels on the broker's own container, which the door in front of the box
reads ([DEPLOY.md](DEPLOY.md#what-the-containers-declare)).

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

A topic is named `tc49/<component>/<leaf>`: `layout`, `schedule`,
`dispatch`, `drive` or `ui`. `drive` holds one topic, the driver saying it is
up: every other topic the driver publishes is a command, which sits under the
component that answers it. The component comes first because it is the component that
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
Today the mark sits on exactly the fifteen gesture rows. The throttle a person
drives with ([#207](https://github.com/rails49/control/issues/207),
[ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)),
the railroad's driving mode, the
track power a person commands
([ADR-0051](adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md))
the railroad a person loads
([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)),
the fast clock and the railroad's settings a person sets
([ADR-0090](adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md),
[#1126](https://github.com/rails49/control/issues/1126))
are nine of them, under `layout`, which is the component that responds to
them. Beyond them, one state row carries the mark: a toggle's,
`tc49/ui/state/toggle/<name>`, which a page writes when a person presses the
toggle. It is rule 1's widget exception: concurrent pages do it no harm,
because the row is always the whole value and the last one written is the
right one
([ADR-0087](adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)
decision 3). A button's event row, `tc49/ui/button/<name>`, carries it too,
because a page publishes it when a person presses the button. Whether a row
carries the mark is an ACL decision, made when the row lands.

**Writer** is the component the name already states for everything a
component emits. On a request row it is `any`: one responder, any number of
writers (rule 1), and `any (browser)` is the mark above.

A row ending in `<name>` is a **pattern**: one topic per widget on the loaded
drawing, the widget's name as the last level. `ui` declares these rows. A
page writes the toggle and button rows when a person presses one; nothing in
control writes the text row ([ADR-0087](adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)).

| Topic | Kind | Writer | Meaning |
| --- | --- | --- | --- |
| `tc49/layout/state/railroad` | state | layout | the railroad this broker runs, `""` while the binding stands ([ADR-0059](adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)), and whether anything was built from it ([ADR-0085](adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md)) |
| `tc49/layout/railroad_wanted` | event | any (browser) | load this railroad, the apps staying up ([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)) |
| `tc49/layout/alive_confirmed` | event | layout | `layout` is up and built on a railroad, said once a second ([#716](https://github.com/rails49/control/issues/716), [#1113](https://github.com/rails49/control/issues/1113)) |
| `tc49/schedule/scheduler_alive_confirmed` | event | scheduler | the scheduler is up and built on a railroad, said once a second ([#1113](https://github.com/rails49/control/issues/1113)) |
| `tc49/dispatch/dispatcher_alive_confirmed` | event | dispatcher | the dispatcher is up and built on a railroad, said once a second ([#1113](https://github.com/rails49/control/issues/1113)) |
| `tc49/drive/driver_alive_confirmed` | event | driver | the driver is up with a railroad loaded, said once a second ([#1113](https://github.com/rails49/control/issues/1113)) |
| `tc49/layout/block_occupied` | event | layout | a detector saw a block fill |
| `tc49/layout/block_vacated` | event | layout | a block is empty: both its ends read clear, or the move this app carried out named it the block behind a train now fully into the block ahead ([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)) |
| `tc49/layout/power_wanted` | event | any (browser) | give the track power, drain the railroad, or remove the supply at once ([ADR-0051](adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md), [ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)) |
| `tc49/layout/state/power` | state | layout | on, draining or off: whether a train may move at all ([ADR-0041](adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md), [ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)) |
| `tc49/layout/align` | command | any | throw these points, and authorise the transit it names, if any |
| `tc49/layout/move` | command | any | take the train across, this fast |
| `tc49/layout/withdraw_wanted` | event | any | take back this move, unless the train is running or was running when the move was acted on, or has been given a non-zero speed since ([#1068](https://github.com/rails49/control/issues/1068), [#1076](https://github.com/rails49/control/issues/1076)) |
| `tc49/layout/move_withdrawn` | event | layout | the move was taken back: the train never left its block ([#1068](https://github.com/rails49/control/issues/1068)) |
| `tc49/layout/throttle_wanted` | event | any (browser) | how fast a person is driving a train |
| `tc49/layout/driving_wanted` | event | any (browser) | switch the railroad's driving mode ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)) |
| `tc49/layout/state/driving` | state | layout | manual or automatic: who drives the trains ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)) |
| `tc49/layout/state/clock` | state | layout, simulator | the fast clock: the railroad's time of day and its speed-up ([ADR-0090](adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)) |
| `tc49/layout/clock_wanted` | event | any (browser) | set the fast clock: a time of day, a speed-up, or both ([ADR-0090](adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)) |
| `tc49/layout/take_wanted` | event | any (browser) | a throttle takes a train, or the train is released ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)) |
| `tc49/layout/throttle_alive` | event | any (browser) | a throttle holding a train is still there ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)) |
| `tc49/layout/state/taken` | state | layout | which throttle holds each train ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)) |
| `tc49/layout/function_wanted` | event | any (browser) | a throttle switches one of its train's functions ([#849](https://github.com/rails49/control/issues/849)) |
| `tc49/layout/state/functions` | state | layout | which of each train's functions are on ([#849](https://github.com/rails49/control/issues/849)) |
| `tc49/layout/state/settings` | state | layout | the railroad's settings, the point gap and the driver's speeds, and the installation's throttle silence ([#1125](https://github.com/rails49/control/issues/1125), [#1130](https://github.com/rails49/control/issues/1130)) |
| `tc49/layout/settings_wanted` | event | any (browser) | set the point gap, the driver's speeds or the throttle silence, each optional ([#1126](https://github.com/rails49/control/issues/1126), [#1131](https://github.com/rails49/control/issues/1131)) |
| `tc49/schedule/request_wanted` | event | any (browser) | a gesture: the request minus the id and depart the scheduler owns |
| `tc49/schedule/reversal_wanted` | event | any (browser) | turn a train around where it stands |
| `tc49/schedule/state/exhausted` | state | scheduler | the timetable has run dry |
| `tc49/schedule/state/facing` | state | scheduler | the run each train would make across its block |
| `tc49/dispatch/request_submitted` | event | any | a request, composed and released |
| `tc49/dispatch/placement_wanted` | event | any (browser) | where a train actually is ([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)) |
| `tc49/dispatch/cancel_wanted` | event | any (browser) | end one request without arriving ([ADR-0049](adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md), [ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)) |
| `tc49/dispatch/reorder_wanted` | event | any (browser) | move one request in the list the dispatcher serves ([ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)) |
| `tc49/dispatch/point_wanted` | event | any (browser) | a person asks for a point's position ([ADR-0068](adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)) |
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
| `tc49/dispatch/placement_refused` | event | dispatcher | a placement not accepted, and why ([ADR-0092](adr/0092-an-app-reads-the-roster-again-for-a-train-it-has-not-got.md)) |
| `tc49/dispatch/train_removed` | event | dispatcher | a train taken off the layout |
| `tc49/dispatch/state/moving` | state | dispatcher | whether any train is crossing, which `layout` reads to end a drain ([ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)) |
| `tc49/dispatch/state/aspects` | state | dispatcher | every signalled end's aspect |
| `tc49/dispatch/state/allocation` | state | dispatcher | the run's whole picture |
| `tc49/dispatch/state/disputed` | state | dispatcher | where the detectors contradict the placement ([#153](https://github.com/rails49/control/issues/153)) |
| `tc49/dispatch/state/unfit` | state | dispatcher | the trains the last rebuild under the same name took off the layout, and why ([#709](https://github.com/rails49/control/issues/709)) |
| `tc49/dispatch/state/broken` | state | dispatcher | the lock table's rules it found broken ([#1118](https://github.com/rails49/control/issues/1118)) |
| `tc49/ui/state/text/<name>` | state | any | the text a text widget shows ([ADR-0087](adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)) |
| `tc49/ui/state/toggle/<name>` | state | any (browser) | a toggle's position ([ADR-0087](adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)) |
| `tc49/ui/button/<name>` | event | any (browser) | a button was pressed ([ADR-0087](adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)) |

| Consumer | Filter(s) |
| --- | --- |
| Scheduler | `tc49/dispatch/#` **and** `tc49/schedule/#` |
| Dispatcher | `tc49/layout/#` **and** `tc49/dispatch/#` |
| Driver | `tc49/dispatch/move_granted` |
| Layout interface | `tc49/layout/align`, `tc49/layout/move`, `tc49/layout/withdraw_wanted`, `tc49/layout/power_wanted`, `tc49/layout/railroad_wanted`, `tc49/layout/driving_wanted`, `tc49/layout/clock_wanted`, `tc49/layout/take_wanted`, `tc49/layout/throttle_alive`, `tc49/layout/throttle_wanted`, `tc49/layout/function_wanted`, `tc49/layout/settings_wanted`, `tc49/layout/state/power`, `tc49/dispatch/train_placed` / `train_removed`, `tc49/dispatch/state/aspects`, `tc49/dispatch/state/moving`, `tc49/dispatch/state/allocation`, `tc49/schedule/state/facing` `tc49/layout/state/device/#` **and** `tc49/layout/state/wanted/function/#` |
| Translator | `tc49/layout/state/wanted/#`, **and** `tc49/layout/state/railroad` where it publishes sensors, **and** `tc49/layout/state/clock` where it passes the fast clock to its hardware |
| Trace tap | `tc49/#` |

Every app but the layout interface also subscribes
`tc49/layout/state/railroad`, and acts on one thing only: a name or a stamp
other than the build it is running, which is a railroad being loaded under it
(ADR-0060, #688, above) — and never on a row saying `built: false`, from which
nothing was built (ADR-0085). A translator does so where it reads the store: one publishing
`device/sensor` reads the names the hardware knows those sensors by out of
the drawing, and those are a railroad's (ADR-0063, below). One that reads
nothing does not, hardware needing no layout. The layout interface does not
either, being the row's writer: it follows
`tc49/layout/railroad_wanted` instead, which is the gesture it answers. Every
binding of it reads back its own `tc49/layout/state/power` for the
precondition on that gesture and waits for `off`, the one that drives no
hardware included: the simulator answers the band's power presses as the
layout does and comes up `off` (ADR-0070).

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

Every payload is a JSON object, except a widget's: that payload is raw
(`ui` below). The listings give each topic's fields in the
trace's canonical key order, which `tc49.lib.inventory` fixes. Every **state**
topic's payload leads with `at`, the stamp the bus above describes, and no
event payload carries one; it is stated once here rather than repeated on
every state row below, a widget's excepted. Every field is
**required unless marked *optional***; an enum's values are the field's whole
vocabulary, and which way an unreadable one falls is declared with it. Names
are strings throughout: a **train** as the roster names it, a **block** as the
layout names it, a **block end** as `<block>.<A|B>`, and a **transit** either
qualified as `<connection>.<transit>` or split into its two names, as each
topic states.

An **enum** is a field whose values are a closed set the contract names.
Each set has one home:

| field | home in `tc49.lib` |
| --- | --- |
| `driving` | `inventory`, `DRIVINGS` |
| `power` | `inventory`, `POWERS` |
| `power` on `device/track` | `inventory`, `SUPPLY` |
| `occupancy` | `inventory`, `OCCUPIED`, `CLEAR`, `UNKNOWN` |
| `position` | `inventory`, `CLOSED`, `THROWN` |
| `aspect` | `inventory`, `Aspect` |
| `link` | `inventory`, `Link` |
| `reason` on `grant_refused` | `inventory`, `Refusal` |
| `reason` on `request_rejected`, and on `request_admitted`'s `pruned` | `rejection` |
| `reason` on `placement_refused` | `rejection`, `PlacementRefusal` |
| `reason` on `request_cancelled` | `cancellation` |

The closed set goes wherever the field goes: `power` is an enum on
`tc49/layout/state/power` and on the `power_wanted` gesture that asks to move
it. So a new value is a change to the contract, not a payload a reader
tolerates. Which way an unreadable value falls is the reader's choice, made by
what a drop would cost:

- An unreadable `power` on `state/power` reads as `off`, and the dispatcher
  routes nothing. Dropping it would leave the dispatcher committing over
  track whose state could not be read. An unreadable supply on `device/track`
  reads as `off` too. On `power_wanted` an unreadable `power` is dropped, and
  nothing is set ([#175](https://github.com/rails49/control/issues/175)).
- An unreadable `driving` on `state/driving` reads as `manual`, where the
  railroad comes up and under which a train no throttle holds stands; on
  `driving_wanted` it is dropped.
- An unreadable `occupancy` reads as `unknown`: no information about that end,
  and the level last held stands.
- A `point_wanted` whose `position` is neither value is dropped.
- A grant whose `aspect` the driver has no speed for sends no move, so the
  train stays where it is, as on `stop`.
- Any `link` but `up` reads as not up, and the railroad's power folds to
  `off`.
- An unreadable `state/moving` reads as `true`, so it never ends a drain:
  cutting the supply under a train strands it.
- The reasons on `request_rejected`, `request_cancelled`, `grant_refused`
  and `placement_refused` are read only for what a person is shown. The UI shows a reason it has no
  words for as it came.

#### `layout`

- `tc49/layout/state/railroad` — `name`: the railroad, as the store lists it;
  `built`: whether anything was built from it (below).
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
  (ADR-0060, `lib/loading.py`). **So is the same name with another stamp**
  ([#688](https://github.com/rails49/control/issues/688)): the binding
  publishes the row once per build, from its constructor, so `at` says when
  this railroad was built and is unchanged when the broker hands the row over
  again. A new `at` on the running railroad's name is that railroad built
  again from the store — after a restore wrote it — and every app following
  the row rebuilds on it, translators reading sensor names from the drawing
  and the UI among them. An app started on a railroad knows no stamp for it,
  and takes the first row naming it as the build it runs. A build under the
  same name keeps `tc49/dispatch/state/allocation` and
  `tc49/schedule/state/facing`, which say where the trains stand on steel a
  rebuild has not moved ([ADR-0071](adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)). Clearing rather than republishing, because a
  desired speed for a locomotive the new railroad does not have, or occupancy
  for a block end it does not have, is a row nothing would ever republish and
  a page opened afterwards would read as current. A railroad the store cannot
  give is said on stderr and not taken: the app goes on running the one it
  has (ADR-0050). `tests/system/test_reload.py` holds this for every app.
  **`""` is no railroad** ([#727](https://github.com/rails49/control/issues/727)):
  a binding that **stands** publishes `{"name": ""}` each time it comes to
  stand, before it waits for a pick, and the next build's constructor
  replaces it. So a page tells "no railroad loaded" from "layout not
  running". A follower drops a row naming `""`: one standing keeps standing,
  one built on a railroad keeps running it.
  **`built: false` is a railroad named and not built**
  ([ADR-0085](adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md)
  decision 4, [#889](https://github.com/rails49/control/issues/889)). `built`
  is `true` where the railroad named was built from its drawing, as before,
  and an absent `built` reads as `true`, so a row from an older writer means
  what it meant. `false` is a railroad whose drawing is not a **valid
  drawing**: the binding records it in the store as loaded and publishes it
  with a new `at` — after a restart on it, after a save of the loaded
  railroad, and after a pick under another name. On the steel that is a
  track plan being rebuilt, and no train should run on the last build. The
  binding goes on running what it holds — the last build in memory, or
  nothing under that name after a restart — and still answers power presses,
  so a person can drive the station by hand to test. A follower drops the
  row: it builds nothing, keeps what it holds and clears none of its rows, so
  `tc49/dispatch/state/allocation` and `tc49/schedule/state/facing` stand
  until a build under that name adopts them (ADR-0071). That build is the
  same name with `built: true` and a new `at`, as any rebuild is. A
  railroad the store does not have at all is still refused, as above.
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
  **Naming the railroad already loaded is answered like naming another**
  ([#688](https://github.com/rails49/control/issues/688)): it means "run
  what the store holds", so the binding builds it again from the store under
  the same precondition and republishes the state row with a new `at`. The
  UI publishes it after a restore, for that reason.
  **Track power off is the precondition.** It is answered only where
  `tc49/layout/state/power` reads `off`, and dropped otherwise — a refusal
  with nowhere to go, this app answering nothing, and the UI's settings dialog
  is what says why while the track has power (ADR-0034, ADR-0072).
  With the power off nothing moves and no turnout throws, and the
  person who turns it back on is the one confirming the rails match the
  drawing just loaded (ADR-0051, the operator as the backstop). Nothing here
  orchestrates a shutdown — turning the power off is a gesture a person
  already has, and the layout interface never writes `off` of its own accord.
  A railroad the store cannot give is refused the same way and the running
  one is unchanged.
- `tc49/layout/block_occupied`, `tc49/layout/block_vacated` — `block`: the
  block a detector reported on. Anonymous: no train field, because a detector
  cannot name one. A detector reports a **level**, so a repeated reading
  re-asserts what a consumer already holds and at-least-once delivery needs
  no counter; the usual physical order is occupied then vacated, the head
  into the next block before the tail clears the last
  ([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)),
  and a train shorter than the gap between two blocks' detectors gives the
  other ([ADR-0077](adr/0077-a-train-is-not-sent-into-a-block-that-reads-occupied-and-a-move-ends-on-both-readings.md)).
- `tc49/layout/alive_confirmed` — payload `{}`. `layout` publishes it once a
  second, by the monotonic clock and not once a turn, from its drain loop
  while it is built on a railroad; a `layout` that is standing, or reloading
  for another railroad, publishes none, and loading needs the power off, so a
  cut then changes nothing. Something off the box watches it and **cuts track
  power when it stops**: each translator that drives trains
  ([rails49/dccex#236](https://github.com/rails49/dccex/issues/236)) and any
  device on the bus that cuts track power
  ([rails49/.github#29](https://github.com/rails49/.github/issues/29)); what
  a consumer does then is theirs. **Not retained**: a retained value would be
  handed to a late subscriber after the box had stopped. The simulator
  publishes it in `layout`'s place, because the page needs it on a simulated
  railroad too; the devices that cut track power on it are on steel boxes
  only, so there it cuts nothing. It is not a detector's event, so the
  rule below that a detector publishes no heartbeat does not reach it
  ([#716](https://github.com/rails49/control/issues/716),
  [#1113](https://github.com/rails49/control/issues/1113)).
- `tc49/schedule/scheduler_alive_confirmed`,
  `tc49/dispatch/dispatcher_alive_confirmed`,
  `tc49/drive/driver_alive_confirmed` — payload `{}`. Each app publishes its
  own as `layout` publishes `alive_confirmed`: once a second by the monotonic
  clock from its drain loop, while it is built on a railroad, and none while
  it stands. The driver reads no documents, so for it built is a railroad
  loaded. **Not retained**, for the same reason. **Not marked `browser`**:
  every page already reads `tc49/#`, and the mark would let a page say an app
  is up when it is not. Each leaf names its app, a leaf being unique across
  the inventory. The consumer is the page: while the loaded railroad is
  built, it expects all four of these and `layout`'s, and names on the band
  each app it has not heard for 3 s, one never heard since the page
  connected included, until that app is heard again. With no railroad
  loaded, or one not built, it judges none. This is the one place that
  handles an app being down
  ([#1113](https://github.com/rails49/control/issues/1113)).
- `tc49/layout/power_wanted` — browser-writable — `power`: enum `on`,
  `draining` or `off`, the same closed set `state/power` below carries; any
  other value is dropped ([ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)). `layout` is what answers it, and it answers
  by writing `tc49/layout/state/wanted/track` — never by a page reaching a
  translator directly (ADR-0051).
  - `on`: the supply on. From `draining` it ends the drain.
  - `draining`: from `on` only, and dropped otherwise. `layout` publishes
    `state/power: draining` and keeps the supply on until
    `tc49/dispatch/state/moving` reads `false`, then writes
    `wanted/track: off`, zeroes every retained `wanted/traction` row, and
    publishes `off`.
  - `off`: the emergency stop. Applied at once in every state, with no
    guard: `wanted/track: off`, and every `wanted/traction` row zeroed.

  Whichever binding of the layout interface is running answers it, the
  simulator included: it has no translator to write to, so it states the word
  on `state/power` itself, under the same rules. While the power is not `on`
  it starts no move, and a move under way advances only while the supply is
  on, so it runs to its sensors through a drain and waits through `off`
  ([ADR-0070](adr/0070-the-simulator-obeys-the-bands-power-presses.md),
  [#832](https://github.com/rails49/control/issues/832)).
- `tc49/layout/state/power` — `power`: enum `on`, `draining` or `off`
  ([ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)). An unreadable payload reads as `off`: dropping it would leave the
  dispatcher routing over track whose state could not be read. `on` and `off`
  are folded from `device/track` and the links — `off` where `device/track`
  reads `off` or a link reads `down`; `draining` is `layout`'s own, published
  on answering `power_wanted: draining` and held over the fold until the
  drain ends, no hardware being able to report one (ADR-0063). The simulator
  publishes `off` from its constructor, as `layout` does, and then the word
  each answered `power_wanted` commanded (ADR-0070). `stopped`, the emergency
  stop with the track live that [ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md) retires, is outside the set and reads
  as `off` ([#834](https://github.com/rails49/control/issues/834)).
- `tc49/layout/align` — `connection`; `transit`: bare name within the
  connection; `points`: list of `{addr, position, reported}`, `position` enum
  `closed` or `thrown`, `reported` a boolean, always present: whether the
  hardware reports where the point at that address lies, so `layout`, which
  holds no table of points, knows which to wait for
  ([ADR-0097](adr/0097-a-reported-point-lies-where-device-point-says-and-a-train-waits-for-it.md)).
  A point without `reported`, or with one that is not a boolean, fails the
  whole frame, as any other unreadable point does. `points` is `[]` where
  nothing needs throwing. `connection` and `transit`
  may both be `null`, for a throw by hand: the frame names no transit and
  `points` carries the points to set, any number of them. A frame with only
  one of the two `null` is unreadable and dropped whole
  ([ADR-0068](adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)).
- `tc49/layout/move` — `train`; `connection`; `transit`: bare name, the
  grant's qualified transit split; `into`: the block entered; `speed`: a
  magnitude, `0.0` … `1.0`, the fraction of that locomotive's maximum to run
  this move at. Not a decoder step and not a scale speed, and unsigned —
  which way the train goes along the track is the layout interface's, which
  holds the geometry and the way round the locomotive stands
  ([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
- `tc49/layout/withdraw_wanted` — `train`; `transit`: qualified,
  `<connection>.<transit>`, the transit the train's outstanding move crosses;
  `into`: the block that move enters, as `move` names it. A transit names the
  way and not the direction, so `into` is what tells a move back over a
  transit from the one that just crossed it. Not browser-writable. The dispatcher publishes it when a `cancel_wanted`
  lands on a request with a move outstanding, in either driving mode, and
  `layout` answers it. A train is driven if it was running when the move
  was acted on — the last speed `layout` wrote on some addressed car not
  `0.0`, which a decoder keeps — or if `layout` has written a non-zero speed
  to any of its addressed cars since, from the move or from a throttle. No
  withdrawal is taken while the train is running, whatever state the move is
  in. Otherwise a move `layout` holds for an `align`, a facing or the power
  has not been acted on and is taken back where its `into` matches too, and
  one acted on is taken back
  where the train has not been driven: the train is put back in the block it
  stood in and, unless a throttle holds it, told `0.0`. A move not there yet
  is answered at once and the train's next `move` dropped if it names that
  transit and `into`; a `train_placed` or `train_removed` clears that.
  Dropped, with no answer, where the train is running, where it has been
  driven since the move was acted on, where the move has arrived, and where
  the train already stands in the block the move enters. A frame without a
  string `into` is unreadable and dropped. The simulator answers none: it
  drives every move at once
  ([#1068](https://github.com/rails49/control/issues/1068),
  [#1076](https://github.com/rails49/control/issues/1076),
  [#1080](https://github.com/rails49/control/issues/1080)).
- `tc49/layout/move_withdrawn` — `train`, `transit`, `into`: as asked.
  Published once per withdrawal taken, and read by the dispatcher, which
  drops one not naming the transit and `into` of a cancelled request's
  outstanding move
  ([#1068](https://github.com/rails49/control/issues/1068),
  [#1080](https://github.com/rails49/control/issues/1080)).
- `tc49/layout/throttle_wanted` — browser-writable — `train`; `speed`: a
  number in −1.0 … 1.0, the fraction of that train's maximum, `0.0` being
  stop, signed for which way the train runs along its own length — positive
  nose-first; `throttle`: the id of the throttle turning the lever. Applied
  where that throttle holds the train, granted move or not, while
  `state/power` reads `on` or `draining`; dropped at `off`, for a train
  `layout` holds no facing or no position for, and from any other throttle
  ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md),
  [ADR-0081](adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)).
  Which locomotive the speed reaches, and which way round it stands, is
  `layout`'s, which reads the roster. `tc49.lib.payload.wanted_throttle` reads
  `throttle` as a field that may be absent, and `layout` drops a frame without
  one. When a granted move ends at its sensor `layout` writes `0.0`, and the
  next frame is applied again. A frame whose sign is opposite to the last
  nonzero speed `layout` wrote for the train writes `0.0` instead, and so does
  every later frame of that sign until the throttle sends `0` or `layout`
  stops the train itself
  ([ADR-0084](adr/0084-a-reverser-moves-only-with-the-lever-at-0.md),
  [ADR-0088](adr/0088-a-stop-the-layout-writes-frees-the-reverser-as-the-throttles-0-does.md)).
- `tc49/layout/driving_wanted` — browser-writable — `driving`: enum `manual`
  or `automatic`, the same closed set `state/driving` below carries; any
  other value is dropped. Accepted at any power
  ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
  `layout` answers it.
- `tc49/layout/state/driving` — `driving`: enum `manual` or `automatic`, the
  railroad's driving mode. `layout` publishes `manual` when it starts. An
  unreadable payload reads as `manual`. In `manual`, a granted move of a train
  no throttle holds writes no traction: it stands at its signal until a
  throttle takes it. In `automatic`, `layout` writes the grant's speed for it.
  Switching to `manual`, a train `layout` is driving finishes its outstanding
  move and then stands; switching to `automatic`, each train with a move
  outstanding and no throttle is given its grant's speed.
- `tc49/layout/state/clock` — `time`: integer, fast-clock seconds since
  midnight, `0` to `86399`; `speed_up`: number greater than 0, fast seconds
  per real second. `layout` publishes it once a real second, by the monotonic
  clock and at the beat of `alive_confirmed`, while a railroad is loaded, and
  none while it stands, and at once after it takes a `clock_wanted`. The
  simulator, in its place, publishes it when it is given a fast clock, read
  off its run clock once a second of that run clock: a real second live. A
  batch run (`bench`) gives it none, so no benchmark run publishes a clock and
  a replay stays byte-identical. Loading a railroad clears it with the other `layout` rows
  ([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md))
  and starts the clock again at the start time and speed-up the railroad
  keeps in the store, `layouts/<layout>.clock.yaml`
  ([LAYOUT.md](store/LAYOUT.md)), or at the box's wall time of day at a
  speed-up of 1 where it keeps none. It wraps at midnight, has no date, and
  runs whatever track power and the run are doing. The page reads it, and a
  translator may pass it on to its hardware without acting on it; no other app
  does, and nothing in the control path may
  ([ADR-0044](adr/0044-the-boundary-period-is-real-time-and-the-fast-clock-is-out-of-the-control-path.md),
  [ADR-0090](adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).
- `tc49/layout/clock_wanted` — browser-writable — at least one of `time`:
  integer, seconds since midnight, `0` to `86399`, which the clock takes at
  once; and `speed_up`: number greater than 0, which the clock runs at from
  now. A field left out leaves that part of the clock as it is. A payload with
  neither, or with a value out of range, is dropped whole, as any malformed
  gesture is. Taken whatever track power and the run are doing. `layout`, or
  the simulator in its place, answers it, publishes `state/clock` at once and
  keeps the setting with the railroad: a new `time` as its start, rounded down
  to the minute, and the speed-up the clock now runs at
  ([ADR-0090](adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).
- `tc49/layout/take_wanted` — browser-writable — `train`; `throttle`: a
  non-empty string, the id the throttle's page minted when it opened, or
  `null` to release the train. A take of a train no throttle holds is
  applied; a take of a train another throttle holds is dropped. A take by a
  throttle already holding another train releases that train first, as `null`
  would. `null`
  releases the train whoever holds it, which is also the force release a
  panel makes. A missing `throttle` is not a release: the frame is dropped.
  Released in `manual`, the train's traction is written `0.0`. In
  `automatic` with a move outstanding and `state/power` reading `on` or
  `draining`, nothing is written and the train keeps its speed until the move
  ends, or, where the last speed written for it is `0.0` or none, it is given
  its grant's speed; otherwise `0.0`
  ([ADR-0081](adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md),
  [ADR-0083](adr/0083-a-train-released-standing-mid-move-is-given-its-grants-speed.md)).
  The id names the throttle that holds a train, not who sent a frame: any
  client may send any of these rows.
- `tc49/layout/throttle_alive` — browser-writable — `throttle`: the id. A
  throttle publishes it once a second while it holds a train. `layout`
  releases every train of a throttle it has not heard for 5 s by default,
  set per installation ([DEPLOY.md](DEPLOY.md#a-silent-throttle)), as
  `take_wanted` with `null` would.
- `tc49/layout/state/taken` — `taken`: map of train to throttle id. A train
  the map does not name, no throttle holds. Empty when `layout` starts. Read
  an entry at a time: an unreadable entry leaves its train held by nobody,
  and an unreadable payload holds nothing.
- `tc49/layout/function_wanted` — browser-writable — `train`; `throttle`: the
  id of the throttle holding the train, a non-empty string, where missing,
  `null` or empty fails the read; `function`: a function's name as the
  catalogue gives it, a non-empty string; `on`: a boolean, any other value
  failing the read. A frame whose `throttle` does not hold the train is
  dropped. Otherwise `layout` writes the `wanted/function` row of every car
  in the train that has an address and declares a function of that name, in
  the train's order, each on the car's number for it — the first in the car's
  declared order where it has two — with `value` set to `on`
  ([#1097](https://github.com/rails49/control/issues/1097)). A train the roster does
  not name, or a name no addressed car of the train declares, is dropped with
  a log line. Accepted at any power and in either driving mode. Nothing else
  writes a function row, with one exception: when `layout` lets go of a train
  (a release, `take_wanted` with `throttle: null`, a silent throttle), each of
  the train's **momentary** functions that `state/functions` says is on is
  written off, on each row a press of its name writes that is on
  ([#998](https://github.com/rails49/control/issues/998)). Latching functions,
  `train_removed`, a cut and a restart leave the rows as they are
  ([#849](https://github.com/rails49/control/issues/849)).
- `tc49/layout/state/functions` — `functions`: map of train to a map of
  function name to boolean, `true` where any `wanted/function` row a press
  of that name writes has `value` `true`. A train or name with no such row is
  absent, which reads off. Empty when `layout` starts, and published again whenever a
  `wanted/function` row it knows of changes: its own writes, and the retained
  rows a bus that outlived it hands back at start, so a light a decoder still
  has on shows on after a restart. An unreadable row is skipped.
- `tc49/layout/state/settings` — every field always present, a value nobody
  has set being its default:
  - `point_gap`: number, seconds, `0` to `5`, the time `layout` waits after
    a point command before it sends the next point command or lets go the
    move waiting on it; `0` is no wait. The gap the railroad keeps in the
    store, `layouts/<layout>.settings.yaml` ([LAYOUT.md](store/LAYOUT.md)),
    or `0.5` where it keeps none.
  - `speeds`: object, the railroad's: `clear` and `caution`, each a fraction
    of the locomotive's maximum, greater than `0` and at most `1`. So far
    nobody sets them, so they are `clear` 0.6 and `caution` 0.3
    ([ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
  - `throttle_silence`: number, seconds, `2` to `60`, how long a throttle
    holding a train may go unheard before `layout` lets go of its trains.
    The installation's, `TC49_LAYOUT_THROTTLE_SILENCE` or 5
    ([DEPLOY.md](DEPLOY.md#a-silent-throttle)): it does not change with the
    railroad, though like the rest it is on the row only while one is
    loaded ([#1130](https://github.com/rails49/control/issues/1130)).

  `layout` publishes it as a railroad is loaded; at once after it takes a
  `settings_wanted`; and none while it stands. Loading a railroad clears it with the other `layout`
  rows
  ([ADR-0060](adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
  The simulator does not publish it. The page shows the gap in the Settings
  dialog's Points tab; no app reads it yet, `layout` holding the gap and
  the silence it says
  ([#1125](https://github.com/rails49/control/issues/1125),
  [#1127](https://github.com/rails49/control/issues/1127)).
- `tc49/layout/settings_wanted` — browser-writable — any of these fields, at
  least one:
  - `point_gap`: number, seconds, `0` to `5`.
  - `speeds`: object with `clear`, `caution` or both, each greater than `0`
    and at most `1`.
  - `throttle_silence`: number, seconds, `2` to `60`.

  A field left out keeps its value, and so does a speed left out of
  `speeds`. A payload with none of the three, with an unknown field, or with
  any value out of range is dropped whole, as any malformed gesture is. It
  is also dropped while no railroad is loaded. Taken whatever track power
  and the run are doing, and a change needs no rebuild. `layout` uses the
  gap from the next `align`, publishes `state/settings` at once and keeps
  the gap with the railroad. So far it takes only the gap: a payload
  setting none changes nothing until `layout` keeps the speeds with the
  railroad and the silence with the installation
  ([#1132](https://github.com/rails49/control/issues/1132)). The page
  publishes the gap from the Settings dialog's Points tab
  ([#1126](https://github.com/rails49/control/issues/1126),
  [#1131](https://github.com/rails49/control/issues/1131)).

#### `schedule`

The fifteen browser-writable rows — the two here, the four under `dispatch`
and the nine under `layout` above — are where rule 4 bites hardest: each
payload is read defensively, and one that fails the read is dropped.

- `tc49/schedule/request_wanted` — browser-writable — `train`; `dest`: list,
  each entry a block or a block end, a bare block meaning either end.
- `tc49/schedule/reversal_wanted` — browser-writable — `train`.
- `tc49/schedule/state/exhausted` — `exhausted`: boolean, `true` once the
  last timetable request has gone out.
- `tc49/schedule/state/facing` — `facing`: map of train to the run it would
  make across its block, `<block>.A-to-B` or `<block>.B-to-A`; a train facing
  `<block>.A-to-B` would depart through that block's B end (GLOSSARY.md,
  **Facing**). A move changes it when the dispatcher records the train in
  the block entered, not at the grant. The bare end letter this value once carried is refused rather
  than read, a retained row written by an older build losing that train's
  facing rather than turning it round. Kept through a rebuild under the same
  railroad name and adopted as after a restart; cleared when another railroad
  is loaded ([ADR-0071](adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)).

#### `dispatch`

- `tc49/dispatch/request_submitted` — `id`: opaque unique string
  ([ADR-0033](adr/0033-a-request-id-is-unique-not-meaningful.md)); `train`;
  `depart`: the block end the train departs through, or `null` with `after`;
  `dest`: list of arrival block ends, at least one; `after` *optional*: the
  id of the train's request this one follows, so that it starts where that
  one ends. A request with `after` is admitted and goes in the list, and is
  not routed until the request it follows has arrived. Its departure end is
  then the end of the arrival block opposite the end the train came in
  through, so the train carries on the way it was going; where that end
  leads nowhere, the request is rejected `unreachable` at that time. Where
  the request it follows is cancelled underway and this one was chained
  after it once the cancel was asked, it departs the same way from the block
  the train stops in, or by the end the cancelled request departed by where
  the train never left its origin. Where the request it follows ends any
  other way, by rejection, by cancellation while it waited or underway
  before this one was chained, or by a placement or a removal, it is
  cancelled `revoked`
  ([#836](https://github.com/rails49/control/issues/836),
  [ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
  An `after` that names no request of the same train the dispatcher has
  admitted or answered, or that comes with a `depart`, is rejected
  `malformed`; one naming a request that has already ended is settled at
  admission as above. The scheduler composes a drag with `after` wherever
  the train has a request in flight, naming the latest of them
  ([#827](https://github.com/rails49/control/issues/827)).
- `tc49/dispatch/placement_wanted` — browser-writable — `train`; `block`:
  block name, or `null` for off the layout. The key's presence is
  load-bearing: a payload without `block` fails the read, while an explicit
  `null` is a positive statement
  ([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)). A block is
  accepted at any power where it is **free**: no train placed there, no lock
  on it, and on no active train's remaining route (`DispatchState.free()`).
  The placed train's own route is no claim, since an accepted placement
  cancels it first.
  A placement not accepted is answered on `placement_refused`, below, and
  changes nothing; one
  that cannot be read as a placement names no train and is dropped with no
  answer. `null` is accepted at any power
  ([ADR-0069](adr/0069-a-train-comes-off-while-running-and-its-track-opens-when-it-reads-clear.md),
  [ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
  With power `on`, a block reading occupied that nothing claims is an
  unexplained reading as before, so the drag comes before the cars go down.
- `tc49/dispatch/cancel_wanted` — browser-writable — `id`: the request to
  end. A request waiting is cancelled at once, and so is one underway with no
  move outstanding. One with a move outstanding is granted nothing further
  and asks `layout` for the move back on `withdraw_wanted`: it is cancelled
  at once on the `move_withdrawn` that answers it, where nothing has driven
  the train (`withdraw_wanted` says what that is), and otherwise when the move ends at
  its sensor
  ([ADR-0049](adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md),
  [#1068](https://github.com/rails49/control/issues/1068)).
  The requests of the same train chained after it before the cancel was
  asked are cancelled with it, each with its own `request_cancelled`, reason
  `revoked`. One chained after it once the cancel was asked departs from the
  block the train stops in, as after an arrival
  ([#836](https://github.com/rails49/control/issues/836)). An id the
  dispatcher does not hold is dropped like any other gesture it cannot act on
  ([ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
- `tc49/dispatch/reorder_wanted` — browser-writable — `id`: the request to
  move; `before`: the id of the request it is to go in front of, or `null`
  for the end of the list. The key's presence is load-bearing: a payload
  without `before` fails the read, while an explicit `null` is a positive
  statement. Dropped where either request has started, where either is
  unknown, or where it would put a train's chained request before the one it
  follows
  ([ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
  `tc49.lib.payload.wanted_reorder` is the reader.
- `tc49/dispatch/point_wanted` — browser-writable — `addr`: the point's
  address, a non-empty string; `position`: enum `closed` or `thrown`, the
  position wanted. The dispatcher drops it with no reply when `addr` is not
  a non-empty string or `position` is neither enum value, when no point on
  the loaded railroad wears `addr`, or when any point wearing `addr` lies on
  the way of a transit that is locked or committed. Otherwise it publishes
  `tc49/layout/align` with `connection` and `transit` `null` and the one
  point `{addr, position, reported}`, `reported` `true` where any point
  wearing `addr` is reported. It is accepted in every run state and with track
  power on or off
  ([ADR-0068](adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)).
- `tc49/dispatch/request_admitted` — `id`; `dest`: the arrival ends that
  survived pruning; `pruned`: list of `{end, reason}`, `reason` enum
  `no_fit`, `no_entry` or `unreachable`, from `tc49.lib.rejection`.
- `tc49/dispatch/request_rejected` — `id`; `reason`: enum `malformed`,
  `unknown_train`, `unknown_block`, `no_origin`, `wrong_origin`, `no_fit`,
  `no_entry`, `unreachable` — the set is `tc49.lib.rejection`, and the UI's
  copy of it is generated.
- `tc49/dispatch/request_completed` — `id`.
- `tc49/dispatch/request_cancelled` — `id`; `reason`: enum `revoked`,
  `removed`, `displaced` — the set is `tc49.lib.cancellation`. `revoked` is
  the gesture that names the request's own end, or the end of the request
  it follows, and the other two are the two directions of a placement that
  retired it.
- `tc49/dispatch/route_chosen` — `id`; `route`: list alternating block and
  transit names, starting and ending on a block, a single block for the
  degenerate already-there case; `k_tried`: integer, candidate routes
  examined, `0` for the degenerate case.
- `tc49/dispatch/move_granted` — `id`; `train`; `transit`: qualified
  `<connection>.<transit>`; `into`: the block entered; `aspect`: enum `stop`,
  `caution` or `clear`
  ([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
- `tc49/dispatch/grant_refused` — `id`; `reason`: enum `unsafe`, `held` or
  `transit_conflict`, the set `tc49.lib.inventory.Refusal`; `obstacles`: list
  of `{resource, holder}` — the block or transit that blocked a candidate, and
  the train holding it. `held` is a block or transit held by another train
  (`Refusal.HELD`), never the run. A grant not made because power is not `on`
  is not announced here
  ([ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
- `tc49/dispatch/lock_granted`, `tc49/dispatch/lock_released` — `train`;
  `resources`: list of blocks and transits.
- `tc49/dispatch/train_placed` — `train`; `block`.
- `tc49/dispatch/placement_refused` — `train`: the train the
  `placement_wanted` named; `block`: the block it named, or `null` for a
  removal; `reason`: enum `unknown_train` (on neither the dispatcher's roster
  nor the store's, read again), `unknown_block`, `not_free`, `no_fit` — the
  set is `tc49.lib.rejection.PlacementRefusal`, and the UI's copy of it is
  generated. It names what the gesture named and so carries no id
  ([ADR-0092](adr/0092-an-app-reads-the-roster-again-for-a-train-it-has-not-got.md)). Read by the run
  view's roster pane, which says it under the train's row
  ([#1011](https://github.com/rails49/control/issues/1011)).
- `tc49/dispatch/train_removed` — `train`.
- `tc49/dispatch/state/moving` — `moving`: boolean, true while any train is
  crossing and false otherwise: from the grant of a move until the sensor says
  the train arrived in the move's `into` block, and while a restored crossing
  hint names it ([#123](https://github.com/rails49/control/issues/123)). A
  train standing in a block, at a signal partway along its route or anywhere
  else, is not moving, so on a route of several moves it goes true and false
  once per move ([#844](https://github.com/rails49/control/issues/844)).
  Republished when it changes. A
  reader takes an unreadable value as `true`
  ([Payload schemas](#payload-schemas)). `layout` reads it to end a drain
  ([ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
- `tc49/dispatch/state/aspects` — `aspects`: map of signalled block end to
  aspect. An end nothing ever leaves does not appear.
- `tc49/dispatch/state/disputed` — `trains`: sorted list of trains standing
  in a block that reads clear; `blocks`: sorted list of blocks reading
  occupied with nothing claiming them. Both empty unless power reads `off`
  ([ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
- `tc49/dispatch/state/unfit` — `trains`: list of `{train, block, why}`, in
  train order: each train the last rebuild under the same railroad name took
  off the layout, the block it stood in, and `why` — `gone` where the new
  drawing has no such block, `short` where the block no longer holds the
  train. Published from the constructor, `[]` when nothing came off, so a
  joining client is served a value
  ([ADR-0032](adr/0032-a-joining-client-is-served-the-runs-retained-state.md));
  republished without a listed train once it is placed (`train_placed`).
  The next rebuild replaces it, and loading another railroad clears it with
  the rest of the dispatcher's rows
  ([ADR-0071](adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md),
  [#709](https://github.com/rails49/control/issues/709)). Read by the run
  view.
- `tc49/dispatch/state/broken` — `rules`: sorted list of strings, one per
  lock-table rule the dispatcher's last check found broken, the same line it
  writes to stderr ([ADR-0076](adr/0076-a-broken-lock-table-holds-the-run.md)).
  Published from the constructor, `[]` when nothing is broken, and again
  whenever the list changes, back to `[]` once the tables agree again. A
  broken rule is a bug; the run view shows each as `dispatcher: <rule>` on the
  band, so a drain the dispatcher asked for itself says why
  ([#1118](https://github.com/rails49/control/issues/1118)).
- `tc49/dispatch/state/allocation` — `trains`: map of train to standing
  block; `crossing`: map of crossing train to its transit; `locks`: map of
  resource to holding train; `requests`: list of
  `{id, train, depart, dest, after, route, refused, cancelling}` in **list order**, the order the
  dispatcher serves them
  ([ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)),
  `after` *optional* — present where the request follows an earlier one,
  as on `request_submitted`; `route` *optional* — present once the route is
  committed, which is when the request has started; `depart` is `null` on a
  request with `after` until the one it follows has arrived;
  `refused` *optional* — `{reason, obstacles}` as the latest `grant_refused`
  for the request carried them, at a launch or for the next move of one
  underway, and gone once a launch or a move is granted it; `cancelling`
  *optional* — the block the outstanding move enters, as `withdraw_wanted`
  names it in `into`, from the `cancel_wanted` held for that move until the
  request leaves the list. Both are here so a page that connects after the
  event shows what one open at the time did
  ([#1117](https://github.com/rails49/control/issues/1117)); the restart
  reader ignores them. Kept through a rebuild under the
  same railroad name, then republished by the new build: each train is placed
  again where its block still exists and still holds it, and the run comes up
  held. Cleared when another railroad is loaded
  ([ADR-0071](adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)).

#### `ui`

A widget payload is **raw**: not JSON, no `at`, and no field control defines.
Control carries it without reading it
([ADR-0087](adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md) decision 4).

- `tc49/ui/state/text/<name>` — UTF-8 text, shown as it arrives. ANSI SGR
  codes are kept in the row as written; the page renders bold, red, amber and
  green, and removes any other code
  ([#929](https://github.com/rails49/control/issues/929)). Retained, so a page
  opened later shows the current text. Two writers of one row overwrite each
  other, and a deleted widget's row stays on the broker.
- `tc49/ui/state/toggle/<name>` — browser-writable — the toggle's on payload
  or its off payload, as typed in the drawing. A page reads the toggle's
  position by comparing the row with the two payloads; a row matching neither,
  or no row, shows neither position. Retained, so a page opened later and a
  listener that restarts both find the position. No app of control reads it;
  a listener outside control does.
- `tc49/ui/button/<name>` — browser-writable — the button's payload, as typed
  in the drawing. One press publishes once, whatever the track power. An
  event, not retained, so a page opened later and a listener that restarts
  find no press. No app of control reads it; a listener outside control does.

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
(ADR-0047). Nothing needs it yet: a timetable goes in whole at the
start of a run, and the queue does the staggering.

**No event payload carries a timestamp.** Time on the record is observation:
the trace tap stamps each line with `time`, seconds since the run started
— simulated in batch, wall live — and no event, request or grant carries one,
so no app can read one or come to depend on it. A **state** payload carries
`at`, and does not breach that rule: it is stamped by the binding that
publishes rather than by an app, it says the order two values of one topic
were published in and nothing about the hour of the day, and it is read by
that comparison alone.

**`layout` publishes the fast clock** on `tc49/layout/state/clock`, once a
real second while a railroad is loaded: the railroad's time of day and its
speed-up. The simulator, when it is given one, publishes the same row off its
run clock; a batch run gives it none. A person sets it from any page with
`tc49/layout/clock_wanted`, and every page is told at once. The railroad keeps
the start time and speed-up it is loaded at, saved when a person sets them and
never as the clock runs. Every page draws the time it is sent and reads no wall
clock of its own, so two tablets whose clocks disagree still show one time
([ADR-0090](adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).
Nothing in the control path reads it — it feeds scheduling and scenery, never
dispatch and never safety, so a train that is late is late and nothing follows
from it
([ADR-0044](adr/0044-the-boundary-period-is-real-time-and-the-fast-clock-is-out-of-the-control-path.md)).

## Device vocabulary

What passes between `layout` and the hardware under it, in two halves: one
retained state topic per device naming what that device should do, and one
naming what it is observed to do. Every row has a single writer (rule 1) —
`layout` for a desired row, and for an observed one the one thing that answers
for that address — and whatever recognises an address acts on it while
everything else ignores it, so no ownership table exists anywhere and an
address nothing answers to does no harm, as a packet nobody picks up does
([ADR-0043](adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
The rows are `tc49.lib.inventory.DEVICE_TOPICS`. What a translator does
with them, and where it cannot, is in that translator's own repository.

**What `layout` asks of the hardware.** `wanted/point` is written on each
`align`, `wanted/signal` on each aspect the dispatcher shows, `wanted/track` on
each press of the power (#287), `wanted/traction` on each `move` it acts on
and again on the arrival, its sign composed from the train's facing and the
way round each car is coupled
([#296](https://github.com/rails49/control/issues/296)), and
`wanted/function` on each `function_wanted` it applies
([#849](https://github.com/rails49/control/issues/849)) and off for each
momentary function on when it lets go of a train
([#998](https://github.com/rails49/control/issues/998)). `wanted/function`'s
`value` is a **boolean** and not a word out of a catalogue:
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
| `tc49/layout/state/wanted/track` | `power` | `power` `on` or `off` |

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
| `tc49/layout/state/device/link/<id>` | `id`, `link`, `detail` | `link` `up` or `down`; `detail` *optional*, free text |
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

**The supply is `on` or `off`.** The observed row carries no drain, and
that asymmetry is the vocabulary's own: what the railroad is doing with its
supply is not bounded by what a sensor can answer. A drain keeps the rails
live until nothing is moving, so under one the supply reads `on`, and that is
the truth about the supply rather than a gap in what a publisher can report
([ADR-0063](adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)).
Whether the railroad is draining is `tc49/layout/state/power`, which gets that
value from `layout`'s own answer rather than from this row. A `device/track`
frame stating any third value is refused like any other value outside the
closed set, and reads `off` with them.

**`reason` on the supply is for the participant that cannot reach it**:
`{power: off, reason: "…"}`, so a person reads why the railroad is dark
without a second row to find. Free text and optional, on the same terms as
the sensor's — nothing branches on it, and a supply that reads `off` with no
reason is no less `off`.

**It also names a district the hardware cut itself.** A district reaches no
topic, so a trip the publisher can see has nowhere else to be said: while one
is tripped the `reason` names it, `{power: on, reason: "district B tripped"}`
where another district is still powered and `power` `off` where none is
([`rails49/dccex`](https://github.com/rails49/dccex) ADR-0016,
[#601](https://github.com/rails49/control/issues/601)). The `on` case is why
the row carries it at all: the supply really is on, so without the reason that
frame reads exactly like a railroad with nothing wrong with it, which is the
one failure nobody can act on
([ADR-0050](adr/0050-broken-hardware-is-reported-never-worked-around.md)).
`power` does not change with it and neither does the fold — `layout` reads
`power` alone, so a trip holds no run and `tc49/layout/state/power` goes on
saying what the rails carry. The reader of the reason is a person: the band
shows it as a fault, whichever way `power` stands, and nothing branches on it
([ui/EDITOR.md](ui/EDITOR.md#the-band),
[#602](https://github.com/rails49/control/issues/602)).

**A reason about the link takes precedence.** One free-text field and two
conditions that can hold at once, so what it says is the participant that
cannot reach the supply: a publisher that has lost its station cannot see
which district tripped either, and naming one it can no longer observe is the
stand-in ADR-0050 refuses. The trip is named again once the link is back, the
row being a retained level and a trip a condition that holds until somebody
resets it.

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
pass. For an address the drawing lists as `reported`, `device/point` is where
the point lies: the translator that drives it publishes the position the
hardware measured, or, where it measures none, the position it last put the
hardware in, whether from `wanted/point` or from its own logic
([ADR-0097](adr/0097-a-reported-point-lies-where-device-point-says-and-a-train-waits-for-it.md)).
For any other address a translator publishes `device/point` only where its
hardware actually reports a position, a commanded one never being echoed back
as a measured one (ADR-0043), and `wanted/point` stands for where the point
lies; turnouts without feedback
([ADR-0022](adr/0022-a-symbol-carries-its-hardware-address.md)) get none, a
faked reply being worse than silence. `layout` and the Run view read
`device/point`; the dispatcher does not.

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
publishes nothing, and each translator's own doc says which those are.
`layout` does not subscribe it.
It is for a UI, for a person to read, and nothing branches on it.

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

