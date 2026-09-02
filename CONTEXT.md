# Train Control

Dispatching trains on a model railroad: deadlock-free, high-throughput
allocation of track to scheduling requests. The app never touches hardware:
whatever drives the track implements the **layout interface** — reporting
sensor readings, executing turnout, signal and throttle commands. A physical
railroad is the normative binding of that interface and a simulator the
subordinate one, whichever exists first
([ADR-0030](docs/adr/0030-the-physical-railroad-is-the-normative-binding.md)).
Components communicate over an event bus and an asset CRUD contract
([docs/SYSTEM.md](docs/SYSTEM.md)).

## Language

### Layout

**Block**:
A section of track without turnouts where a train can park, oriented with ends
`A` and `B` and having a length.
_Avoid_: section, segment, track

**Role**:
What a block is for, drawn on it: a **station** is called at and left again, a
**siding** holds a train as long as it likes — minutes, days, forever — and a
**through** block is never a destination. Advice to the scheduler's generator
about where to *send* a train and never about where one may *be*, so origins
and a person's placement are unconstrained and `through` on a terminal block
is a headshunt rather than a contradiction. Absent it, a block is a station
([ADR-0046](docs/adr/0046-a-blocks-role-and-filter-are-advice-to-the-generator.md)).
**Station** is this role and nothing else here: the app that owns the command
station's USB device and mirrors it on TCP 2560 is `dccex-usb`
([docs/dccex_usb/README.md](docs/dccex_usb/README.md)).
_Avoid_: transient (one letter from **transit**), type, category, purpose

**Admits**:
Which **train kinds** a block takes, drawn on it as a set: `[passenger,
mixed]` accepts a mixed train and refuses a goods one. Advice on the same
terms as a **role** and enforced by nobody — every physical impossibility is
already a length and `no_fit`, and what is left is policy the layout permits
(ADR-0046). Absent it, a block admits every kind.
_Avoid_: permits, allows, filter (the thing it does, not what it is called)

**Terminal block**:
A block with only one connected end, derived from the connections rather than
declared. Can only be the start or end of a route, never intermediate.
_Avoid_: dead end. *Siding* is a physical description — a trailing dead-end
track, which is usually a terminal block — and stays available as such
(station-C's `C4`–`C7` are sidings). It is not a synonym for the model
concept: say "terminal block" when the one connected end is what matters.

**Connection**:
What joins one end of each of one or more blocks, realized by zero or more
turnouts. Declares its named transits and, **by inversion**, which pairs of
them are `concurrent`; every pair not declared conflicts
([ADR-0006](docs/adr/0006-conflicts-declared-by-inversion.md)).
_Avoid_: connector, node. *Junction* and *joint* are not synonyms to avoid but
the drawing's two words for what derives to one connection — see below.

**Transit**:
One traversable (end, end) pair through a connection, always named.
**Undirected** — one transit covers both directions of travel — and
**self-exclusive**, so head-on use is excluded structurally. Two transits at the
same connection may be in use simultaneously only if the connection declares
them `concurrent`. The same concept one level down: a symbol declares transits
between its pins, usually unnamed, and derivation composes symbol transits
into connection transits.
_Avoid_: route (reserved for the request-level path), path, crossing — the
noun, for a transit or for the symbol kind of that name; the verb is
sanctioned, and `tc49/dispatch/state/allocation`'s `crossing` maps a train to
the transit it is crossing.

**Signal**:
What stands at a block end and tells a driver whether to go and how fast. Shows
one **aspect**, set by the dispatcher. An end nothing ever leaves carries none,
a signal that could only show `stop` being furniture.
_Avoid_: light, head, semaphore, distant

**Aspect**:
What a signal shows, one of exactly three, read off how far ahead the
dispatcher has locked
([ADR-0025](docs/adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)):

| Aspect | Locked ahead | Swiss | Meaning to the driver |
| --- | --- | --- | --- |
| `stop` | nothing | Halt | stand |
| `caution` | one block | Fb 2 | proceed, prepared to stop at the next signal |
| `clear` | two or more | Freie Fahrt (Fb 1) | full speed |

The Swiss column is what each aspect answers to and not a translation: Fb 2
names a speed, 40 km/h, where `caution` names a braking instruction, and which
of the two the middle aspect finally is stays open (ADR-0025).

`stop` unless a block beyond has been reserved, which follows from the locks
rather than being a rule of its own.
_Avoid_: indication, state, colour, signal (the signal shows the aspect),
approach (the middle aspect's earlier name)

**Lamp**:
One of a signal's three lights, named for its colour: green, red, amber. An
aspect is a *set* of lit lamps and not a lamp, which is why no lamp is named
for an aspect — `stop` is red alone, `caution` is green with amber, `clear`
is green alone, as the Swiss standard sets them.
_Avoid_: bulb, light, LED, and any aspect's name

### Drawing

**Drawing**:
The authored schematic of a railroad: symbols joined by wires through their
pins. Shows connectivity, never scale. The source of truth — the layout is
derived from it and never authored
([ADR-0015](docs/adr/0015-drawing-is-the-source-of-truth.md)).
_Avoid_: diagram, plan, track plan

**Symbol**:
A drawing element declaring pins, transits between them, and which transit
pairs are `concurrent` — the shape of a connection, one level down. Blocks,
terminals, turnouts, crossings, slips, and portals are symbols.
_Avoid_: element, tile, stencil

**Point**:
A motorised symbol — a turnout, a single slip or a double slip. One motor, two
positions, one address. A fixed crossing has no motor and is not one. The
plural also names the set a transit's way must have thrown to be traversable.
_Avoid_: switch, turnout (a turnout is one kind of point, not the category)

**Address**:
The string a point's motor answers to on the hardware, written `addr` and typed
by whoever wired it. Nothing checks it — a DCC accessory number is a string
that happens to be digits, and only the railroad knows what is true. Two points
may share one, and then they move together
([ADR-0022](docs/adr/0022-a-symbol-carries-its-hardware-address.md)).
_Avoid_: id, number, dcc address

**Position**:
What a point's motor is set to: `closed` or `thrown`, the pair a DCC accessory
decoder answers to. Not a **leg** — a leg is one way through the symbol, and
the library declares which leg wants which position.
_Avoid_: state, straight/curved, normal/reversed

**Leg**:
One of a symbol's own transits, named on its kind: a turnout's `straight` and
`diverging`, a slip's `a`, `b` and `slip`. The library declares which position
each leg of a point wants, a turnout's legs being named for its positions and a
slip's not.
_Avoid_: symbol transit, branch

**Way**:
The path a transit takes through a connection: the symbols it crosses and the
leg it takes through each. Derivation composes it and the layout keeps only its
two ends and the points along it — a way itself is the drawing's knowledge.
_Avoid_: path, walk, route (reserved for the request-level path)

**Pin**:
A connection point holding exactly two connections. A symbol pin accepts one
wire, the symbol being its other connection; a free-standing pin joins two
wires as a bend. A pin with one connection is an error. A block symbol's pins
are its ends `A` and `B`.
_Avoid_: port

**Wire**:
The edge joining two pins. Its shape carries no meaning: derivation reads
only which pin connects to which.
_Avoid_: track, line, edge

**Terminal symbol**:
A one-pin symbol marking a deliberate track end, so a dangling pin always
means a mistake. Terminal *blocks* stay derived from connectivity.

**Portal**:
A one-pin symbol paired by label with exactly one other portal; the pair
joins its wires as if directly connected and derives to nothing. A drawing
device for joining distant parts of the canvas. Placed with its mate, since one
alone is a label worn once and derivation refuses it
([ADR-0020](docs/adr/0020-a-portal-is-placed-as-a-pair.md)).
_Avoid_: connector, link

**Junction**:
A connected group of non-block symbols declaring at least one transit: the
drawing's way of holding a connection whose turnout detail is drawn. Derives to
exactly one connection, whose name its members carry as `connection`, or, where
the group is one symbol, which is the symbol's own name. A group declaring no
transit is not one — a terminal capping a block end derives to nothing, and the
editor tints only junctions.
_Avoid_: throat, node, cluster

**Joint**:
A way from one block end to another crossing no symbol that declares a transit:
one bare wire, or a chain of them through bend pins or a portal pair. Also
derives to exactly one connection — one transit spanning the two ends — and
carries that connection's name on one of its own wires. A **portal pair is not
a joint**: it is one way a joint's chain crosses the canvas, and a joint
through one is a joint however it is drawn.
_Avoid_: gap, splice, bare wire (a joint may be several)

### Stock

**Model**:
What a product *is*, independent of any railroad that owns one: a length, a
**kind**, and the meaning of each DCC function — which number sounds the horn
on that item. Two railroads owning the same item share one entry, which is why
a model is not a **car**
([ADR-0045](docs/adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
_Avoid_: type (reads as a synonym of *kind*, which is taken), class, product

**Car**:
One item a railroad owns: **a model with zero or more fields overridden**, and
its own DCC address where it has a decoder, unique across the railroad. Zero
overrides is the common case and still names its model, so a car has one
shape; scratch-built stock earns a model of its own rather than a second kind
of car. A **locomotive is a car** whose model's kind says so, which is why the
address hangs here and not on a train.
_Avoid_: vehicle, item, wagon, rolling stock (the mass noun, which is *stock*)

**Address** (of a car):
The number programmed into a car's decoder — bare, taking **no system prefix**,
unlike a point's. It is programmed once and generally kept, and it is the same
number whoever sends the packet: turnout wiring can be split across systems and
traction cannot, so a railroad changing command station rewrites nothing
(ADR-0045, refining
[ADR-0043](docs/adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
_Avoid_: id, cab, loco address

**Catalogue**:
The models an installation knows, one database rather than one per railroad.
Sharing one between railroaders is somebody else's product and out of scope.
_Avoid_: library (taken by the symbol library), roster (which holds cars),
inventory

**Kind**:
What a model is — `locomotive`, `passenger`, `freight`, `special` — and, one
level up, what a train is. A **train's kind is derived** from the cars it
hauls, **ignoring locomotives**: every hauled train has one, so counting them
would make every train *mixed*. Exactly one sort hauled gives that sort, more
than one gives `mixed`, and none is a `light engine` — a real move rather
than a degenerate case. **The two lists differ**: `locomotive` is never a
train's kind, `mixed` and `light engine` are never a model's, and a block's
**admits** lists train kinds, so an engine shed takes `[light engine]` and
never `[locomotive]` ([ADR-0046](docs/adr/0046-a-blocks-role-and-filter-are-advice-to-the-generator.md)).
_Avoid_: type, class, category

**Train**:
An **ordered list of cars**, moving or parked as a unit; its length is the sum
of its parts and its **kind** is derived from them. A train at rest occupies
exactly one block; while crossing it holds the transit and, until its tail
clears, the block behind as well. Durable — a railroad keeps rakes made up
between sessions — and carries a **priority**.
_Avoid_: consist

**Orientation**:
Which way round a car is coupled in its train. A locomotive's forward is a
fixed direction of the physical item, so orientation composed with the train's
**facing** is what gives a direction on the track — and it is what lets a
locomotive at each end of a train run opposite (ADR-0045).
_Avoid_: direction, facing (which is the train's, and about its block)

**Priority**:
A train's claim on the queue, lowest number highest. **Strict among
simultaneously launchable requests**: where two could both launch the higher
wins regardless of age, and where the higher-priority one cannot launch the
lower one still goes. So starvation stays bounded within a priority level by
[ADR-0012](docs/adr/0012-the-pending-scan-ages-by-refusal-count.md)'s aging and
is deliberately unbounded across levels, which is why freight runs at night.
_Avoid_: rank, class, weight

**Roster**:
The **cars** a railroad owns, served by the store beside its drawing, with the
trains made up from them alongside. With the
drawing it is the whole of what a **run** is built from: a railroad, its
stock, and a person who puts the stock on the rails
([#171](https://github.com/rails49/control/issues/171)). A car in
it is **known**, which is separate from a train being **placed**: a railroad at
rest says what stock it has without saying where any of it stands
([ADR-0039](docs/adr/0039-a-train-may-be-off-the-layout.md), one level down
since ADR-0045). Also the name of
the pane that draws it, as `netlist` names both what derivation produces and
the pane it is read in.
_Avoid_: closet, fleet, inventory

**Placed**:
Of a train: present in the dispatcher's `block_of`, standing in that block and
holding its standing lock. A train that is not placed is **off the layout** —
an ordinary state rather than a fault, and *absence* from the mapping rather
than a sentinel block name
([ADR-0039](docs/adr/0039-a-train-may-be-off-the-layout.md)). Every placed
train is made of cars on the roster; a train may be placed nowhere, and an
unplaced train has no **facing**, there being no block for a facing to be an
end of.
_Avoid_: closet, positioned. *Not on the layout* is the same state said a
second way, and the state has one phrase.

**Facing**:
The run a parked train would make across its block, written **`A-to-B`** or
**`B-to-A`** — a train facing `A-to-B` would depart nose-first through B.
Said as the run and not as the end reached, so the value can be read without
the convention in front of you; the end is one question away
(`lib.layout.departure_end`) and the two spellings are one fact.
Declared with initial placement and thereafter determined by four rules:
routes are strict pass-throughs, so a train that left nose-first faces away
from the end it entered through; a train **propelled** — pushed out of the end
its nose points away from, which a request's **departure end** may ask for —
enters the next block tail-first and so faces the end it entered through; on a
**terminal block** there is no end to face away towards, and facing is the run
that departs by its one connected end whatever a placement or a route would
say; and deliberate reversal at rest is the one change routes do not account
for. Every one of those is a change the stock actually underwent: committing
to a route is a plan and moves no arrow
([#295](https://github.com/rails49/control/issues/295)). Held by the scheduler
and published on its own state topic as `<block>.A-to-B`, which every view
reads to draw a train's direction and `layout` reads to give a speed its sign
([ADR-0052](docs/adr/0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md)).
Not dispatcher state — a request's
departure end carries everything the dispatcher needs, and may contradict
facing.
_Avoid_: direction (ambiguous with travel direction), heading, orientation.
The bare end letter the value once was is retired
([#241](https://github.com/rails49/control/issues/241)): it is refused at
load and refused in a state file, never read as a run.

**Propelled**:
A movement out of the end a train's nose points *away* from: pushed rather
than pulled. Said of one move and never of a train, since the same train is
propelled over one transit and nose-first over the next. An **ordinary
movement and not an error** — a request's **departure end** may ask for one,
and a train that makes one enters the next block tail-first, which is one of
the four rules that determine **facing**. It is half of the sign `layout` puts
on a speed, the other half being each car's **orientation**
([ADR-0052](docs/adr/0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md)).
_Avoid_: reversing (which is turning round at rest, and a different thing),
backing, shunting, pushed as the noun

**Automatic / manual**:
Who turns a train's throttle. Every train is one or the other and
**automatic** at rest: taking a train in a **throttle** makes it manual and
releasing it puts it back
([#207](https://github.com/rails49/control/issues/207)). Held by `layout`,
which is what a throttle's gestures reach, and published on
`tc49/layout/state/mode`, where a train the map does not name is automatic. It
names who drives and nothing more — a manual train is dispatched like any
other, holding its block, still granted moves and moving only on a route the
dispatcher allocated, with a person trusted to read the signal it is given.
Neither the dispatcher nor the driver ever reads it.
_Avoid_: hand control, taken over; and *mode* said of the **system**, which
is **held** or **running** and a different thing on a different topic. An
operator running a signal at stop is rogue operation this word does not cover
and the system does not model.

**Throttle**:
The control a person drives a train with: a view of this repository's UI whose
commands ride the bus as two gestures — `tc49/layout/mode_wanted`, which takes
a train and gives it back, and `tc49/layout/throttle_wanted`, which is the
throttle being turned. Gestures because there are any number of throttles —
two tabs are two of them — where the device row one ends at has `layout` as
its single writer
([ADR-0035](docs/adr/0035-a-topic-has-one-writing-role.md),
[#263](https://github.com/rails49/control/issues/263)). Its speed is signed
for which way the train runs along its own length, nose-first positive, and
its magnitude is the fraction of maximum, `0.0` being stop; which locomotive
that reaches is `layout`'s, which reads the roster.
_Avoid_: cab, controller, regulator. Not **traction**, which is what a
decoder does with a speed, and not the **driver**, which is an app and reads
an aspect.

### Dispatch

**Request**:
An order to deliver a train out through one end of its block and in through one
of a set of **arrival ends**. Rejected if no arrival end survives — none fits
the train, or none is reachable — or if it states a departure block the train is
not standing in; otherwise accepted and queued. A rejection is an answer on the
bus, never an exception, since the submitter may be a browser
([ADR-0021](docs/adr/0021-a-bad-request-is-answered-not-raised.md)). It ends
three ways and no others: by **arrival**, by that rejection, or by
**cancellation**.
_Avoid_: order, job, working. The sweep keeps `workings` — the axis, the
`sweep-<n>t-<n>w` row key and the stored results
([BENCHMARKS.md](docs/bench/BENCHMARKS.md)) — because that is a frozen data
format, and a format is not a licence to name anything new with the word.

**Departure end**:
The end of its block a train **leaves through** on a request, written
`<block>.A` / `<block>.B` as an arrival end is. A request states one, and a
chained request may state only the letter, the block it will depart from being
a dispatcher choice not yet made. Where the stated end is one no train can
leave by — the wall of a **terminal block** — the one connected end is the
answer, that being all a stub has. A request's departure end, not **facing**,
is what the dispatcher routes from, and the two may disagree
([ADR-0019](docs/adr/0019-facing-is-scheduler-state.md)). What the
disagreement means is that the train is pushed: it leaves through the end its
tail stands at, and every block of that route it enters tail-first
([#295](https://github.com/rails49/control/issues/295)).
_Avoid_: leaving end, origin end, exit

**Arrival end**:
One acceptable ending for a request: a block together with the end the train
**enters through**, written `<block>.A` / `<block>.B` exactly as a departure end
is. A request names a *set* of them, unordered and equally acceptable, and the
dispatcher commits to one when it chooses the route
([ADR-0007](docs/adr/0007-requests-name-a-set-of-arrival-ends.md)). Naming both
ends of one block says "either way round"; naming several blocks says "any of
these tracks".
_Avoid_: destination (the request has no single one), arrival side, platform

**Route**:
A train's full path for a request: an alternating sequence of blocks and
transits, fixed when the train starts moving. Strictly pass-through — a train
enters each block at one end and exits at the other; reversal happens only
between requests, at rest. Also a **simple path**: no block or transit occurs
twice. So a reversing loop turns a train over *two* requests, not one — not
because reversal is forbidden (the loop needs none) but because the second leg
would revisit the loop's own blocks.
_Avoid_: itinerary, journey, plan

**Lock**:
Exclusive claim on a block or transit by one train. Incremental locking claims
a little way ahead of the train and releases what it has left — one block ahead
is enough to move, two is what buys full speed, and a third is never asked for
([ADR-0026](docs/adr/0026-two-blocks-ahead-is-full-speed.md)); full-route
locking claims every resource up front. Occupancy is a **standing lock**: every train, moving or
parked, requested or not, always holds the lock on the block it stands in.
_Avoid_: reservation, allocation

**Committed**:
Of a resource: on a route the dispatcher has chosen, with no lock on it yet —
the weaker of the two claims a route carries, and what the stretch ahead of the
locks is. Of a route: chosen, and so fixed
([ADR-0002](docs/adr/0002-fixed-route-per-request.md)). A resource can be
committed and locked at once, and the lock is then what it shows.
_Avoid_: planned, plan, pending (a request pends, a resource does not)

**Held**:
Of a **run**: the dispatcher will commit nothing — no route chosen, no move
granted, no lock taken — until a person releases it. One of the run's own
three states, `held`, `running` or **draining**, published by the dispatcher
and moved by a gesture
([ADR-0037](docs/adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
A brake and not an emergency stop: a move already granted runs to its sensor,
and what keeps a railroad still after a power cut is track power, one layer
down. The layout holds it too, in two ways: `tc49/layout/state/power` arriving
as anything but `on` sets `run` to `held`, and a release is refused until it is
back
([ADR-0041](docs/adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)),
and an **unexplained reading** sets it the same way
([ADR-0048](docs/adr/0048-an-unexplained-reading-holds-the-run.md)).
Admission is untouched — requests queue up while held. A run **comes up
held unless its own document stood its trains on the rails**: a restored
session comes up held, so does the empty layout every operator's run starts
from, and what opens running is the harness's batch loop, built from a
scenario file.
_Avoid_: paused, stopped, frozen. Not the `held` **grant_refused** reason,
which says a resource is locked by another train: a different thing, on a
different topic, about one request rather than the run.

**Drain**:
The ordinary way to turn a railroad off: the run stops **launching**, the
trains already moving run to the end of the routes they are on, and the
dispatcher writes `held` itself at the first moment none is left. `draining`
is the third value of the run and not a state of its own, and the gate is on
launching rather than on admission — admission is cheap and reversible,
launching is the commitment, so requests queue up through a drain as they do
through a hold. It is what the panel's OFF asks for and the completion is
what it waits for before cutting track power
([ADR-0051](docs/adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md),
[#294](https://github.com/rails49/control/issues/294)); an abrupt cut instead
would leave no **position** trustworthy and could strand a train mid-transit.
A **hold** during one abandons it at once, which is also the way out of a
drain a wedged train would hold open forever — hold, and take that train off
the layout.
_Avoid_: shutdown, wind-down, quiesce, stop admitting (it is launching that
stops). Not the queue *draining* in the order it accumulated, which is the
ordinary verb for a queue emptying and says nothing about the run.

**Cancellation**:
A request ended without the train arriving, because a person said so: they
cancelled it outright, or they said where the train actually is and the
placement retired it under them
([ADR-0049](docs/adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)).
The gesture names a **train** and no request, and ends everything that train
has, pending and active. What the request held is released except the block
the train stands in, which is its **standing lock**; a cancellation caught
mid-transit waits for the sensors that end the move, nothing on the bus
retracting a `move` already sent. The reason is `revoked`, `removed` or
`displaced`, and it says which gesture ended the request rather than why the
railroad could not finish it.
_Avoid_: abort, kill, delete, revoke as the general word (it is one of the
three reasons). Not a **rejection**, which refuses a request before it is
queued and is an answer to whoever submitted it.

**Disputed**:
Where the placement and the detectors contradict each other, named while the
run is **held**: a *train* whose block the layout reports clear, and a *block*
the layout reports occupied with nothing claiming it. Published as a set the
panel points a person at, and it **resolves nothing** — occupancy is
anonymous, so the check only points and a person ends each entry with a
placement ([#153](https://github.com/rails49/control/issues/153)). A block
the layout has said nothing about is neither: silence is not a clear reading.
_Avoid_: mismatch, discrepancy, error. Not a **transit conflict**, which is
two transits that may not be in use at once.

**Unexplained reading**:
A detector reading no granted move accounts for: a `block_occupied` with
nothing claiming the block, or a `block_vacated` of a block the dispatcher
believes a train stands in. Occupancy is anonymous, so the dispatcher reads
identity off its lock table, and a reading the table cannot explain says the
table has stopped describing the steel — a hand putting a locomotive down, a
train pushed while the supply was off, a detector asserting on dirt. It
**holds the run**, by the path track power takes, and what it contradicts is
named in the **disputed** set for a person to walk
([ADR-0048](docs/adr/0048-an-unexplained-reading-holds-the-run.md)). It never
raises, and nothing is placed on the strength of it.
_Avoid_: unexpected sensor, stray reading, phantom occupancy, false positive
(which names one cause of a reading, not the reading)

**Active / idle train**:
A train is **active** while it has a committed route — launched, not yet
completed — and **idle** otherwise, whether or not a request for it is pending.
An idle train's standing lock makes its block *permanently* unavailable, since
nothing in the dispatcher will move it; this is what
[SAFETY.md](docs/dispatcher/SAFETY.md) means by a permanent obstacle.
_Avoid_: running/stopped, busy/free

**Sweep**:
The dispatcher's grant pass, run where the lock table or the waiting set
changes — a request admitted, a `block_vacated` releasing what a move held,
the run released
([ADR-0047](docs/adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
A sweep covers the active trains and the whole pending queue, so a refused
train is reconsidered exactly when the resource it waited on frees and every
pending request accrues a refusal in the same sweep, which is what carries
the aging order
([ADR-0012](docs/adr/0012-the-pending-scan-ages-by-refusal-count.md)). There
is no grant boundary and no beat: the dispatcher grants on the events that
arrive, and every grant is `safe()`-checked before it commits.
_Avoid_: grant phase said of a beat, boundary, tick — the old grant boundary
left the contract with ADR-0047

**Fast clock**:
The railroad's scaled operating time: the wall clock with a start time and a
multiplier, both railroad configuration, so anything that wants it derives it
— it has no carrier on the bus. It is what a scenic lighting cycle would
follow and what a milestone-2 timetable is written against. Free-running and
settable, and **never read in the control path** — a train waits on
detectors, so a late train is just late and moving the clock commands nothing
(ADR-0044's surviving rule, ADR-0047).
_Avoid_: scale time, sim time. Not the run clock the trace's `time` stamp
reads, which is elapsed seconds since the session started

**Tick**:
The **simulator's** old word for its beat, retired with the grant boundary
(ADR-0047): the simulator is a discrete-event engine now, scheduling each
accepted move's two sensor events on fixed delays of its own. Travel time is
those delays, a property of the simulator and not of the model — on a
physical railroad a transit takes as long as it takes.
_Avoid_: step, cycle, or reusing tick for the live loop's command poll

### Bus

**Topic**:
A named bus channel, `tc49/<component>/<leaf>`, the component — `layout`,
`schedule`, `dispatch` — being the one that **declares** it: the events it
emits, of which it is the single writer, and the requests it responds to,
which any number of writers may send and which disclose their source nowhere
([ADR-0035](docs/adr/0035-a-topic-has-one-writing-role.md),
[#263](https://github.com/rails49/control/issues/263)). Concurrent writers
are for event topics, never state topics. Consumers subscribe by prefix
filter; the full inventory is [SYSTEM.md](docs/SYSTEM.md#event-inventory).
_Avoid_: channel, queue

**Event topic / state topic**:
Every topic is exactly one of the two. An event topic carries facts that
happened and is never replayed; a state topic is last-value-wins, delivered
to late subscribers, and marked in the path (`…/state/<name>`).
_Avoid_: retained message (the MQTT mechanism, not the model concept)

**Stamp**:
The `at` every state payload carries and no event payload does: the run
clock's reading when the value was published, in seconds since the session
started. It is what keeps the later of two values of one state topic when the
wire hands them over backwards — later wins, equal replaces, earlier is
ignored, and an unstamped value is taken and clears the held stamp
([#240](https://github.com/rails49/control/issues/240)). Written by the
binding that publishes and never by an app, so no app component reads a clock
([ADR-0009](docs/adr/0009-layout-interface-owns-time.md)). It orders within
one session and says nothing across a restart: the clock starts at zero every
run, so the bus re-stamps what it loads from the durable file and the restored
picture is the oldest thing known
([ADR-0030](docs/adr/0030-the-physical-railroad-is-the-normative-binding.md)).
_Avoid_: timestamp or clock time (it is neither wall time nor comparable
across sessions), sequence number or counter (nothing is minted, and no
publisher owns it), version

**Device vocabulary**:
The retained state topics naming one device each, in two halves. What the
device **should do**, under `tc49/layout/state/wanted/` — a locomotive's speed
and functions, a point's position, a signal's aspect, the track's power —
written by `layout`, with a **translator**, one app per hardware system,
acting on every address it recognises. What it is **observed to do**, under
`tc49/layout/state/device/` — a sensor's occupancy, a point's position where
the hardware reports one, the track's power, and a translator's **link** —
written by whatever watches or drives the thing addressed, of which there is
exactly one per address, and read by `layout`. The rest of the system never
names a device, `align` and `move` naming a transit
([ADR-0043](docs/adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
Both halves are `tc49.lib.inventory.DEVICE_TOPICS`.
_Avoid_: device layer, hardware topics, driver (which names an app)

**Address** (on a device topic):
The trailing levels of a device topic, repeated in the payload as `addr`. Two
shapes, and which one a row takes is physical: a **traction** or function
address is bare, and a **point** or signal address names its system first,
`<system>/<addr>` — fixed wiring can be split across systems and traction
cannot (ADR-0043, refined by
[ADR-0045](docs/adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
A **sensor** takes a third shape of its own, the block end it watches. Not a
leaf: the row is the topic above the address, which is what `split_device`
takes apart. The two `track` rows carry none, there being one railroad-wide
power desired and one observed; a **link** carries one and repeats it as
`system` rather than as `addr`, naming no device.
_Avoid_: id, suffix, path

**Traction**:
Moving a train: what a locomotive's decoder does with a **speed**, against the
**fixed wiring** — points and signals — that is the other thing an address
reaches. The distinction is what the two address shapes turn on. A speed is
signed for direction along the track and its magnitude is the fraction of that
locomotive's maximum, `0.0` being stop; a decoder step never leaves a
translator. The `move` command states the **magnitude alone**, the driver
having no way to know which way round a locomotive stands, and `layout` is
what gives it the sign
([ADR-0025](docs/adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
_Avoid_: throttle (a person's control, which is its own entry), motive power,
traction power (which is the track supply)

**Detector**:
What watches a **block end** and publishes what it sees there, on one retained
state topic per **sensor**: `occupied`, `clear` or `unknown`. Addressed by the
block end, `<block>.<end>`, and never by the detector's own identifier — the
drawing carries the mapping and the detector is configured with the names it
must publish, so nothing above the layout interface learns detector geometry
(ADR-0043, [#194](https://github.com/rails49/control/issues/194)). It
publishes a **level change and nothing else**: no heartbeat, no restatement on
a timer, and
nothing asks it for its state, retention being what a late subscriber gets.
`unknown` is a value and not an absence — the detector knows *why* it cannot
say, and the free-text `reason` carries that for a person to read, while a
consumer treats it as no information about that end. Two of them watch a
block, and folding the pair into `block_occupied` and `block_vacated` is
`layout`'s.
_Avoid_: camera (one kind of detector), block detector; and not the **sensor**
itself, which is the block end watched and is what the topic is addressed by

**Link**:
Whether a translator can reach the hardware it drives: `up` or `down`,
observed and published like any other device state, addressed by the `system`
whose link it is and carrying a free-text `detail`. It is what lets a view say
the command station is unreachable rather than leaving the railroad merely
looking idle, and it is where verifying that the hardware is really reachable
belongs: at runtime, with a person present who can act on it, never in a gate
that would need a powered layout to pass
([ADR-0050](docs/adr/0050-broken-hardware-is-reported-never-worked-around.md),
ADR-0043).
_Avoid_: connection (the track between two blocks, which is its own entry),
health, heartbeat, status

**Enum**:
A field whose values are a closed set the contract names, listed beside the
field in `tc49.lib.inventory`. Three fields are enums: `run`, `held`,
`running` or `draining`; `power`, `on`, `stopped` or `off`; and `mode`,
`automatic` or `manual`. The closed set goes wherever
the field goes — `run` is an enum on the run's own state topic and on the
gesture that asks to move it — so a fresh value is a change to the contract
and not a payload a reader tolerates.
Which way an unreadable value falls is not the field's but the reader's,
decided by what a drop would cost: an unreadable `power` is read as `off` and
holds the run, where dropping it would leave the run committing over track
whose state could not be read; an unreadable `run` is dropped and nothing is
set ([#175](https://github.com/rails49/control/issues/175)); an unreadable
`mode` is dropped too, neither value being safe to invent for a train whose
driver nobody could read.
_Avoid_: word (the term this entry used until
[#242](https://github.com/rails49/control/issues/242)), status. Not a
**flag**, which is what [SYSTEM.md](docs/SYSTEM.md) calls a state topic
carrying a boolean — `exhausted` is one and is not an enum.

**Command**:
An imperative event the layout interface executes: `align` (set a connection
to a transit) and `move` (a train crosses a transit into a block, at a stated
speed). The only imperatives on the bus — everything else is a past-tense fact.
The grant and the command share a word — `tc49/dispatch/move_granted` and
`tc49/layout/move` — because the second is the first restated as an imperative.
_Avoid_: instruction, `cross` (the name this command carried until
[#236](https://github.com/rails49/control/issues/236)); the verb stays
sanctioned, and **Transit** says where.

**Gesture**:
What a person's action on a UI puts on the bus: a train and where to put it,
and nothing else. **Not a request** — it carries no id and no departure end,
which is the whole of what the scheduler adds when it composes the request the
gesture asks for. One that cannot be composed is dropped rather than answered,
there being no id to address an answer to
([ADR-0036](docs/adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)).
_Avoid_: command (reserved for the layout interface's imperatives), request,
click, action

**Request id**:
The scheduler-minted identity of a request. Both idempotency key (duplicate
events are dropped) and correlation key threading a request's lifecycle and
move events — and **opaque to both**, so uniqueness is the whole contract and
no consumer reads the shape
([ADR-0033](docs/adr/0033-a-request-id-is-unique-not-meaningful.md)). The
scheduler mints `<train>-1`, `<train>-2`, … from one undivided counter in
the order a timetable states, which replay needs — and a run carrying
gestures does not, no benchmark run receiving any. Never clock-derived, and never minted by a
page.
_Avoid_: event id (there is no universal envelope id)

### Interruptions

Three failures look alike and differ in who still holds the truth. Naming
them apart is what keeps a page reload from being sized like a power cut
([ADR-0032](docs/adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
The two hardware controls below are a fourth thing again: the apps stay up
throughout, so nothing is lost and nothing is recovered.

**Rejoin**:
A client reconnecting to a session that never stopped. Nothing was lost: the
dispatcher is running and holds the truth, and the client is a late subscriber
that catches up from the run's retained state.
_Avoid_: reconnect (the socket, not the catching up), recovery

**Restart**:
The apps coming back up while the rails stayed as they were. What was lost is
the dispatcher's lock table, which no sensor can return — sensors are
anonymous — so placement must be seeded before the first sensor event, from
something persisted or by a person placing every train again.
_Avoid_: reboot, cold start (which is a restart with nothing to restore)

**Recovery**:
Coming back after the layout lost power. Everything a restart lost, and what
was believed is now *suspect*: a train that stalled in a tunnel gets lifted
out by hand. Ends with a person confirming placement however much was
persisted; persistence makes that cheaper, never automatic.
_Avoid_: restart, resync

**Emergency stop**:
Every locomotive told to stand, with the track still live. The locos stop;
points hold their positions and the decoders keep their state. A control on
the command station, reported to the app as `stopped` on
`tc49/layout/state/power`, and the run **holds** on it
([ADR-0041](docs/adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
It ends with a person clearing the stop and pressing GO; power returning
releases nothing by itself.
_Avoid_: e-stop, stop (the aspect), hold (the run's own state, which a person
moves)

**Power off**:
The track supply removed. Nothing moves, and the accessory decoders lose it
too, so no point position can be trusted afterwards. Reported as `off` on the
same topic and holding the run the same way — the two differ for the person
recovering, not for the dispatcher. Not **recovery**: the apps stayed up and
their picture is only as stale as the steel that stopped moving. What is lost
is a train granted a move when the supply went: it is stranded between blocks
and no sensor will ever say where it stopped.
_Avoid_: shutdown, blackout, emergency stop (the track stays live for that)

### Contracts

**Binding**:
One implementation of a contract that [SYSTEM.md](docs/SYSTEM.md) defines
normatively. The contract is the authority; a binding is not, and replacing
one changes no app. Bindings differ in whether they supersede or coexist.
_Avoid_: implementation, adapter, backend. Not *driver*, which names an app.

**Milestone binding**:
A binding that supersedes: exactly one exists at a time, and the next
milestone deletes it. The in-process bus gives way to MQTT, the YAML store to
REST. Nothing to drift from.
_Avoid_: provisional binding, stub

**Language binding**:
A binding that coexists: one per language, all live indefinitely. Python
today, TypeScript alongside it once there is a UI. Siblings can drift, so they
answer to a checkable schema of the contract rather than to prose or to each
other ([ADR-0014](docs/adr/0014-python-apps-typescript-ui.md)).
_Avoid_: port, sibling library, SDK

**Layout binding**:
A binding of the layout interface, one per thing that can run the track. It
coexists, and it is **ranked**: the physical railroad is the normative one and
the simulator conforms to it. Where the two could differ the physical railroad
decides, even at cost to the simulator. Simulation stays behind the interface
in its own app, free to grow there but never a field, a topic or a branch
anywhere else
([ADR-0030](docs/adr/0030-the-physical-railroad-is-the-normative-binding.md)).
_Avoid_: backend, mode, target
