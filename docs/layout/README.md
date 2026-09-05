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
each block end — and the **roster**, which is how a train becomes the addresses
that answer for it. Nothing else of the railroad's: the points a transit needs
ride on `align`
([ADR-0031](../adr/0031-the-layout-carries-the-points-a-transit-needs.md)), so
this app throws what it is told and holds no table of its own.

*Subscribes* `tc49/layout/align`, `tc49/layout/move`,
`tc49/layout/power_wanted`, `tc49/layout/mode_wanted`,
`tc49/layout/throttle_wanted`, `tc49/dispatch/train_placed`,
`tc49/dispatch/train_removed`, `tc49/dispatch/state/aspects`,
`tc49/dispatch/state/run`, `tc49/schedule/state/facing` and
`tc49/layout/state/device/#`.

*Publishes* `tc49/layout/block_occupied`, `tc49/layout/block_vacated`,
`tc49/layout/state/wanted/traction/<addr>`,
`tc49/layout/state/wanted/point/<addr>`,
`tc49/layout/state/wanted/signal/<addr>`, `tc49/layout/state/wanted/track`,
`tc49/layout/state/power` and `tc49/layout/state/mode`.

The facing is the one topic here that is nobody's hardware and nobody's
command: it is the scheduler's state, and this app reads it because the sign of
a speed cannot be composed without it and there is nowhere else it lives
([ADR-0052](../adr/0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md)).
The run is the second of that kind, and read for one thing only — the guard
on a plain `off` below
([ADR-0062](../adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)).
Nothing else here branches on the run: a `move` is acted on because it was
granted, and a held run grants none.

## The command line

```
python -m tc49.layout --broker <host:port> --railroad <name> --store <url>
```

Three flags, the ones a compose service passes: where the broker is, which
railroad it runs, and where the store serves the documents that railroad is
built from ([ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
decision 5). Started against an empty broker with no store and no other app
running, it reads its two documents — retrying until the store answers — waits
for the broker, waits out the moment the broker takes to hand back whatever
traction rows the last process left, publishes its own retained rows and stays
up. It exits on nothing but a signal.

That last wait is what the constructor's zeroing needs on this binding: a
traction row is retained, so a broker that outlived the last process hands the
speed it was left at back verbatim, and the row's one writer is this app
([#333](https://github.com/rails49/control/issues/333),
[ADR-0054](../adr/0054-the-railroad-comes-up-at-rest-and-points-replay.md)).
The in-process bus had those values synchronously; a broker sends them moments
after the subscription lands.

The settling time is not a flag. What it is worth is a fact about the
detectors a railroad has
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)), so
it is the constructor's argument and the suite's to drive, not a number a
person restarts a container to change.

The app is constructed on the bus like the rest of them, with the two
documents the railroad is — the layout it answers for and the roster of stock
that runs on it — the run clock, and the settling time the debounce below
uses:

```python
LayoutInterface(bus, layout, roster, clock)          # 300 ms of settling
LayoutInterface(bus, layout, roster, clock, 0.05)    # detectors that need less
```

The clock is required rather than defaulted for the bus's reason: an app given
none would debounce against a clock that never moves.

**Whoever owns the loop calls `settle()`**, which is what acts on a level that
has stood long enough. In the deployment that is this app's own process: it
advances the clock to wall time, calls `settle()` and drains the bus, once per
period. The harness does the same in one process, standing this app and the
`dccex` translator where the simulator would be
([#314](https://github.com/rails49/control/issues/314)), and the loop is the
same three steps. The period bounds the resolution and nothing
else: 0.1 s against 300 ms of settling has a settled level acted on between
0.3 s and 0.4 s after it stood, which is the right order for a detector.
Nothing schedules the call — a detector publishes a level *change* and nothing
else, so an owner that never made it would sit on a quiet railroad holding an
arrival nobody was told about. The suite drives the clock rather than sleeping
on it and calls `settle()` itself.

**Whose levels those are, on a physical railroad, is a person's.** No camera
publishes `device/sensor` yet, so somebody types them a line at a time and
what they type is published as the row a detector would write, by
`tc49 readings` — that keyboard as a client of the broker beside this app
rather than in one process with it
([#315](https://github.com/rails49/control/issues/315),
[#379](https://github.com/rails49/control/issues/379)). This app is told
nothing about it: a typed level settles, folds and completes a crossing
exactly as a camera's does, which is the whole of what standing in for
hardware means — and it is the reason the fold is tested against typed levels
as readily as against a detector's.

A box runs `python -m tc49.simulator` where it does not run
`python -m tc49.layout`, which is what makes it a simulation rather than steel
([DEPLOY.md](../DEPLOY.md)): a run has one binding
of the interface and neither knows the other exists
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)),
and the benchmarks measure a railroad nobody has to power on.

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

An `align` authorises **one** crossing and the move that is acted on spends
it, so the rule guards every crossing of a transit and not only its first. A
record of every transit ever aligned would pass the check forever after the
first move, which is a train sent over points that have not thrown or that a
later `align` for a crossing route has since thrown the other way (#305). This
fails closed — a move with no `align` of its own waits — and costs nothing in
the ordinary order, the points being thrown for each crossing whether or not
this app remembers the last one.

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
returns anyway. The value read is the **observed** one, folded from what the
hardware reports below, so a `move` arriving while a cut is in flight is still
acted on until the station says the supply went
([ADR-0062](../adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md),
as amended).

A held command meets all three at the moment it is acted on and not at the
moment it arrived, since the railroad can move under it while it waits.

**Every payload is read and never trusted**
([SYSTEM.md](../SYSTEM.md#event-inventory), rule 4). Nine topics from six
publishers reach this app and it answers none of them — it reports observations
— so a frame that cannot be read is **dropped**, silently and to the trace, and
so is a command the layout contradicts: one naming a transit this railroad does
not hold, or one whose transit reaches neither end of the block the command says
the train is entering. Either way the command names no near end for a train to
be standing at.

## The traction write

On a `move` it acts on, this app publishes
`tc49/layout/state/wanted/traction/<addr>` for every car of the train that has
an address, and `0.0` to exactly those addresses again when the train arrives.
It is the last thing between the device vocabulary and a wheel turning, and it
is the one write here that composes two facts rather than passing one on.

That is a train this app is **driving**. A train a person has taken in a
throttle gets neither write, and the same rows are where their lever lands
instead (*Who drives* below).

**How fast** is the move's own `speed`, a magnitude in 0.0 … 1.0
([#283](https://github.com/rails49/control/issues/283)). The sign is this app's
to give and never the command's, so what is taken is the magnitude and a frame
that signed one anyway does not get to reverse a locomotive by it.

**Which way** is two facts composed:

1. **Does this move leave the end the train faces?** The move's departure end
   is the end of the origin block the transit crosses, and facing — read from
   `tc49/schedule/state/facing`, a retained state topic, so the last value is
   there even with the scheduler down — says which end the train's nose points
   at. Equal means the train goes nose-first; different means it is
   **propelled**, which is an ordinary movement and not an error (CONTEXT.md,
   **Propelled**).
2. **Which way round is this car coupled?** The `orientation` on the car's
   entry in the train, `forward` or `reverse`
   ([ADR-0045](../adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
   This is what lets a locomotive at each end of a train run opposite.

So the sign sent to one car is **positive** when the move is nose-first and the
car is `forward`, or when the move is propelled and the car is `reverse`, and
negative otherwise.

**Which cars.** Every car of the train that has an `addr`, in the train's own
order. A car whose model's `kind` is not a locomotive but which carries a
decoder is commanded too — nothing here reads `kind`, because a powered van is
a real thing and the address is what says a car can be told a speed.

### Two refusals

**No facing, no move.** A `move` for a train whose facing this app has never
seen is dropped: none published for it, one it cannot spell, or one naming a
block other than the one the train is departing. Guessing is a locomotive
driven the wrong way down the track, and a drop is what a failed read is worth
for an app that answers nothing ([SYSTEM.md](../SYSTEM.md#event-inventory),
rule 4). Nothing holds the command for a facing, so a facing arriving later
does not retroactively run the train — where a command is *held* for its
`align`, though, it is signed on the facing it has at the moment it acts, like
every other rule here. A `move` that states no **speed** falls the same way and
for the same reason: this app would have to choose a number nobody asked for.

**No address, no command.** A train whose cars carry no address at all — the
simulator's trains are like this, and so is anything a hand moves — still gets
its `align`, its near-end check and its crossing record, and simply has nothing
to publish. That is not a failure and is not logged as one, and it is the same
answer for a train this railroad's roster does not name: there are no wheels
there to turn the wrong way, so no facing is wanted either.

### Arrival

`0.0` goes to every address this app commanded, on the **first** of the entered
block's ends to settle occupied — the reading `block_occupied` goes out on. It
does not wait for the vacate: the train is in the block it was sent to, and the
tail clearing is a fact about the block behind. Exactly the addresses that were
commanded, since a car nothing was sent for is a car nothing may be sent for.

## Who drives, and a person's throttle

A train is **automatic** or **manual**: taking it in a throttle makes it manual
and giving it back puts it back
([#207](https://github.com/rails49/control/issues/207)). The word names who
turns the throttle and **nothing else** — a manual train is dispatched like any
other, holds its block, is granted moves, and a person is trusted to read the
signal it is given. Neither the dispatcher nor the driver ever hears of it.

**The map.** `tc49/layout/mode_wanted` states where a train's mode is to stand
rather than asking for a change, so a second `manual` on a train already taken
is not a race. This app holds the map and publishes the whole of it on
`tc49/layout/state/mode` whenever it changes, holding only the manual trains:
`automatic` is the resting value, so a train the map does not name is
automatic. `train: null` names **every** train this app holds — every train it
has a position for — which is a thing a person does to a railroad rather than
to the train they have picked. Handing the railroad over that way **skips the
trains this app is driving** and takes the rest
([#436](https://github.com/rails49/control/issues/436)): a gesture about the
railroad is not a person looking at a train, and taking one under way on a
grant would stop the arrival being this app's to write, so it would keep its
commanded speed past the block it was sent to. The skipped trains are dropped
to the trace and nothing is published to name them — `state/mode` is what says
where every train's mode now stands. A train somebody **names** is untouched in
either direction, and so is `train: null` with `automatic`, which is giving
trains back and asks nothing of a moving one. A gesture that cannot be read
leaves the mode
where it was: falling to `manual` would hand a train to a person who is not
there, and falling to `automatic` would take one out of the hands of a person
who is. On startup the map is empty and the topic says so, and a value a
previous session left there is superseded rather than adopted — the mode is a
person's hand on a throttle, and a restart is not a hand.

**What the mode changes is one thing: whether this app writes the wheels.** A
manual train's `move` still throws its points, still meets the near-end check
and is still recorded as crossing — that is the route, and the route is not the
driving. The traction write is the person's, so nothing goes out on the grant
and no `0.0` goes out on the arrival: a person stops their own train, and the
signal at the far end is what tells them to. The two refusals above have
nothing to refuse either, a move with no facing being carried out like any
other, since there is no sign here to guess at.

**Taking a train writes nothing.** It keeps whatever speed it had and the
person's first movement of the lever is what changes it. Writing zero on
take-over would stop a running train the instant somebody selected it, which is
not what selecting it means. What does change is the arrival: a crossing this
app was driving stops being its to stop.

**Giving it back writes the speed the train's current grant implies**, which is
`0.0` where there is none — a train handed back mid-transit does not keep the
speed a person left on it. There is no grant to imply a speed in three cases
and they write `0.0`: no move of that train's is in flight, one is but this app
could not sign it, and the rails are dead, over which a grant cannot be acted
on at all and a running speed left standing on a row is a train that would
start the moment the power came back.

**The lever** is `tc49/layout/throttle_wanted`, a speed in −1.0 … 1.0 signed
for the train — positive nose-first — and it reaches the same rows a `move`
does, one signed speed per addressed car composed the same way. The one
difference is where nose-first comes from: a move states a destination block
and the sign is composed against the train's facing, where a lever states the
direction outright. So a person pushes forward and the train moves nose-first,
whichever way round the locomotives are wired and however many of them there
are.

Four things drop a gesture, and none of them is answered:

- **A train that is not manual.** The grant is what moves an automatic train,
  and a lever nobody is holding does not get to overtake it.
- **Dead rails**, which refuse a person's hand as they refuse a grant
  (ADR-0041). Nothing is written rather than a zero: the row holds whatever it
  last held, and a gesture that could not be acted on has said nothing about
  it.
- **A train this app does not hold**, standing nowhere it knows of.
- **A train it has no facing for** — none published, or one it cannot spell.
  Which **block** that facing names is not asked, where a `move` asks it: the
  sign here is the lever's own, a facing lags the train it is about — another
  app publishes it, on another topic — and a lever that went dead for as long
  as the lag lasted would be a person pulling back to stop and not being heard.

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

**One departure is one release.** The same departure reaches this app twice —
as the move it carried out, which is what names the block behind, and as that
block's own detectors going clear, which is the tail leaving — and which
settles first is a race, the train being out of X at the instant it is fully
into Y. So whichever arrives first publishes the `block_vacated` and the other
says nothing: what this app has said about each block is one record, written by
whichever rule publishes it, and the occupied levels X still holds when the
move releases it are the train that left and are **spent** by that release
rather than folded back into a train standing there
([#311](https://github.com/rails49/control/issues/311)). A block released this
way is recorded clear and not forgotten, so it reads occupied again the
ordinary way, by a change in the fold.

**A spent end counts again.** What a release spends is the ends of X reading
occupied at the moment it runs, and they count again as soon as that
departure is over: when the end itself settles a level of its own, and when X
is published occupied again, which un-spends *both* of its ends — a new train
standing in X ends the previous departure's account. Otherwise an end that was
spent and never changes again — a car left standing, a detector stuck occupied
— would be out of the fold for good, and the block behind the next train would
be published vacated while the steel still reads occupied. A level no move
explains is still a level, and holding the run on it is the point
([ADR-0048](../adr/0048-an-unexplained-reading-holds-the-run.md),
[#331](https://github.com/rails49/control/issues/331)).

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
A `power_wanted` is written through to `wanted/track` with the word it was
given — bar the one word that is guarded, below — and **nothing is said about
`state/power` on the strength of having commanded it**: a railroad that answered `on` because somebody pressed ON would
be this app taking its own word for the state of the track. It cannot verify
that the supply really went and does not try — it assumes the device it
commanded did what it was asked, and it is the system designer's job to put such
a device there ([#232](https://github.com/rails49/control/issues/232)).

**A plain `off` is applied only where nothing is moving.** The one command
this app does not write through as it came
([ADR-0062](../adr/0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)).
A topic names the app that answers it and never the process that sent the
frame, so nothing about `power_wanted` says the panel wrote it with a drain
behind it: a raw client, a test or a later UI publishing `off` would cut the
supply under whatever is mid-transit and strand it where no sensor will ever
say it stopped (CONTEXT.md, **Power off**). So this gesture is re-validated
against current state on arrival, as every other browser-writable one already
is, and the state it is validated against is `tc49/dispatch/state/run`:

| the run reads | a plain `off` |
| --- | --- |
| `held`, `moving` false | applied |
| nothing yet — no dispatcher has stated a run | applied |
| `held`, `moving` true | refused |
| `running` or `draining`, either way | refused |

`held` and not merely "not moving", because an `off` on a running run with
nothing granted would race the dispatcher's next grant by milliseconds. And
**no run is no reason to refuse**: the guard refuses on evidence that
something moves and on nothing else — with no dispatcher up nothing has been
granted, and a railroad that could not be turned off would be worse than the
race. A row that cannot be read leaves the run this app already held standing,
and a row with no `moving` at all reads as nothing moving, an older dispatcher
saying nothing about what is under way being no evidence either.

**What `moving` sees is the dispatcher's grants**, and a train somebody has
taken in a throttle and is driving with no request behind it is neither active
nor crossing. So the row reads not moving and the `off` is applied while that
train rolls — this app writes its wheels on the throttle gesture alone, with
no grant to ask about. Asking for power off with a train in hand is a user
error the app does not guard (CONTEXT.md, **Moving**).

**An `off` that is applied leaves the railroad at rest.** Before the word goes
out, `0.0` is written over every retained `wanted/traction` row, exactly as at
startup below. "The railroad comes up at rest" is a promise about a **power
off** and the `on` after it as well as about a process start, and the supply
going is not a **restart**, so the startup rule does not reach it: an arrival
zeroes the row of a train this app drives and nothing zeroes the row of one a
person holds in a throttle, so a plain `off` would otherwise leave a speed
standing and the next `on` would bring current back over it
([#435](https://github.com/rails49/control/issues/435)). The order is
load-bearing — a translator acts on desired rows as they arrive, so zeros first
means the last thing the station is told before the supply goes is a stop — and
it is only this `off`: a refused gesture changes nothing, and `stopped` is a run
that is meant to resume from it, which zeroed rows would turn into a re-drive.
`wanted/point` is left alone here for the reason it is left alone at startup.

A refused `off` is **dropped**, in silence and to the trace with the reason,
as every gesture this app cannot act on is
([ADR-0034](../adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).
It is not held for later: an intention kept would be the panel's stale wait
moved server-side, and this app answers nothing that could clear it. A client
that wants the supply removed from a running railroad has the panel's two
words — ask for a drain, and cut when it is done. `on` and `stopped` are
untouched and apply in every run state: an emergency stop asks the rails for
less, and returning to `on` releases nothing (ADR-0041, ADR-0051).

**`state/power` is folded from what the hardware reports.** The supply's own
word, `device/track`, wherever every `device/link` that has ever been seen
reads `up`; `off` otherwise. A participant that cannot reach its hardware
leaves a railroad no train may move on whatever the supply says, since the
participant saying it may be the unreachable one. *Ever seen* and not
*currently connected*: a link is a retained level, so one that said `down` and
then died leaves the value standing, and forgetting it would turn a broken
railroad back on
([ADR-0050](../adr/0050-broken-hardware-is-reported-never-worked-around.md)).

Each link row is keyed by the id its publisher calls itself — no drawing and
no list of ours names one — so several participants each keep their own row
and the second's `up` does not erase the first's `down`. An id this app has
not heard is one it waits for no word from: nothing must announce itself for
the railroad to come up (ADR-0058,
[ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)).
A supply reported `off` may carry a free-text `reason`, which is a person's
to read and nothing this app branches on.

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
throws until a person turns it on, normally from the panel. That `off` is not
a gesture and the guard above does not reach it. Thereafter it never writes
`off` of its own accord: it writes the word it was told to write, and the
supply going away below it moves `state/power` and never `wanted/track`.

**And on startup the railroad is at rest.** The app also comes up having
written `0.0` over every retained `wanted/traction` row it finds. A traction
row is retained, so a broker that outlived the app hands the last run's speed
straight back and a translator sends it at the first connect — a locomotive
rolling on the power-on with no grant and the run still held
([#333](https://github.com/rails49/control/issues/333)). Zero is written here
rather than by a translator standing down, because this app is the row's one
writer and the ruling then holds when a process is killed as well as when it
exits. `wanted/point` is left to replay: traction has a resting value and a
point has none, so the retained belief about where the last session left the
blades is the only answer short of throwing every point at startup
([ADR-0054](../adr/0054-the-railroad-comes-up-at-rest-and-points-replay.md)).

## What is not here yet

- **The function row**, `tc49/layout/state/wanted/function/<addr>/<number>`.
  It is the one desired row with no writer: a function press has no gesture to
  arrive on, so it is nobody's until a throttle asks (ADR-0045).
- **Any hardware protocol.** This app speaks the device vocabulary and nothing
  else; what a translator does with an address is its own business.
