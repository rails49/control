# A portal is placed as a pair

A **portal** ([CONTEXT.md](../../CONTEXT.md#drawing)) is a one-pin symbol
paired by label with exactly one other portal, and a label worn once derives to
nothing: the drawing is refused. Every portal used to start that way, minted
wearing its own name as its label, which is a label no second portal can be
wearing. The only thing that cleared it was remembering to open the properties
dialog and type the mate's label. That is the silent accumulation of
[#74](https://github.com/rails49/control/issues/74)'s stranded bends one layer
up: a state easy to reach, easy to leave, and fatal to derivation.

A portal is now placed by one gesture that yields both halves. The drop lands
the first and the ghost becomes its mate, wearing the same label and turned 180
degrees, so the next click drops the far end. The flight is the idiom the
editor already has, since drawing a wire is click-then-click
([EDITOR.md](../ui/EDITOR.md#drawing-wires)): nothing new is taught, no question
interrupts the sketch, and the pair is one undo step in both directions. The
mate starts turned because the common drawing is track that runs, vanishes and
continues the same way somewhere else, whose two mouths face opposite. The
staging-yard case, where both face inward, is one `r` away.

The alternative to reject explicitly, because it will be proposed again as an
obvious improvement, is **pairing by adoption**: let the second portal placed
take up a lone portal's label instead of minting a fresh one. It cannot ask
which lone portal it means, so it has to guess, and an ordinary drawing order
defeats it. Draw two tunnels by placing both west mouths and then both east
mouths, and adoption pairs W1 with W2 and E1 with E2: a drawing that derives
cleanly and means something nobody drew. A rule that can produce a wrong
derivable layout is worse than one that produces a finding, because the finding
was what would have caught the mistake.

The same hazard arrives through name reuse, which is why a portal's label is
minted from the labels in the drawing rather than from `mint()`'s free names.
Deleting one portal of the pair labelled `p1` frees the name `p1` while the
survivor still wears the label, so a label minted as a name would hand `p1` to
the next portal placed and pair it with the orphan.

Two consequences. **A portal's name and its label are no longer the same
string** in a drawing where portals have been deleted, or where more than one
pair has been placed: a pair advances the label once and the names twice.
And **prevention stops at placement**. Deleting one portal of a finished pair
still strands the other, left alone deliberately: it is a visible act, and the
mark from [#77](https://github.com/rails49/control/issues/77) catches it, drawn
in red wearing the label it is looking for. Placement is where the accident
was; the rest of a drawing's life belongs to the finding.
