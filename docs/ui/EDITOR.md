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

The same railroad in this editor. Track is black and a block's rectangle white,
and every pin is drawn.

![Gotthard in the editor](images/gotthard.svg)

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

Placing and dragging keep that invariant. A drop that would cover an occupied
square places nothing, and the ghost says so before the drop by tinting the
squares in the way. A drag of the selection holds its last legal offset while
the pointer is over an obstacle, and follows the pointer again once the offset
is clear.

Rotate and flip are not constrained, since a turned symbol has a different
footprint and can land on a neighbour. An overlap is reported instead: the
squares are marked and the findings name the symbols. It is computed from the
drawing rather than raised by the action, so it reads the same after an undo or
after opening a file that already had one.

Zoom and pan are the SVG `viewBox`: the wheel zooms about the pointer and the
middle button pans. Both directions of the wheel were there from the start and
neither was findable, so the header carries a minus and a plus beside Fit and
the keyboard has `+`, `-` and `0`.

A bend is placed by the same two keys as any other symbol, `at` naming a cell
and `rot` turning its one pin onto a face of it
([DRAWING.md](../store/DRAWING.md#geometry)). That makes a bend's `rot` its
orientation rather than a turn, so dragging one cannot translate by whole cells
the way every other symbol does: it would only ever reach faces of the
orientation it was born with. A bend dragged alone snaps to the nearest face
instead, `rot` and all. In a selection of several it translates rigidly with
the rest, where the whole-cell rule is the one that applies.

No committed drawing has any placement, so opening one deals its symbols into
rows to be dragged from. That is not auto-layout and says nothing about the
topology; it is an ordinary edit, undone like any other and saved only if the
drawing is saved.

## Palette

A symbol is dragged out of the palette onto the canvas. There is no armed tool
and no mode: nothing about the editor's state changes what the next click on
the canvas means, which was the trouble with arming a tile — the screen said
the tile was pressed, and nothing said the next click would put a turnout
where you were only trying to select.

The symbol follows the pointer as a ghost drawn on the grid, at the cell it
would land on, in the artwork it will be placed in. Its footprint centres on
the pointer; `at` names a whole cell, so an even-width footprint lands half a
square off, which is as close as the grid allows. Nothing is drawn while the
pointer is off the canvas, there being nowhere to place it there.

`r` turns the ghost and `f` flips it, the same two keys that turn and flip a
selection. The orientation is sticky: it carries into the next drag, whatever
the kind, because a rotated run of turnouts should cost one keypress for the
run and not one for each of them. The tiles keep showing the symbol at 0
degrees; the ghost shows the truth the moment it is grabbed. Escape, Delete and
the right button abandon the drag.

A portal is placed as a pair. Dropping one puts its mate straight back in
flight, wearing the same label and turned 180 degrees, so the next click lands
the far end. The turn suits track that vanishes and continues the same way
somewhere else, whose two mouths face opposite; `r` turns it for the drawings
that do not. Nothing is asked and nothing is armed: the mate is the same ghost
under the same three keys, and the pair is one undo step, so undo takes both
halves back and undo mid-flight takes the first half and the ghost together.
Abandoning the mate leaves one portal, which is a finding rather than an
error ([ADR-0020](../adr/0020-a-portal-is-placed-as-a-pair.md)).

Tiles carry no names. Each kind is drawn one way, so the drawing is the name,
and the title attribute has the word for anyone who wants it.

The tiles are laid out in three groups, in the order of the table below: the
block by itself; the six symbols track crosses or divides at, two to a row so
that the pairs — the two slips, the two 90 degree crossings — sit side by
side; and the two ends of a drawing, where track stops and where it leaves the
sheet. Space between the groups is the only thing telling them apart. A
heading would be the only word in the palette, naming a category the symbols
already show. The block takes a whole row rather than half of one: its 6x1
tile is as wide as the pane allows, and halving it would draw it smaller than
every other symbol when the tiles are all at one grid square.

The placeable symbols, with their semantics defined in
[DRAWING.md](../store/DRAWING.md#symbols). The images are the tiles themselves,
all at one grid square, so a symbol's width here is its footprint; the
dimensions below are normative.

| Symbol | | Notes |
| --- | --- | --- |
| Block | ![block](images/symbol-block.svg) | shows occupancy on the panel; carries a signal and a sensor at each end |
| Turnout | ![turnout](images/symbol-turnout.svg) | |
| Crossing | ![crossing](images/symbol-crossing.svg) | |
| Single slip | ![single slip](images/symbol-single_slip.svg) | |
| Double slip | ![double slip](images/symbol-double_slip.svg) | |
| 90° crossing | ![90 degree crossing](images/symbol-crossing_90.svg) | upright, two straight routes |
| 90° crossing, diagonal | ![90 degree crossing, diagonal](images/symbol-crossing_90d.svg) | the same at 45 degrees |
| Terminal | ![terminal](images/symbol-terminal.svg) | deliberate track end |
| Portal | ![portal](images/symbol-portal.svg) | paired by label; placed as a pair |

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
spacing would vary with direction. A track stroke ends in a round cap and pins
are round, so track joins seamlessly at any wire angle; a wire meeting a fixed
45 degree leg at another angle reads as a rounded bend, not a kink.

Track that ends inside another shape is cut instead, because a round cap would
bulge past a buffer bar or a portal's mouth. Where the end is square the cap is
butt; where it is oblique the stroke is clipped, so the stub still lights and
still widens like any other track, and nothing is painted over the junction tint
behind it.

The signal, the tick, the buffer bar and the portal's mouth are proportioned
against the grid square rather than against W. They are marks the size of a
tile, not track that widens with it, so their fractions are of G and stay that
way.

Colours follow the editor's mode. In edit mode track is black and a block's
rectangle is white, and a signal shows both its lamps lit. Run mode, out of
scope for now, recolours by toggling classes: track by route reservation, a
block's rectangle by occupancy, and a signal by dimming the aspect it is not
showing, green where a route is reserved at that end and red otherwise.

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
side. The label, the block's name or the train parked in it, is
centred in the rectangle; sensors are not drawn and everything else lives in
the right-click dialog. A plus at the rectangle's lower corner on side A marks
that side, drawn at the rectangle's own 0.3W.

The label turns with the block but not inside its artwork: a horizontal block
reads upright and a vertical one bottom to top, at both quarter turns and
under a flip, so a label is never upside down and never mirrored. Which end is
A is the plus's business, not the label's. It is drawn at 0.50G, or at
whatever smaller size makes it fit the rectangle's long side — that being the
width it has to fit whichever way the block stands. The size is estimated from
the name's length rather than measured, since measuring means a second render
pass to read a number the label is already laid out from, and a label a few
percent smaller than it had to be is invisible where a render loop is not.
There is no floor: a name long enough to shrink past legibility is drawn small
rather than clipped, because the zoom rescues small text and nothing rescues
text that is not there.

Each stub carries a signal centred on it, unless nothing ever leaves that end:
a chamfered plaque 0.53G by 0.22G floating 0.09G clear of the track, holding
two lamps 0.12G across, red then green. There is no mast. The A signal hangs below the track, on the left of a
train leaving through A, as the SBB places signals. The B signal is the A
signal turned 180 degrees about the block's centre, above the track with its
lamps in the opposite order, which keeps the symbol point symmetric and makes
rotation and flip read naturally.

**An end nothing leaves carries no signal.** A siding's blind end — Claro 4's
B end, which runs into a buffer stop — could only ever show red, and a signal
that can never clear is furniture. Which ends those are is read off the
derived layout: an end appears in a transit or it does not, joints being
transits too, so no topology is computed here. The plaque and both lamps are
omitted rather than dimmed, a dim signal being an aspect and there being no
signal there to show one.

An end goes dark only once its pin is satisfied. An unwired end is in no
transit either, but it is unfinished rather than blind, and a block whose
signals vanished the moment it was dropped — the palette tile and the ghost
having just shown both — would read as a fault in the drawing rather than a
fact about it. A drawing that does not derive is no answer at all, and every
signal stays.

**Terminal**, 1×1, pin at `(0, 0.5)`. A track stub from the pin to a
vertical bar 0.6G tall and 1.2W wide: the buffer stop. The stub is cut square
at both ends. At the bar the cut keeps it from bulging past it; at the pin the
pin covers the cut in edit mode and the incoming wire's round cap covers it in
run mode.

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
toe, the second rotated.

All three kinds share this artwork. A slip adds a tick, the road it has and a
plain crossing has not: two straight strokes, one parallel to each of the two
legs the road joins, offset 0.22G from each leg's centreline and meeting where
those two offset lines cross. Arms about 0.14G, hairline weight, square ends,
no flare. The tick sits in the obtuse sector between the two legs, the only
pair a slip road can join, so where it is says which road exists: one for the
single slip (`a1`–`b2`), both for the double.

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

**Portal**, 1×1, pin at `(0, 0.5)`. A track stub whose end is cut at 22
degrees from vertical, and two grey hairlines at that same angle beyond it,
each about 0.53G long: the first crosses the track's centreline at the cut, the
second 0.09G further out.

A block's label is the only text on the canvas. Nothing else is named there, a
portal and a junction region included; a name is read in the properties dialog
and in the netlist pane.

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

`r`, `f` and Delete are the whole verb set, so the header carries none of them:
a button that duplicates a key it does not teach is a button doing nothing. The
right-click menu names the key beside each item, which is where a shortcut is
conventionally learnt, and a line under the palette heading covers the drag,
which has no menu to hang one on.

Click and drag mean different things on a pin, and which one it is is settled
by whether the pointer moves. A click starts or ends a wire; a drag past a few
pixels takes hold of the bend instead. Drawing a wire is click-then-click
rather than a drag, so the threshold cannot steal one.

Deleting a symbol deletes its wires, and the pins at their far ends go red.

A wire is cut from its own right-click menu, which is the only way to delete
one: a wire has no symbol to select, so no keystroke can take it, and the
verbs above all read the selection. Cutting leaves both pins a wire short and
so red, which is what says where the track now stops. The menu offers the cut
only where no symbol is under the pointer, since a symbol's own wires pass
within a hair of its pins — an abutted one has no length at all — and a click
on a turnout is a question about the turnout.

Undo and redo are snapshot-based: the drawing is a small document, so every
mutation pushes a copy. Copy and paste is not supported; it opens id and
portal-label questions that rare layout editing does not justify.

### Properties

The right-click dialog edits a symbol's name, and per kind: a block's length
and sensor ids, and a portal's label.

**Only a name hardware answers to is shown.** A block is named, and so is a
turnout or a slip, which has a motor the bus will address. A fixed crossing has
nothing to command, a pin and a terminal are wiring, and a portal is known by
its label, so those names are minted, hidden, and read in the netlist pane when
they are wanted at all. A kind left with nothing to set opens no dialog: an
empty modal is worse than none, so a pin, a terminal and a fixed crossing are
offered only the transforms. New names are minted short — `b1`, `sw1`, `n1`, `e1`, `p1` — a key
being read in the wire list far more than anywhere else.

A block's key is its only name: the one drawn in the block, read in the
netlist, and prefixed to every transit id in a trace. That is why it is minted
short and why renaming one is a real change.

Transit names are not edited here. A drawing can still write one on a symbol's
leg and derivation honours it — a name on a turnout's straight leg is taken by
every derived transit that runs through it, and a transit crossing two named
legs is refused, naming both ([DRAWING.md](../store/DRAWING.md)). The dialog
does not offer it: a derived transit is named for the two block ends it joins,
and those names carry the context. Dropping the field is what leaves a fixed
crossing with nothing to set at all.

### Junctions

A junction is a connected group of non-block symbols declaring at least one
transit, which is exactly what derivation computes, so the editor computes it
too rather than asking. Wire a crossing to a turnout and they become one
junction.

**A junction is read in the netlist pane, not tinted on the canvas.** Its name
heads its section there, above the symbols it is drawn from, so a stray wire
that merges two throats shows as one section listing both. Every junction was
once tinted as a region on the sheet, which put shading behind half the
symbols in a drawing while nothing was wrong; the same merged throat is one
section where you expected two, read rather than seen.

What is still tinted is a junction in trouble: a name another connection also
wears, or two its own symbols disagree about, marked where it is rather than
only in a panel. It is the only tint left on the canvas, so colour there means
something is wrong. Names are minted, so a clash needs a hand-typed name and
is rare.

A region was never named. A junction drawn from one symbol is named after that
symbol, so a name written over the region sat beside the symbol and read as a
label the symbol carried — which is what the canvas reserves for a block.

**A connection's name is nobody's to type.** Names are minted, `j1`, `j2`, and
written into the drawing at once, so a junction always has a valid name and
nothing interrupts a sketch. Minting happens the moment `/review` says which
junctions exist, and folds into the snapshot of the edit that caused it, so one
action stays one undo step. There is no rename: a connection is not a thing
hardware answers to, so its name is bookkeeping the editor keeps for itself,
and the netlist pane is where it is read for debugging. A name already written
in a drawing is honoured — minting only fills the gaps — which is what keeps
Gotthard's `airolo` where it is.

Deleting a symbol can split a junction in two, and wiring two together merges
them. Either way names end up where derivation refuses them, and either way
the editor settles it when no typed name is involved. A split re-mints on both
sides; a merge collapses to the lowest minted name already on the junction, so
what the diff shows is the other names coming off. Where a merge leaves exactly
one typed name among minted ones, the typed name wins outright: it is the only
name anybody chose. Two typed names is the one case left, and it stays the
refusal it was — choosing which half is Airolo is not the editor's decision to
make. What tells the two apart is the shape of the name itself: `j` and digits
is one the editor made, and anything else is one a person typed.

A wire joining two blocks directly is a connection too
([DRAWING.md](../store/DRAWING.md#a-wire-between-two-blocks)). Its name is
minted the same way and settled the same way, and nothing is drawn for it.

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

`A3_B__CW_A` lit: out of Airolo's track 3, across the throat, into Claro west.
That throat is the one the opening counts 19 transits and 33 concurrent pairs
at; this drawing names its connection `butterfly`.

![a transit lit across the throat](images/butterfly-transit.svg)

Derivation refusing is shown the same way, at the edit that caused it.

## Files

A drawing is a file, `layouts/<name>.drawing.yaml`, so it persists and is
shared through git like everything else in the repo (#64). The header's New…
asks for a name up front and opens an empty canvas under it; nothing is
written until the first Save, so an abandoned start leaves no file. Save As…
writes the open drawing, unsaved edits included, under a new name at once, and
Save targets that name from then on; the file under the old name keeps its
last-saved state, which is how a test variant forks from a committed railroad.
Both refuse a name a drawing already has: overwriting one deliberately is
opening it and pressing Save. Deleting or renaming a file stays in git, where
it is reviewable.

## Validation

Findings are listed in one panel:

- pins with one connection, and unpaired portal labels: save allowed,
  derivation refused;
- connection names two people typed, and transits naming themselves from two
  symbol legs: save allowed, derivation refused;
- overlaps of wires with symbols or wires: warning only.

Two of those states are prevented at the gesture that would otherwise create
them, rather than only reported once created. A wire in flight does not outlive
the pin it started from (#74), and a portal is placed as a pair, so neither a
stranded bend nor a lone portal accumulates unnoticed. Prevention stops at
placement: deleting one portal of a pair still strands the other, and that is
left to the finding, being a deliberate act with a mark on the canvas
([ADR-0020](../adr/0020-a-portal-is-placed-as-a-pair.md)).

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

Dragging a symbol out of the palette is pointer events too, not the HTML drag
and drop API, which cannot do it: during a native drag the browser owns the
keyboard, so `r` and `f` never arrive and Escape is spoken for, and the drag
image is one static bitmap, so a ghost cannot turn. The palette and the canvas
are sibling shadow roots and see none of each other's pointer stream, so the
editor shell listens on the window and routes.

The pending placement — the kind and its orientation — lives on the editor
document beside the half-drawn wire, which is the same sort of thing: a gesture
that has said something about the document and not yet written it. Where the
pointer is stays with the canvas and dies with the gesture. That split is what
puts the centring, the footprint a turn transposes, and the refusal over an
occupied square in the tested layer rather than in a component.

Toolbar icons are inline SVG. Shoelace's `sl-icon` fetches from a CDN at
runtime unless a base path is registered, and the editor has to work on the
railroad's own network.

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
a plain TypeScript module with no DOM, and that is where most of the Vitest
tests are. It is the layer where a bug is invisible on screen and corrupt in the
file: a move that detaches a wire, an undo that half-restores. No browser
automation for now.

A component is not exempt. The model owns the document, a component owns the
DOM, and anything that is neither is a module in `model/` with a test, whichever
file calls it: a rule deciding what a gesture means, what a menu applies to,
which keystroke belongs to the canvas.

This section used to say that Lit components stay thin enough that there is
little in them to test, and that one grows a test when it grows logic. Five of
the six bugs fixed in `ddbefb2..feb1fae` were in `ui/src/ui/`: keys typed into a
dialog field reaching the canvas, a junction overlay reading as a symbol's own
label, a right-click menu drawn empty, no way to cut a wire at all, and a joiner
headed as a connection in the netlist pane. Four of the five were fixable in a
layer that had a seam or could be given one, which is where `keys.test.ts` and
`menu.test.ts` come from. The fifth, the junction overlay, is the only bug of
the six that landed without a regression test, and it is the one that lived
entirely in `tc-canvas.ts`.

Nothing in that component was reachable from a test: every pointer handler
began by converting pixels to grid squares through `getScreenCTM`, which
happy-dom does not implement. The pointer-gesture machine — press, drag, band,
pan, and the right-click rules — is now `model/gesture.ts` (#63). It takes the
editor per call and answers with an outcome the component maps onto rendering
and events; the component keeps the pixel conversion and the viewBox, and
`gesture.test.ts` drives the rules from grid points.

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
