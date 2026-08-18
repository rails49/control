# Drawing format and derivation

The drawing document type and the derivation of layouts from it, decided in
#41 and implemented in `src/tc49/store/drawing.py`: the generic connection
symbol and the derivation passes in #42, the symbols of fixed geometry in #44.
Every railroad is drawn (#43), each converted mechanically from the layout it
was written as, then `crossover-yard` redrawn from real symbols on top of that
and Gotthard's Airolo and Claro west in #46.
The store serves drawings alone (#45): a layout is derived on `get` and is not
a file, which is what [LAYOUT.md](LAYOUT.md) describes. Order of work:
derivation (Python, no UI), then the
[editor](../ui/EDITOR.md), then the [panel](../ui/PANEL.md). Terminology
follows [CONTEXT.md](../../CONTEXT.md).

## What a drawing is

A drawing is a schematic, like a prototype signal box display: it shows
connectivity, not scale. Symbols are placed on a grid and joined by wires
through their pins. Wire shape carries no meaning; derivation reads only which
pin connects to which, so moving symbols or rerouting wires never changes the
derived layout.

The drawing is the source of truth
([ADR-0015](../adr/0015-drawing-is-the-source-of-truth.md)). The layout is
derived from it on `get` and is never authored. The drawing is strictly
richer: turnout geometry, signals, labels, hardware ids and the placement of
everything on the canvas
([ADR-0018](../adr/0018-the-drawing-carries-its-own-geometry.md)) live only
there and cannot be recovered from a layout.

## Pins and wires

A wire joins two pins. A symbol pin accepts exactly one wire, the symbol
being its other connection; a free-standing pin joins exactly two wire
segments and serves as a bend point. Either way every pin has two
connections.

A pin with one connection is an error, rendered red in the editor. A drawing
with red pins can be saved, so work in progress can be parked, but derivation
refuses it: a `get` never returns a layout from an incomplete drawing. A
deliberate track end takes an explicit terminal symbol, which turns the most
likely drawing mistake, a wire left unattached, into a visible error instead
of a silently terminal block. In the derived layout terminal blocks remain
derived from connectivity, exactly as today.

### A wire between two blocks

Every movement between blocks is a named transit inside a named connection, so
two blocks joined by plain track still need a connection to hold that transit.
A bare wire cannot be one: it declares no transit and has no name.

Such a wire therefore carries the name itself, written as a mapping instead of
a pair:

```yaml
wires:
  - {pins: [west.B, east.A], connection: gap}
```

Derivation emits a connection of that name with one transit spanning the two
ends. Only a wire whose way reaches from one block end to another without
passing through a connection symbol may take the key; anywhere else it is
refused. Where the joint is routed through bend pins the name goes on any one
segment of the chain, and two different names on one chain are refused, the
same rule transit-name overrides follow.

The editor mints these names and never shows them, so a person draws a wire
between two blocks and is asked nothing.

## Symbols

A symbol declares pins, transits between them, and which transit pairs are
`concurrent`. That is the same shape as a connection, one level down, and it
is why derivation is composition: connection transits are built from symbol
transits.

| Symbol | Kind | Pins | Transits | Concurrent | Notes |
| --- | --- | --- | --- | --- | --- |
| Block | `block` | 2 (`A`, `B`) | the block itself | n/a | length, optional display label, optional sensor id per end |
| Terminal | `terminal` | 1 (`P`) | none | n/a | marks a deliberate track end |
| Turnout | `turnout` | 3 (`toe`, `straight`, `diverging`) | `straight`, `diverging` | none | |
| Crossing | `crossing` | 4 (`a1`, `a2`, `b1`, `b2`) | `a`, `b` | none | a grade crossing: one train at a time |
| Single slip | `single_slip` | 4 | `a`, `b`, `slip` | none | |
| Double slip | `double_slip` | 4 | `a`, `b`, `slip_1`, `slip_2` | none | topologically two turnouts joined toe to toe |
| 90° crossing | `crossing_90` | 4 (`a1`, `a2`, `b1`, `b2`) | `a`, `b` | none | drawn upright |
| 90° crossing, diagonal | `crossing_90d` | 4 (`a1`, `a2`, `b1`, `b2`) | `a`, `b` | none | drawn at 45 degrees |
| Portal | `portal` | 1 (`P`) | none | n/a | paired by label; the pair is a wire |
| Connection (generic) | `connection` | N | declared | declared | format only, not in the editor palette |

A crossing and the slips share four pins, two per route, named for the route
and the side: `a1` and `b1` on one side, `a2` and `b2` on the other. The two
through routes are `a` (`a1`-`a2`) and `b` (`b1`-`b2`); a slip route joins one
side to the other over the other track, `a1`-`b2` for the single slip and both
`a1`-`b2` and `b1`-`a2` for the double slip. That is the same thing as the
double slip being two turnouts joined toe to toe. The 90 degree crossings use
the same four pin names and the two through routes, and offer no slips.

A block carries a signal and a sensor at each end, always. Neither is placed
and neither is optional, so neither is a field: they are part of what a block
symbol is, and the block artwork draws them. What the drawing may record is a
sensor's hardware id, which is a property of a sensor that already exists.
(A signal at an end that leads only to a terminal governs a departure no train
can make, and is worth hiding once the rest is settled.)

Everything about these symbols is fixed, so a drawing writes only `kind` and
the names it wants (below). In particular none of them declares anything
concurrent, and none can: every route through a crossing or a slip takes the
shared frog, and a turnout's two routes share its toe.

The exclusive crossing is what makes composition come out right. An earlier
draft declared the crossing's two routes concurrent; re-deriving
`crossover-yard` shows that is wrong. Its scissors crossover is drawn as four
turnouts and, where the two diagonals meet, a `crossing_90d`: the two crossover
transits share the crossing, so composition yields exactly the one concurrent
pair the layout declared by hand, `[up_straight, dn_straight]`, while a
concurrent crossing would also emit the colliding crossover pair.

Each kind has exactly one drawn appearance, specified in
[ui/EDITOR.md](../ui/EDITOR.md#symbol-geometry); diagonal legs are always 45
degrees, and a wire meeting a pin at another angle bends there. The two 90
degree crossings are separate kinds rather than appearances of one because
their footprints and pin positions differ. An earlier draft had an `angle`
placement property picking between several appearances of a crossing; no
committed drawing ever used it and it is removed.

### The generic connection symbol

An N-pin symbol that declares its transits and concurrency verbatim.
Derivation passes it through unchanged, so every existing layout converts to
a drawing mechanically and losslessly, and a junction whose real geometry is
not yet drawn can be modelled anyway, then refined one junction at a time. A
junction drawn this way shows no turnout detail on the panel.

Migration is over and the kind has no users left, so it is legacy. It loads,
it derives, and the [editor](../ui/EDITOR.md) gives it no support at all: it
is neither placed nor drawn, having no fixed pin set to place. `facing-pair`'s
one use was a plain joint, which is now a named wire (#48);
`single-track-meet`'s four were turnouts, redrawn as such (#56); and Gotthard's
Claro east, the last, was drawn from turnouts in #58, which is where the
declared transits and the netlist's tiles were finally compared — and the
tiles won. Whether the kind leaves the format is a decision in its own right.

### Portals

A portal joins distant parts of a drawing without a wire across the whole
canvas (return loops, hidden staging). Two portals with the same label are
one joint; derivation treats the joined wires as directly connected and emits
nothing for the portal itself. A label must appear on exactly two portals,
each with its pin wired; anything else is an error, save allowed, derive
refused.

## Drawing schema

Drawings are YAML, at `layouts/<name>.drawing.yaml`. The whole of
`facing-pair`:

```yaml
drawing: facing-pair
units: mm

symbols:
  west: { kind: block, length: 1000 }
  east: { kind: block, length: 1000 }
  west_stop: { kind: terminal }
  east_stop: { kind: terminal }

wires:
  - [west.A, west_stop.P]
  - { pins: [west.B, east.A], connection: gap }
  - [east.B, east_stop.P]
```

A junction of fixed geometry, `crossover-yard`'s scissors crossover:

```yaml
symbols:
  up_w_points:
    kind: turnout
    connection: crossover
    names: { straight: up_straight, diverging: up_to_dn }
  up_e_points: { kind: turnout, connection: crossover }
  diamond: { kind: crossing_90d, connection: crossover }
```

- **Symbols are a mapping from name to `kind` and its properties.** A block
  takes a `length`, an optional display `label` and optional `sensors` per end;
  a portal a `label`; a terminal and a free-standing pin (`kind: pin`) nothing.
  A symbol of fixed geometry takes only the names below. The generic connection
  symbol declares its `pins`, its `transits`, and optionally which pairs of
  them are `concurrent`. Every kind also takes the placement keys of
  [Geometry](#geometry).
- **A block's key is its id, its `label` is for people.** The id is short and
  stable because it prefixes every transit id on the bus and in traces; the
  label is the platform's real name, `Zürich HB Gleis 1`, and changing it
  touches nothing downstream. The editor shows the label where there is one and
  the id otherwise.
- **Pins are written `<symbol>.<pin>`.** A block's are its ends `A` and `B`;
  a one-pin symbol's is `P`; the symbol table above gives the rest, and a
  generic connection symbol names its own.
- **A wire is a pair of pins**, and `wires:` is the whole of the topology. A
  wire joining two blocks directly is written as a mapping instead, carrying
  the `connection` name for the transit it becomes. Where the wire runs on the
  canvas is the editor's business, not the file's.
- **`connection` names the junction a symbol belongs to.** Every symbol of one
  junction that writes it must agree; a junction drawn from several symbols has
  no other way to be named.
- **`names` gives a symbol's transits the names the derived transits take.**
  It is keyed by the symbol transit, `{ straight: up_straight }`, so the name
  goes where the way through goes. The generic connection symbol writes the
  same thing by writing its `transits` as a mapping, the key being the derived
  name; written instead as a list of pin pairs, each takes the derived default.
  `concurrent` needs the mapping form, having nothing else to name.

The schema is checked when the document loads, so a drawing that loads is
well-formed. The pin rules are checked at derivation instead, which is what
lets an incomplete drawing be saved.

### Geometry

Where a symbol sits is part of the document
([ADR-0018](../adr/0018-the-drawing-carries-its-own-geometry.md)), written on
the symbol beside its properties. Every key is optional and derivation reads
none of them.

| Key | Applies to | Meaning |
| --- | --- | --- |
| `at` | every kind | the grid cell of the symbol's top-left square |
| `rot` | symbols with more than one pin | 0, 90, 180 or 270 |
| `flip` | symbols with more than one pin | mirrored or not |

A placed block reads `west: { kind: block, length: 1000, at: [2, 4] }`.

The canvas is a grid of squares. A symbol occupies whole squares and pins sit
at the centres of square sides, which is why rotation is a multiple of 90
degrees. A free-standing pin sits at a face centre like any other pin, and
being on a boundary rather than in a square it occupies none. It is placed by
the same two keys as everything else: `at` names a cell and `rot` turns its one
pin onto that cell's west, north, east or south face. A face belongs to two
cells, so the editor always writes the cell east or south of it and one face
has one spelling.

Wires carry no geometry. A wire is drawn straight between its two pins, and a
bend is a free-standing pin, which is a symbol with a placement of its own.

A drawing without placement still loads and still derives. It has no picture,
so the editor cannot show it until someone places it, there being no
auto-layout.

## Hardware ids

The drawing holds hardware identities as optional symbol properties: sensor
ids on block ends, decoder addresses on turnouts later. Derivation drops
them, so the layout and the contracts in [SYSTEM.md](../SYSTEM.md) are
unchanged, and SYSTEM.md's position that the transit-to-turnout table is
private hardware configuration stands. A physical layout interface reads the
drawing to build its maps, the same way the panel reads it to infer turnout
positions ([ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md)).
A drawing with no hardware ids is valid; the simulator needs none.

## Derivation

Three passes over a small graph, run once per `get` against a snapshot that
is immutable for the run:

1. Connected components of non-block symbols give the connections.
2. Walking symbol transits between a component's boundary pins gives the
   connection transits.
3. Composing symbol concurrency pairwise over those transits gives
   `concurrent`.

Cost is negligible: Gotthard's largest component is Airolo, a few hundred
traversal steps and 171 pairwise checks. The derived layout is run through
the existing validator as a safety net against derivation bugs.

Pass 2 already computes the way each transit takes, as the symbols and local
transits it crosses, and pass 3 already decides exclusivity by comparing two
such ways. Both are discarded once the layout is built. `explain()` returns
them instead: for each transit its way, and for each pair the symbol they
share. That is what lets the [editor](../ui/EDITOR.md) say not only that two
transits exclude each other but which frog makes them.

### Names and determinism

Transit names default to a function of the two block ends and can be
overridden, with the override stored in the drawing. Derived names must be a
pure function of topology, never of drawing order or symbol ids, and the
derived layout needs canonical key order. Otherwise moving a symbol renames a
transit, changes the trace bytes, and churns every golden file for no
semantic reason.

The default transit name is the two block ends, sorted and with the dot
replaced: `west.B` and `east.A` give `east_A__west_B`. Sorting is what makes
it a function of the pair rather than of the direction the walk happened to
take. Two transits at one connection deriving the same name is refused, since
a layout keys transits by name; naming one of them in the drawing settles it.
An end pair also has to be two *distinct* ends, so a way that leaves a block
end and arrives back through it is refused as well.

A transit name is overridden on the symbol transit the way through takes, so
one symbol names every way that crosses it. `crossover-yard`'s four crossover
transits are named on the two west turnouts, since every way through the
crossover takes the straight or the diverging side of one of them. Overriding
the same way twice with different names is refused rather than resolved by
order.

A connection's name is authored rather than derived: it is what the symbols of
its component write as `connection`, and where they write nothing, the name of
the one symbol that declares transits — a junction that is one turnout, or one
generic connection symbol, names itself. Both are things someone wrote in the
drawing rather than artefacts of drawing order, so neither breaks the rule
above, but renaming the symbol of a one-symbol junction does rename its
connection. A junction drawn from several symbols that writes no `connection`
is refused, as is one written with two different names, or two junctions
written with the same one.

Because it is authored, a connection name has to come from somewhere when
nobody has typed one. The editor mints `j1`, `j2` and so on as junctions form
and writes them into the drawing, so they are authored by the time derivation
sees them and stable thereafter, even though the number came from drawing
order. Nobody types one: a connection is not a thing hardware answers to, so
the editor offers no way to name one and keeps them settled itself
([EDITOR.md](../ui/EDITOR.md#junctions)) — a split re-mints, a merge collapses
to the lowest minted name the junction already wore, and a typed name among
minted ones survives them. Names already in the committed drawings are kept as
they are, minting only filling the gaps, so `airolo` still heads its connection
in `tc49 layout show` and prefixes every transit id in a trace.

Derivation itself settles nothing. Two names on one junction is refused there
as it always was, the layout being a pure function of the document
([ADR-0015](../adr/0015-drawing-is-the-source-of-truth.md)); the editor is
where a drawing is repaired, and hand-edited YAML gets the refusal.

## Asset store

The store keeps two document types, `drawing` and `scenario`; `get()` derives
the Layout on read. This keeps
[ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)'s two
coarse document types intact and leaves no second copy of the topology to
fall out of date. Drawings live at `layouts/<name>.drawing.yaml` and are the
only committed topology; `put` takes a drawing or a scenario and refuses a
layout, there being nowhere to store one.

What is given up is the readable topology diff in review: one moved wire can
flip concurrency across many transit pairs while the drawing diff shows one
changed line. A `tc49 layout show <name>` command covers that on demand.

The editor needs the document `get` throws away, so the store also reads a
drawing back unchanged. `get` is left alone: every other caller wants the
layout.

`put` merges rather than dumps. Comments are most of what a hand-written
drawing says: 107 of Gotthard's 237 lines, including the Rocrail id mapping
and which lengths are assumed. Writing placement onto every symbol with
`yaml.safe_dump` would delete all of it, so `put` applies the incoming
document into the existing one key by key, in `store/yamlfile.py`. Reading a
drawing and saving it back unchanged returns the file byte for byte; a symbol
that moves keeps the comment written against it, and a symbol that is deleted
takes that comment with it.

Three things do not survive. A comment inside `wires:` goes, the list having
no keys to merge by and being replaced whole, so reasoning about wiring
belongs in the header. A sequence wrapped by hand across several lines comes
back on one. And the order of `symbols:` is the file's, not the editor's: a
symbol keeps the place it was written in and a new one is added at the end,
which keeps a moved symbol out of the diff at the cost of ignoring a reorder.
None of the three can change a derived layout.

## Converting a layout into a drawing

Migration was compulsory, since a railroad that has not been drawn cannot be
loaded, and the generic connection symbol made it mechanical. `to_drawing` in
`src/tc49/store/convert.py` reads a layout document and writes the drawing that
derives it:

- each block becomes a block symbol with its length;
- each connection becomes one generic connection symbol of the same name,
  carrying its transits, their hand-picked names and its `concurrent` verbatim;
- a block end is a pin on that symbol, named for the end it holds — `up_w.B`
  wires to `crossover.up_w_B` — so the wire list is one line per block end;
- a block end no connection holds gets a terminal symbol, which keeps the
  derived terminal blocks the same.

Conversion is lossless by construction, which is what let the four railroads
migrate with no topology re-typed; their reasoning comments moved into the
drawings by hand, so no rationale was lost either. The round trip is still
asserted, now without a hand-written file in it: converting a derived layout
and deriving the result gives the same layout back, for every committed
railroad. What conversion cannot supply is geometry — a junction arrives as one
opaque symbol, and refining it into turnouts and crossings is a separate,
reviewable step, done for `crossover-yard` in #44, for Gotthard's Airolo and
Claro west in #46, and for Claro east in #58. Refining is also where a drawing
can start disagreeing with what was declared, which is what had stopped Claro
east: drawing it moved three of its five transits and split it into the two
throats its two lines actually make.
