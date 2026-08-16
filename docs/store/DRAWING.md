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
richer: turnout geometry, signals, labels, and hardware ids live only there
and cannot be recovered from a layout.

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

## Symbols

A symbol declares pins, transits between them, and which transit pairs are
`concurrent`. That is the same shape as a connection, one level down, and it
is why derivation is composition: connection transits are built from symbol
transits.

| Symbol | Kind | Pins | Transits | Concurrent | Notes |
| --- | --- | --- | --- | --- | --- |
| Block | `block` | 2 (`A`, `B`) | the block itself | n/a | length and optional sensor id per end as properties |
| Terminal | `terminal` | 1 (`P`) | none | n/a | marks a deliberate track end |
| Turnout | `turnout` | 3 (`toe`, `straight`, `diverging`) | `straight`, `diverging` | none | |
| Crossing | `crossing` | 4 (`a1`, `a2`, `b1`, `b2`) | `a`, `b` | none | a grade crossing: one train at a time |
| Single slip | `single_slip` | 4 | `a`, `b`, `slip` | none | |
| Double slip | `double_slip` | 4 | `a`, `b`, `slip_1`, `slip_2` | none | topologically two turnouts joined toe to toe |
| Portal | `portal` | 1 (`P`) | none | n/a | paired by label; the pair is a wire |
| Connection (generic) | `connection` | N | declared | declared | format only, not in the editor palette |

A crossing and the slips share four pins, two per route, named for the route
and the side: `a1` and `b1` on one side, `a2` and `b2` on the other. The two
through routes are `a` (`a1`-`a2`) and `b` (`b1`-`b2`); a slip route joins one
side to the other over the other track, `a1`-`b2` for the single slip and both
`a1`-`b2` and `b1`-`a2` for the double slip. That is the same thing as the
double slip being two turnouts joined toe to toe.

Everything about these symbols is fixed, so a drawing writes only `kind` and
the names it wants (below). In particular none of them declares anything
concurrent, and none can: every route through a crossing or a slip takes the
shared frog, and a turnout's two routes share its toe.

The exclusive crossing is what makes composition come out right. An earlier
draft declared the crossing's two routes concurrent; re-deriving
`crossover-yard` shows that is wrong. Its scissors crossover is drawn as four
turnouts and a crossing on the diagonals: the two crossover transits share the
crossing, so composition yields exactly the one concurrent pair the layout
declared by hand, `[up_straight, dn_straight]`, while a concurrent crossing
would also emit the colliding crossover pair.

The drawn angle of a crossing or slip (15 or 30 degrees) is a decorative
property, not a distinct symbol: flip and rotation cover sign and
orientation, and changing the angle cannot change the derived layout.

### The generic connection symbol

An N-pin symbol that declares its transits and concurrency verbatim.
Derivation passes it through unchanged, so every existing layout converts to
a drawing mechanically and losslessly, and a junction whose real geometry is
not yet drawn can be modelled anyway, then refined one junction at a time.
Gotthard's Claro east is the standing example, and the last one: the netlist
and the hand-written layout disagree about its geometry, so it keeps the
opaque symbol until #35 settles which is right. The symbol appears only in
machine-written drawings: it is not offered in the editor palette, though the
editor renders it when a loaded drawing contains one. A junction drawn this
way shows no turnout detail on the panel.

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
  gap:
    kind: connection
    pins: [A, B]
    transits:
      span: [A, B]
  west_stop: { kind: terminal }
  east_stop: { kind: terminal }

wires:
  - [west.A, west_stop.P]
  - [west.B, gap.A]
  - [gap.B, east.A]
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
  diamond: { kind: crossing, connection: crossover }
```

- **Symbols are a mapping from name to `kind` and its properties.** A block
  takes a `length` and optional `sensors` per end, a portal a `label`, a
  terminal and a free-standing pin (`kind: pin`) nothing. A symbol of fixed
  geometry takes only the names below. The generic connection symbol declares
  its `pins`, its `transits`, and optionally which pairs of them are
  `concurrent`.
- **Pins are written `<symbol>.<pin>`.** A block's are its ends `A` and `B`;
  a one-pin symbol's is `P`; the symbol table above gives the rest, and a
  generic connection symbol names its own.
- **A wire is a pair of pins**, and `wires:` is the whole of the topology.
  Where the wire runs on the canvas is the editor's business, not the file's.
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
reviewable step, done for `crossover-yard` in #44 and for Gotthard's Airolo
and Claro west in #46. Refining is also where a drawing can start disagreeing
with what was declared, which is what stopped Claro east.
