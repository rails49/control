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

**Terminal block**:
A block with only one connected end, derived from the connections rather than
declared. Can only be the start or end of a route, never intermediate.
_Avoid_: dead end. *Siding* is a physical description — a trailing dead-end
track, which is usually a terminal block — and stays available as such (Claro's
`claro_4`–`claro_7` are sidings). It is not a synonym for the model concept:
say "terminal block" when the one connected end is what matters.

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
_Avoid_: route (reserved for the request-level path), path, crossing

**Signal**:
What stands at a block end and tells a driver whether to go and how fast. Shows
one **aspect**, set by the dispatcher. An end nothing ever leaves carries none,
a signal that could only show `stop` being furniture.
_Avoid_: light, head, semaphore, distant

**Aspect**:
What a signal shows, one of exactly three — `stop`, `approach` (proceed,
prepared to stop at the next signal), and `clear` (full speed) — read off how
far ahead the dispatcher has locked: nothing, one block, two or more
([ADR-0025](docs/adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
`stop` unless a block beyond has been reserved, which follows from the locks
rather than being a rule of its own.
_Avoid_: indication, state, colour, signal (the signal shows the aspect)

**Lamp**:
One of a signal's three lights, named for its colour: green, red, amber. An
aspect is a *set* of lit lamps and not a lamp, which is why no lamp is named
for an aspect — `stop` is red alone, `approach` is green with amber, `clear`
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

**Train**:
A collection of locomotives and cars moving or parked as a unit; its length is
the sum of its parts. A train at rest occupies exactly one block; while
crossing it holds the transit and, until its tail clears, the block behind as
well.
_Avoid_: consist

**Roster**:
The trains a railroad owns, served by the store beside its drawing. A train in
it is **known**, which is separate from being **placed**: a railroad at rest
says what stock it has without saying where any of it stands
([ADR-0039](docs/adr/0039-a-train-may-be-off-the-layout.md)). Also the name of
the pane that draws it, as `netlist` names both what derivation produces and
the pane it is read in.
_Avoid_: closet, fleet, inventory

**Placed**:
Of a train: present in the dispatcher's `block_of`, standing in that block and
holding its standing lock. A train that is not placed is **off the layout** —
an ordinary state rather than a fault, and *absence* from the mapping rather
than a sentinel block name
([ADR-0039](docs/adr/0039-a-train-may-be-off-the-layout.md)). Every placed
train is on the roster; a train on the roster may be placed nowhere, and an
unplaced train has no **facing**, there being no block for a facing to be an
end of.
_Avoid_: closet, positioned. *Not on the layout* is the same state said a
second way, and the state has one phrase.

**Facing**:
The end of its block through which a parked train would depart nose-first.
Declared with initial placement and thereafter determined by three rules:
routes are strict pass-throughs, so a train faces away from the end it
entered through; on a **terminal block** there is no such end, and facing is
its one connected end whatever a placement or a route would say; and
deliberate reversal at rest is the one change routes do not account for. Held
by the scheduler and published on its own state topic, which every view reads
to draw a train's direction. Not dispatcher state — a request's departure end
carries everything the dispatcher needs, and may contradict facing.
_Avoid_: direction (ambiguous with travel direction), heading, orientation

### Dispatch

**Request**:
An order to deliver a train out through one end of its block and in through one
of a set of **arrival ends**. Rejected if no arrival end survives — none fits
the train, or none is reachable — or if it states a departure block the train is
not standing in; otherwise accepted and queued. A rejection is an answer on the
bus, never an exception, since the submitter may be a browser
([ADR-0021](docs/adr/0021-a-bad-request-is-answered-not-raised.md)).
_Avoid_: order, job, working

**Departure end**:
The end of its block a train **leaves through** on a request, written
`<block>.A` / `<block>.B` as an arrival end is. A request states one, and a
chained request may state only the letter, the block it will depart from being
a dispatcher choice not yet made. Where the stated end is one no train can
leave by — the wall of a **terminal block** — the one connected end is the
answer, that being all a stub has. A request's departure end, not **facing**,
is what the dispatcher routes from, and the two may disagree
([ADR-0019](docs/adr/0019-facing-is-scheduler-state.md)).
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
granted, no lock taken — until a person releases it. The run's own state,
`held` or `running`, published by the dispatcher and moved by a gesture
([ADR-0037](docs/adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
A brake and not an emergency stop: a move already granted runs to its sensor,
and what keeps a railroad still after a power cut is track power, one layer
down. The layout holds it too: `tc49/layout/state/power` arriving as anything
but `on` sets the word to `held`, and a release is refused until it is back
([ADR-0041](docs/adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
Admission is untouched — requests queue up while held. A run **comes up
held unless its own document stood its trains on the rails**: a restored
session comes up held, so does the empty layout every operator's run starts
from, and what opens running is the harness's batch loop, built from a
scenario file.
_Avoid_: paused, stopped, frozen. Not the `held` **grant_refused** reason,
which says a resource is locked by another train: a different thing, on a
different topic, about one request rather than the run.

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

**Active / idle train**:
A train is **active** while it has a committed route — launched, not yet
completed — and **idle** otherwise, whether or not a request for it is pending.
An idle train's standing lock makes its block *permanently* unavailable, since
nothing in the dispatcher will move it; this is what
[SAFETY.md](docs/dispatcher/SAFETY.md) means by a permanent obstacle.
_Avoid_: running/stopped, busy/free

**Grant boundary**:
The beat the layout interface publishes and the dispatcher grants on: each one
triggers a grant phase over the sensor events buffered since the last, so
grants are a function of that set and not of arrival order
([ADR-0009](docs/adr/0009-layout-interface-owns-time.md)). Every binding
publishes it as `tc49/layout/boundary` carrying a `boundary` count, numbered
rather than bare so that a redelivery cannot double-advance anything counting
it. What generates the beat is the binding — the simulator's tick, a clock on
a physical railroad — and the dispatcher never reads a clock either way.
_Avoid_: beat, round, cycle

**Tick**:
The **simulator's** beat, published as its grant boundary and carrying a
deterministic counter: each tick a moving train completes one transit, and
travel time within blocks and transit length are ignored. That is a property
of the simulator, not of the model — on a physical railroad a transit takes as
long as it takes
([ADR-0027](docs/adr/0027-the-tick-is-the-simulators-grant-boundary.md)). The
dispatcher never learns the boundary number.
_Avoid_: step, cycle. Not a synonym for *grant boundary*: say that where any
binding's beat would do, and never on the contract, which every binding
speaks

### Bus

**Topic**:
A named bus channel, `tc49/<role>/<leaf>`, the role — `layout`, `schedule`,
`dispatch`, `drive`, `ui` — naming its single writing **role**, of which there
may be concurrent instances on an event topic and never on a state topic
([ADR-0035](docs/adr/0035-a-topic-has-one-writing-role.md)). Consumers
subscribe by prefix filter; the full inventory is
[SYSTEM.md](docs/SYSTEM.md#event-inventory).
_Avoid_: channel, queue

**Event topic / state topic**:
Every topic is exactly one of the two. An event topic carries facts that
happened and is never replayed; a state topic is last-value-wins, delivered
to late subscribers, and marked in the path (`…/state/<name>`).
_Avoid_: retained message (the MQTT mechanism, not the model concept)

**Command**:
An imperative event the layout interface executes: `align` (set a connection
to a transit) and `cross` (a train crosses a transit into a block, at a stated
speed). The only imperatives on the bus — everything else is a past-tense fact.
_Avoid_: instruction

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
scenario order, which replay needs — and a run carrying gestures does not,
no benchmark run receiving any. Never clock-derived, and never minted by a
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
anonymous — so placement must be seeded before the first sensor event, from a
scenario or from something persisted.
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
