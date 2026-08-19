# Layout editor and dispatch panel

The visual editor for drawings, designed in [EDITOR.md](../docs/ui/EDITOR.md),
and the dispatch panel that replays a recorded trace over a drawing
([PANEL.md](../docs/ui/PANEL.md), #70). TypeScript, pnpm, Lit and Shoelace;
the drawing surface is SVG in the DOM.

## Running it

Both pages talk to the store's HTTP face, which runs separately:

```
uv run tc49 serve          # the store, on 127.0.0.1:8765
pnpm install
pnpm dev                   # the editor at /, the panel at /panel.html
```

`../scripts/dev.sh` does both and starts only what is not already up, which is
worth having because vite holds 5173 strictly: a second `pnpm dev` fails rather
than moving to 5174, leaving an open tab talking to a server that has gone.
Vite binds `[::1]`, so the pages are reached as `localhost` rather than
`127.0.0.1`.

The panel picks a railroad from the store and opens a trace file from disk —
`tc49 bench crossover-yard/meet --trace Incremental` prints one — then plays
or steps it tick by tick.

```
pnpm check                 # tsc --noEmit
pnpm test                  # vitest
pnpm build
```

## What is where

```
src/
  symbols.generated.ts   pins, transits, the palette — written by `tc49 symbols`
  model/
    drawing.ts   the document, exactly as the store serves and takes it back
    geometry.ts  footprints, pin anchors, quarter turns, the 15 degree snap
    editor.ts    the editing session: selection, wires, snapshots, undo
    gesture.ts   what a pointer gesture means: press, drag, band, pan
    naming.ts    connection names, minted and written into the drawing
    store.ts     the four routes
    trace.ts     a recorded trace, parsed and stepped tick by tick
    panel.ts     the panel model: bus payloads in, render state out
  render/
    artwork.ts   what each symbol looks like, hand-written against the
                 generated pin names
  ui/
    tc-editor.ts   the shell: toolbar, findings, keys, talking to the store
    tc-palette.ts  one tile per placeable kind
    tc-canvas.ts   the surface: pointer events, viewBox zoom and pan
    tc-netlist.ts  the derived netlist, and why each pair does or does not
                   run together
    tc-properties.ts  the properties dialog
    tc-menu.ts     the right-click menu
    tc-panel.ts    the dispatch panel: trace replay painted over the drawing
    <component>.styles.ts  a component's styles, beside it
    shared.styles.ts   what more than one of them wears: the palette, the
                   symbol rules, the lit way, the box a menu drops into
test/            vitest; keys.test.ts and menu.test.ts need a DOM (happy-dom),
                 the rest run without one
```

**The front end knows no topology.** Pin degrees, junction membership, the
derived layout and the explanations come from `POST /review`. TypeScript owns
placement, geometry, mutation and rendering, and nothing else; a second
implementation of the union-find would eventually disagree with the first,
inside the tool whose job is to be believed.

`model/` is where most of the tests are, because that is the layer where a bug
is invisible on screen and corrupt in the file.

A component is not exempt. The model owns the document, a component owns the
DOM, and anything that is neither is a module in `model/` with a test, whichever
file calls it. A rule deciding what a gesture means, what a menu applies to, or
which keystroke belongs to the canvas is that third kind, and belongs where it
can be tested. See [EDITOR.md](../docs/ui/EDITOR.md#tests).

## Using it

Click a palette tile to arm it, then click the canvas to place; the tile stays
armed so a row of blocks is a row of clicks, and Escape disarms it. Dropping a
symbol so a pin lands on another's writes a real wire of zero length, so
dragging apart later stretches the wire rather than breaking the join.

Click a pin to start a wire, empty canvas to bend it through a free-standing
pin, and a pin to end it. The wireline snaps softly to 15 degrees as an aid;
clicking a pin overrides it.

Drag to move, drag empty canvas to rubber-band, shift-click to add. `R`
rotates, `F` flips, `Delete` deletes, `Escape` cancels, `Cmd/Ctrl+Z` undoes and
`Cmd/Ctrl+Shift+Z` redoes, `Cmd/Ctrl+S` saves. The wheel zooms and the middle
button pans.

Right-click for properties, for the name of the junction or the joint
under the pointer, and to cut the wire under it — a wire has no symbol to
select, so the menu is the only way to delete one. A junction is named `j1`, `j2` as it forms, so nothing
interrupts a sketch; renaming one is worth doing when it earns a name, because
the name heads its section in the netlist.

Selecting a transit in the netlist lights its way on the canvas and says, for
every other transit at that connection, whether it runs together with it or
which symbol they share. That is the feature the rest of the editor serves.

No committed drawing has any placement and there is no auto-layout, so opening
one deals its symbols into rows to be dragged from. That is an ordinary edit:
undo takes it back, and it reaches the file only if you save.
