# The app

One app, one loaded railroad, and a list of views of it
([ADR-0038](../docs/adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)):
the run view, which paints a live session over the drawing
([PANEL.md](../docs/ui/PANEL.md)), the throttle, which a person drives
trains from ([THROTTLE.md](../docs/ui/THROTTLE.md)), the stock view, where the
cars and the trains a railroad owns are made
([STOCK.md](../docs/ui/STOCK.md)), and the editor, which draws the railroad
([EDITOR.md](../docs/ui/EDITOR.md)). TypeScript, pnpm, Lit and
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

The view is in the hash — `#run`, `#throttle`, `#stock` and `#edit` — so a
reload and a bookmark keep it, and a link naming no view opens on the run
view.

`../scripts/dev.sh` does all of it and starts only what is not already up,
which is worth having because vite holds 5173 strictly: a second `pnpm dev`
fails rather than moving to 5174, leaving an open tab talking to a server that
has gone. The page is reached as `localhost`; vite also binds every interface,
because a browser on the LAN has exactly one way to a UI under development and
an address is it, while the store stays on loopback behind vite's proxy.

It also brings up the broker the page's session (`src/model/session.ts`)
connects to — mosquitto in a container of its own, `1883` for native clients
and `9001` for the browser, reached through the app's own origin at `/mqtt`. It starts no app: each has a
command line of its own and comes up alone (ADR-0059, decision 5), so a
simulated railroad to drive is `python -m tc49.simulator --broker
127.0.0.1:1883 --store http://127.0.0.1:8765`, which comes up on the railroad
the store records as loaded and stands where it records none (ADR-0072).
**The broker is the only thing that loads a railroad**: the layout interface
publishes its name on a retained row and the app reads its documents off the
store. The settings dialog behind the band's gear does not load one itself —
it asks, on `tc49/layout/railroad_wanted`, and the layout interface answers by
publishing the row (ADR-0060, ADR-0072). Its list is live only while
`tc49/layout/state/power` reads `off` with a railroad loaded and nothing is
unsaved, and says why when it is not. Making a railroad is the dialog's too:
New writes an empty drawing and Copy loaded as… has the store copy the loaded
railroad's documents, and each then asks for what it wrote the same way
(#737).

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
  main.ts        the page's entry: the app, `look.css` and its two themes,
                 and Shoelace's assets from the app's own origin
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
    rules.ts     the store's rules over a document, transcribed once
    store.ts     the routes, and which of the three ways a call to one
                 failed
    trace.ts     the broker's messages read as events, and the gestures
                 published back
    views.ts     the views the app has of the railroad, and the hash they are
                 bookmarked by
    panel.ts     the run's model: bus payloads in, render state out
    session.ts   the page's one broker connection: the railroad the row
                 names, the panel model it feeds, the presses, the OFF drain
    throttle.ts  what the throttle draws for each train there is to drive
    stock.ts     the roster and the catalogue being edited, and everything
                 derived from the pair
    railroad.ts  the loaded railroad's documents: read when the row names
                 it, read again until the store answers, and the roster's
                 Save
    scene.ts     what the drawing alone answers: the frame a fit and an export
                 are drawn in, an arrow's pose, which symbol wears an address
    pinch.ts     the view two fingers on the canvas hold: pan, and zoom about
                 their midpoint
    under.ts     what is under a point on the canvas, read from a grid
                 position back to the thing a click there means
    inspect.ts   a `/review` read back: what the netlist pane says and what
                 the canvas lights
    filing.ts    the editor's dealings with the store: what is open, whether
                 it is saved, what the store last said, what went wrong
    export.ts    the drawing as a standalone SVG file, cloned from the canvas
    commands.ts  every command a view offers: its name, its key, its menu, and
                 when it is dead
    settings.ts  when the settings dialog's railroad part is refused, and why
    backup.ts    backing the store up: where it stands, what git last said,
                 and what could not be asked at all
    box.ts       the box this page is served from, as the installation
                 answers for it
    requests.ts  the request list: the requests the dispatcher holds, in
                 serving order, and what a drag of one asks
  render/
    artwork.ts   what each symbol looks like, hand-written against the
                 generated pin names
    units.ts     units and colours: every dimension a fraction of the grid
                 square G, and the palette
  ui/
    tc-app.ts      the app: the loaded railroad, the views, the keys, and the
                   band and the rail, drawn from @rails49/look
    tc-editor.ts   the editing view: palette, canvas, netlist, dialogs
    tc-palette.ts  one tile per placeable kind
    tc-canvas.ts   the one drawing surface, in either of its two modes: the
                   viewport, the artwork, and what only edit or only run draws
    tc-netlist.ts  the derived netlist, and why each pair does or does not
                   run together
    tc-properties.ts  the properties dialog
    tc-menu.ts     the right-click menu
    tc-settings.ts the settings dialog behind the band's gear: which railroad
                   is loaded, New and Copy loaded as…, and the way into backup
    tc-backup.ts   the backup dialog: whether the store is kept anywhere,
                   the press that keeps it now, and the backups to come back to
    tc-panel.ts    the run view: the overlay it hands the canvas to paint,
                   the drag, the right-click menu and the roster pane
    tc-roster.ts   the roster pane: every train the railroad owns, on the
                   layout or off it, a row to drag out of and back to
    tc-requests.ts the request list under the roster: a cancel on each, a
                   drag to reorder the waiting ones
    tc-throttle.ts the throttle view: the picker, or a column per held train
                   side by side as its width fits, with a take column; the
                   session stays the app's
    tc-driving.ts  one held train's driving controls: drive it, give it back
    tc-train-picker.ts  the throttle's train picker: a card per train, Take,
                   Force release and Take back
    tc-clock.ts    the station clock on the throttle's cab, in wall time
    wake.ts        the screen kept awake while this page's throttle holds a
                   train
    tc-stock.ts    the stock view: cars and models on the left, the trains
                   composed from them on the right
    dismissal.ts   the overlay a menu drops over the page, worn by all three
                   menu systems: the press outside that dismisses, and the
                   right-click that is handed on to what is underneath
    <component>.styles.ts  a component's styles, beside it
    shared.styles.ts   what more than one of them wears: the palette and the
                   symbol rules
test/            vitest; the suites that mount a component need a DOM
                 (happy-dom), the rest run without one
  setup.ts       turns off Shoelace's glyph fetches for every suite
```

**The chrome is `@rails49/look`'s.** The band, the rail, the power control,
the dialogs and the Shoelace theme come from the package, and the app styles
none of them. `look-check` in the gate fails if it does
([ADR-0073](../docs/adr/0073-the-chrome-comes-from-look.md)).

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
