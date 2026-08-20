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

**Facing**:
The end of its block through which a parked train would depart nose-first.
Declared with initial placement, thereafter fully determined: routes are
strict pass-throughs, so a train faces away from the end it entered through,
and deliberate reversal at rest is the only other change. Not dispatcher
state — a request's departure end carries everything the dispatcher needs.
_Avoid_: direction (ambiguous with travel direction), heading, orientation

### Dispatch

**Request**:
An order to deliver a train out through one end of its block and in through one
of a set of **arrival ends**. Rejected if no arrival end survives — none fits
the train, or none is reachable — or if it states a departure block the train is
not standing in; otherwise accepted and queued. A rejection is an answer on the
bus, never an exception, since the submitter may be a browser
([ADR-0021](docs/adr/0021-a-bad-request-is-answered-not-raised.md)).
_Avoid_: order, job

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
([ADR-0009](docs/adr/0009-layout-interface-owns-time.md)). What generates it is
the binding — the simulator's tick, a clock on a physical railroad — and the
dispatcher never reads a clock either way.
_Avoid_: beat, round, cycle

**Tick**:
The **simulator's** grant boundary, carrying a deterministic counter: each
tick a moving train completes one transit, and travel time within blocks and
transit length are ignored. That is a property of the simulator, not of the
model — on a physical railroad a transit takes as long as it takes
([ADR-0027](docs/adr/0027-the-tick-is-the-simulators-grant-boundary.md)). The
dispatcher never learns the tick number.
_Avoid_: step, cycle. Not a synonym for *grant boundary*: say that where any
binding's beat would do

### Bus

**Topic**:
A named bus channel, `tc49/<role>/<leaf>`, the role — `layout`, `schedule`,
`dispatch`, `drive` — naming its single writer. Consumers subscribe by prefix
filter; the full inventory is
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

**Request id**:
The scheduler-minted identity of a request, deterministic in scenario order
(`<train>-1`, `<train>-2`, …) — never clock-derived. Both idempotency key
(duplicate events are dropped) and correlation key threading a request's
lifecycle and move events.
_Avoid_: event id (there is no universal envelope id)

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
