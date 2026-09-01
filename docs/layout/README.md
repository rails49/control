# Layout

The layout interface is a core app, `layout`: always running,
hardware-independent, and the only writer of what the hardware is asked to do
([ADR-0043](../adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
Above it the railroad is blocks, transits and trains; below it is the **device
vocabulary**, one retained state topic per device
([SYSTEM.md](../SYSTEM.md#device-vocabulary)). Nothing above this app names a
device and nothing below it names a transit, which is what lets two hardware
systems drive one railroad with no ownership table anywhere.

It is the physical binding of the interface, and the normative one: the
`simulator` is the other binding of the same contract, and where the two could
differ the physical railroad decides
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)).
Neither knows about the other, and a run has one of them.

The general contract is [SYSTEM.md](../SYSTEM.md#layout-interface), which is
where the topics and their payloads are. This page is what this app does with
them.

## What it reads and writes

*Reads* the layout — the transits a `move` may name, and the signal standing at
each block end. Nothing else: the points a transit needs ride on `align`
([ADR-0031](../adr/0031-the-layout-carries-the-points-a-transit-needs.md)), so
this app throws what it is told and holds no table of its own.

*Subscribes* `tc49/layout/align`, `tc49/layout/move`,
`tc49/layout/power_wanted`, `tc49/dispatch/train_placed`,
`tc49/dispatch/train_removed`, `tc49/dispatch/state/aspects` and
`tc49/layout/state/device/#`.

*Publishes* `tc49/layout/block_occupied`, `tc49/layout/block_vacated`,
`tc49/layout/state/wanted/point/<addr>`,
`tc49/layout/state/wanted/signal/<addr>`, `tc49/layout/state/wanted/track` and
`tc49/layout/state/power`.

## The command line

There is none yet, and that is the milestone and not the app: the bus is a
Python object inside one process ([SYSTEM.md](../SYSTEM.md#the-bus)), so no
core app has a command line — `scheduler`, `dispatcher` and `driver` have none
either. `station` does, and it is the one app that speaks no bus topic at all.

The app is constructed on the bus like the rest of them, with the railroad it
answers for, the run clock, and the settling time the debounce below uses:

```python
LayoutInterface(bus, layout, clock)          # 300 ms of settling
LayoutInterface(bus, layout, clock, 0.05)    # detectors that need less
```

The clock is required rather than defaulted for the bus's reason: an app given
none would debounce against a clock that never moves. Whoever owns the loop
calls `settle()`, which is what acts on a level that has stood long enough —
there is no loop yet, so today the suite is the only caller.

It gets a command line, and `deploy/` gets a container for it, the day the
broker arrives and each app is its own process
([ADR-0013](../adr/0013-apps-are-deployment-units.md)). The bench harness
assembles the `simulator` instead
([ARCHITECTURE.md](../ARCHITECTURE.md#package-layout)): a run has one binding
of the interface, and the benchmarks measure a railroad nobody has to power on.

## The three command rules

Each of them exists because the bus promises less than it looks like it does,
and each turns a command that was true once into a no-op rather than into a
collision.

**Align before move.** The two commands have two publishers and the bus
promises no ordering between topics, so a `move` naming a transit no `align`
has named is **held** until one does, and the points are written first.
Starting a train onto points that have not thrown is what the rule prevents,
and this is the only component that sees both commands. An `align` names its
transit before every grant, so a held command waits for the next frame and not
for a timer.

**The near-end check.** A `move` is acted on only if that train is standing at
the transit's near end
([ADR-0047](../adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
At-least-once delivery can repeat one minutes late, and after arrival the train
has left the near end — so a redelivery is a no-op **on state alone**, with no
clock, no stamp and no agreement between apps. The same check refuses a command
overtaken by a hand's placement and one naming a train no longer on the layout.
Where each train stands comes from `train_placed`, `train_removed` and the
moves this app has itself carried out.

**No move while the rails are dead.** Nothing is acted on while `state/power`
is not `on`
([ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
That is what makes a restart safe, and it has teeth on every one of them now
that the app comes up with the railroad off. A command that arrives dead is
dropped rather than queued: one honoured minutes after the power came back is a
train moving long after anybody asked for it, and the run is held when power
returns anyway.

A held command meets all three at the moment it is acted on and not at the
moment it arrived, since the railroad can move under it while it waits.

**Every payload is read and never trusted**
([SYSTEM.md](../SYSTEM.md#event-inventory), rule 4). Six topics from five
publishers reach this app and it answers none of them — it reports observations
— so a frame that cannot be read is **dropped**, silently and to the trace, and
so is a command the layout contradicts: one naming a transit this railroad does
not hold, or one whose transit reaches neither end of the block the command says
the train is entering. Either way the command names no near end for a train to
be standing at.

## Alignment

An `align` carries the points its transit needs as address-and-position pairs,
read from the layout by the dispatcher (ADR-0031). This app writes one desired
value per **address** and holds no table: two pairs naming one address are one
write, since one accessory output throws a crossover's two ends as a unit and a
way may name that address twice. Where two pairs on one address disagree about
the position the first is written — a way that wants one address in two
positions cannot be set at all, and the drawing's review is where that fault is
reported, not the wire.

The points are written **again on every `align`**, never only on change: a hand
may have flipped one since, and a translator throws what it is told (ADR-0043).

## Aspects

On every `tc49/dispatch/state/aspects` this app writes `wanted/signal` for each
signalled end, looked up through the layout's `signal_at`. Ends no signal
stands at are skipped — an end nothing ever leaves carries none, a signal that
could only show `stop` being furniture. The lookup is here and not in the
dispatcher because `state/aspects` is read by the panel and by a person driving
by eye, and neither of them wants an address
([#203](https://github.com/rails49/control/issues/203)).

At startup every signalled end is seeded `stop`, and that needs no rule of its
own: a held run puts every signal to stop and the dispatcher's value names
every signalled end, so the retained value this app is handed on subscribing is
the seed. Two ends sharing one address are two writes to one topic and the last
stands, which is what one output driving two heads does.

## Occupancy

**Levels in, edges out.** A detector reports presence at one block end, and
presence is a level that can be asked for at any time; the bus carries the
changes because it is an event bus
([#243](https://github.com/rails49/control/issues/243)). So this app holds the
level at each block end and publishes `block_occupied` or `block_vacated` only
where a level moves. A repeated level re-asserts what is already held and is a
no-op, which is the whole of what at-least-once delivery needs here: no
counter, no dedup.

**A block reads occupied while either of its ends does.** Both of a block's
detectors stay inside the interface
([SYSTEM.md](../SYSTEM.md#layout-interface)), so what the pair answers together
is one occupancy, and a change in that fold is the block's own event. It is
published whether or not a move explains it: a hand putting a locomotive down
is how every session starts, and what to make of a reading nothing accounts for
is the dispatcher's judgement — it holds the run and names the block for a
person to walk
([ADR-0048](../adr/0048-an-unexplained-reading-holds-the-run.md)) — not this
app's.

**The block behind is named by the move.** A train entering block Y trips Y's
first detector with its head and its second once it is fully in. The first is
`block_occupied(Y)`; the second is `block_vacated(X)`, and X is the block this
app's own accepted `move` left. That is the one event no detector could
produce: occupancy is anonymous, and nothing below the interface knows what is
behind a train. So the physical order is **occupied then vacated**, which is
the order the dispatcher already expects (ADR-0047).

Which end of the entered block the train comes in at is the end across the
transit, read off the layout from the `move` that was carried out. The block's
*far* end is a different thing — its second sensor, the one a train trips once
it is fully in — and the two are opposite ends of the one block
([#279](https://github.com/rails49/control/issues/279)).

**The debounce.** A camera-based detector runs at 2–8 Hz with no debounce of
its own and is biased towards reporting occupied, so a new level is held for a
**settling time** before it is acted on, and a level that flips back inside
that window is never seen upstream. The settling time is **configuration**: a
constructor argument, 300 ms by default, because what it is worth is a fact
about the detectors a railroad has and not something this app can know
(ADR-0030). It is on no topic, and nothing above the interface is told there is
a debounce at all.

**`unknown` is no information about that end.** No edge comes of it, it does
not discard the level the end last actually had, and it does not cancel a level
that is settling. The `reason` beside it is logged once per transition into
`unknown`, for a person: the detector knows why it cannot say — no model, not
calibrated, drift — and nothing in the system branches on it. If the end a
crossing train is expected to arrive at is `unknown` when it should have fired,
nothing new happens here: the arrival is never confirmed, which is already
ADR-0040's second leg — a timer stops the train and wedges the block, with
removal as the recourse
([#237](https://github.com/rails49/control/issues/237)).

## Power

**Commanded on arrival, never buffered.** There is no beat and no time
quantisation, and an emergency stop that waits is not an emergency stop
([ADR-0051](../adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)).
A `power_wanted` is written straight through to `wanted/track` with the word it
was given, and **nothing is said about `state/power` on the strength of having
commanded it**: a railroad that answered `on` because somebody pressed ON would
be this app taking its own word for the state of the track. It cannot verify
that the supply really went and does not try — it assumes the device it
commanded did what it was asked, and it is the system designer's job to put such
a device there ([#232](https://github.com/rails49/control/issues/232)).

**`state/power` is folded from what the hardware reports.** The supply's own
word, `device/track`, wherever every `device/link` that has ever been seen
reads `up`; `off` otherwise. A translator that cannot reach its hardware leaves
a railroad no train may move on whatever the supply says, since the translator
saying it may be the unreachable one. *Ever seen* and not *currently connected*:
a link is a retained level, so one that published `down` and then died leaves
the value standing, and forgetting it would turn a broken railroad back on
([ADR-0050](../adr/0050-broken-hardware-is-reported-never-worked-around.md)).

Anything that cannot be read falls the same way, which is the direction a state
topic must fail in
([#181](https://github.com/rails49/control/issues/181)): a supply that cannot be
read is not one a train may move on, and a link that cannot be read is not one
this app may call good. `stopped` reaches `state/power` as itself rather than as
`off`, because the two differ for the person recovering — one is cleared and the
other switched back on — while the dispatcher branches on "not `on`" either way
(ADR-0041).

**On startup the railroad is off.** The app comes up having written
`wanted/track: off` and `state/power: off`, so nothing moves and no turnout
throws until a person turns it on, normally from the panel. Thereafter it never
writes `off` of its own accord: it writes the word it was told to write, and
the supply going away below it moves `state/power` and never `wanted/track`.

## What is not here yet

- **The traction write**, `tc49/layout/state/wanted/traction/<addr>`, and
  therefore anything that turns a wheel. It composes a speed's sign out of the
  train's facing and each car's orientation, which is why it is
  [#296](https://github.com/rails49/control/issues/296) and why this app reads
  no roster today. An accepted `move` records the train as crossing and stops
  there; the absence is deliberate.
- **A train's mode and a person's throttle**, which reach the locomotive
  through that same write
  ([#297](https://github.com/rails49/control/issues/297)).
- **Any hardware protocol.** This app speaks the device vocabulary and nothing
  else; what a translator does with an address is its own business.
