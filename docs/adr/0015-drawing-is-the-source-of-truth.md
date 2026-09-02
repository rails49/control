# The drawing is the source of truth

The asset store keeps two document types, `drawing` and `scenario`. A drawing
is symbols joined by wires through their pins
([DRAWING.md](../store/DRAWING.md)). The layout is derived from it on `get`
and is never authored. No `.layout.yaml` files exist.

The relationship can only point this way. A dispatch panel shows more than the
dispatch model contains: turnouts, signals, station labels. That detail lives in
the drawing and cannot be recovered from a layout file, so the drawing is
strictly richer and the layout is a projection of it.

Two alternatives were rejected.

**Layout authored, drawing as a sidecar overlay** keeps hand-authoring but
creates two documents describing the same topology, each hand-editable. Drift is
then the expected failure, and reconciling it means deciding which of two
disagreeing files is right, with no principle for answering.

**Generating and committing the layout alongside the drawing** was rejected on
the same duplication argument, once the supposed benefit turned out to be thin.
The case for it was that a committed layout makes a mis-dragged wire visible in
review as a topology diff. But the drawing is YAML with stable ids, so a
mis-dragged wire already appears as a changed pin-to-pin edge, which is the
cause rather than the effect and reads at least as well. There is no cost
argument either: derivation is three passes over a graph of tens of nodes, well
under a millisecond for `reversing-loops`, run once per `get` against a
snapshot that is immutable for the run.

What this gives up is blast radius. One moved wire can flip concurrency across
many transit pairs, and the drawing diff shows one changed line where a layout
diff would show all of it. A `tc49 layout show <name>` command covers that on
demand, as a tool rather than a committed file.

Two consequences follow. Migration becomes compulsory, since a railroad that
has not been drawn cannot be loaded; the generic N-pin connection symbol makes
that mechanical and lossless, because derivation passes it through unchanged.
And the reasoning comments that `layouts/reversing-loops.layout.yaml` carried
have to move into the drawing, along with the parts of
[LAYOUT.md](../store/LAYOUT.md) that document the layout schema as the authored
format.

[ADR-0010](0010-asset-store-serves-coarse-read-only-documents.md) is
unaffected in shape: still two coarse document types, still whole-document
verbs, still read-only for components, still validated so a `get` never returns
an invalid document. The derived layout is run through the existing validator,
which is the cheap safety net against derivation bugs.
