# The drawing carries its own geometry

A drawing is a picture someone arranged, so the arrangement is part of the
document. Symbols take optional `at`, `rot`, `flip` and `angle` keys alongside
`kind` and their properties, in the same file
([DRAWING.md](../store/DRAWING.md#geometry)). Derivation ignores them.
(Amended: `angle` was removed with the appearance mechanism when the symbol
geometry was fixed at one appearance per kind; see DRAWING.md#symbols.)

This does not weaken
[ADR-0015](0015-drawing-is-the-source-of-truth.md). The layout is still
derived and never authored, and `wires:` is still the whole of the topology.
What changes is that the drawing is richer by one more thing the layout cannot
hold, which is the same argument ADR-0015 makes about turnouts and labels.

The reason geometry has to be stored at all is that there is no auto-layout.
The [editor](../ui/EDITOR.md) rejects the diagram libraries whose value is
auto-routing, and a schematic that rearranges itself on load would be useless
for reading a railroad. Without stored placement, every open would have to
invent one.

Two alternatives were rejected.

**A sidecar geometry file** keyed by symbol name leaves the drawing schema
untouched, which was its whole attraction. It creates a second table that can
go stale against the first: a symbol deleted in one file and not the other, a
placement with no symbol, a symbol with no placement. Each needs a rule, and
none of those errors can exist when the placement lives on the symbol it
places.

**Deriving a layout on every open** was rejected on the same ground as the
diagram libraries. It also makes placement unownable: two people opening the
same railroad see different pictures, and there is nothing to review.

Geometry never determines topology. Two pins at the same position look joined
and are not, so the editor treats abutting as a gesture and writes a real wire
of zero length. That keeps moves safe: a symbol dragged away stretches its
wires rather than losing them, and no rearrangement can change a derived
layout.

What this costs is the file. Placement lands on every symbol line, so the first
editor save of a hand-written drawing rewrites all of them. `reversing-loops`
is 237 lines of which 107 are reasoning comments, and `yaml.safe_dump` would
delete every one. The store's `put` therefore merges into the existing document
with `ruamel.yaml` rather than dumping a fresh one, and a comment attached to a
symbol survives that symbol being placed. Comments inside `wires:` do not
survive, the list being replaced wholesale, so reasoning about wiring belongs
in the header.
