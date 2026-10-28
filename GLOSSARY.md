# Train Control

The words used in `control`, the software that schedules, dispatches and drives
trains on a model railroad. Words used in more than one rails49 repository are
in the [organisation's GLOSSARY.md](https://github.com/rails49/.github/blob/main/GLOSSARY.md).
Each entry says what a thing is and links to the doc that owns it
([ADR-0021](https://github.com/rails49/.github/blob/main/docs/adr/0021-each-fact-has-one-owner-and-the-glossary-is-glossary-md.md)).

## Language

### Layout

**Block**:
A section of track without turnouts where a train can park. It has two ends,
`A` and `B`, and a length
([LAYOUT.md](docs/store/LAYOUT.md#the-derived-layout)).
_Avoid_: section, segment, track

**Role**:
What a block is for: a `station` is called at and left again, a `siding` holds
a train as long as it likes, and a `through` block is never a destination. It
is advice to the scheduler's generator about where to send a train, never about
where one may be ([GOALS.md](docs/GOALS.md#tracks)).
_Avoid_: transient (one letter from transit), type, category, purpose

**Admits**:
The set of train kinds a block takes. It is advice on the same terms as a role,
and nothing enforces it ([GOALS.md](docs/GOALS.md#tracks)).
_Avoid_: permits, allows, filter

**Terminal block**:
A block with only one connected end, derived from the connections rather than
declared. It can only start or end a route
([LAYOUT.md](docs/store/LAYOUT.md#the-derived-layout)).
_Avoid_: dead end, siding (a physical trailing track, usually a terminal block)

**Connection**:
What joins one end of each of one or more blocks, realized by zero or more
turnouts. It declares its named transits and which pairs of them are
`concurrent`; every other pair conflicts
([LAYOUT.md](docs/store/LAYOUT.md#the-derived-layout)).
_Avoid_: connector, node

**Transit**:
One named (end, end) pair through a connection. It is undirected, one transit
covering both directions of travel, and self-exclusive, so head-on use is
excluded without declaring anything
([LAYOUT.md](docs/store/LAYOUT.md#the-derived-layout)).
_Avoid_: route (the request-level path), path, crossing (as a noun for a
transit)

**Signal**:
What stands at a block end and tells a driver whether to go and how fast. It
shows one aspect, set by the dispatcher, and an end nothing ever leaves carries
none ([DRAWING.md](docs/store/DRAWING.md#hardware-ids)).
_Avoid_: light, head, semaphore, distant

**Aspect**:
What a signal shows: `stop`, `caution` or `clear`, read off how far ahead the
dispatcher has locked
([DISPATCH.md](docs/dispatcher/DISPATCH.md#aspects)).
_Avoid_: indication, state, colour, signal (which shows the aspect), approach
(formerly)

**Lamp**:
One of a signal's lights, named for its colour: green, red or amber. An
aspect is a set of lit lamps, so no lamp is named for an aspect
([EDITOR.md](docs/ui/EDITOR.md#symbol-geometry)).
_Avoid_: bulb, light, LED, any aspect's name

### Drawing

**Drawing**:
The authored schematic of a railroad: symbols joined by wires through their
pins. It shows connectivity, not scale, and the layout is derived from it
([DRAWING.md](docs/store/DRAWING.md#what-a-drawing-is)).
_Avoid_: diagram, plan, track plan

**Valid drawing**:
A drawing the layout can be derived from. An invalid one is saved like any
other but nothing is built from it
([DRAWING.md](docs/store/DRAWING.md#what-a-drawing-is)).
_Avoid_: derives, does not derive, invalid layout

**Symbol**:
A drawing element that declares pins, transits between them, and which transit
pairs are `concurrent`: the shape of a connection, one level down
([DRAWING.md](docs/store/DRAWING.md#symbols)).
_Avoid_: element, tile, stencil

**Point**:
A motorised symbol: a turnout, a single slip or a double slip. It has one motor
and two positions ([DRAWING.md](docs/store/DRAWING.md#hardware-ids)).
_Avoid_: switch, turnout (one kind of point)

**Point gap**:
The time after one point command before the next point command, or before the
move that waits on it, goes ahead: one per railroad, kept with it and set from
the Settings dialog ([SYSTEM.md](docs/SYSTEM.md)).
_Avoid_: point delay, throw interval

**Position**:
What a point's motor is set to: `closed` or `thrown`
([DRAWING.md](docs/store/DRAWING.md#hardware-ids)).
_Avoid_: state, straight/curved, normal/reversed, leg (one way through the
symbol)

**Leg**:
One of a symbol's own transits, named on its kind: a turnout's `straight` and
`diverging`, a slip's `a`, `b` and `slip`. No kind's legs are named for its
positions ([DRAWING.md](docs/store/DRAWING.md#hardware-ids)).
_Avoid_: symbol transit, branch

**Way**:
The path a transit takes through a connection: the symbols it crosses and the
leg it takes through each. The layout keeps only its two ends and the points
along it ([DRAWING.md](docs/store/DRAWING.md#derivation)).
_Avoid_: path, walk, route (the request-level path)

**Pin**:
A connection point holding exactly two connections. A symbol pin takes one
wire, the symbol being its other connection, and a free-standing pin joins two
wires as a bend ([DRAWING.md](docs/store/DRAWING.md#pins-and-wires)).
_Avoid_: port

**Wire**:
The edge joining two pins. Its shape carries no meaning
([DRAWING.md](docs/store/DRAWING.md#pins-and-wires)).
_Avoid_: track, line, edge

**Terminal symbol**:
A one-pin symbol marking a deliberate track end, so a dangling pin always means
a mistake ([DRAWING.md](docs/store/DRAWING.md#pins-and-wires)).
_Avoid_: stop (the aspect), dead end

**Portal**:
A one-pin symbol paired by label with exactly one other portal. The pair joins
its wires as if directly connected and derives to nothing
([DRAWING.md](docs/store/DRAWING.md#portals)).
_Avoid_: connector, link (a participant's reach to its hardware)

**Junction**:
A connected group of non-block symbols declaring at least one transit. It
derives to exactly one connection, named by its members' `connection` or, for a
single symbol, by that symbol's own name
([EDITOR.md](docs/ui/EDITOR.md#junctions)).
_Avoid_: throat, node, cluster

**Joint**:
A way from one block end to another crossing no symbol that declares a
transit: one bare wire, or a chain of them through bend pins or a portal pair.
It derives to one connection with one transit, named on one of its own wires
([DRAWING.md](docs/store/DRAWING.md#a-wire-between-two-blocks)).
_Avoid_: gap, splice, bare wire (a joint may be several)

**Fixed wiring**:
Points and signals: the hardware an address reaches that stays where it was
installed, as against a locomotive's decoder. Its addresses are typed on the
drawing ([DRAWING.md](docs/store/DRAWING.md#hardware-ids)).
_Avoid_: accessories, infrastructure

**Widget**:
A text widget, a button or a toggle placed on the drawing. It has no pins and
the layout is not derived from it. Its typed name names its topic, and control
carries its payload without reading it
([ADR-0087](docs/adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)).
_Avoid_: symbol, element, indicator, control

**Text widget**:
A widget showing the last text posted on its topic, or its default text until
something is posted
([ADR-0087](docs/adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)).
_Avoid_: label, display, readout

**Button**:
A widget that sends its payload once each time a person presses it
([ADR-0087](docs/adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)).
_Avoid_: trigger, action (a gesture)

**Toggle**:
A widget with two positions, on and off, each with its own payload. Its topic
keeps the payload of the position last pressed
([ADR-0087](docs/adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md)).
_Avoid_: switch (a point), lever

### Stock

**Model**:
What a product is, independent of any railroad that owns one: a name, a
scale, a length, a kind, whether it has a decoder and what its functions are,
and optionally a photo and notes. Two railroads owning the same item share one
model ([LAYOUT.md](docs/store/LAYOUT.md#catalogue-schema)).
_Avoid_: type (reads as kind), class, product

**Car**:
One item a railroad owns: a model with zero or more fields overridden, its own
address where it has a decoder, and its own camera where it carries one. No
two cars on one railroad share either. A car stands in at most one train. A
locomotive is a car whose model's kind says so
([LAYOUT.md](docs/store/LAYOUT.md#roster-schema)).
_Avoid_: vehicle, item, wagon, rolling stock (the mass noun is stock)

**Function**:
Something a decoder turns on and off, numbered on the decoder and named per
model, such as a horn or the headlights. It is **latching**, on at
one press and off at the next, or **momentary**, on only while the throttle's
button is held. The stock view calls them *toggle* and *hold*.
_Avoid_: feature, effect, output

**Camera car**:
A car that carries a camera. A throttle holding a train the camera car is in
shows the camera's live picture. The roster says where the camera answers
([LAYOUT.md](docs/store/LAYOUT.md#roster-schema)).
_Avoid_: camera train, video car

**Catalogue**:
The models an installation knows, one set for every railroad in the store
([LAYOUT.md](docs/store/LAYOUT.md#catalogue-schema)).
_Avoid_: library (the symbol library), roster (which holds cars), inventory

**Kind**:
What a model is, `locomotive`, `passenger`, `freight` or `special`, and what a
train is, derived from the cars it hauls. A train's kinds are a different list,
with `mixed` and `light engine` and without `locomotive`
([LAYOUT.md](docs/store/LAYOUT.md#roster-schema)).
_Avoid_: type, class, category

**Train**:
An ordered list of cars, moving or parked as a unit, with a priority. Its
length and kind derive from its cars, and a railroad keeps it between sessions
([LAYOUT.md](docs/store/LAYOUT.md#roster-schema)).
_Avoid_: consist

**Orientation**:
Which way round a car is coupled in its train. With the train's facing it gives
a direction on the track ([LAYOUT.md](docs/store/LAYOUT.md#roster-schema)).
_Avoid_: direction, facing (the train's, about its block)

**Priority**:
Where a train's new request goes in the list of waiting requests: after every
request of the same or a higher priority, lowest number highest
([GOALS.md](docs/GOALS.md#dispatching)).
_Avoid_: rank, class, weight

**Roster**:
The cars a railroad owns and the trains made up from them, kept beside its
drawing. A car on it is known, which is separate from a train being placed.
Also the name of the pane that draws it
([LAYOUT.md](docs/store/LAYOUT.md#roster-schema)).
_Avoid_: closet, fleet, inventory

**Placed**:
Of a train: present in the dispatcher's `block_of`, standing in that block and
holding its standing lock. A person drags the train from the roster into a
free block, then puts its cars there. A train that is not placed is off the
layout, an ordinary state rather than a fault
([SYSTEM.md](docs/SYSTEM.md#dispatcher)).
_Avoid_: closet, positioned, not on the layout (say off the layout)

**Free block**:
A block no train is placed in, with no lock on it, and on no active train's
remaining route. Only a free block takes a placement
([ADR-0080](docs/adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
_Avoid_: empty, clear (a detector reading), vacant, unlocked

**Facing**:
The run a parked train would make across its block, written `A-to-B` or
`B-to-A`: a train facing `A-to-B` would depart nose-first through B. It is the
scheduler's state, not the dispatcher's
([SYSTEM.md](docs/SYSTEM.md#scheduler)).
_Avoid_: direction (ambiguous with travel direction), heading, orientation, the
bare end letter (formerly)

**Propelled**:
Of one move: out of the end a train's nose points away from, pushed rather
than pulled. It is an ordinary movement, not an error
([layout/README.md](docs/layout/README.md#the-traction-write)).
_Avoid_: reversing (turning round at rest), backing, shunting, pushed (as a
noun)

**Driving mode**:
Who drives the trains, set for the whole railroad: `manual`, where people
drive every train from throttles, or `automatic`, where the app drives every
train no throttle has taken. The railroad comes up `manual`
([ADR-0079](docs/adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
_Avoid_: hand control, taken over, mode (alone), auto

**Throttle**:
The control a person drives one train with: a panel of the throttle view whose
commands ride the bus as gestures that take a train, keep it held, turn its
speed and switch its functions. A throttle holds at most one train, and at most
one throttle holds a train, which it drives at any time, granted move or not.
Released, the train stops in manual driving mode; in automatic it keeps its
speed until its move ends, and is driven on if it stands
([THROTTLE.md](docs/ui/THROTTLE.md), ADR-0089).
_Avoid_: cab, controller, regulator, traction (what a decoder does with a
speed), driver (an app)

**Reverser**:
A throttle's forward/reverse switch. Forward drives the train nose-first,
reverse tail-first. It turns neither the train's facing nor any car's
orientation. It moves only with the lever at 0 (ADR-0084).
_Avoid_: direction, direction switch

### Dispatch

**Request**:
An order to deliver a train out through one end of its block and in through
one of a set of arrival ends. It ends by arrival, by rejection or by
cancellation. A train's later request starts where its earlier one ends, so
two in a row send a train by way of a block. The waiting requests are a list
in the order the dispatcher serves them, and a person can cancel or reorder
any request that has not started
([DISPATCH.md](docs/dispatcher/DISPATCH.md#semantics)).
_Avoid_: order, job, working (kept only in the sweep's stored data), schedule
(a timetable's), run, trip

**Departure end**:
The end of its block a train leaves through on a request, written `<block>.A`
or `<block>.B`. It, and not facing, is what the dispatcher routes from
([DISPATCH.md](docs/dispatcher/DISPATCH.md#requests)).
_Avoid_: leaving end, origin end, exit

**Arrival end**:
One acceptable ending for a request: a block and the end the train enters
through, written `<block>.A` or `<block>.B`. A request names a set of them, all
equally acceptable ([DISPATCH.md](docs/dispatcher/DISPATCH.md#requests)).
_Avoid_: destination (a request has no single one), arrival side, platform

**Route**:
A train's full path for a request: an alternating sequence of blocks and
transits, fixed when the train starts moving. It is a strict pass-through and a
simple path ([DISPATCH.md](docs/dispatcher/DISPATCH.md#semantics)).
_Avoid_: itinerary, journey, plan

**Lock**:
An exclusive claim on a block or transit by one train. Every train always holds
the lock on the block it stands in, its standing lock
([DISPATCH.md](docs/dispatcher/DISPATCH.md#locking)).
_Avoid_: reservation, allocation

**Committed**:
Of a resource: on a route the dispatcher has chosen, with no lock on it yet. Of
a route: chosen, and so fixed
([DISPATCH.md](docs/dispatcher/DISPATCH.md#locking)).
_Avoid_: planned, plan, pending (a request pends, a resource does not)

**Lit**:
Of a transit: locked or committed, as the run view draws it. Of a point: on a
lit transit ([PANEL.md](docs/ui/PANEL.md#what-it-shows)).
_Avoid_: reserved, highlighted

**Power**:
The railroad's one switch a person sets: `on`, `draining` or `off`. While `on`
the dispatcher routes waiting requests as soon as it can; otherwise it
routes nothing and they wait. The railroad comes up `off`
([ADR-0078](docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
_Avoid_: run, go, hold, held, running (all formerly), track supply (what `on`
and `off` switch)

**Drain**:
The ordinary way from `on` to `off`: nothing new starts, every moving train
stops in the next block and keeps its route, and the track supply goes off
when none is moving. A person turning power back on ends it
([ADR-0078](docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
_Avoid_: shutdown, wind-down, quiesce, finish the route (formerly)

**Moving**:
Some train is crossing, so cutting the track supply now would strand it. A
train standing in a block, at a signal partway along its route or anywhere
else, is not moving. It is a boolean beside power, not a fourth value
([SYSTEM.md](docs/SYSTEM.md#dispatcher)).
_Avoid_: busy, in motion, rolling, quiet, still (say not moving)

**Cancellation**:
A request ended without the train arriving, because a person cancelled it or
placed the train somewhere. The reason is `revoked`, `removed` or `displaced`
([SYSTEM.md](docs/SYSTEM.md#dispatcher)).
_Avoid_: abort, kill, delete, revoke (one of the three reasons), rejection
(which refuses a request before it is queued)

**Disputed**:
Where the placement and the detectors contradict each other while power is
off: a train whose block reads clear, or a block reading occupied with
nothing claiming it. The set points a person at each and resolves nothing
([SYSTEM.md](docs/SYSTEM.md#dispatcher)).
_Avoid_: mismatch, discrepancy, error, conflict (two transits that may not be
in use at once)

**Unfit**:
The trains the last rebuild of the railroad under the same name took off the
layout, each with its block and why: the block is gone or too short
([BUS.md](docs/BUS.md#dispatch)).
_Avoid_: invalid, orphaned, disputed (a placement against the detectors)

**Unexplained reading**:
A detector reading no granted move accounts for: a `block_occupied` with
nothing claiming the block, or a `block_vacated` of a block a train stands in.
It drains the railroad ([SYSTEM.md](docs/SYSTEM.md#dispatcher)).
_Avoid_: unexpected sensor, stray reading, phantom occupancy, false positive
(one cause of such a reading)

**Active / idle train**:
A train is active while it has a committed route, launched and not yet
completed, and idle otherwise, whether or not a request for it is pending
([SAFETY.md](docs/dispatcher/SAFETY.md#state)).
_Avoid_: running/stopped, busy/free

**Sweep**:
The dispatcher's grant pass over the active trains and the whole request
list, in its order, run where the lock table or the waiting set changes
([DISPATCH.md](docs/dispatcher/DISPATCH.md#time-model)).
_Avoid_: grant phase (said of a beat), boundary, tick (formerly)

**Fast clock**:
The railroad's operating time of day. It runs at its speed-up from a start
time, both kept with the railroad, begins at the start time each time the
railroad is loaded, and wraps at midnight. There is one for the railroad, every
page shows the same one, and it keeps running whatever track power and the run
are doing. Nothing in the control path reads it
([ADR-0090](docs/adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).
_Avoid_: scale time, sim time, run clock (the trace's elapsed seconds), session
clock (the elapsed time the band showed before)

**Speed-up**:
How many fast-clock seconds pass in one real second: at 8, an hour of the
railroad's day takes 7.5 minutes
([ADR-0090](docs/adr/0090-layout-publishes-the-fast-clock-and-the-railroad-keeps-its-start-and-speed-up.md)).
_Avoid_: multiplier, rate, scale

### Bus

**Topic**:
A named bus channel, `tc49/<component>/<leaf>`, declared by the component that
writes its events or answers its requests
([BUS.md](docs/BUS.md#the-bus)).
_Avoid_: channel, queue

**Event topic / state topic**:
Every topic is one of the two. An event topic carries facts that happened and
is never replayed; a state topic keeps its last value for late subscribers and
is marked in the path, `…/state/<name>` ([BUS.md](docs/BUS.md#the-bus)).
_Avoid_: retained message (the MQTT mechanism)

**Stamp**:
The `at` every state payload carries and no event payload does: the run
clock's reading when the value was published. It orders two values of one
topic within one run ([BUS.md](docs/BUS.md#the-bus)).
_Avoid_: timestamp, clock time, sequence number, counter, version

**Device vocabulary**:
The retained state topics naming one device each, in two halves: what a device
should do, under `tc49/layout/state/wanted/`, and what it is observed to do,
under `tc49/layout/state/device/`
([BUS.md](docs/BUS.md#device-vocabulary)).
_Avoid_: device layer, hardware topics, driver (an app)

**Address**:
The string a piece of hardware answers to, typed by whoever wired it. It names
no system, and on a device topic it is the trailing levels, repeated in the
payload as `addr` ([BUS.md](docs/BUS.md#device-vocabulary)).
_Avoid_: id (a link row's key), number, cab, dcc address, loco address,
suffix, path

**Traction**:
Moving a train: what a locomotive's decoder does with a speed, as against the
fixed wiring an address also reaches. A speed is signed for direction along
the track, and its magnitude is a fraction of the locomotive's maximum
([layout/README.md](docs/layout/README.md#the-traction-write)).
_Avoid_: throttle (a person's control), motive power, traction power (the track
supply)

**Detector**:
What watches a block end, its sensor, and publishes `occupied`, `clear` or
`unknown` on one retained state topic per sensor, addressed by
`<block>.<end>` ([BUS.md](docs/BUS.md#device-vocabulary)).
_Avoid_: camera (the device one kind is built on), block detector, sensor (the
block end watched)

**Link**:
Whether a participant can reach the hardware it drives, `up` or `down`. It is
published like any other device state and keyed by the id the publisher calls
itself ([BUS.md](docs/BUS.md#device-vocabulary)).
_Avoid_: connection (between blocks), health, heartbeat, status, system
(formerly, for the id)

**Enum**:
A field whose values are a closed set the contract names
([BUS.md](docs/BUS.md#payload-schemas)).
_Avoid_: word (formerly), status

**Command**:
An imperative event the layout interface executes: `align`, which sets a
connection to a transit, and `move`, which takes a train across a transit into
a block. They are the only imperatives on the bus
([BUS.md](docs/BUS.md#event-inventory)).
_Avoid_: instruction, cross (formerly, for `move`; the verb is fine)

**Gesture**:
What a person's action on a UI puts on the bus: a train and where to put it,
and nothing else. It is not a request: the scheduler adds the id and the
departure end ([SYSTEM.md](docs/SYSTEM.md#scheduler)).
_Avoid_: command (the layout interface's imperatives), request, click, action

**Request id**:
The identity the scheduler mints for a request, used to drop duplicates and to
tie a request's events together. It is opaque: uniqueness is the whole
contract ([SYSTEM.md](docs/SYSTEM.md#scheduler)).
_Avoid_: event id (there is no envelope id)

### Interruptions

Three failures that look alike and differ in who still holds the truth, and
three things beside them ([SYSTEM.md](docs/SYSTEM.md#interruptions)).

**Rejoin**:
A client reconnecting to a run that never stopped. Nothing was lost
([SYSTEM.md](docs/SYSTEM.md#interruptions)).
_Avoid_: reconnect (the socket, not the catching up), recovery

**Restart**:
The apps coming back up while the rails stayed as they were. The dispatcher's
lock table is lost ([SYSTEM.md](docs/SYSTEM.md#interruptions)).
_Avoid_: reboot

**Cold start**:
An app clearing the retained rows it owns and building them again, without the
process restarting ([SYSTEM.md](docs/SYSTEM.md#interruptions)).
_Avoid_: reset, reload (a page reload is a rejoin), reboot, restart

**Standing**:
An app that is up with no railroad
([SYSTEM.md](docs/SYSTEM.md#interruptions)).
_Avoid_: idle, waiting (the store's own retry), down, off (power)

**Recovery**:
Coming back after the layout lost power, when what was believed is suspect. It
ends with a person confirming each train's placement
([SYSTEM.md](docs/SYSTEM.md#interruptions)).
_Avoid_: restart, resync

**Emergency stop**:
Power straight to `off`, without a drain. A train between blocks stands
there, and carries on with its move when power is back `on`
([ADR-0078](docs/adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
_Avoid_: e-stop, stop (the aspect), stopped (formerly a third track supply
value, with the track live)

**Railroad at rest**:
Every retained `tc49/layout/state/wanted/traction` row holding `0.0`. It is a
property of the commanded rows, never an observation of the steel
([SYSTEM.md](docs/SYSTEM.md#track-power)).
_Avoid_: at rest (of a train, standing still), idle, quiet

### Store

**Railroad**:
One person's railroad, filed under one name: a drawing, the roster of the
stock it owns, the scenarios drawn on it and the script its translator loads.
One broker runs one, the loaded railroad, named on
`tc49/layout/state/railroad` ([SYSTEM.md](docs/SYSTEM.md#asset-store)).
_Avoid_: installation (the box and its store), site, world, session (one run of
one railroad), layout (the interface app), active layout (say loaded)

**Backup**:
A commit of an installation's store, made by the app driving git over the
store root ([BACKUP.md](docs/store/BACKUP.md)).
_Avoid_: snapshot, save (one document written by the editor), sync, archive

**Restore**:
Putting the store back as a named backup held it, or bringing the latest
backup into an empty store
([BACKUP.md](docs/store/BACKUP.md#restoring)).
_Avoid_: revert, roll back, undo (the editor's, over one drawing), recovery
(where trains stand)

### Contracts

**Binding**:
One implementation of a contract that BUS.md or SYSTEM.md defines. The
contract is the authority, and replacing a binding changes no app
([ARCHITECTURE.md](docs/ARCHITECTURE.md#bindings)).
_Avoid_: implementation, adapter, backend, driver (an app)

**Language binding**:
One binding per language, all of them kept
([ARCHITECTURE.md](docs/ARCHITECTURE.md#bindings)).
_Avoid_: port, sibling library, SDK

**Layout binding**:
A binding of the layout interface, one per thing that can run the track. The
physical railroad is the normative one, and the simulator conforms to it
([GOALS.md](docs/GOALS.md#approach)).
_Avoid_: backend, mode, target

**Invariant**:
A statement an ADR makes about what the bus shows: the retained values, and
what the messages so far have said. It holds once the messages in flight are
delivered. "While power is not `on`, every signal shows stop" is one
([ADR-0096](docs/adr/0096-invariants-are-stated-over-what-the-bus-shows-and-checked-in-tests.md)).
_Avoid_: rule (BUS.md's rules 1–4 are the bus contract), predicate, check

**Camera app**:
The app `camera`: it reads a camera car's picture and serves it on control's
origin
([ADR-0082](docs/adr/0082-the-camera-cars-picture-is-relayed-by-the-camera-app.md)).
_Avoid_: camera relay, camera server, picture service

**Photo camera**:
What answers `GET /camera/snapshot` with one picture, for a model's photo. No
app of this repository answers that route
([SYSTEM.md](docs/SYSTEM.md#asset-store)).
_Avoid_: camera app, snapshot service, photo app, camera (the device a
detector is built on)
