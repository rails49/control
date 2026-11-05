# Control Model Railroads

A model railroad comprises **assets** (what it is made of) and **operations**
(what is done with them). Terminology follows the glossary in
[GLOSSARY.md](../GLOSSARY.md).

## Assets

### Tracks

The rails the railroad runs on, divided into blocks and the connections between
them.

**Blocks** are sections of track without turnouts where a train can park. Each
block is oriented with ends `A` and `B`. Each end has a **sensor**, which
watches a point near that end and reports whether something is at it. A sensor
does not report on the block: with a train standing between them, a block's
two sensors both read `clear`. A block's length is the distance between its two
sensors, and each sensor sits at least a stopping distance in from the end of
its block, so a train stopped as its head reaches one comes to rest inside the
block. Each end a train can leave through carries a
**signal**, which is how a driver is told whether to go and how fast; an end
nothing ever leaves carries none.

A block also says what it is for. Its **role** — `station`, `siding` or
`through` — is whether a train may be sent there and how long it may then
stand: called at and left again, held as long as it likes, or never a
destination. What it **admits** is a set of train kinds. Both are advice to
the generator that invents traffic, never feasibility: a person may send any
train anywhere the steel allows, and the dispatcher checks neither
([ADR-0046](adr/0046-a-blocks-role-and-filter-are-advice-to-the-generator.md)).
A block with no role is a station, and `through` on a terminal block is a
headshunt rather than a contradiction. A block with no admits takes every
kind, and `[passenger, mixed]` takes a mixed train and refuses a freight one.
Nothing enforces admits: a train that cannot physically stand in a block is
already refused on length as `no_fit`, and what is left is policy the layout
permits.

**Connections** join one end (`A` or `B`) of each of one or more blocks, and
are realized by zero or more turnouts. The ways a train can traverse a
connection are its **transits** — (end, end) pairs — and often only some of
the possible ones exist:

| Blocks joined | Typical realization | Transits |
| --- | --- | --- |
| 1 | Terminal station | — |
| 2 | Track segment, possibly of length zero | `a ↔ b` |
| 3 | Turnout | Only some, e.g. `a ↔ b` and `a ↔ c` but not `b ↔ c` |

Transits are undirected, so one entry covers both directions of travel. Each
connection also declares which of its transits are **`concurrent`** — usable by
two trains at once, e.g. the two straight paths of a crossing. Everything not
declared conflicts, which is why a plain turnout declares nothing at all
([ADR-0006](adr/0006-conflicts-declared-by-inversion.md)).

> **Note** the resemblance to a graph, with connections as vertices and blocks
> as edges.

### Stock

The rolling stock traveling or parked on the tracks, in three levels
([ADR-0045](adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)):

- A **model** is what a product is, independent of any railroad: a length, a
  **kind** — locomotive, passenger, freight, special — and the meaning of each
  numbered function.
- A **car** is one item a railroad owns: a model with zero or more fields
  overridden, and its own decoder address where it has one. A locomotive is a
  car whose model's kind says so.
- A **train** is an ordered list of cars, each coupled one way round or the
  other. Its length is the sum of its parts, its kind is derived from the cars
  it hauls, and it carries a **priority**. A train at rest occupies exactly one
  block; while crossing it occupies the transit and, until its tail has been
  seen to leave, the block behind as well. It must fit in every block of its
  route, and it fits a block when it is no longer than the block. A route
  through a shorter block is refused, and so is a placement on one. Exceptions
  to the first are intended, for one block or for one request, and are not
  designed. A train let into a block shorter than itself would occupy whatever
  its tail has not been seen to leave, turnouts included, and what lies behind
  it could not be reached while it stands there. It is outside the deadlock
  argument until the check is extended to it.

A railroad **owns** its stock: its **roster** is the cars it has and the trains
made up from them, whether any of them is on the layout or not
([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)). That is what a run
begins from — a railroad, its roster, and a person who puts the trains on the
layout and drags them where they should go. Nothing else is needed to start
one, and a run whose trains are all still **off the layout** is the ordinary
way an evening starts rather than a failure.

A train comes onto the layout and leaves it only when a person places or
removes it and says so in the UI. No sensor reading puts a train on the layout
or takes one off, and cars a train leaves behind are not a train.

## Operations

Railroad operations divide into three distinct functions, each of them an app
([ADR-0013](adr/0013-apps-are-deployment-units.md)). What follows is the whole
of them.

### Scheduling

Decides which train departs from where, to what destination, and when — as
soon as possible, or at a stated time. A stated time is read off the
railroad's **fast clock**, the scaled time a model railroad runs its
operations on and the only thing a timetable can be written against; posting
a request at its time is the scheduler's own responsibility, and nothing of
it reaches the dispatcher's contract
([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)). Its prototype counterpart is the timetable,
though a model railroad more often wants plausible random traffic than an
exact one. Requests arrive continually; a schedule may also be set up in
advance.

A request delivers a train out through one end of the block it stands in and
in through one of a set of arrival ends
([ADR-0007](adr/0007-requests-name-a-set-of-arrival-ends.md)). Three sources
produce them — a timetable released at its due times, a generator inventing
traffic, and a person clicking on the panel — and all three are the one
scheduler, so there is a single writer and a single minter of request ids.
The person's click reaches it as a **gesture**, which names a train and where
to put it and is not itself a request
([ADR-0036](adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)).

To invent traffic that can succeed, the scheduler has to know which trains are
idle and where they stand, so it reads the layout and follows the dispatcher's
events. It judges nothing: whether a request is possible is the dispatcher's
answer and only ever the dispatcher's
([ADR-0028](adr/0028-the-scheduler-knows-where-trains-stand.md)).

### Dispatching

Accepts requests by finding and allocating routes, deadlock-free and with high
throughput — the research core, in [DISPATCH.md](dispatcher/DISPATCH.md) and
[SAFETY.md](dispatcher/SAFETY.md). A route is chosen when the train starts
moving and never changed
([ADR-0002](adr/0002-fixed-route-per-request.md)); only its locks are
incremental.

**Incrementally** is the point. An express running Milano to Zürich without
intermediate stops crosses many blocks, and locking all of them at departure
would hold most of the railroad for one train for the whole journey. Instead
the dispatcher locks a little way ahead, sets the turnouts of what it has
locked, and clears the signal. As the train advances it locks further ahead
and releases what the train has left. A signal shows `stop` unless a block
beyond it has been explicitly reserved for a train, which is a consequence of
locks rather than a rule about signals.

The lock table is the one record of where trains are. Each lock says whether
its train **occupies** the block or transit, or holds it ahead. The dispatcher
keeps the table and publishes it, and the layout interface and the UI read it.
Sensors are how the dispatcher follows a train, each reading taken against the
move that train was granted
([#1165](https://github.com/rails49/control/issues/1165)). For a move out of
block X, over transit T, into block Y:

| Reading | What it shows | The table |
| --- | --- | --- |
| none: the move is granted | | T is occupied |
| X's sensor at the end the train leaves by reads `occupied`, then `clear` | the tail has left X | X is released |
| Y's sensor at the end the train enters by reads `occupied` | the head is in Y | the train may be granted its next move |
| that sensor then reads `clear` | the whole train is in Y | T is released, with anything of that train's still held behind it |

A reading changes the table only for the move that expects it. A train that
leaves a block by the end it came in through follows the same four lines, and
a person backing a train at a platform changes nothing. The last line also
covers a train placed beyond the sensor it would leave by, and a reading missed
while a sensor was not reporting.

Where the entry sensor is `unknown` as the train passes, the far sensor reading
`occupied` says the head is in. A request ends when the whole train is in its
last block, or when the far sensor reads `occupied` if the entry sensor was not
seen to clear. A transit left that way stays occupied until the train's next
move or a placement. A train reversing starts only after its last request has
ended, so it is never sent back over its own tail
([#1171](https://github.com/rails49/control/issues/1171)).

How far ahead it has locked is exactly what the train's signal says, because
stopping takes distance:

| Locked ahead | Aspect | The train |
| --- | --- | --- |
| nothing | `stop` | stands |
| one block | `caution` | moves, slowly enough to stop at the next signal |
| two or more | `clear` | runs at full speed |

So one block ahead is enough to move — a train can at least reach the next
block, and may have to wait there — and **two is what buys full speed**. Two is
also the most that is ever asked for: a third block ahead shows the same aspect
as the second, so it buys nothing and holds track another train may be waiting
for ([ADR-0026](adr/0026-two-blocks-ahead-is-full-speed.md)). A disputed
block does not count as locked ahead, since no train is sent into it. A train
that is refused its next move shows `stop`.

The waiting requests are a **list** a person can see, and the dispatcher
serves them in its order: an earlier request gets the first claim, and a later
one still starts when an earlier one cannot. A new request goes in after every
request of the same or a higher **priority**, lowest number highest, and a
person may cancel or reorder any request that has not started. A train's later
request starts where its earlier one ends, so two drags send a train to a
block by way of another
([ADR-0080](adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).

The dispatcher routes only while the railroad's **power** is `on`. Power is
one switch a person sets, `on`, `draining` or `off`, and the railroad comes up
`off`. A drain stops every moving train in the next block, keeping its route,
and then cuts the supply; an emergency stop cuts it at once. Turning power on
again resumes what was granted
([ADR-0078](adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).

### Driving

Takes the role of a locomotive engineer, one per train, performed by a person
or automatically. A driver decides one thing — how fast, or whether to stop —
by reading the signal it faces. It does not decide where the train goes: the
turnouts are already set when the signal clears, so the train follows the rails
it is given.

Who drives is the railroad's **driving mode**, and the railroad comes up
`manual`: people drive every train from throttles. In `automatic` the app
drives every train no throttle holds. At most one throttle holds a train, and
it drives the train at any time, granted move or not. A granted move still
ends with the train stopped in the block it enters. A train driven out of its
block shows up as a sensor reading `occupied` where no train is expected, and
that block is named for a person while the others run
([#1154](https://github.com/rails49/control/issues/1154),
[ADR-0079](adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md),
[ADR-0081](adr/0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)).

A train with no further grant runs on through the block it enters and is
stopped when the block's far sensor reads `occupied`, so it stands at its signal
with the whole block for a next grant to arrive in. With the far sensor `unknown`
it is stopped when the sensor it entered by has read `occupied` and then `clear`,
or, with that already so, when the far sensor goes `unknown`. Each of these is an
arrival. Whatever the train's tail has not been seen to leave stays occupied by
it until its next move or a placement. With both sensors `unknown` a train
`layout` is driving stops, nothing there being able to end its move, and is given
its speed back when one of them returns and does not say it has arrived.

A train at `clear` whose far signal shows `stop` has only a stopping distance left
after the far sensor. So once its head is in the block, `layout` drops it to the
railroad's `caution` speed. A train a throttle holds keeps the person's speed.

A train whose next move goes back out through the end it came in by must not flip
with its tail on the turnout. `layout` holds that move until the train has been
stopped, then acts on it with no wait: nothing reports that a train has stopped.
A train a throttle holds is not held, the person reversing it with the lever.

A person driving looks out of the window. An automated driver has to be told
which aspect applies to its train, since track detectors are anonymous and
report occupancy without identity; the dispatcher, which knows which train is
where, says so as part of granting the move
([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).

`caution` promises the train can stop before the next signal, and something
has to make that true. The working answer is a per-locomotive calibration of
what "slow" means, together with a constraint on the railroad rather than on
the software: each sensor sits at least a stopping distance in from the end of
its block.
**This is an open subject** — speed signalling, which puts a limit in the
aspect itself, is among the alternatives — and which solution is implemented
will be decided once there is running experience to decide it with.

## Approach

The app does not talk to hardware. It talks to the **layout interface**: sensor
readings come in, turnout, signal and throttle commands go out. Which hardware
sits behind it is irrelevant to this app — the interface assumes only that
individual turnouts can be aligned, individual signals lit, and individual
trains throttled.

The interface has two bindings, and they are **ranked**. A physical railroad is
the normative one: the interface is shaped by what real track, real detectors
and real locomotives can do, and where the two bindings could differ the
physical railroad decides even at cost to the simulator. The **simulator** is
the second binding. It is useful for testing and for evaluating a layout before
it is built, may grow as elaborate as those uses need, and stays confined to
its own app rather than shaping the contract
([ADR-0030](adr/0030-the-physical-railroad-is-the-normative-binding.md)).

The layout interface also owns time
([ADR-0009](adr/0009-layout-interface-owns-time.md)) and is the only part that
knows how a locomotive actually behaves: told to take a train into a block at a
speed, it is what throttles up, watches the detector and stops. Under the
simulator travel time is a pair of fixed delays of the simulator's own; on a
physical railroad transits take as long as they take
([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).

The layout interface passes on what each sensor reads once the reading has
settled, drives trains and stops them. It keeps no record of which block is
occupied: that is the lock table's. The simulator reports sensor readings at
block ends, as the physical railroad does, and nothing else.

### What the app is assumed to be told

Everything above assumes the layout interface tells the truth: that a detector
reporting `occupied` is right, and that points told to throw have thrown.
Collision safety rests on that, since the lock table keeps two trains apart
only if the track the dispatcher thinks it set is the track that is there. A
physical railroad guarantees neither. Points fail to throw and report nothing,
so a route that failed to set looks correct
([ADR-0017](adr/0017-turnout-position-is-inferred-by-the-panel.md)). A decoder misses its
packet, a locomotive stalls, or someone lifts a train off the track by hand.
Collision safety is the property that matters when these happen, and it is the
one the current argument does not cover.

Failures come in four kinds, and what each takes out of use and what resumes
it is the org's
[OPERATING.md](https://github.com/rails49/.github/blob/main/docs/OPERATING.md):

1. **On the railroad, observed:** a failure that is seen takes only what it
   names out of use and the rest runs, except that the station's link down, or a
   trip of the last powered district, takes everything out of use.
2. **In control's own picture:** a broken lock-table rule or a software bug
   drains the railroad, and a person turning power on acknowledges it.
3. **The controller silent:** when `layout`, the broker or the box stops,
   something off the box cuts track power.
4. **Not observed:** a wrong reading, a point that did not throw or a hand that
   moved a train is not guarded, and the consequences are accepted.

The fourth kind is the set assumed perfect, and that is a decision rather than
an oversight.

**The operator is assumed to leave the railroad to the app**, and that is a
decision of the same kind. The app is correct about the railroad it is told
about, and a person can change the steel without saying so. Some of that it
sees. A sensor reading `occupied` is explained when a train occupies that block
or has been granted the move into it. Otherwise the block is **disputed**: it
is named for a person to walk, no train is sent into it, whoever holds it
ahead, and the others run
([#1154](https://github.com/rails49/control/issues/1154)). A `clear` reading
never contradicts a train, since both sensors of a block read `clear` with a
train between them.

Most of it it cannot see, and none of this is guarded:

- A train lifted off, or pushed off its sensor, without the UI being told. It
  stays in the table and is granted its moves. The first sign is a train that
  does not arrive, or an `occupied` reading somewhere else.
- A train reversed on a throttle after its head has passed a sensor and before
  its tail has. The readings are those of a short train that came in whole, so
  the table has it in the block and releases the transit it stands on.
- Cars left between sensors.
- A train whose entry sensor goes `unknown` as the train passes it, whose far
  sensor then goes `unknown`, and whose entry sensor returns `clear` having never
  read it. It is given its speed back, and nothing stops it unless the far sensor
  returns.
- A sensor that reads `clear` between two cars of a passing train, which ends
  the move early. Whatever reports on a sensor is required to read `occupied`
  without a break from a train's head to its tail.
- A train driven from a throttle the app does not know about.

Asking for power off with a train in hand is a user error it does not guard
(`GLOSSARY.md`, **Moving**).

What that costs is correctness, not liveness. A consumer never raises on what
it reads (BUS.md, rule 4) and an unexplained reading is handled rather than
thrown, so nothing here makes the app fall over. The lock table stops
describing the steel, and collision safety is the property that rests on it.

Placing and lifting stock by hand is not the deviation. It is how stock joins
an evening and how every session starts
([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)), and it ends with a
person confirming a placement. A removal keeps the track under any sensor that
still reads `occupied` until that sensor reads `clear`
([ADR-0069](adr/0069-a-train-comes-off-while-running-and-its-track-opens-when-it-reads-clear.md)).
The deviation is moving a train the app believes is somewhere else, or driving
one it does not know is moving.

### What the system does not do

- **Prove deadlock freedom mechanically.** A written argument is the bar
  ([SAFETY.md](dispatcher/SAFETY.md#rigor)).
- **Plan for a collision.** A driver can go through a stop signal as a car can run
  a red light, and a collision can follow. The system does not model rogue
  operation and has no mechanism to prevent it. An asleep driver who does not
  stop a train causes an accident on a real railroad too.
- **Share a model catalogue between railroaders.** The catalogue is one local
  database for the installation, shared between one owner's railroads and no
  further ([#199](https://github.com/rails49/control/issues/199)).
- **Program decoders.** Tools made for it reach the command station directly,
  and the app never knows.
