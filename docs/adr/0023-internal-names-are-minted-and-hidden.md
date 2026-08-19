# Internal names are minted and hidden

A name is typed only where a person has to say it out loud. That is a block,
which the operator names, the bus carries and a scenario places trains in, and
a portal label, which is how a pair of mouths is known to be a pair. Every
other name (a turnout, a slip, a crossing, a pin, a terminal, a junction) is
minted by the editor, hidden from the canvas and the properties dialog, and
read only in the netlist pane.

The rule this replaces is in `ui/src/model/drawing.ts`: a name was typed "when
hardware answers to it, a block, or a symbol with a motor the bus will
address". The bus never addressed a turnout
([ADR-0017](0017-turnout-position-is-inferred-by-the-panel.md)), and now that
something does, it addresses `addr` and not the key
([ADR-0022](0022-a-symbol-carries-its-hardware-address.md)). Either way the
symbol's key was never the handle it was kept typed for. `NAMED` loses
`turnout`, `single_slip` and `double_slip`, and a turnout's properties dialog
holds its address and nothing else.

Connection names were already nobody's to type: minted `j1`, `j2` and written
at once, with no rename anywhere in the editor
([EDITOR.md](../ui/EDITOR.md#junctions)). This makes that the whole story
rather than a default a hand-written file can opt out of. A drawing that names
its junctions `airolo` still loads and still derives; **opening it replaces
every connection name it carries with a minted one**, so the name is not shown,
not editable, not something a new drawing can acquire, and not something an
open one still holds. The drawing format is unchanged: a `connection` key is
still written and still read.

## What it deletes

Two findings stop existing.

A connection name clash, two junctions wearing one typed name or one junction
wearing two, cannot arise. Two things make that true and neither is enough on
its own: no gesture types a connection name, and re-minting on load means no
open drawing holds one that was typed. Without the second, the clash is one
edit away from any hand-written railroad: delete the block between two named
junctions, wire the neighbours together, and derivation answers that `airolo`
and `claro_west` are one connection. The editor cannot settle that, because
choosing which half is Airolo is not its decision. The clash, the canvas tint
that marked it and the sentence naming which half is which all go. `settle`'s
split-and-merge arbitration stays, since it is what keeps minted names correct,
and every name it now chooses between is one it minted itself.

A symbol name clash stops being a finding and becomes a refusal. The properties
dialog is the only place a name is typed, so it validates before it closes and
says `'claro_2' is already taken` where the name was typed. Today the dialog
closes, discards the edit, and reports it in a panel across the screen. Blocks
are few and deliberately named, so this is a rare mistake now shown at the
moment it is made.

## What it costs

Gotthard's turnouts are named for RocRail's switch ids, deliberately, and the
drawing says so. Those names survive in the yaml and in the netlist pane, but
stop being visible on the canvas or editable in the dialog, and a turnout drawn
from now on gets `sw7` and means nothing by it. The tie to hardware is `addr`
instead, which is the tie that was wanted.

Its junctions stop being called `airolo`, `butterfly` and `claro_west` once the
drawing is opened and saved. That is the point rather than a side effect, and
the names remain in the file's comments and in the netlist pane's section
headers under their minted replacements. If reading them back matters more than
expected, the answer is a display name on a junction, not a return to typing
the key.

The alternative was keeping symbol names typed and letting `addr` be optional:
name it if you know the switch id, address it if you know the accessory number.
That is two handles on one point that can disagree, with no rule saying which
one is right.
