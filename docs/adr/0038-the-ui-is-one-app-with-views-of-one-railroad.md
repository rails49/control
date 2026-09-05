# The UI is one app: views of one railroad

**Amended by [ADR-0059](0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md), 2026-09-03:** `tc49 live` and the bridge below are deleted. The page reaches the bus as a client of the broker on `/mqtt`, and the store, the containers and the hardware answer it as before. One page, one loaded railroad, a list of views: unchanged.

The browser ships one page. It holds **one loaded railroad** and a list of
**views** of it — today an editor and a run view, later stock and schedules —
with one of them current. This replaces two Vite entries, two pages and a link
between them ([#166](https://github.com/rails49/control/issues/166)).

The objection on record is stale rather than wrong. `tc-header.ts` said "the
editor and the panel stay separate entries and separate pages"; EDITOR.md said
they "are separate entries and separate apps
([ADR-0016](0016-the-panel-is-a-scheduler.md)) and nothing here merges them".
ADR-0016's claim was that the panel *is* a scheduler, and
[ADR-0036](0036-the-scheduler-is-an-app-the-panel-is-a-view.md) reversed it: the
panel is a view that writes two `tc49/ui` gesture topics and holds no scheduler
state. Two views that judge nothing are not two authorities.
[ADR-0013](0013-apps-are-deployment-units.md)'s sense of *app* was never in
question — `ui` is one deployment unit, and ARCHITECTURE.md always said so.

## The UI is the product; the CLI is the harness

This is already true structurally and is written down here because the UI's
shape follows from it. Every command `tc49` offers — `bench`, `sweep`, `live`,
`serve`, `generate`, `layout` — is in the `bench` package, which CLAUDE.md calls
"the research harness, not an app, and the only code that wires apps together".
The person operating a railroad opens a browser.

What that costs is the **scenario**, which is on the operator's path today: it
is the only source of the train roster, the initial placement and an `at`-timed
request list, and `tc49 live` cannot build an assembly without one. A scenario
is the harness's file format — a roster and a canned request list in one test
file — and a person does not name one. What a person does is load a railroad,
put its trains on the layout, and drag them where they should go. Retiring the
scenario from that path is
[#171](https://github.com/rails49/control/issues/171); this decision is what
makes it a step rather than a rewrite.

## A railroad, not a drawing and not a scenario

The unit the app has open is a **railroad**: its drawing, its roster, and later
its schedules. Trains are placed on a layout and schedules are written against
one, so the layout is where both belong.

Two consequences fall out. **Which railroad is loaded is the app's, not a
view's** — it is not the editor's `File ▸ Open` with the run view guessing
separately. And a **run is of a railroad**, so the socket path that
[#148](https://github.com/rails49/control/issues/148) made carry the session's
identity carries a railroad once #171 lands, with the word changed and the
reasoning intact.

A deployment driving real hardware has exactly one railroad, the one that is
wired. The picker is not restricted on that account: a swapped railroad comes up
**held** (ADR-0037), and what actually keeps wheels still is the track-power
command, which is the hardware adapter's and not the browser's. Restricting the
picker would buy nothing the hold does not already give, and would cost
exploring drawn railroads in simulation, which is worth keeping.

## The band is the system; the bar is the document

Two rows of chrome, divided by what they are about.

The **band** carries what is true of the whole system: which railroad is loaded
and the means of loading another, whether it holds unsaved edits, whether the
store, the bridge, the containers and eventually the hardware are answering,
which view is current, and later track power. The **bar** carries what acts on
the current view's document: File, Edit, View, zoom, HOLD and GO.

This amends the rule `tc-header.ts` carried — "It shows status and nothing else.
Everything a person presses stays in the row below." That rule was already
broken by the band's own navigation link, and it has no answer for track power,
which is pressable and is a fact about the whole railroad rather than about a
document. The line that survives is *what it is about*, not *whether it is
pressable*. It also gives the store-not-answering string somewhere to live: a
health area rather than a squeeze beside the drawing's name.

**Views are data, rendered as one toggle while there are two.** The control is a
list with a current entry; two entries render as a single icon-button, and a
third makes it a selector. Stock and schedules then add an entry rather than
force a redesign.

## One canvas, two modes

The drawing surface is one component. It owns the viewport — zoom, pan, fit,
wheel — pixel-to-square conversion, hit-testing and the artwork. Its **mode**
decides whether pins and the grid are drawn and whether live state paints. What
a press *means* is the current view's, supplied as a gesture machine, which
keeps the rule the editor already states: the model owns the document, a
component owns the DOM.

This is recovery, not invention. Run mode is already a named concept in the
drawing layer — EDITOR.md's canvas section, `artwork.ts`, `units.ts` and
`shared.styles.ts` all describe what run mode does to the artwork. Two
components was an accident of build order, and it cost two copies of wire,
symbol and label rendering and a run view that has **never had zoom or fit**.

## Trains on the layout freeze the drawing

With any train placed, the editing view is read-only: look, zoom, inspect the
netlist, do not draw. You do not rewire track with locomotives standing on it.

This retires EDITOR.md's "Editing and running the same railroad at once is not
prevented. The store snapshots at startup, so a run in progress keeps the layout
it began with and an edit lands for the next one." That was safe when editing
and running were two pages a person navigated between deliberately. Behind a
toggle it is a trap: move a turnout, switch view, and the run view paints the
store's *current* drawing under a dispatcher state that refers to the topology
the run began with. The picture would be a lie at exactly the place a person
looks to see whether a route is safe.

Serving the run's own snapshot to the run view was the alternative, and it is
the more permissive answer: editing stays free and the picture stays true. It
was rejected because it needs a second source of every drawing and a way to
serve it, and because the freeze is what the railroad does anyway. Should the
snapshot ever exist for another reason — a restart replaying what a run began
with — the freeze can be reconsidered on its own terms.

## Replay leaves the browser

The run view can read a recorded trace and step through it. That was built
because the view needed something to render before `tc49 live` and the bridge
existed, and it survives as how the panel's colours get looked at.

Both reasons have expired. The live path is now the dev path: pick a simulated
railroad, place trains, press GO, drag one. And the chrome replay needs — a
drawings list, a file opener, a transport, a rate in boundaries per second — is
most of what makes the run view hard to merge, all of it meaningless to an
operator, and none of it about a railroad that exists.

Traces stay load-bearing exactly as ADR-0036 has them: the tap records every
event, metrics derive from recordings, and benchmarks assert byte-identical
replays. That is analysis, and analysis is the harness's. What is deleted is a
browser that reads trace files, not the trace.

A recording of last night's session is a real thing to want on a railroad. When
it is wanted it comes back as session history over the bus, not as a file
picker, and it is a view of its own by then.

## Consequences

**The panel's page becomes the run view.** PANEL.md keeps its subject — what the
railroad's state looks like drawn on the drawing, and the gestures that ask for
a train to be moved — and loses the half about picking a trace and joining a
scenario.

**One place answers "what am I looking at".** The band. Previously the drawing
name was in one row on one page and the scenario in a different row on another.

**The left pane is one slot.** The editor's palette in one view, the roster in
the other ([ADR-0039](0039-a-train-may-be-off-the-layout.md)), the same width
and the same place.

**Nothing about the bus changes.** No topic, no payload and no role is touched
by any of this. The browser writes the `tc49/ui` leaves it already writes, which
is what keeps ADR-0036's single-minter argument holding and what makes this a
decision about a page rather than about the system.
