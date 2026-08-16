# Layout editor

Design for the visual layout editor, decided in #41. Second phase of the UI
work, after derivation ([DRAWING.md](../store/DRAWING.md)) and before the
[panel](PANEL.md). Terminology follows [CONTEXT.md](../../CONTEXT.md).

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

## Canvas

The canvas is a grid of squares. A symbol occupies one or more whole squares;
each square is free or occupied by exactly one symbol. Pins sit at the
centers of square sides. Symbols rotate in 90 degree steps and flip; diagonal
running comes from wires at angles, not from rotating symbols. The drawn
angle of crossings and slips is a property (15 or 30 degrees), set in the
properties dialog, so the palette carries one entry per symbol kind.

Zoom and pan are the SVG `viewBox`.

## Palette

The placeable symbols, with their semantics defined in
[DRAWING.md](../store/DRAWING.md#symbols):

| Symbol | | Notes |
| --- | --- | --- |
| Block | ![blocks](images/blocks.png) | shows occupancy on the panel |
| Terminal | ![terminal](images/terminal.png) | deliberate track end |
| Turnout | ![turnout](images/turnout.png) | |
| Crossing | ![crossing](images/crossing.png) | |
| Single slip | ![single slip](images/single-slip.png) | |
| Double slip | ![double slip](images/double-slip.png) | |
| Portal | ![portal](images/portal.png) | paired by label |

The generic connection symbol is not in the palette. The editor renders one
when a loaded drawing contains it (Gotthard's Claro east, until #35 settles
what its real geometry is), but a person never places one.

## Drawing wires

Clicking a pin starts a wire: a wireline follows the pointer, softly snapped
to multiples of 15 degrees, with a click on a pin overriding the snap.
Clicking empty canvas places a free-standing pin, a bend, and continues;
clicking a pin that can accept the wire ends it.

Wire geometry is decorative. Wires must not cross symbols or other wires, but
the rule is enforced by warning, never by rejecting the edit: an overlap is a
misleading picture, not a wrong layout, so the offending segments are
highlighted and listed, and derivation proceeds. Rejecting edits would mean
collision detection fighting every drag.

## Editing

Left click selects; drag moves; mouse rubber-band or shift-click selects
groups. Moves rubber-band the wires: an endpoint attached to a moved pin
stays attached and stretches, and a wire whose both owners move translates
rigidly, so a move can never change the derived layout. Rotate, flip, and
delete apply to the selection, from a right-click menu with key bindings.

The right-click properties dialog edits name, block length, sensor ids, and
transit-name overrides.

Undo and redo are snapshot-based: the drawing is a small document, so every
mutation pushes a copy. Copy and paste is not supported; it opens id and
portal-label questions that rare layout editing does not justify.

## Validation

The editor shows three findings, all listed in one panel:

- red pins (one connection) and unpaired portals: save allowed, derivation
  refused;
- overlaps of wires with symbols or wires: warning only.

Editing and running the same railroad are exclusive, because the store
snapshots at startup.

## Scenario editing

Placing trains is dragging onto blocks; train length is set in the same
properties dialog that sets block length, keeping the flat
`{length: n, at: block}` scenario shape. The composed loco-and-car roster of
[GOALS.md](../GOALS.md) is deferred; the `trains:` key is unchanged either
way.

## Implementation

TypeScript, pnpm, Lit and Shoelace. The drawing surface is SVG in the DOM:
hit-testing, hover and selection come from pointer events, live state is a
CSS class toggle. Gotthard is a few hundred elements, far below where SVG
struggles.

Diagram libraries (JointJS, GoJS, React Flow) were considered and rejected:
their value is auto-routing and free-form graph models, the first deliberately
absent here and the second replaced by seven fixed symbols, and each brings
its own document model to fight. Canvas engines pay off at thousands of
animated elements, not a few hundred static ones. What the editor needs, grid
snap, a wireline preview, class toggles, `viewBox` zoom, is smaller than any
library's learning curve.

Validation stays in the existing Python validator rather than being
reimplemented in TypeScript; the server that serves it comes with the panel
([PANEL.md](PANEL.md#implementation)).
