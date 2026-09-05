# Drawing format and derivation

The drawing document type and the derivation of layouts from it, decided in
#41 and implemented in `src/tc49/store/drawing.py`: the generic connection
symbol and the derivation passes in #42, the symbols of fixed geometry in #44.
Every railroad is drawn (#43), each converted mechanically from the layout it
was written as, then `crossover-yard` redrawn from real symbols on top of that
and `reversing-loops`'s station-A and station-C west in #46.
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
| Block | `block` | 2 (`A`, `B`) | the block itself | n/a | length; a signal address per signalled end, a sensor name per end named otherwise |
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

A block carries a signal and a sensor at each end, always. Neither is placed,
so neither is drawn by the drawing: they are part of what a block symbol is,
and the block artwork draws them.
(A signal at an end that leads only to a terminal governs a departure no train
can make, and is worth hiding once the rest is settled.)

What *is* a field is the address of the signal installed at an end, under
`signals` ([Hardware ids](#hardware-ids)): a signal is fixed wiring like a
turnout motor, so its address is typed on the drawing, and an end with no
address on it is an end no signal stands at. Beside it, under `sensors`, is
the name the hardware watching an end knows its sensor by — an end saying
nothing is watched under `<block>.<end>`, which is what most ends want
([Hardware ids](#hardware-ids)).

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

Migration is over and the kind has no users left, so it is legacy. It loads, it
derives, and the [editor](../ui/EDITOR.md) gives it no support at all: it is
neither placed nor drawn, having no fixed pin set to place. `facing-pair`'s one
use was a plain joint, which is now a named wire (#48); `single-track-meet`'s
four were turnouts, redrawn as such (#56); and `reversing-loops`'s station-C
east, the last, was drawn from turnouts in #58, which is where the declared
transits and the netlist's tiles were finally compared — and the tiles won.
Whether the kind leaves the format is a decision in its own right.

### Portals

A portal joins distant parts of a drawing without a wire across the whole
canvas (return loops, hidden staging). Two portals with the same label join
their wires as if directly connected, and derivation emits nothing for the
portal itself. A label must appear on exactly two portals, each with its pin
wired; anything else is an error, save allowed, derive refused. A review
reports every such label with the portals wearing it, the way it reports red
pins, so an editor learns about all of them at once instead of one per fix.

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
  takes a `length` and optional `signals` and `sensors`, each keyed by its
  ends; a portal a
  `label`; a turnout
  or a slip an optional `addr` ([Hardware ids](#hardware-ids)); a terminal and a
  free-standing pin (`kind: pin`) nothing.
  A symbol of fixed geometry takes only the names below. The generic connection
  symbol declares its `pins`, its `transits`, and optionally which pairs of
  them are `concurrent`. Every kind also takes the placement keys of
  [Geometry](#geometry).
- **A block's key is its only name.** It is short and stable because it
  prefixes every transit id on the bus and in traces, and it is what the editor
  draws in the block. A block carried a display `label` for the platform's real
  name, `Zürich HB Gleis 1`, and nothing ever set one: the key was the name
  being read, so the second name was dropped (#82). `label` now belongs to a
  portal alone, where it pairs two mouths.
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

The drawing holds the identities of the fixed wiring, as optional symbol
properties: `addr` on a turnout or a slip, and `signals` and `sensors` on a
block, keyed by the end each signal stands at and the end each sensor
watches.

```yaml
b_station_a: { kind: block, at: [12, 4], length: 900, signals: { A: '40', B: '41' } }
```

A **signal** is installed at one end of one block, so the drawing is where its
address is typed, the way a turnout motor's is
([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md),
[#203](https://github.com/rails49/control/issues/203)) — it is not named in
software the way a camera watching a block end is. The key is the end, `A` or
`B`, the ends a block has everywhere else; a key that is no end of that block
is refused at load, naming the block. A block may signal one end, both, or
neither, and an unsignalled end is absent rather than empty: an end nothing
ever leaves carries no signal, one that could only show `stop` being furniture
([CONTEXT.md](../../CONTEXT.md#layout), **Signal**). The value is any non-empty
string and names no system, as a point's address does not
([ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)).

Derivation carries the signals into the layout document beside the block's
length, so the layout answers which signal stands at a block end without
reopening the drawing ([LAYOUT.md](LAYOUT.md#the-derived-layout)). Two ends may
share an address, as two points may: two signals on one address show one aspect
together. What is done with an aspect — publishing one, and what the
signal makes of it — reaches no contract here (#203).

Derivation keeps the point addresses too, as the `points`
each transit needs
([ADR-0031](../adr/0031-the-layout-carries-the-points-a-transit-needs.md)) —
still no turnouts in the layout, but their addresses
([LAYOUT.md](LAYOUT.md#the-derived-layout)). The dispatcher publishes them on
each `align` ([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md)),
so an adapter throws what it is told and holds no table of its own. A point
wearing no address is left out rather than stopping derivation: the drawing is
where an unaddressed point is reported. A drawing with no hardware ids is
valid; the simulator needs none.

A sensor, unlike the signal beside it, is not addressed by what the drawing
says about it. It is addressed by the block end it watches, `<block>.<end>`, on
every railroad
([ADR-0043](../adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)),
so a trace is comparable between installations and nothing above the layout
interface learns detector geometry.

What the drawing carries instead is the name *the hardware* knows that sensor
by, under `sensors`, keyed by the end as `signals` is:

```yaml
  yard_w: {kind: block, length: 1400, sensors: {B: jmri/LS3}}
```

A system that names its own sensors, and whose protocol requires the system's
name, cannot be told what to call itself the way a camera can, so the drawing
is where the two names meet
([ADR-0063](../adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)).
**An end that says nothing is watched under `<block>.<end>`** — the same string
the topic uses, so the ordinary railroad writes nothing and the two cannot
drift. A key that is no end of the block is refused at load, naming the block.
The address is a plain string and nothing checks it, exactly as a point's is
not checked; what the hardware answers to is knowledge the drawing cannot hold.

It reaches no layout: this is a hardware address, and the derived document
carries none of them but the ones a transit needs
([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md)). Whoever
publishes `device/sensor` reads it from the drawing
([DEVICES.md](../layout/DEVICES.md)), which is why a translator that publishes
sensors has a railroad to be told about.

**A point's address names no system**, the rule its signal wears above and
[ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)'s:
it is the string the hardware answers to, `5` as readily as anything else, and
whatever is wired subscribes the desired rows and acts on the addresses it
recognises. Two systems that number a point alike both act, and that is the
deployer's addressing to fix.

`addr` is a plain string and nothing checks it, for shape or for anything
else. What a point answers to is knowledge the drawing cannot hold, and which
systems are running is knowledge nothing here has either: an address nobody
answers to does no harm (ADR-0059). The one check the editor makes is that a
motorised symbol has *some* address, since a drawing without them
derives but cannot be driven ([EDITOR.md](../ui/EDITOR.md#validation)).

**Points may share an address, and then they move together.** One accessory
output throws a crossover's two ends as a unit, so a throat can have fewer
usable ways than its geometry suggests — `reversing-loops` gangs `sw1` with
`sw2` and `sw6` through `sw9`, all of them on `dccex`. Sharing is meaningful
rather than a mistake, so nothing asks addresses to be unique. Two things do
follow from it, and the review reports both as `motor_faults`:

- A way needing two points on one address set differently cannot be thrown.
- Two ways declared `concurrent` promise that two trains may hold the
  connection at once, which the hardware cannot honour if they want a shared
  address in opposite positions.

Neither is visible under the simulator, which has no addresses
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)), and
neither stops derivation: addresses are dropped from the layout, so a drawing
with a motor fault reads fine and cannot be driven.

Every motorised kind has one motor and two positions, `closed` and `thrown`,
the pair a DCC accessory decoder answers to. No kind's legs are named for
them, so the library declares which leg wants which position:

| Kind | `closed` | `thrown` |
| --- | --- | --- |
| `turnout` | `straight` | `diverging` |
| `single_slip` | `a`, `b` | `slip` |
| `double_slip` | `a`, `b` | `slip_1`, `slip_2` |

A fixed crossing has no motor and takes no `addr`. Nothing in the concurrency
model changes: the library declares nothing concurrent through a crossing or a
slip, because every route through one takes the shared frog, so two ways never
run through a slip at once whatever its motor is doing.

## Derivation

Three passes over a small graph, run once per `get` against a snapshot that
is immutable for the run:

1. Connected components of non-block symbols give the connections.
2. Walking symbol transits between a component's boundary pins gives the
   connection transits.
3. Composing symbol concurrency pairwise over those transits gives
   `concurrent`.

Cost is negligible: `reversing-loops`'s largest component is station-A, a few
hundred traversal steps and 171 pairwise checks. The derived layout is run
through the existing validator as a safety net against derivation bugs.

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

Both are statements about a way rather than about any one symbol, so both
refusals carry the walks behind them — the two that share a name, or the one
that loops — and a review hands them to the editor beside the sentence, in the
shape `explain()` gives a transit's way. That is what lets the drawing show
the fault where it is
([ADR-0024](../adr/0024-the-drawing-shows-its-own-faults.md)). Every other
refusal carries no way, and the review reports none.

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
they are, minting only filling the gaps, so `station_a` still heads its
connection in `tc49 layout show` and prefixes every transit id in a trace.

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

`put` merges rather than dumps. Comments are most of what a drawing says about
itself: 90 of `reversing-loops`'s 235 lines, including the junction-by-junction
account of the railroad and which decoder addresses are ganged. Writing
placement onto every symbol with `yaml.safe_dump` would delete all of it, so
`put` applies the incoming document into the existing one key by key, in
`store/yamlfile.py`. Reading a drawing and saving it back unchanged returns the
file byte for byte; a symbol that moves keeps the comment written against it,
and a symbol that is deleted takes that comment with it.

Three things do not survive. A comment inside `wires:` goes, the list having
no keys to merge by and being replaced whole, so reasoning about wiring
belongs in the header. A sequence wrapped by hand across several lines comes
back on one. And the order of `symbols:` is the file's, not the editor's: a
symbol keeps the place it was written in and a new one is added at the end,
which keeps a moved symbol out of the diff at the cost of ignoring a reorder.
None of the three can change a derived layout.

## How the layouts were converted into drawings

Migration was compulsory, since a railroad that has not been drawn cannot be
loaded, and the generic connection symbol made it mechanical. A `to_drawing`
tool read a layout document and wrote the drawing that derives it:

- each block became a block symbol with its length;
- each connection became one generic connection symbol of the same name,
  carrying its transits, their hand-picked names and its `concurrent` verbatim;
- a block end was a pin on that symbol, named for the end it held — `up_w.B`
  wiring to `crossover.up_w_B` — so the wire list was one line per block end;
- a block end no connection held got a terminal symbol, which kept the derived
  terminal blocks the same.

The conversion was lossless by construction, which is what let the four
railroads migrate with no topology re-typed; their reasoning comments moved
into the drawings by hand, so no rationale was lost either. What it could not
supply is geometry — a junction arrived as one opaque symbol, and refining it
into turnouts and crossings was a separate, reviewable step, done for
`crossover-yard` in #44, for `reversing-loops`'s station-A and station-C west
in #46, and for station-C east in #58. Refining is also where a drawing can
start disagreeing with what was declared, which is what had stopped station-C
east: drawing it moved three of its five transits and split it into the two
throats its two lines actually make.

The tool did its job and has been removed (#121). It had had no caller since
#45, and no human will hand-author a layout, so the one use that could have
kept it alive — importing a layout from somewhere else — is not coming; what
remained was a round-trip test charging every layout schema change for a
function nothing called.
