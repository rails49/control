# Layout editor

The visual editor for drawings, designed in [EDITOR.md](../docs/ui/EDITOR.md).
TypeScript, pnpm, Lit and Shoelace; the drawing surface is SVG in the DOM.

## Running it

The editor talks to the store's HTTP face, which runs separately:

```
uv run tc49 serve          # the store, on 127.0.0.1:8765
pnpm install
pnpm dev                   # the editor, proxying /drawings and /review
```

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
    store.ts     the four routes
  render/
    artwork.ts   what each symbol looks like, hand-written against the
                 generated pin names
  ui/
    tc-editor.ts   the shell: toolbar, findings, keys, talking to the store
    tc-palette.ts  one tile per placeable kind
    tc-canvas.ts   the surface: pointer events, viewBox zoom and pan
    styles.ts      every component's styles
test/            vitest, against model/ — no DOM
```

**The front end knows no topology.** Pin degrees, junction membership, the
derived layout and the explanations come from `POST /review`. TypeScript owns
placement, geometry, mutation and rendering, and nothing else; a second
implementation of the union-find would eventually disagree with the first,
inside the tool whose job is to be believed.

`model/` is where the tests are, because that is the layer where a bug is
invisible on screen and corrupt in the file. The Lit components stay thin
enough that there is little in them to test.

## Using it

Click a palette tile to arm it, then click the canvas to place; the tile stays
armed so a row of blocks is a row of clicks, and Escape disarms it. Dropping a
symbol so a pin lands on another's writes a real wire of zero length, so
dragging apart later stretches the wire rather than breaking the joint.

Click a pin to start a wire, empty canvas to bend it through a free-standing
pin, and a pin to end it. The wireline snaps softly to 15 degrees as an aid;
clicking a pin overrides it.

Drag to move, drag empty canvas to rubber-band, shift-click to add. `R`
rotates, `F` flips, `Delete` deletes, `Escape` cancels, `Cmd/Ctrl+Z` undoes and
`Cmd/Ctrl+Shift+Z` redoes, `Cmd/Ctrl+S` saves. The wheel zooms and the middle
button pans.

No committed drawing has any placement and there is no auto-layout, so opening
one deals its symbols into rows to be dragged from. That is an ordinary edit:
undo takes it back, and it reaches the file only if you save.
