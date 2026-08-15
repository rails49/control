# Layout editor and dispatch panel

A future project, deliberately outside milestone 1. Nothing here is decided for
the code currently being built; this page records a design worked out in
discussion so it can be picked up later. Terminology follows
[CONTEXT.md](../../CONTEXT.md), which this project would extend.

## Motivation

Prototype railways use signal boxes (*Stellwerke*) to display track occupancy
and related state. Model railroads mimic them: a track plan showing blocks and
their connections, turnout positions, train locations and direction, and
reserved routes.

This app keeps topology in layout files and everything else in in-app data
structures. Two things are missing:

- a way to create layouts visually, and
- a way to watch the railroad in real time.

RocRail supplies both. Its display is good and it has most of the required
features, but it is closed source, it assumes control of the layout in addition
to showing state, which would collide with the control this app implements, and
its editor is unpleasant to use. Orienting the diagonal connecting pieces in
particular takes far longer than it should.

## What the drawing is

The picture is schematic, without regard to real dimensions, which is how both
prototype dispatch panels and RocRail work. Block length is a property set in a
right-click panel, never something drawn to scale.

A drawing is a **port graph**. You place symbols and join their ports with
wires. Wire shape carries no meaning: derivation reads only which port connects
to which.

A **symbol** is a set of ports, a set of internal paths between those ports, and
which pairs of paths may be used at once. That is the same shape as a
connection in the layout format, one level down:

| Symbol | Ports | Paths | Concurrent |
| --- | --- | --- | --- |
| Block | 2 (`A`, `B`) | the block itself | n/a |
| Turnout | 3 | toe-straight, toe-diverging | none |
| Diamond crossing | 4 | the two straights | both |
| Double slip | 4 | 4 | one pair |
| Connection (generic) | N | declared | declared |

Two structural properties fall out of the block symbol having exactly two
ports, and a port accepting exactly one wire:

- **One connection per block end** stops being a rule to check and becomes
  undrawable. Hanging a siding off the middle of a station track is not
  expressible, which is correct; it becomes an explicit *split block* operation,
  because it really is two blocks.
- **Terminal blocks stay derived.** A block with one port unwired is terminal.

### The generic connection symbol

An N-port symbol that declares its transits and concurrency directly, rather
than being built from turnouts. Derivation passes it through unchanged, so it
is the identity element of the whole scheme. It does three jobs:

- Every existing layout converts to a drawing mechanically and losslessly.
- A junction whose real geometry is unknown can be modelled anyway. Gotthard's
  Airolo is exactly this case: it declares nothing `concurrent` on purpose,
  with a note that this is too strict and should be relaxed once the real
  geometry is known. Forcing turnouts to be drawn would mean inventing that
  geometry, and derived concurrency would silently replace the deliberate
  choice.
- Detail can be added one junction at a time, independently.

The cost is that a junction drawn this way shows no turnout detail on the panel.

## Derivation

The drawing is the source of truth. The layout is derived from it and is never
authored. The drawing is strictly richer (turnouts, signals, labels) and cannot
be recovered from a layout file, so the relationship can only point this way.

Three passes over a small graph:

1. Connected components of non-block symbols give the connections.
2. Walking internal paths between a component's boundary ports gives the
   transits.
3. Composing symbol concurrency pairwise over those transits gives `concurrent`.

Cost is negligible. Gotthard's largest component is Airolo with 19 transits over
roughly ten symbols: a few hundred traversal steps and 171 pairwise checks, run
once per `get` against a snapshot that is immutable for the run.

The scheme was checked against `crossover-yard`. Its `up_straight` and
`dn_straight` share only the diamond and cross it on the two different straight
paths, so composition yields exactly the one `concurrent` pair the file declares
by hand.

### Names and determinism

Transit names default to a function of the two block ends and can be overridden,
with the override stored in the drawing. Gotthard's hand-picked names survive
migration; Airolo's 19 need no typing unless someone wants them named.

Derived names must be a pure function of topology, never of drawing order or
symbol ids, and the derived layout needs canonical key order. Otherwise moving
a symbol renames a transit, changes the trace bytes, and churns every golden
file for no semantic reason.

## Asset store

Two document types, `drawing` and `scenario`. There are no `.layout.yaml`
files; `get()` derives the Layout on read, the way terminal blocks are derived
today. Components are unaffected: they call `get` and receive a `Layout`.

This keeps [ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)'s
two coarse document types intact rather than growing a third, and there is no
second copy of the topology to fall out of date. What it gives up is the
readable topology diff in review: one moved wire can flip concurrency across
many transit pairs, and the drawing diff shows one changed line. A
`tc49 layout show <name>` command covers that on demand.

The derived layout should still be run through the existing validator. It is a
cheap safety net against derivation bugs.

## The panel

### What it shows

Blocks render as a rectangle: colour for state, label for the train, arrow for
direction. Reserved-but-empty blocks get a distinct fill, so a committed route
reads as a lit path.

There are no sensor dots at block ends. `block_occupied` and `block_vacated`
carry a block, and the layout interface publishes anonymous occupancy and never
asserts train identity. RocRail's two dots depict per-end detection, which is
finer than anything on this bus. Train identity is reconstructed from
`lock_granted`, exactly as the dispatcher does; direction comes from the chosen
route or the entry end of the last granted transit.

**Turnout positions are inferred from `align`.** The panel holds the drawing, so
it can work out which turnouts a transit traverses. This needs no turnout
identity in the app, no new bus topic, and no change to
[SYSTEM.md](../SYSTEM.md)'s position that the transit-to-turnout-positions table
is private hardware configuration. It shows commanded position, not measured
position, so a point that failed to throw would look fine. Reported position
becomes worth adding if hardware with point feedback ever exists.

**Signals attach to a block port.** A signal governs departures through one
block end, and routes are strict pass-throughs with no reversal within a route,
so a signal at `claro_2.B` can only mean "may the train in `claro_2` leave via
B". Placing one is a toggle on a port, and it cannot be attached to something
meaningless.

The aspect rule is **locked-ahead**: green if the resource beyond that end is
currently locked to the train standing there. That is what a real signal means,
it reuses the lock ledger the panel already maintains for reserved-block
shading, and it stays stable while a train runs. Deriving the aspect from
`grant_refused` instead would require a per-train state machine over an event
topic and would describe the dispatcher's state rather than the railway's.

### What it does

The panel is read-only apart from submitting requests. Clicking a train and
then one or more arrival ends publishes `request_submitted`, the existing topic
in the existing `schedule` role, and the dispatcher answers with
`request_admitted` or `request_rejected`. This is the scheduling UI
[SYSTEM.md](../SYSTEM.md) anticipates when it calls the milestone-1 scheduler
"the honest template for a future scheduling UI: publish intents, let the
dispatcher judge."

The panel therefore **is** a scheduler, and modes are exclusive: a run uses the
file scheduler or the panel, never both. That preserves the single-writer rule
and the single deterministic id minter. Scenario runs keep byte-identical
replay; panel runs make no such claim. Later the panel-scheduler can preload a
scenario and also take clicks, which is still one writer.

Manual turnout throwing is not offered. RocRail allows it because it owns manual
shunting, which this model excludes: trains move only on granted routes and
reversal happens only between requests, at rest. There is also no turnout
identity for a command to address, and a second authority deciding what is safe
would sit alongside the dispatcher.

## Implementation

One Python server exposes the asset store over REST and bridges `tc49/#` to the
browser over a WebSocket. Validation stays in the existing Python validator
rather than being reimplemented in TypeScript. The MQTT transport switch later
changes only what the bridge subscribes to.

The front end is TypeScript, pnpm, Lit and Shoelace, per the usual toolchain.
The drawing surface is **SVG in the DOM**: hit-testing, hover and selection come
from pointer events, live state is a CSS class toggle, and zoom and pan are the
`viewBox`. Gotthard is a few hundred elements, far below where SVG struggles.

Wires auto-route by default: straight if the ports align, otherwise a single 45°
dogleg. Adding a waypoint makes a wire manual permanently, and it is then only
translated when a symbol moves, never rerouted. A general orthogonal router was
rejected as the feature that demos well and then fights the user daily. Because
wire shape is decorative, a poor route is a cosmetic annoyance and never a wrong
layout, so this can start simple.

Scenario editing covers placing trains by dragging onto blocks and setting
length in the same panel that sets block length, keeping today's flat
`{length: n, at: block}` shape. The composed loco-and-car roster of
[GOALS.md](../GOALS.md) is wanted eventually but is deferred; the `trains:` key
is unchanged either way, with `length` becoming derived when it arrives.

## Order of work

1. **Derivation, in Python, no UI.** Convert both committed layouts to drawings
   using generic connection symbols, which must round-trip exactly. Then refine
   `crossover-yard`'s double crossover into four turnouts plus a diamond by hand
   and re-derive. Getting back the four transits and exactly the one
   `[up_straight, dn_straight]` concurrent pair proves the architecture. This
   phase can say "stop".
2. **SVG panel over a recorded trace file.** No server. Immediately useful for
   reviewing past benchmark runs.
3. **The server**, and the panel live.
4. **The editor**, on the same symbol library.
5. **Request submission** from the panel.

The editor comes late rather than first. Converting the committed layouts is
mechanical, so the panel has real drawings to render before any editor exists,
and derivation is the risk worth retiring first.

## Open

- Where drawing files live. `layouts/<name>.drawing.yaml` fits, since layouts no
  longer occupy that directory.
- Group select, move, duplicate and delete, and undo. Ordinary editor work with
  no architectural fork, so it was left undesigned.
- [LAYOUT.md](../LAYOUT.md) documents the layout schema as the authored format,
  and both committed layouts carry reasoning comments that would have to move
  into drawings. That is a real rewrite.
- Editing and running the same railroad are exclusive, because the store
  snapshots at startup.
- `CONTEXT.md` would gain drawing, symbol, port, wire, panel and signal. Those
  entries are not written, because `CONTEXT.md` belongs to the work in progress.

## Decisions

Three decisions are recorded as ADRs in [adr/](adr), unnumbered while they sit
outside the main sequence:

- [The drawing is the source of truth](adr/drawing-is-the-source-of-truth.md)
- [The panel is a scheduler](adr/the-panel-is-a-scheduler.md)
- [Turnout position is inferred by the panel](adr/turnout-position-is-inferred-by-the-panel.md)
