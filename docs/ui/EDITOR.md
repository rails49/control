# Layout editor

Design for the visual layout editor, decided in #41 and settled in detail
here. Second phase of the UI work, after derivation
([DRAWING.md](../store/DRAWING.md)) and before the [panel](PANEL.md).
Terminology follows [CONTEXT.md](../../CONTEXT.md).

Prototype railways use signal boxes (*Stellwerke*) to display track occupancy
and related state; model railroads mimic them. The editor creates and edits
the drawings those displays render.

![SBB signal box](images/stellwerk.png)

RocRail supplies an editor and display, but it is closed source, assumes
control of the layout, and its editor is unpleasant to use, orienting
diagonal pieces in particular. Layouts need editing rarely, so keeping the
editor simple at the expense of some convenience is the design choice
throughout; the panel, which is used constantly, is where polish goes.

![RocRail layout](images/rocrail.png)

## What it is for

Drawing a railroad is the easy half. The hard half is knowing that the picture
means what you think it means, because what the dispatcher runs is not the
picture but the netlist derived from it, and the interesting part of that
netlist is which movements may run at the same time.

Airolo makes the point. Its WX310 is drawn the standard way, four turnouts and
a crossing, and derivation composes 19 transits and 33 concurrent pairs out of
them. Nobody can confirm 33 pairs by reading them. So the editor shows the
derived netlist beside the drawing and, for any transit, the way it takes and
the reason it excludes each other transit. That is the feature the rest of the
editor exists to serve.

## Canvas

The canvas is a grid of squares, and the grid is not negotiable. A symbol
occupies one or more whole squares; each square is free or occupied by exactly
one symbol. Pins sit at the centres of square sides, which is why symbols
rotate in 90 degree steps and flip. Diagonal running comes from wires at
angles, not from rotating symbols.

A free-standing pin sits at a face centre like any other pin. Being on a
boundary it occupies no square, so a bend may sit against an occupied one.

Zoom and pan are the SVG `viewBox`: the wheel zooms about the pointer and the
middle button pans. A bend is placed by the same two keys as any other symbol,
`at` naming a cell and `rot` turning its one pin onto a face of it
([DRAWING.md](../store/DRAWING.md#geometry)).

No committed drawing has any placement, so opening one deals its symbols into
rows to be dragged from. That is not auto-layout and says nothing about the
topology; it is an ordinary edit, undone like any other and saved only if the
drawing is saved.

## Palette

The placeable symbols, with their semantics defined in
[DRAWING.md](../store/DRAWING.md#symbols). The images are illustrative
targets, to be replaced by screenshots of the implemented artwork; the
dimensions below are normative.

| Symbol | | Notes |
| --- | --- | --- |
| Block | ![blocks](images/blocks.png) | shows occupancy on the panel; carries a signal and a sensor at each end |
| Terminal | ![terminal](images/terminal.png) | deliberate track end |
| Turnout | ![turnout](images/turnout.png) | |
| Crossing | ![crossing](images/crossing.png) | |
| Single slip | ![single slip](images/single-slip.png) | |
| Double slip | ![double slip](images/double-slip.png) | |
| 90° crossing | | upright, two straight routes |
| 90° crossing, diagonal | | the same at 45 degrees |
| Portal | ![portal](images/portal.png) | paired by label; shows its label |

Signals and sensors are not palette entries. Every block has both at both
ends, so there is nothing to place.

The generic connection symbol is not placed and not drawn. It has no fixed pin
set to place, migration is over, and since Claro east was redrawn from real
symbols (#58) it has no users left at all.

### Units and colours

One grid square is the unit G. Every dimension on the canvas is a fraction
of G, so the drawing scales as one piece; the size of G on screen is the
`viewBox` zoom and is not stored. Track and wire width is W = f·G with
f = 0.15. The fractions and the colours are named constants in one
TypeScript module, the colours as CSS custom properties; configuring the
look is editing that module, not a settings UI.

Track is drawn solid, never patterned: wires run at any angle, so a pattern's
spacing would vary with direction. Every track stroke ends in a round cap and
pins are round, so track joins seamlessly at any wire angle; a wire meeting a
fixed 45 degree leg at another angle reads as a rounded bend, not a kink.

Colours follow the editor's mode. In edit mode track is black and a block's
rectangle is white. Run mode, out of scope for now, recolours by toggling
classes: track by route reservation, a block's rectangle by occupancy, a
block's signals green where a route is reserved at that end and red
otherwise.

### Pins

Pins are circles of diameter W. In edit mode every pin is drawn: green when
satisfied, red otherwise, straight from `/review`'s `red_pins` — the front
end computes no topology. In run mode pins are not drawn and track reads as
continuous.

### Symbol geometry

Coordinates in G, origin at the top left of the unturned footprint, pins on
face centres as always. Rotations and flips give the other orientations.

**Block**, 6×1, pins at `(0, 0.5)` and `(6, 0.5)`. A centred rectangle
4G×0.8G, border 0.3W, filled white in edit mode, and a 1G track stub on each
side. The label, the block's display name or the train parked in it, is
centred in the rectangle; nothing else is written outside it — everything
else lives in the right-click dialog, and sensors are not drawn. A small
plus at the rectangle's lower corner on side A marks that side. Each stub
carries a signal drawn as in the sample, a short mast with a round head:
above the track at the A end, below at the B end, so the symbol is point
symmetric and rotation and flip read naturally.

**Terminal**, 1×1, pin at `(0, 0.5)`. A track stub from the pin to a
vertical bar 0.6G tall and 0.7W wide: the buffer stop.

**Turnout**, 1×1. `toe` at `(0, 0.5)`, `straight` at `(1, 0.5)`,
`diverging` at `(0.5, 0)`. Both roads leave the toe: the straight road runs
to the east pin, the diverging road is a 45 degree stub to the top pin. This
is the only 1×1 geometry with a 45 degree leg ending on a face centre, and a
wire continuing at 45 degrees reaches the next row's track line in half a
square, which is how turnouts stack between parallel station tracks.

**Crossing and slips**, 2×1. Route `a` is the horizontal, `a1` at
`(0, 0.5)` to `a2` at `(2, 0.5)`; route `b` is the 45 degree diagonal, `b1`
at `(0.5, 1)` to `b2` at `(1.5, 0)`. They cross at `(1, 0.5)`, the face
centre the two squares share, so the crossing is exactly two turnouts toe to
toe, the second rotated. All three kinds share this artwork; a slip adds a
small tick bridging its two legs near the crossing, one for the single slip
(`a1`–`b2`), both for the double. Tick geometry is provisional — likely
thinner than W, roughly 0.2G long and 0.25G from the crossing — and is
finalised by eye.

A lit transit lights exactly the track it traverses: each route is drawn as
two half-strokes meeting at the crossing, so a through route lights its two
halves and a slip lights its entry half, its tick, and its exit half.

**90° crossings.** `crossing_90`, 1×1: two straight routes through the four
face centres, horizontal and vertical. `crossing_90d`, 2×1: the same
crossing drawn diagonally, a symmetric X of two 45 degree routes, `(0.5, 1)`
to `(1.5, 0)` and `(0.5, 0)` to `(1.5, 1)`, crossing at `(1, 0.5)`. They are
two kinds, not two appearances of one, because their footprints and pin
positions differ; a symmetric X through the centre of a square footprint
would need corner pins, which is why the diagonal one is 2×1.

**Portal**, 1×1, pin at `(0, 0.5)`. A track stub and a mouth, with its
pairing label drawn beside it in small text, in both modes: the label is the
symbol's meaning, and matching a pair by eye is how a typo in one is found.

Each kind has exactly one appearance; diagonal legs are always 45 degrees.
The former `angle` property that picked between appearances is removed
(no committed drawing used it), and with it the appearance row in the
properties dialog.

## Drawing wires

Clicking a pin starts a wire: a wireline follows the pointer, softly snapped
to multiples of 15 degrees, with a click on a pin overriding the snap. The
snap is an aid for laying parallel track, not a rule; a wire takes whatever
angle its two pins give it. Clicking empty canvas places a free-standing pin,
a bend, and continues; clicking a pin that can accept the wire ends it.

Dropping a symbol so that one of its pins lands on another's is the fast way
to join them, and it writes a real wire of zero length. Turnouts are usually
built this way. What it does not do is make position meaningful: the wire is
in the file, so dragging the symbol away later stretches the wire instead of
breaking the connection.

Wire geometry is decorative. Wires must not cross symbols or other wires, but
the rule is enforced by warning, never by rejecting the edit: an overlap is a
misleading picture, not a wrong layout, so the offending segments are
highlighted and listed, and derivation proceeds. Rejecting edits would mean
collision detection fighting every drag.

## Editing

Left click selects; drag moves; mouse rubber-band or shift-click selects
groups. Moves rubber-band the wires: a wire carries no geometry and is drawn
straight between its two pins, so an endpoint attached to a moved pin stays
attached and stretches, a wire whose both owners move translates rigidly, and a
move cannot change the derived layout. Rotate, flip, and delete apply to the
selection, from a right-click menu with key bindings; each selected symbol
turns about its own cell rather than the selection turning as a block.

Deleting a symbol deletes its wires, and the pins at their far ends go red.

Undo and redo are snapshot-based: the drawing is a small document, so every
mutation pushes a copy. Copy and paste is not supported; it opens id and
portal-label questions that rare layout editing does not justify.

### Properties

The right-click dialog edits a symbol's name, and per kind: a block's length,
display label and sensor ids; a symbol leg's transit name.

A block's key is a short stable id and its label is its real name, `Zürich HB
Gleis 1`. The id prefixes every transit id in a trace, so it is worth keeping
short and worth not renaming; the label is free to change.

Transit names are set on a symbol's legs, which is how the drawing stores them
and how they behave: a name written on a turnout's straight leg is taken by
every derived transit that runs through it. Naming a leg and watching which
transits in the netlist pane pick the name up is the explanation. A transit
that crosses two named legs is refused, and the finding says which two.

### Junctions

A junction is a connected group of non-block symbols, which is exactly what
derivation computes, so the editor computes it too rather than asking. Wire a
crossing to a turnout and they become one tinted region with one name. That
region is worth looking at in its own right: a stray wire that merges two
throats into one junction is visible as one region where you expected two,
long before it shows up as a wrong concurrency pair.

Names are minted, `j1`, `j2`, and written into the drawing at once, so a
junction always has a valid name and nothing interrupts a sketch. Minting
happens the moment `/review` says which junctions exist, and folds into the
snapshot of the edit that caused it, so one action stays one undo step.
Renaming is one click on the region, and worth doing when the junction earns a
name, because the name heads its section in the netlist and prefixes every
transit id through it.

Deleting a symbol can split a junction in two, and wiring two together merges
them. A minted name is re-minted silently on both sides; nobody is reading
`j7`. A name someone typed stays on both halves, which derivation refuses as
a duplicate, and the findings list says so. Choosing which half is Airolo is
not the editor's decision to make. What tells the two apart is the shape of the
name itself: `j` and digits is one the editor made, and anything else is one a
person typed.

A wire joining two blocks directly is a connection too
([DRAWING.md](../store/DRAWING.md#a-wire-between-two-blocks)). Its name is
minted the same way, nothing is drawn for it, and it can be renamed from the
wire's own menu.

## Inspecting the netlist

The derived netlist sits beside the canvas and redraws as you edit. It is the
same content `tc49 layout show` prints: blocks, and per connection its
transits with their two block ends and its concurrent pairs.

Selecting a transit lights its way on the canvas, symbol by symbol and leg by
leg, and lists every other transit at that connection as either concurrent or
excluded, naming the symbol they share. *Exclusive because both take `sw16`*
is a claim about the drawing that can be checked by looking at it. Selecting a
symbol gives the inverse: every transit through it, split into those that can
run together and those that cannot.

Derivation refusing is shown the same way, at the edit that caused it.

## Validation

Findings are listed in one panel:

- pins with one connection, and unpaired portal labels: save allowed,
  derivation refused;
- duplicate connection names after a split, and transits naming themselves
  from two symbol legs: save allowed, derivation refused;
- overlaps of wires with symbols or wires: warning only.

Editing and running the same railroad at once is not prevented. The store
snapshots at startup, so a run in progress keeps the layout it began with and
an edit lands for the next one.

## Scenario editing

Placing trains is dragging onto blocks; train length is set in the same
properties dialog that sets block length, keeping the flat
`{length: n, at: block}` scenario shape. The composed loco-and-car roster of
[GOALS.md](../GOALS.md) is deferred; the `trains:` key is unchanged either
way.

## Implementation

TypeScript, pnpm, Lit and Shoelace, at `ui/` in the repo root. The drawing
surface is SVG in the DOM: hit-testing, hover and selection come from pointer
events, live state is a CSS class toggle. Gotthard is a few hundred elements,
far below where SVG struggles.

Diagram libraries (JointJS, GoJS, React Flow) were considered and rejected:
their value is auto-routing and free-form graph models, the first deliberately
absent here and the second replaced by seven fixed symbols, and each brings
its own document model to fight. Canvas engines pay off at thousands of
animated elements, not a few hundred static ones. What the editor needs, grid
snap, a wireline preview, class toggles, `viewBox` zoom, is smaller than any
library's learning curve.

**The front end knows no topology.** Pin degrees, junction membership, the
derived layout and the explanations all come from one endpoint that takes the
current document and returns them. TypeScript owns placement, geometry,
mutation and rendering, and nothing else. A second implementation of the
union-find would eventually disagree with the first, and it would disagree
inside the tool whose job is to be believed.

The server is the store's own HTTP face, `src/tc49/store/server.py`, started
with `tc49 serve`. It belongs to the store because every one of its routes is
a store operation, which keeps `tests/system/test_app_boundaries.py` intact:

    GET  /drawings              the railroads there are
    GET  /drawings/<name>       one drawing, as the document it is
    PUT  /drawings/<name>       save it, keeping what the file says
    POST /review                what a drawing means, derived and explained

`review` takes a document rather than a name, because the interesting drawing
is the one being edited: unsaved, and often not yet derivable. It answers with
the red pins, the junctions as symbol groups each carrying the name its
connection takes, the joints — the ways from one block end to another crossing
no connection symbol, with the wires that may carry a name — the derived
layout, its explanation, and the refusal where there is one. A drawing with a
red pin is the normal state mid-edit, so that comes back as a refusal inside a
200; only a document that will not load at all is a bad request. Whatever is
wrong with a drawing, the editor reads a status and a reason rather than losing
the connection.

A junction and a joint each report a `name`, `null` where the drawing has not
settled one, and `names`, what the drawing actually writes. That is what tells
the two unnamed cases apart: nothing written is a name to mint, and several
written is a disagreement someone typed, which the editor leaves alone.

A component that declares no transit is not a junction, so the terminal
capping a block end is not tinted as one.

A drawing that still has a generic connection symbol has to open, so the editor
draws it as a box with the pins it declares and no turnout detail. It stays off
the palette, having no fixed pin set to place.

The panel later adds a bus bridge alongside it
([PANEL.md](PANEL.md#implementation)).

Symbol pins and transits are generated into `ui/src/symbols.generated.ts` from
the library in `drawing.py` by `tc49 symbols`, with a test asserting the
committed file is current, so a renamed pin is a TypeScript compile error
rather than a wrong drawing. Alongside them go the palette and the rotations,
which come from the same declarations. Artwork stays hand-written against
those names.

### Tests

The editor's document, symbols and placements and wires and undo snapshots, is
a plain TypeScript module with no DOM, and that is where the Vitest tests are.
It is the layer where a bug is invisible on screen and corrupt in the file: a
move that detaches a wire, an undo that half-restores. Lit components stay thin
enough that there is little in them to test, and one grows a test when it grows
logic. No browser automation for now.

On the Python side: the endpoints, `explain()`, and a round trip asserting a
loaded and saved drawing keeps its comments.

## Order of work

The first cut is what the netlist needs: place, move, rotate, flip, wires,
junction regions, leg naming, the live netlist, the inspector, red pins, undo.
Scenario editing, portals, group selection and overlap warnings come after.
None of them can change a derived netlist, which is why they wait.

No committed drawing has any placement and there is no auto-layout, so each
railroad is drawn once by hand: `facing-pair` first at five symbols, then
`crossover-yard` at fifteen because its scissors crossover is the derivation
that DRAWING.md leans on hardest, then `single-track-meet`, then Gotthard at
thirty-six symbols and forty-four wires. Each drawn railroad is checked by
deriving it and comparing against the layout derived from the committed file.
Structure should match exactly; transit names will differ wherever a `names:`
override has not been re-entered.

Gotthard was last because Claro east had to be drawn from real symbols to be
drawn at all, and that was #35: the netlist and the hand-written layout
disagreed about its geometry. It landed on its own as #58, a topology change
rather than a drawing one, with the trace churn reviewed. The tiles won, and
what they showed is that the station's east end is two throats rather than
one.
