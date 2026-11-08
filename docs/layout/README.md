# Layout

The layout interface is a core app, `layout`: always running,
hardware-independent, and the only writer of what the hardware is asked to do
([ADR-0043](../adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
Above it the railroad is blocks, transits and trains; below it is the **device
vocabulary**, one retained state topic per device
([BUS.md](../BUS.md#device-vocabulary)). Nothing above this app names a
device and nothing below it names a transit, which is what lets two hardware
systems drive one railroad with no ownership table anywhere.

It is the physical binding of the interface, and the normative one: the
`simulator` is the other binding of the same contract, and where the two could
differ the physical railroad decides
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)).
Neither knows about the other, and a run has one of them.

The general contract is [SYSTEM.md](../SYSTEM.md#layout-interface), which is
where the topics and their payloads are. This page is what this app does with
them. What a translator does with each device row is in that translator's
own repository.

## What it reads and writes

*Reads* the layout — the transits a `move` may name, and the signal standing at
each block end — and the **roster**, which is how a train becomes the addresses
that answer for it. Nothing else of the railroad's: the points a transit needs
ride on `align`
([ADR-0031](../adr/0031-the-layout-carries-the-points-a-transit-needs.md)), so
this app throws what it is told and holds no table of its own.

*Subscribes* `tc49/layout/align`, `tc49/layout/move`,
`tc49/layout/power_wanted`, `tc49/layout/driving_wanted`,
`tc49/layout/take_wanted`, `tc49/layout/throttle_alive`,
`tc49/layout/throttle_wanted`, `tc49/layout/function_wanted`,
`tc49/dispatch/train_placed`, `tc49/dispatch/train_removed`,
`tc49/dispatch/state/aspects`, `tc49/dispatch/state/moving`,
`tc49/dispatch/state/allocation`, read once as it starts,
`tc49/schedule/state/facing`, `tc49/layout/sensor`,
`tc49/layout/state/device/#` and
`tc49/layout/state/wanted/function/#`, the function rows it writes, read back.

*Publishes* `tc49/layout/state/wanted/traction/<addr>`,
`tc49/layout/state/wanted/function/<addr>/<number>`,
`tc49/layout/state/wanted/point/<addr>`,
`tc49/layout/state/wanted/signal/<addr>`, `tc49/layout/state/wanted/track`,
`tc49/layout/state/power`, `tc49/layout/state/driving`,
`tc49/layout/state/taken`, `tc49/layout/state/functions`,
`tc49/layout/state/unknown_sensors` and
`tc49/layout/state/settled/sensor/<block>.<end>`.

The facing is the one topic here that is nobody's hardware and nobody's
command: it is the scheduler's state, and this app reads it because the sign of
a speed cannot be composed without it and there is nowhere else it lives
([ADR-0052](../adr/0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md)).
Whether a train is moving is the second of that kind, the dispatcher's, and
read for one thing only — when a drain may cut the supply, below
([ADR-0078](../adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
Nothing else here branches on it: a `move` is acted on because it was granted.

## The command line

```
python -m tc49.layout --broker <host:port> --store <url>
```

Two flags, the ones a compose service passes: where the broker is, and where
the store serves the documents the railroad is built from
([ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
decision 5). Started against an empty broker with no store and no other app
running, it waits for the broker, reads the store's record of the railroad
loaded last (`GET /loaded`) and then its two documents — retrying until the
store answers — waits out the moment the broker takes to hand back whatever
traction rows the last process left, publishes its own retained rows and stays
up. It exits on nothing but a signal.

**It starts on the railroad the store records**
([ADR-0072](../adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md),
decision 5). Each time it is built on a railroad — on the way up, and on each
gesture it answers — it writes that railroad's name to the record (`PUT
/loaded`), so a box comes back on the railroad its rails were built to. Nothing
on the command line names one: a box that records none stands until its first
railroad is loaded or created in the settings dialog, and a recorded railroad
the store no longer has is refused as any starting point is, the record left
for the next load to overwrite.

**How long a throttle may go silent is not a flag.** It is the
installation's, the same whatever railroad is loaded, so it comes from
`installation.yaml` at the store root (`GET /installation`), read once as the
app starts, before any railroad is loaded: none is 5 s, and one that does not
read is said in the log and treated as none. A person sets it on
`settings_wanted`, 2 to 60 seconds, and `layout` writes it back there
([DEPLOY.md](../DEPLOY.md#a-silent-throttle),
[#1132](https://github.com/rails49/control/issues/1132)).

The broker before the documents, because a railroad the store has not got is
one this app **stands** on: up, naming no railroad (`""`) on
`tc49/layout/state/railroad` and publishing nothing else, until a person picks
one it can read
([ADR-0060](../adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md),
[#564](https://github.com/rails49/control/issues/564),
[#727](https://github.com/rails49/control/issues/727)). A box whose store is
empty is an ordinary state, and the gesture that ends it comes over the bus.

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
period. The harness stood this app and the `dccex` translator in one process
where the simulator would be
([#314](https://github.com/rails49/control/issues/314)) until #587; the
translator is [`rails49/dccex`](https://github.com/rails49/dccex) now, so a
run on steel is this process and that one on a broker, and the loop is the
same three steps either way. The period bounds the resolution and nothing
else: 0.1 s against 300 ms of settling has a settled level acted on between
0.3 s and 0.4 s after it stood, which is the right order for a detector.
Nothing schedules the call — a detector publishes a level *change* and nothing
else, so an owner that never made it would sit on a quiet railroad holding an
arrival nobody was told about. The suite drives the clock rather than sleeping
on it and calls `settle()` itself.

**The same loop says the app is up.** Once a second by the monotonic clock,
whatever the period, it publishes `tc49/layout/alive_confirmed` with `{}`, so
something off the box can cut track power when the box goes silent. Standing
and reloading are outside the loop and say nothing. The simulator says it in
`layout`'s place, for the page, which names an app it has not heard for 3 s
([#716](https://github.com/rails49/control/issues/716),
[#1113](https://github.com/rails49/control/issues/1113), BUS.md).

**Whose levels those are, on a physical railroad, is a person's.** No camera
publishes `tc49/layout/sensor` yet, so somebody types them a line at a time and
what they type is published as the report a detector would write, and said
again each second, by `tc49 readings` — that keyboard as a client of the broker beside this app
rather than in one process with it
([#315](https://github.com/rails49/control/issues/315),
[#379](https://github.com/rails49/control/issues/379)). This app is told
nothing about it: a typed level settles, goes out on its row and completes a
crossing exactly as a camera's does, which is the whole of what standing in for
hardware means — and it is the reason settling is tested against typed levels
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

**A reported point is waited for.** Each point on an `align` says whether its
address is reported. The transit counts as aligned only once each reported
point has a `device/point` saying the position the `align` asked for, so a
point that fails to throw holds the train rather than sending it the wrong
way. From when the move is let through until its entry sensor has read occupied
then clear, the train then being past the points, a reported point saying another
position stops the train, as an arrival does; a throttle may drive it on. What the
block left reads does not come into it. A throw by hand waits for nothing
([ADR-0097](../adr/0097-a-reported-point-lies-where-device-point-says-and-a-train-waits-for-it.md)).

**The near-end check.** A `move` is acted on only if that train is standing at
the transit's near end
([ADR-0047](../adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
At-least-once delivery can repeat one minutes late, and after arrival the train
has left the near end — so a redelivery is a no-op **on state alone**, with no
clock, no stamp and no agreement between apps. The same check refuses a command
overtaken by a hand's placement and one naming a train no longer on the layout.
Where each train stands comes from `train_placed`, `train_removed` and the
moves this app has itself carried out. Those are events, which the broker does
not keep, so the app starts from the dispatcher's retained
`state/allocation`: each train it names in a block of this railroad stands
there ([#960](https://github.com/rails49/control/issues/960)).

**No move while the rails are dead.** Nothing is acted on while `state/power`
reads `off`
([ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
That is what makes a restart safe, and it has teeth on every one of them now
that the app comes up with the railroad off. A command that arrives dead is
**kept**, one per transit, and not acted on: the dispatcher granted it, and
`on` resumes every granted move
([ADR-0078](../adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md),
decision 6). When `state/power` next reads `on`, each kept command is put back
through all three rules, so a train taken off or placed elsewhere meanwhile
fails the near-end check and its move is dropped then. Through a drain the
supply is on, and a `move` is acted on as it is while `on`: the train runs
through the next block and stops at its far sensor, and the drain ends after it
(ADR-0078, decision 4; [#862](https://github.com/rails49/control/issues/862)).
The value read is `state/power` as this app states it: folded from what the
hardware reports below, with a drain and a cut held over the fold, so a
`move` arriving while a cut is in flight is kept although the station still
reports the supply live.

A held or kept command meets all three at the moment it is acted on and not at the
moment it arrived, since the railroad can move under it while it waits.

**Every payload is read and never trusted**
([BUS.md](../BUS.md#event-inventory), rule 4). Nine topics from six
publishers reach this app and it answers none of them — it reports observations
— so a frame that cannot be read is **dropped**, silently and to the trace, and
so is a command the layout contradicts: one naming a transit this railroad does
not hold, or one whose transit reaches neither end of the block the command says
the train is entering. Either way the command names no near end for a train to
be standing at.

## The traction write

On a `move` it acts on, this app publishes
`tc49/layout/state/wanted/traction/<addr>` for every car of the train that has
an address, the same sign at `caution` where the drop below applies, and `0.0` to
those addresses again when the train arrives.
It is the last thing between the device vocabulary and a wheel turning, and it
is the one write here that composes two facts rather than passing one on.

That is a train this app is **driving**: in `automatic`, with no throttle
holding it. A train a throttle holds gets the arrival's `0.0` and not the
grant's speed, the same rows being where its lever lands, and a train nobody
drives in `manual` gets neither write (*Who drives* below).

**The `caution` drop.** A train at `clear` whose far signal then shows `stop` has
only a stopping distance left after the far sensor. So a crossing this app is
driving and is still outstanding, with its head in the block, a grant's speed to
give and its far sensor's end at `stop`, is lowered: where its speed exceeds the
railroad's `caution` speed, it is replaced by the same sign at `caution`, kept on
the crossing and written. It never raises a speed. `state/aspects` is kept for
this, and an end it does not name reads `stop`, which covers an end with no signal
and the time before the first value. It is checked at the entry sensor settling
occupied, at each `state/aspects`, at a release that makes the crossing this app's
and at each giving of the speed, so a resume or a train taken up is given the
lowered one. A train a throttle holds keeps the person's speed. A release in
`automatic` drops the train to `caution` if it runs faster the way the move takes
it: the one exception to a release keeping the speed, and it is not raised for one
running slower. A `caution` a person changes is used from the next check.

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
   **propelled**, pushed out of the end its nose points away from. That is an
   ordinary movement and not an error. It is said of one move and never of a
   train, since the same train is propelled over one transit and nose-first
   over the next, and a propelled train enters the next block tail-first.
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

**No facing, no move.** A `move` for a train with an address whose facing this
app cannot use is **held** until a facing naming the block the train departs
arrives ([ADR-0095](../adr/0095-layout-holds-a-move-until-its-facing-names-the-block-the-train-departs.md)):
none published for it, one it cannot spell, or one naming a block other than
the one the train is departing. Guessing is a locomotive driven the wrong way
down the track. The scheduler publishes the facing and the driver the move,
and the bus promises no order between two writers, so the move arriving first
is ordinary running. Each facing puts the held move back through every rule, so
a train taken off or placed elsewhere meanwhile has its move dropped then. A
second `move` for the same transit replaces the one held, and there is no
timer. A command *held* for its `align` is likewise signed on the facing it has
at the moment it acts. A `move` that states no **speed** is dropped: this app
would have to choose a number nobody asked for.

**No address, no command.** A train whose cars carry no address at all — the
simulator's trains are like this, and so is anything a hand moves — still gets
its `align`, its near-end check and its crossing record, and simply has nothing
to publish. That is not a failure and is not logged as one, and it is the same
answer for a train this railroad's roster does not name: there are no wheels
there to turn the wrong way, so no facing is wanted either.

### A move that reverses the train

A train whose next move goes back out through the end it came in by must not flip
with its tail on the turnout. A `move` is **held**, one per transit, where it has
addressed cars and the crossing in the block it departs is the same train's,
outstanding and `driving`, with its near end that crossing's entry sensor. The
near end is compared rather than the heading: a train leaving through the end it
came in by reverses whatever its facing says, and the comparison does not depend
on a facing that lags the train.

The arrival puts it back through every rule after its `0.0`, with no wait between
the `0.0` and the speed: nothing reports that a train has stopped,
[ADR-0084](../adr/0084-a-reverser-moves-only-with-the-lever-at-0.md) rejected a
fixed wait as a guess at CV4, and it measured a decoder ramping through 0 with no
jolt. A withdrawal, a placement and a removal drop the held move as they drop the
other waiting moves, and a second `move` for the same transit replaces it,
unless the near-end check drops it first: one whose near end is in the block
the train left is dropped, and the held move and any withdrawal asked for it
stand. A withdrawal asked while the train runs takes effect at the arrival: stopping the
train earlier could leave it on the points, so it runs on to its far sensor, stops
there and the move never starts, `move_withdrawn` going out after the `0.0`
([#1176](https://github.com/rails49/control/issues/1176)). A placement or a removal
before then takes the ask with the move, with no answer. Under
`off` the move is kept first, and judged again on `on`. A train a throttle holds is
not held, since no speed is written for it: the person reverses with the lever.

### Arrival

A crossing remembers two things about its **entry sensor**, the end it comes in
at: `head_in`, that it has settled occupied, and `tail_in`, that it has then
settled clear. The **arrival** happens once, at the first of:

| Reading | Result |
|---|---|
| The **far sensor** settles occupied | the arrival, then the crossing is deleted and the origin released |
| The entry sensor settles clear with `head_in`, and the far sensor is `unknown` | the arrival; the crossing stays for its far sensor |
| The far sensor goes `unknown` with `tail_in` already true | the arrival |

The arrival is `0.0` to every address this app commanded, where the crossing is
`driving` or a throttle holds the train, and nothing otherwise, since a car nothing
was sent for is a car nothing may be sent for. Then the grant implies nothing more,
and any move held for the train goes back through the rules. The entry sensor
reading occupied stops nothing: the train runs on through its block and stands at
its signal, with the whole block for a next grant to arrive in.

**A further move carries the train through.** A further `move` for the train, this
app driving it or a throttle holding it, ends the crossing it departs as a move:
there is no stop at its far sensor, and `head_in`, `tail_in`, `reported` and the
deletion at the far sensor go on as before. The same goes for the train's earlier
crossings when this app gives the later one its speed or a throttle takes it. In
`manual` with no throttle holding the train, the crossing it departs stays
outstanding: the train finishes its move and stops at the far sensor, and its next
grant is nobody's. Without this a train nobody is driving runs on through the next
block at its last speed.

### Removal

A train may be taken off running
([ADR-0069](../adr/0069-a-train-comes-off-while-running-and-its-track-opens-when-it-reads-clear.md)),
and a decoder in a hand keeps the last speed it was told. So `train_removed`
writes `0.0` to every addressed car of the train, held by a throttle or not and
whatever the power, and forgets any move of that train in flight: its later
readings write no speed for it, and the block behind reads clear on its own
detectors like any other.

### Placement

The dispatcher cancels a train's requests before it accepts a placement, so on
`train_placed` this app forgets every move of that train's it holds: the one
in flight and any waiting on an `align`, a facing or the power
([#1061](https://github.com/rails49/control/issues/1061)). A train no throttle
holds that is running is written `0.0`, since a decoder lifted running keeps
its last speed. A train a throttle holds keeps the person's speed.

## Who drives, and a person's throttle

The railroad has one **driving mode**, `manual` or `automatic`, and at most one
throttle holds a train
([ADR-0079](../adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
Neither changes the route: every train is dispatched the same, holds its block,
is granted moves and gets its points thrown and its near end checked. What they
decide is who writes the wheels
([ADR-0081](../adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)):

| | no throttle holds the train | a throttle holds it |
| --- | --- | --- |
| `automatic` | this app, at the grant's speed, within a granted move | the throttle, at any time |
| `manual` | nobody: the train stands at its signal | the throttle, at any time |

**The mode.** `tc49/layout/driving_wanted` switches it, at any power, and this
app states it on `tc49/layout/state/driving`. It comes up `manual`, and a value
a previous session left there is superseded rather than adopted. A gesture that
cannot be read is dropped.

- **To `manual`**, nothing is written. A train this app is driving finishes its
  outstanding move, is told `0.0` on arrival as before, and stands: its next
  grant is nobody's until a throttle takes it.
- **To `automatic`**, each train with a move outstanding and no throttle is
  given the speed its grant implies, a train standing between its sensors running
  on to the far sensor.

**Who holds which train.** `tc49/layout/take_wanted` `{train, throttle}` takes a
train for the throttle with that id. A take of a train another throttle holds
is dropped to the trace: the last take does not win. A take by a throttle
already holding another train releases that train first, as `null` would
([ADR-0089](../adr/0089-a-throttle-holds-one-train.md)). `throttle: null` releases
the train whoever holds it, which is also a panel's force release; a frame with
no `throttle` at all is dropped. This app states who holds which on
`tc49/layout/state/taken`, empty at startup. A throttle publishes
`tc49/layout/throttle_alive` once a second while it holds a train, and this app
releases every train of a throttle it has not heard for 5 s by default
(`THROTTLE_SILENCE_S`), set per installation in `installation.yaml`
([DEPLOY.md](../DEPLOY.md#a-silent-throttle)) and passed to `LayoutInterface`
as `throttle_silence_s`, checked each time the loop calls `settle()`. One a
person sets on `settings_wanted` holds from the next check.

**Taking a train writes nothing.** It keeps whatever speed it had and the
person's first movement of the lever is what changes it. Writing zero on
take-over would stop a running train the instant somebody selected it.

**Releasing it writes what the mode makes of it.** In `manual`, `0.0`. In
`automatic` with a move outstanding and the rails live (`on` or `draining`),
nothing, bar the `caution` drop: the train keeps the speed the person left until
its move ends at the far sensor, so a train run slowly does not lurch. The crossing becomes this app's,
so the arrival writes `0.0`, a switch to `manual` lets the train finish its
move, and an `on` after a cut gives it its grant's speed. A train whose last
speed written is `0.0` on every car, or that has none written, is given its
grant's speed instead
([ADR-0083](../adr/0083-a-train-released-standing-mid-move-is-given-its-grants-speed.md)):
it would otherwise stand with its route held and never reach its far sensor. The
zeros written at startup and at a cut count. In `automatic` with no move
outstanding, or over dead rails, `0.0`, so no speed waits on a row for the
power to come back. A train no throttle held writes nothing.

**A throttle drives at any time, granted move or not.** A person backs a train
up a few centimetres at a platform with no request made. A move this app is not
driving still throws its points, meets the near-end check and is recorded as
crossing, and nothing goes out on the grant. The facing refusal has nothing to
refuse there, since no sign is composed. When the move ends at its far sensor this
app writes `0.0` whether it or a throttle was driving, and a train nobody drove
is told nothing; the next lever frame drives the train on. Leaving the block is
the person's responsibility: nothing stops a held train at its block's ends,
and one that leaves is a reading no move explains, which is named for a person
while the others run ([#1154](https://github.com/rails49/control/issues/1154)).

**The lever** is `tc49/layout/throttle_wanted`, a speed in −1.0 … 1.0 signed
for the train — positive nose-first — and the `throttle` turning it. It reaches
the same rows a `move` does, one signed speed per addressed car composed the
same way. The one difference is where nose-first comes from: a move states a
destination block and the sign is composed against the train's facing, where a
lever states the direction outright. So a person pushes forward and the train
moves nose-first, whichever way round the locomotives are wired and however
many of them there are.

These drop a lever, and none of them is answered:

- **No `throttle`, or one that does not hold the train.**
- **Dead rails**, `state/power` reading `off`, which refuse a person's hand as
  they refuse a grant (ADR-0041). Nothing is written rather than a zero: the
  row holds whatever it last held. A lever is applied while `on` and while
  `draining`.
- **A train that stands nowhere**: never placed, or taken off by
  `train_removed`.
- **A train it has no facing for** — none published, or one it cannot spell.
  Which **block** that facing names is not asked, where a `move` asks it: the
  sign here is the lever's own, a facing lags the train it is about, and a
  lever that went dead for as long as the lag lasted would be a person pulling
  back to stop and not being heard.

**A flip at speed writes `0.0`**
([ADR-0084](../adr/0084-a-reverser-moves-only-with-the-lever-at-0.md)). A
frame whose sign is opposite to the last nonzero speed written for the train —
the lever's or a grant's, signed for the train before it is composed onto the
cars — writes `0.0` to each addressed car instead, and so does every later
frame of that sign until the throttle sends `0` or this app stops the train:
an arrival, a cut, a release that stops it, or a removal
([ADR-0088](../adr/0088-a-stop-the-layout-writes-frees-the-reverser-as-the-throttles-0-does.md)). The `0.0` a refused frame writes does not count.
How hard a decoder reverses
depends on settings the roster does not record, and behind a long train cars
can leave the rails.

## A train's functions

A throttle switches one of its train's functions by the name the catalogue
gives it: `tc49/layout/function_wanted` `{train, throttle, function, on}`
([#849](https://github.com/rails49/control/issues/849)). A frame that cannot be
read, or whose `throttle` does not hold the train, is dropped. Otherwise this
app writes `tc49/layout/state/wanted/function/<addr>/<number>` with
`{addr, function: <number>, value: <on>}` for the first car in the train's
order that has an address and declares a function of that name, on that car's
first number for it. Which way the train runs is not asked. A train the roster
does not name, or a name no addressed car declares, is dropped with a log
line. A press is accepted at any power and in either driving mode: a light is
not a wheel, and the row waits for the supply.

Nothing else writes a function row, with one exception: when this app lets go
of a train (a release, `take_wanted` with `throttle: null`, a silent throttle),
each of the train's **momentary** functions that `state/functions` says is on
is written off, on the row a press of its name writes
([#998](https://github.com/rails49/control/issues/998)). Nobody holds its
button any more, so the off its throttle sends later is dropped as not the
holder's, and on the real locomotive the horn would keep sounding. Latching
functions, `train_removed`, a cut and a restart leave the rows as they are, so
the lights a person left on stay on.

`tc49/layout/state/functions` says which of each train's functions are on, by
name: the `value` of the row a press of that name writes, absent where there is
no such row. This app reads the rows back, its own writes and the retained ones
a bus that outlived it hands over at start, so a light a decoder still has on
shows on after a restart. A row that cannot be read, or that no press would
write, is left out.

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

An `align` whose `connection` and `transit` are both `null` is a throw by hand
the dispatcher let through (ADR-0068). Its points are written like any other's,
and it authorises no crossing, so a held `move` keeps waiting. Nothing else is
checked: no lock, no power state, no run state. A frame with only one of the
two `null` is dropped whole.

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

## Sensors

**Levels in, levels out.** A detector reports presence at one block end, and
presence is a level that can be asked for at any time; the bus carries the
changes because it is an event bus
([#243](https://github.com/rails49/control/issues/243)). So this app holds each
sensor's level, settles it and passes it on, on
`state/settled/sensor/<block>.<end>`. A repeated level re-asserts what is already
held and is a no-op, which is the whole of what at-least-once delivery needs
here: no counter, no dedup.

**A block reads nothing here.** A sensor watches a point near a block end, and
this app keeps no record of which block is occupied. The dispatcher's lock table
is that record, followed from these rows
([#1171](https://github.com/rails49/control/issues/1171),
[#1173](https://github.com/rails49/control/issues/1173)). A level goes out whether
or not a move explains it: a hand putting a locomotive down is how every session
starts, and what to make of a reading nothing accounts for is the dispatcher's
judgement — it names the block for a person to walk
([#1154](https://github.com/rails49/control/issues/1154)) — not this app's.

Which end of the entered block the train comes in at is the end across the
transit, read off the layout from the `move` that was carried out. The block's
*far* end is a different thing — its second sensor, the one a train's head
reaches last — and the two are opposite ends of the one block
([#279](https://github.com/rails49/control/issues/279)).

**The debounce.** A camera-based detector runs at 2–8 Hz with no debounce of
its own and is biased towards reporting occupied, so a new level is held for a
**settling time** before it is acted on, and a level that flips back inside
that window is never seen upstream. The settling time is **configuration**: a
constructor argument, 300 ms by default, because what it is worth is a fact
about the detectors a railroad has and not something this app can know
(ADR-0030). It is on no topic, and nothing above the interface is told there is
a debounce at all. The settling time filters a flicker. It does not make up for
a detector that reads `clear` between cars: a gap that outlasts it is a `clear`
like any other, and is taken for the train's tail. Reading `occupied` without a
break under a train is asked of whatever reports
([BUS.md](../BUS.md#event-inventory),
[#1167](https://github.com/rails49/control/issues/1167)).

**`unknown` gives no level for that end.** No row comes of it, it does not
discard the level the end last actually had, and it does not cancel a level that
is settling. The `reason` beside it is logged once per transition into
`unknown`, for a person: the detector knows why it cannot say — no model, not
calibrated, drift — and nothing in the system branches on it.

**A sensor not reporting is listed** on `state/unknown_sensors`
([#1151](https://github.com/rails49/control/issues/1151)). Every sensor of the
drawing, `<block>.A` and `<block>.B`, starts there with `reported: false` and the
reason `no report since start`. `settle()` lists one with no report of any kind
for `sensor_silence_s`, reason `no report for <n> s`, timed on this app's clock
at receipt, and one whose report of `unknown` has stood for the settling time,
with its `reason` or `no reason given`. A level within that time cancels it. An
`occupied` or `clear` that has stood for the settling time takes the sensor off
and makes `reported` true, even a level equal to the one held. The row goes out
once a call to `settle()`, only where the list changed. A report naming a sensor
not on the drawing settles as any other and is never listed.

**What a sensor has settled on is kept**, one row per sensor, on
`state/settled/sensor/<block>.<end>`
([#1168](https://github.com/rails49/control/issues/1168)). Each level that stands
publishes it, including one that takes a sensor off the list and equals the last.
While a sensor is listed its row stands at the last level, and a sensor with no
settled level since this app started has none. Coming up and each load of a
railroad clear the rows, so no reading of the last run is read as current.

**The train stops with both sensors listed.** While both sensors of the block a
crossing enters are listed, and the crossing is outstanding and no throttle holds
its train, this app stops the train as the second is listed, where the crossing is
`driving`, and `_give` writes no speed: that covers a `move` acted on while they
are listed, `_resume`, `_take_up` and a change to `automatic`. One alone stops
nothing, an arrival still being there to read. A train a throttle holds keeps its
speed
([ADR-0081](../adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)).
Coming off the list, in `automatic` with `state/power` `on` or `draining`:

| Was stopped for both, and then | Result |
|---|---|
| Entry sensor returns occupied, far still listed | `head_in`; `_carry_on` gives the speed back; stopped when the entry sensor reads clear |
| Entry sensor returns clear with `head_in`, far still listed | the arrival; it stays stopped |
| Entry sensor returns clear with no `head_in`, far still listed | speed given back |
| Far sensor returns occupied | the arrival |
| Far sensor returns clear | speed given back |

Under `off` the next `on` gives the speed. `_carry_on` runs only where the crossing
was stopped for both until that reading: a sensor returning when the train was never
stopped writes nothing, so a train a person left running slowly does not lurch
(ADR-0081, decision 6).

## Power

The rule is [SYSTEM.md](../SYSTEM.md#track-power). This is how `layout`
carries it out, in `src/tc49/layout/interface.py`. Which press is applied,
when a drain ends, and which word is held over the supply is `TrackPower` in
`src/tc49/lib/power.py`, which the simulator uses too.

At start-up the constructor (`__init__`, :326) does this, in this order:

1. Subscribes to the event topics, `power_wanted` among them (:428), so no
   press is lost while it starts.
2. Writes `wanted/track: off`, then `state/power: off` (:450-451).
3. Writes `0.0` on every retained `wanted/traction` row (:465,
   `_traction_rest` at :778).
4. Subscribes to the state rows, `tc49/dispatch/state/moving` (:474) and the
   device rows (:476) among them. A supply row kept by a bus that outlived
   the app then replaces the start-up `off` rather than being overwritten
   by it.

That start-up `off` is not a command, and `TrackPower` never sees it: until
the first press `state/power` is the fold's.

`_on_power_wanted` (:1142) asks `TrackPower.answer` for the word to apply
over the fold, and returns where it is `None`: a press that cannot be read,
`stopped` among them, and a `draining` while `state/power` is not `on`.
`_on_moving` (:1121) hands each `tc49/dispatch/state/moving` frame to
`TrackPower.moving`, which keeps the latest by its stamp, reads one it cannot
read as a train moving, and answers `off` where it ends a drain. A drain
pressed while nothing moves is answered `off` at once.

`_apply` (:1160) carries out the word:

- `off`, a person's emergency stop or the end of a drain: `_traction_rest`
  first, so the zeros reach a translator before the word does, then
  `wanted/track: off`.
- `draining`: nothing written to the hardware. The supply stays on.
- `on`: `wanted/track: on`, then `_resume` (:1189), which in `automatic`
  writes each train with a move outstanding and no throttle the speed its
  grant implies, so a train a cut left between blocks carries on. In
  `manual` it writes nothing; a throttle's train is the person's (#825).

Each calls `_publish_power`.

`_on_device` (:1214) keeps the latest `device/track` value and the latest
`device/link/<id>` value per id, each by its stamp, and calls
`_publish_power`. `_folded` (:1411) answers `off` unless every link it has
heard reads `up`, and the supply's value otherwise. `_publish_power` (:1445)
puts `TrackPower.stated` over that value — `draining` through a drain, and
`off` from a cut until the next `on` — and publishes `state/power` only when
it changes.

`_cross` (:580) acts on a `move` while `state/power` reads `on` or
`draining`, and keeps one that arrives while it reads `off` (:638). When
`_publish_power` next states `on`, `_carry_out_kept` (:1472) puts each kept
move back through `_cross`, under the same checks.

## What is not here yet

- **Any hardware protocol.** This app speaks the device vocabulary and nothing
  else; what a translator does with an address is its own business.
