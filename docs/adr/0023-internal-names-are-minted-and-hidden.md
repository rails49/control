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
its junctions `airolo` still loads and still derives; the name is not shown,
not editable, and not something a new drawing can acquire.

## What it deletes

Two findings stop existing.

A connection name clash, two junctions wearing one typed name or one junction
wearing two, cannot arise, because no gesture types a connection name. The
clash, the canvas tint that marked it and the sentence naming which half is
which all go. `settle`'s split-and-merge arbitration stays, since it is what
keeps minted names correct, and it now has no typed name to defer to.

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

The alternative was keeping symbol names typed and letting `addr` be optional:
name it if you know the switch id, address it if you know the accessory number.
That is two handles on one point that can disagree, with no rule saying which
one is right.
