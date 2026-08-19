# The drawing shows its own faults

What is wrong with a drawing is marked on the drawing, at the thing that is
wrong, rather than listed in prose beside it. A text list is how a computer
says what it found; a person drawing a railroad finds it by looking. The
findings panel goes, and with it the permanent right column
[EDITOR.md](../ui/EDITOR.md#the-band) accounted for at 22rem against a 12rem
palette.

Half of it was already redundant. A red pin is called that because the canvas
draws it red, and the panel restated the count. A junction wearing a clashing
name was tinted where it stood and described again in a sentence. The panel's
only unique content was overlaps, which nothing marked, and the sentence a
refusal came back with.

## Every finding and its mark

| Fault | Mark | Derives? |
| --- | --- | --- |
| A pin short of a wire | the pin, red (as today) | no |
| A portal label worn by other than two | the label, red ground | no |
| Derivation refused | the offending way, lit red along its path | no |
| A motorised symbol with no `addr` | the symbol, quiet mark | yes |
| Symbols sharing a square | the shared squares, quiet mark | yes |

Two weights, not one. Red is what stops derivation. A second, quieter mark is
what derives but is unfinished: an overlap is cosmetic, and a drawing with no
addresses is a valid layout nobody can drive yet. Without the split an
unaddressed turnout on a busy layout looks as urgent as a broken one, and the
canvas's rule that colour there means something is wrong stops discriminating.

The band says which, coarsely. One indicator: this drawing derives, or it does
not. It names no fault and counts nothing, since the canvas is where you find
out where. Overlaps and missing addresses leave it clean. It sits beside what
the band already says, which is what is wrong that is not the author's doing.

## A refusal is a way, not a sentence

`/review` reports the first `ValueError` derivation raises, of twelve. Under
[ADR-0023](0023-internal-names-are-minted-and-hidden.md) five become
impossible, all of them typed-connection-name faults. Three restate a mark the
canvas already carries: a lone portal label, and the two spellings of a pin
holding the wrong number of wires. Two are reachable only from hand-written
yaml, being a transit named from several `names:` overrides, and two blocks
joined through no connection symbol, which the editor mints a joint name for.

Two are left, and both say something about a way through the drawing rather
than about any one symbol:

- the way out of a block end leads back into that same block;
- two transits at one connection derive the same name, two paths joining one
  pair of block ends.

The editor already lights a way symbol by symbol and leg by leg, which is how
the netlist pane shows a transit. A refusal lights the offending way in red
with the same machinery. The sentence is not needed and does not fit on a
canvas.

## The netlist stays a panel

The netlist is now a debugging view rather than, as
[EDITOR.md](../ui/EDITOR.md) opened by calling it, the feature the rest of the
editor exists to serve. Enough railroads have been drawn that derivation is
trusted and the netlist is consulted when something looks wrong. So it
collapses behind `View ▸ Netlist`, and the column goes to zero when it is shut.
Closed on load.

It stays a panel rather than a popup. The netlist's advantage over
`tc49 layout show` in a terminal is that clicking a transit lights its way on
the drawing, so "exclusive because both take `sw16`" is a claim that can be
checked by looking. A modal over the canvas hides the thing being checked and
leaves a CLI listing in a dialog. A floating window would keep the coupling and
was rejected as a window component the editor has avoided needing.
