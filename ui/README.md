# The app

One app, one loaded railroad, and a list of views of it
([ADR-0038](../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)):
the run view, which paints a live session over the drawing
([PANEL.md](../docs/ui/PANEL.md)), the throttle, which a person drives one
train from ([THROTTLE.md](../docs/ui/THROTTLE.md)), and the editor, which draws
the railroad ([EDITOR.md](../docs/ui/EDITOR.md)). TypeScript, pnpm, Lit and
Shoelace; the drawing surface is SVG in the DOM.

## Running it

The page talks to the store's HTTP face, which runs separately:

```
uv run tc49 serve --store bench   # the store, on 127.0.0.1:8765
pnpm install
pnpm dev                          # the app at /, opening in the run view
```

`tc49 serve` on its own serves `~/tc49`, an installation's own railroads, which
a fresh checkout has none of; `--store bench` serves this repository's fixtures
instead, which is what there is to draw against here
([LAYOUT.md](../docs/store/LAYOUT.md), #320).

The view is in the hash — `#run`, `#throttle` and `#edit` — so a reload and a
bookmark keep it, and a link naming no view opens on the run view.

`../scripts/dev.sh` does all of it and starts only what is not already up,
which is worth having because vite holds 5173 strictly: a second `pnpm dev`
fails rather than moving to 5174, leaving an open tab talking to a server that
has gone. The page is reached as `localhost`; every server the script starts
binds each interface, because the reverse proxy that serves
`dev.rails49.org` reaches them from a container (../docs/DEPLOY.md).

It also brings up the session the run view joins — a `tc49 live` on
`ws://127.0.0.1:8766`, reached through the app's own origin at `/live` and
started `--no-store` because the store is already up and outlives any one
session. **The band's picker is the only thing that loads a railroad**, and the
run view joins whatever is loaded: the socket path names it and the session
builds it (#171). A railroad given to the script — `../scripts/dev.sh
reversing-loops` — is the one the session comes up on rather than the one it is
stuck with.

`../scripts/dev.sh stop` puts down everything the script started and leaves
alone anything it did not.

```
pnpm check                 # tsc --noEmit
pnpm test                  # vitest
pnpm build
```

## What is where

```
src/
  symbols.generated.ts   pins, transits, the palette — written by `tc49 generate`
  rejection.generated.ts why a request was rejected — likewise generated
  model/
    drawing.ts   the document, exactly as the store serves and takes it back
    geometry.ts  footprints, pin anchors, quarter turns, the 15 degree snap
    editor.ts    the editing session: selection, wires, snapshots, undo
    gesture.ts   what a pointer gesture means in the editor: press, drag, band
    machine.ts   what the canvas asks of whatever decides what a press means
    drag.ts      what a drag on a run means: a train, and where to put it
    naming.ts    connection names, minted and written into the drawing
    store.ts     the four routes
    trace.ts     the bridge's frames read as events, and the gestures written
                 back
    views.ts     the views the app has of the railroad, and the hash they are
                 bookmarked by
    panel.ts     the run's model: bus payloads in, render state out
    throttle.ts  what the throttle draws for each train there is to drive
    scene.ts     what the drawing alone answers: the frame a fit and an export
                 are drawn in, an arrow's pose, which symbol wears an address
  render/
    artwork.ts   what each symbol looks like, hand-written against the
                 generated pin names
  ui/
    tc-app.ts      the app: the loaded railroad, the views, the band, the bar,
                   the keys and the question before edits are thrown away
    tc-header.ts   the band: what is true of the whole system
    tc-menubar.ts  the bar: the current view's menus, and HOLD/GO
    tc-editor.ts   the editing view: palette, canvas, netlist, dialogs
    tc-palette.ts  one tile per placeable kind
    tc-canvas.ts   the one drawing surface, in either of its two modes: the
                   viewport, the artwork, and what only edit or only run draws
    tc-netlist.ts  the derived netlist, and why each pair does or does not
                   run together
    tc-properties.ts  the properties dialog
    tc-menu.ts     the right-click menu
    tc-panel.ts    the run view: the session, and the overlay it hands the
                   canvas to paint
    tc-throttle.ts the throttle view: pick a train, take it, drive it, give
                   it back — the session stays the run view's
    dismissal.ts   the overlay a menu drops over the page, worn by all three
                   menu systems: the press outside that dismisses, and the
                   right-click that is handed on to what is underneath
    <component>.styles.ts  a component's styles, beside it
    shared.styles.ts   what more than one of them wears: the palette, the
                   symbol rules, and what a menu is made of
test/            vitest; the suites that mount a component need a DOM
                 (happy-dom), the rest run without one
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
