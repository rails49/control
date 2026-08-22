# Control Model Railroads

A model railroad comprises **assets** (what it is made of) and **operations**
(what is done with them). Terminology follows the glossary in
[CONTEXT.md](../CONTEXT.md).

## Assets

### Tracks

The rails the railroad runs on, divided into blocks and the connections between
them.

**Blocks** are sections of track without turnouts where a train can park. Each
block is oriented with ends `A` and `B` and has a length. Sensors report the
presence of train(s) in a block — usually one, but cars decoupled from each
other appear as separate trains. Each end a train can leave through carries a
**signal**, which is how a driver is told whether to go and how fast; an end
nothing ever leaves carries none.

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

The rolling stock traveling or parked on the tracks:

- Individual locomotives and cars, each with a length (and other properties).
- **Trains**: collections of cars and locomotives. A train's length is the sum
  of its parts. A train at rest occupies exactly one block; while crossing it
  holds the transit and, until its tail clears, the block behind as well. It
  must fit in every block of its route.

A railroad **owns** its stock: its **roster** is every train it has, whether
any of them is on the layout or not
([ADR-0039](adr/0039-a-train-may-be-off-the-layout.md)). That is what a run
begins from — a railroad, the trains it owns, and a person who takes them out
of the closet, puts them on the track and drags them where they should go.
Nothing else is needed to start one, and a run with an empty layout is the
ordinary way an evening starts rather than a fault.

## Operations

Railroad operations divide into three distinct functions, each of them an app
([ADR-0013](adr/0013-apps-are-deployment-units.md)). What follows is the whole
of them; [MILESTONE-1.md](MILESTONE-1.md) says which parts are being built
first.

### Scheduling

Decides which train departs from where, to what destination, and when — as
soon as possible, or at a stated time. A stated time is read off the
railroad's **fast clock**, the scaled time a model railroad runs its
operations on and the only thing a timetable can be written against; it is not
a count of the simulator's grant boundaries
([ADR-0027](adr/0027-the-tick-is-the-simulators-grant-boundary.md)), which a
hardware adapter does not produce. Its prototype counterpart is the timetable,
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
and releases what the train has left — a block that a train has vacated is
free, and its signal returns to `stop` at once. Sensors in blocks, and at some
connections, are how it knows: a signal shows `stop` unless a block beyond it
has been explicitly reserved for a train, which is a consequence of locks
rather than a rule about signals.

How far ahead it has locked is exactly what the train's signal says, because
stopping takes distance:

| Locked ahead | Aspect | The train |
| --- | --- | --- |
| nothing | `stop` | stands |
| one block | `approach` | moves, slowly enough to stop at the next signal |
| two or more | `clear` | runs at full speed |

So one block ahead is enough to move — a train can at least reach the next
block, and may have to wait there — and **two is what buys full speed**. Two is
also the most that is ever asked for: a third block ahead shows the same aspect
as the second, so it buys nothing and holds track another train may be waiting
for ([ADR-0026](adr/0026-two-blocks-ahead-is-full-speed.md)).

### Driving

Takes the role of a locomotive engineer, one per train, performed by a person
or automatically. A driver decides one thing — how fast, or whether to stop —
by reading the signal it faces. It does not decide where the train goes: the
turnouts are already set when the signal clears, so the train follows the rails
it is given.

A person driving looks out of the window. An automated driver has to be told
which aspect applies to its train, since track detectors are anonymous and
report occupancy without identity; the dispatcher, which knows which train is
where, says so as part of granting the move
([ADR-0025](adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).

`approach` promises the train can stop before the next signal, and something
has to make that true. The working answer is a per-locomotive calibration of
what "slow" means, together with a constraint on the railroad rather than on
the software: a block is at least a braking distance long at approach speed.
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
Milestone 1 builds only the simulator, which is an order of work rather than a
rank.

The layout interface also owns time
([ADR-0009](adr/0009-layout-interface-owns-time.md)) and is the only part that
knows how a locomotive actually behaves: told to take a train into a block at a
speed, it is what throttles up, watches the detector and stops. Under the
simulator time is a tick and a train crosses one transit per beat; on a
physical railroad a clock sets the beat and transits take as long as they take
([ADR-0027](adr/0027-the-tick-is-the-simulators-grant-boundary.md)).

### Hardware that lies

Everything above assumes the layout interface tells the truth: that a detector
reporting `occupied` is right, and that points told to throw have thrown.
Collision safety rests on that, since the lock table keeps two trains apart
only if the track the dispatcher thinks it set is the track that is there. A
physical railroad guarantees neither. Points fail to throw and report nothing,
so a route that failed to set looks correct
([ADR-0017](adr/0017-turnout-position-is-inferred-by-the-panel.md)). Detectors
bounce, drop out, and read dirty wheels as an empty block. A decoder misses its
packet, a locomotive stalls, or someone lifts a train off the track by hand.
Collision safety is the property that matters when these happen, and it is the
one the current argument does not cover.

**Hardware is assumed perfect**, and that is a decision rather than an
oversight. Every one of these failures has answers — reported point position,
detector redundancy, a plausibility check of sensor events against the lock
table, a watchdog on a transit that takes too long, an emergency stop — and
every answer costs. Which of them earns its cost depends on which failures
actually bite, that is not knowable until there is a layout to learn it from,
and no hardware is running yet, so the set worth working on is empty. The
failures are written down here rather than worked on, so the day hardware
appears the effort starts from a list instead of from a surprise under a
running train.
