# Run view

The live panel: watching the railroad in real time and asking for trains to be
moved. It is one of the app's two views of the loaded railroad, the
[editor](EDITOR.md) being the other
([ADR-0038](../adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)); it
was built after the editor, as the order of work had it.
Decisions that bind it:
[ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md), which
made it a view rather than the scheduler it began as
([ADR-0016](../adr/0016-the-panel-is-a-scheduler.md)),
[ADR-0035](../adr/0035-a-topic-has-one-writing-role.md), and
[ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md).
Terminology follows [GLOSSARY.md](../../GLOSSARY.md).

## What it shows

The run view renders the drawing ([DRAWING.md](../store/DRAWING.md)) with live
state on top. Blocks show colour for state, a label for the train, an arrow
for direction. A locked but empty block gets a fill of its own, so a committed
route reads as a lit path.

**It draws none of it itself.** The surface is `tc-canvas` in **run mode** —
the same canvas the editor draws on, one of two modes of one component
([EDITOR.md](EDITOR.md#canvas),
[#168](https://github.com/rails49/control/issues/168)). Everything below is
what run mode adds over the drawing both modes paint: the state colours, the
labels, the arrows, the aspects, the markers and the drag's shade. It arrives
as one overlay object worked out in `model/panel.ts`, so the component still
computes nothing.

**So the run view has zoom, pan and fit**, on the same keys and the same rail
buttons as the editor — `+`, `−`, `0`. It had none of the three while it drew
its own picture fitted to the sheet, which is what a railroad too large to see
at once cost.

**A grey run view is a railroad the apps did not build.** While
`tc49/layout/state/railroad` names the loaded railroad with `built: false`,
its saved drawing is an invalid drawing and nothing runs on it, so the view
draws the drawing grey, with no trains, no aspects and no markers, and every
gesture is dead: a press throws no point, a train is not picked up, a
right-click opens no menu, and the roster and the request lists take
nothing. The band says *invalid drawing*, and the Edit view is where it is
fixed
([ADR-0085](../adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
decision 4, [#886](https://github.com/rails49/control/issues/886)).

**The railroad's roster is listed in the left pane.** The shell has one
left-pane slot and each view fills it: the editor's palette, this view's
`tc-roster` ([#169](https://github.com/rails49/control/issues/169)). A row is
the photo of a train's first locomotive, its name, its length, and where the
run has it — the block it stands in, *crossing a transit* where it stands in
none (on the layout all the same), or *off the layout*. The photo is the one
the throttle's train picker shows
([#1012](https://github.com/rails49/control/issues/1012)); a train with no
locomotive, or one whose photo does not load, has an empty slot of the same
size, so every row is one height, and a press on the photo picks the train up
as a press on its name does. Ordered by name, so the list does
not reshuffle as the railroad moves.

A railroad's **roster** is every train it owns, whether on the layout or off
it ([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)), so the pane is
fed from two places: `GET /rosters/<railroad>/trains` for what there is, how long
each train is and the model of its first locomotive, and `tc49/dispatch/state/allocation` for which of them the run
has. Two sources because they are two things — the store serves the railroad's
assets, the bus carries the run
([ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)) —
and the pane is handed one list. A train the picture has and the roster does
not still gets a row: it is on the layout, and hiding it would hide what the
operator can see. The roster is not this view's to read: the loaded railroad
(`ui/src/model/railroad.ts`) reads it with the drawing when the row names a
railroad, and the app hands it down
([#758](https://github.com/rails49/control/issues/758)). The pane shows it while
a session is joined and nothing when one is left: a page told nothing must not
claim every train is off the layout.

**The app has it read again when this becomes the current view.** The store is not on
the bus, so nothing publishes a roster change: a person who makes a train up in
the [stock view](STOCK.md) and switches here must see it, and until then the run
keeps the roster it joined with. Only the roster — the session is joined, the
connection is open and every retained topic has been replayed, so re-joining
would take a live picture down to bring back a document.

Trains standing nowhere have rows because those rows are what there is to drag
back onto the railroad. They do not freeze the drawing: track power does
([EDITOR.md](EDITOR.md#track-power-freezes-the-drawing)), and a save with power
off keeps the trains that still fit.

**The request list is under the roster**, in the same pane: `tc-requests`, a
component of its own, read from `tc49/dispatch/state/allocation`'s `requests`
([#829](https://github.com/rails49/control/issues/829),
[ADR-0080](../adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)).
Each list is as tall as its rows, up to half the pane, and scrolls on its own
past that, so the requests sit directly under the trains and the space left
over is below them
([#895](https://github.com/rails49/control/issues/895)).
One row per request, in list order — the order the dispatcher serves them, so
what the list shows is what the dispatcher does next. A row is the train,
where the request starts, where it ends, and *waiting* or *underway*, a
request with a `route` being underway. A request chained `after` an earlier
one has no departure end of its own: its start is the earlier request's
arrival ends, which is where that one leaves the train. A request only
submitted is not listed until the dispatcher's picture has it, and a rejected
one never is; its reason is on the drawing.

Each row has a **cancel**, which publishes `tc49/dispatch/cancel_wanted`
(`{id}`) naming that request, the requests chained after it ending with it. A
**waiting** row can be dragged to another place in the list, which publishes
`tc49/dispatch/reorder_wanted` (`{id, before}`): `before` is the first waiting
request the row lands in front of, `null` for the end. An **underway** row
cannot be dragged, having started, and a drag that would put a train's chained
request above the one it follows — moving it up, or the one it follows down —
is refused; the row goes back where it was and nothing is sent. Those are the
moves the dispatcher would drop. The list moves when the picture does, not on
the drop. The rows and what a drag asks are worked out in
`ui/src/model/requests.ts`; the component draws them and reports where a row
was let go.

**A train's name is drawn in each block it occupies**, whatever the block's
colour: every block the train holds in the picture's `locks` that reads
occupied on `block_occupied` and `block_vacated`. A train passing from one
block to the next is named in the old block, then in both, then in the new
one. Where none of the blocks it holds reads occupied — a page that joined
after the readings, or a detector that has dropped out — it is named in the
block it last stood in, the one `trains` names. The picture's `crossing` says
a train has left that block for a transit; the block keeps its lock and its
colour, and loses the arrow
([#154](https://github.com/rails49/control/issues/154),
[#897](https://github.com/rails49/control/issues/897)). A train the run has
taken off is named nowhere, though the blocks it reads occupied in stay held.

**A block shows its train's photo in place of the name** where there is one:
the model photo of the train's first locomotive, the one the roster pane
shows, read from the same `GET /rosters/<railroad>/trains`
([#1018](https://github.com/rails49/control/issues/1018)). It is centred and
fitted whole inside the rectangle and turns with the block as the name does.
A train with no locomotive, or one whose photo does not load, shows the name
as before. Resting the pointer on the block shows the name, and so does a
tap, for 3 s: a press released before it moves further than a click or a tap
on a point may, which picks nothing up. A press that moves further picks the
train up, as a press on the name does.

**What the detectors dispute is marked on the block it is about.** While the
run is held the dispatcher compares its placement against the occupancy the
layout has reported and publishes the two contradictions on
`tc49/dispatch/state/disputed`: a train standing in a block that reads clear,
and a block that reads occupied with nothing claiming it
([#153](https://github.com/rails49/control/issues/153)). Each wears an amber
outline over whatever state it already has, and the reading that contradicts
the picture is written under the block in words: *reads clear*, *reads
occupied*. The outline rides over the state rather than replacing it, because
the dispute is that the block is other than the picture says and the picture
is the half a person is checking. Amber, not the red a rejection wears:
nothing is broken, and the railroad is as likely to be right as the software.

These are where a person is sent first, and walking the railroad is what
empties them: each `placement_wanted` republishes what is left. The panel
derives none of it — which blocks the layout has reported on at all is
knowledge only the dispatcher holds, and a panel working it out would call
every block nothing has said anything about clear. Releasing the hold with
entries outstanding is allowed, and the set empties with the press; what the
panel is still marking at that moment is what the person is deciding to
accept.

A request renders in three layers, each appearing when the bus first makes it
true. **Requested** (from `request_submitted`): the train, its departure end,
and the candidate arrival ends, endpoints only, since no route exists yet and
drawing a predicted one would be a second pathfinder that lies whenever the
dispatcher disagrees. **Committed** (from `route_chosen`): the whole route
lit in the committed colour. **Held** (from `lock_granted` /
`lock_released`): the locked stretch of that route in the locked colour, and
the signals described below.

**A committed route lights whole.** Its blocks, the legs of the symbols its
transits cross, and the wires those transits are drawn over all light, so the
route reads from the block the train stands in to the arrival end it is
committed to. Without the wires a route through a junction reads as scattered
lit frogs, and a route across a joint (a way crossing no symbol that declares
a transit) lights nothing at all between its two blocks.

Which wires a transit runs over is the store's own rule, `Drawing.wires_on`,
transcribed into `model/inspect.ts`. It is applied one transit at a time and
never over a union of everything lit: a wire between two non-block symbols is
what merges them into one junction, so a union has no transit to attribute a
wire to, and each wire has to take its own transit's colour. The store proves
the rule exact against every railroad it holds, which is what the front end's
cheaper copy rests on. Lit wires are emitted after unlit ones, as the artwork
already emits lit legs last, so a crossing unlit wire cannot half hide one.

**It lights in two colours**, keyed to what the dispatcher is doing:

- **Green** where the dispatcher holds a **lock**. The train may move here.
- **Cyan** where the resource is on a committed route and is **not** locked.
  The route is chosen; the claim has not been made yet.

Locking is incremental
([ADR-0026](../adr/0026-two-blocks-ahead-is-full-speed.md)), so green creeps
forward along a cyan path as the train advances, and the length of the green
says how far the train may go. It agrees with the signal at the block end,
which the dispatcher reads off the same locks.

A live run is the one that locks that way: the deployed dispatcher takes
`Incremental`, so a page watching a railroad is watching an incremental run
([#165](https://github.com/rails49/control/issues/165)). `FullRoute`, which
locks a whole route at launch, is the baseline the batch harness measures
against ([BENCHMARKS.md](../bench/BENCHMARKS.md)) and is not a discipline the
panel ever draws: under it a route would come up green end to end and cyan
would appear only as the locks release behind the train.

Green is read from the lock ledger alone, not from the committed route
intersected with it, which is how the block view already works. A lock the
dispatcher still holds after its request completes therefore stays green
until it is released: it really is still held, and the picture must never
claim the railroad is freer than it is.

Three precedence rules, written down rather than left to the rendering order:

- **Occupancy outranks both.** The block a train stands in keeps its
  occupancy colour and the route's green begins at the first block beyond the
  train. A standing train holds a lock too, so this is a choice rather than
  an oversight.
- **Locked wins on a shared symbol.** A throat symbol carried by a locked
  transit and a committed one at the same time shows the locked colour. That
  overstates the committed route's leg on that symbol, which is the price of
  never hiding the stronger claim behind the weaker.
- **Nothing is predicted.** A request with no committed route still renders
  as endpoints only.

Committed block bodies are dashed and locked ones solid. Cyan against green is
a hard pair for red-green colour deficiency, and whether the train may move is
the distinction worth a channel that is not hue. Track and wires stay solid: a
dash's spacing would vary with a wire's angle, which is why track is never
patterned. A throat has no block body, so it is the part of the route left
with hue alone, and also the part where which way is locked matters most.

Both colours are palette entries in `render/units.ts`. The pale ground a block
body wears is mixed from its own stroke in the stylesheet rather than named a
second time, so a colour and its wash cannot drift apart.

**Each block end shows what its detector reads**
([#898](https://github.com/rails49/control/issues/898)), for a person
debugging the layout. A small square sits inside the block's rectangle at each
end, read off that end's `tc49/layout/state/device/sensor/<block>.<end>` row:
filled for `occupied`, hollow for `clear`, grey for `unknown` or for an end no
row has named yet. The squares are always drawn on a run and never in the Edit
view. They are square and in ink rather than round, red or green, because the
signals at the same ends are round red and green lamps. They are the readings,
not the picture: a block's colour still comes from `block_occupied` and
`block_vacated`, which `layout` folds the two readings into, and those carry
no train identity. Train identity is reconstructed from `lock_granted`,
exactly as the dispatcher does. Direction is not derived
here at all: it is the train's **facing**, read off
`tc49/schedule/state/facing`, which the scheduler keeps from the entry end of
each granted transit and from a committed route's departure end
([ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)). A
train that has never moved has an arrow for the same reason a moved one does.
The value is the run the train would make across its block, `<block>.A-to-B`
or `<block>.B-to-A` (GLOSSARY.md, **Facing**), and the arrow points at the end
that run comes out at — B for `A-to-B` — which is the whole of the reading.

**Point positions are read off `wanted/point`.** `layout` writes a retained
`tc49/layout/state/wanted/point/<addr>` row, `addr` and `position`, for each
point every `align` names, a route's and a person's throw alike
([ADR-0068](../adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)),
and the panel reads those rows and not `align`. A page opened mid-session is
therefore handed every position commanded since the broker came up. An address
is the one a symbol wears
([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md)), and the
panel holds the drawing, so an address maps back to the symbol wearing it. Two
points wearing one address lie the same way, and an address no symbol wears is
ignored. A point stays where its row last left it. An unlit point whose
position is known is drawn in it, the road the other position offers faint, so
a turnout shows its straight road or its diverging one and a slip's tick says
which road it has; one whose position is unknown draws every road plainly.
Which of a turnout's legs `closed` takes is its `closed_leg`
([DRAWING.md](../store/DRAWING.md#hardware-ids)). A
**lit** point (GLOSSARY.md) is drawn with nothing faint: the lit road is the
position it is being set to, and a lit leg the `align` has not reached yet is
a route chosen, not a road the point does not offer. The panel infers
nothing, which supersedes the inference
[ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md) put here.
It still shows commanded position, not measured position, so a point that
failed to throw looks fine. Reported position becomes worth adding if hardware
with point feedback ever exists; the owner's points do not report. Only a
drawing whose points carry addresses can show any of this, and
[`reversing-loops/positions`](../../bench/scenarios/reversing-loops/positions.scenario.yaml)
is the scenario that does — one train across two junctions, which is the
picture to run when the styling is what is being looked at (#130).

**Signals are part of the block symbol.** A block carries a signal at each
end, always, so there is nothing to place and nothing in the drawing to
record. A signal governs departures through one block end, and routes are
strict pass-throughs with no reversal within a route, so a signal at
`station_c_2.B` means "may a train that reaches B leave by it"
([ADR-0093](../adr/0093-every-signal-along-a-trains-locked-blocks-shows-its-aspect-and-a-passed-signal-shows-stop.md)).

**The panel derives no aspect.** The dispatcher publishes one — `stop`,
`caution` or `clear`, read off how far ahead it has locked — on a last-value
topic naming every signalled end, and the panel renders what it is told
([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
An aspect is a function of locks the dispatcher holds and routes it committed,
so a second party working it out is a second authority to disagree with.

Two questions the panel's own locked-ahead derivation raised are answered by
not arising. Whether an end the standing train does not face may show anything
but red: the dispatcher knows the committed route, so it knows the exit of
each block from where the train stands through the last it has locked, and
lights those; every other end shows `stop` because nothing is locked beyond it
for a train that would leave by it, and a signal the train has passed goes back
to `stop` as soon as the train reads occupied in the block beyond (ADR-0093). And the middle aspect, which the binary derivation could not
produce at all: the dispatcher counts the depth, so `caution` and `clear` are
simply two different counts.

An end that leads nowhere carries no signal and the dispatcher does not name
it, so the panel draws none — no rule here, just an end absent from the map.

**Every widget in the drawing is drawn at its place as its face alone**
([ADR-0087](../adr/0087-a-widget-is-on-the-drawing-and-control-carries-its-payload-without-reading-it.md),
[#929](https://github.com/rails49/control/issues/929),
[#939](https://github.com/rails49/control/issues/939)): the face the editor
draws ([EDITOR.md](EDITOR.md#widgets)), with no box, name or kind. A button or
a toggle carries no words, so a text widget beside it says what it does.

- A **text** widget shows the row on `tc49/ui/state/text/<name>`, its default
  text while there is none, and nothing where it has no default. The row is
  shown as it arrives, with ANSI SGR codes read for bold and three colours:
  `1` is bold and `22` ends it; `31` or `91` is red, `33` or `93` amber and
  `32` or `92` green, in look's `--red`, `--amber` and `--green`, and `39`
  ends the colour; `0` resets both. Any other code, and every other escape
  sequence, is removed from what is shown. The words run over the track and
  are cut only at the canvas's edge.
- A **button** is a ring round a disc. The disc is drawn lighter while a
  press is held, a press being sent and not kept.
- A **toggle** is a rounded track with a knob, showing its position read off
  `tc49/ui/state/toggle/<name>` by comparing the row with its two payloads:
  the knob at the right on a green track for `on`, at the left on a grey one
  for `off`. With no row it shows its default. A row matching neither
  payload, or no row and no default, shows the knob in the middle.

The rows are not the railroad's — a widget's topic names none — so
they are kept whichever railroad is joined, and dropped only when the page
connects again, its retained rows then coming back with the rest. A drawing
drawn grey still shows its widgets, each as it would with no row.

![A live session mid-run: two committed routes, green where the dispatcher holds the lock and cyan where it does not, and a drag from `resident` to C6's middle third](images/live-drag.png)

## What it does

The panel is read-only apart from gesturing, and it gestures in three ways: a
drag on the canvas, which asks for a train to be moved; a drag between the
canvas and the roster pane, which says where a train actually is; and a
right-click, which turns one around where it stands.

**Where a drag began is what it means**, never the run's state:

| From | To | Means |
| --- | --- | --- |
| a roster row | a block | place the train there, or move it there by hand |
| a train's marker | the roster pane | take the train off the layout |
| a train's marker | another block | a request for that train |
| a train's marker | its own block | nothing: the cancel gesture |

Deciding by the run's state instead would make one motion mean two things
depending on a word in the band, and would cost queuing a request while the
run is held, which the hold deliberately keeps working for a timetable
([ADR-0037](../adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).

**Dragging** a train from its block to a destination block publishes
`tc49/schedule/request_wanted` — `{train, dest}` — and the scheduler composes the
request the dispatcher then answers with `request_admitted` or
`request_rejected`. The block's outer thirds name one arrival end — the end
the train enters through, as [GLOSSARY.md](../../GLOSSARY.md) defines it — and
the middle third names both, "either way round". While the drag is in
flight the target block's body is shaded where the drop would arrive: the A
half for the A end, the B half for the B end, the whole body for both
([#896](https://github.com/rails49/control/issues/896)). The shade is on the
block itself, not a ring at its pin, so among blocks close together it cannot
read as a neighbour's. Dropping on the train's own
block abandons the drag and writes nothing. The departure end is never part
of the gesture: it is the train's **facing** end, which the scheduler holds
and the dispatcher never sees ([ADR-0019](../adr/0019-facing-is-scheduler-state.md)). Neither is the
request id, which the scheduler mints. One drag names one
block, so multi-block arrival sets
([ADR-0007](../adr/0007-requests-name-a-set-of-arrival-ends.md)) are deferred,
not dropped; drag supersedes the click sequence this page first recorded.

The drag is **filter-free**: the panel never grays out targets or pre-judges
fit or reachability. Every drop submits, the dispatcher stays the sole
feasibility authority, and a rejection renders at the request's endpoints
with its reason spelled out (`no_fit`, `no_entry`, `unreachable`,
`no_origin`, `wrong_origin`, `unknown_train`, `unknown_block`,
`malformed`). `no_origin` is a train that is known but off the layout
([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)); a drag of the
canvas cannot ask for one — a train off the layout has no marker to pick up,
and the scheduler drops a gesture it cannot compose a departure end for — so
it answers a timetable or a stale page. The last three answer a payload the
dispatcher could not read as a request; an honest drag cannot produce one, and
the page that can is a stale one, a race or a
bug ([ADR-0034](../adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).
The names are not retyped here: `src/rejection.generated.ts` is written from
`tc49.lib.rejection` by `tc49 generate`, and the wording table is keyed by
what it says, so a reason the dispatcher mints and this page cannot spell is
a compile error (#126).

The panel is therefore **not** a scheduler: a gesture is not a request, and
the one writer of requests is the scheduler app
([ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)). Two
tabs are two views and harmless, which is what the earlier arrangement could
not manage — it made them two holders of facing and two minters of ids. Modes
stop being exclusive: a timetable and a person are two sources of one
scheduler, and which of them a run has is configuration. Batch runs keep
byte-identical replay; a run carrying gestures makes no such claim, and a
benchmark run receives none.

A gesture the scheduler cannot compose is **dropped in silence** and lives in
the trace. It carries no id, so there is nothing to address an answer to, and
the panel renders the roster from the run — so an honest drag cannot produce
one ([ADR-0034](../adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

**Dragging a roster row onto a block**, and **dragging a train's marker onto
the pane**, are the two directions of one gesture: `tc49/dispatch/placement_wanted`,
`{train, block}`, with `block: null` for off the layout
([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)). Putting a
locomotive on the track and lifting it off are the same act with a different
destination, so there is one leaf and one answer — `train_placed` or
`train_removed`, which the picture follows, or `placement_refused` for one the
dispatcher does not accept
([ADR-0092](../adr/0092-an-app-reads-the-roster-again-for-a-train-it-has-not-got.md)).
The roster pane says the refusal under that train's row, in place of where it
is: *not on the roster*, *`<block>` is not on the drawing*, *`<block>` is not
free* or *too long for `<block>`*, from a wording table keyed by the generated
`PlacementRefusal`, so it is total. The line goes when the train is placed or
removed, or when its row is picked up again
([#1011](https://github.com/rails49/control/issues/1011)).

Placing is **live at any power**, and **only onto a free block**: no train
standing there, no other train's lock on it, and on no other train's
remaining route, read from `tc49/dispatch/state/allocation` — the
dispatcher's own rule, `DispatchState.free()`
([ADR-0080](../adr/0080-the-waiting-requests-are-a-list-a-person-orders.md),
BUS.md `placement_wanted`). The dragged train's own request and locks do not
count, because the dispatcher cancels that request before it asks. A row let
go over a block that is not free writes nothing, since the dispatcher would
drop it; this is a second pre-judgement beside the right-click's. With power
`on` the drag comes before the cars go down, so the block does not read
occupied with nothing claiming it. Taking a train off is live everywhere too:
it only frees track, and the blocks the train reads occupied in stay held by
it until they read clear
([ADR-0069](../adr/0069-a-train-comes-off-while-running-and-its-track-opens-when-it-reads-clear.md)).
The rows are still only while no session is joined. The dispatcher accepts a
block only while the run is held until
[#822](https://github.com/rails49/control/issues/822).
A train is picked up from any block its name is in, and a drop back on one of
them is the cancel gesture. A train between two blocks dropped on a block asks
for nothing. A drop with no block under it — back on the pane, or on bare
paper — writes nothing.

A train **mid-request is lifted off with its request**: the dispatcher cancels
whatever that train has and then takes it off, so `request_cancelled` arrives
before `train_removed` and the marker leaves a picture with no request behind
it ([ADR-0049](../adr/0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)).
That is the derailment case, and it is now a drag rather than a wait: a
locomotive that has stopped comes off in a person's hand instead of the hold
being released so the railroad can run it somewhere it is no longer going.
Dropping it back into a block is the same act pointed the other way, and
cancels the same request — `displaced` where `removed` was.

The gesture that ends a request **without** moving the train is **Cancel
request** on the block's right-click menu, which publishes
`tc49/dispatch/cancel_wanted` (`{id}`) naming the train's first request in
flight, and so ends whatever that train has, pending and active: the requests
chained after it go with it. One request alone is cancelled from its row in
the request list
([#660](https://github.com/rails49/control/issues/660), ADR-0049,
[ADR-0080](../adr/0080-the-waiting-requests-are-a-list-a-person-orders.md)). The
dispatcher republishes its picture when it cancels, and the lit route and
markers go out with the request it no longer holds; `request_cancelled` is
not read. A cancellation that lands while the train is between blocks waits
for the train to enter the block it was granted, and until then the route
stays lit, because the train still holds it. A second press in that window
does nothing. There is no confirmation.

The gestures a **throttle** rides on, `tc49/layout/take_wanted`,
`tc49/layout/throttle_wanted` and `tc49/layout/throttle_alive`, are drawn — in a
view of their own, [THROTTLE.md](THROTTLE.md)
([#207](https://github.com/rails49/control/issues/207),
[#291](https://github.com/rails49/control/issues/291)). Taking a train in a
throttle and turning it are a person's actions on a UI like any other, and
`INBOUND` is this app's write surface. The client they go out on is the
app's session (`ui/src/model/session.ts`): there is one connection per page,
so the throttle asks, the app carries and the session publishes.

**Right-clicking** the block a train stands in opens a menu with two items,
**Turn around** and **Cancel request**. **Turn around** publishes
`tc49/schedule/reversal_wanted` (`{train}`). The
scheduler flips that train's **facing** to the other run across the block —
`A-to-B` becomes `B-to-A` — and the arrow turns. That is the whole of the feedback: nothing
moves, no request is composed, and no `tc49/dispatch` topic carries anything.
On a **terminal block** the gesture is a no-op — one end is all the train can
leave by whichever way it is pointed, and facing never names an end that
leads nowhere ([#145](https://github.com/rails49/control/issues/145)). Facing
is otherwise fully determined once placed, routes being strict pass-throughs,
and deliberate reversal at rest is the one exception
([ADR-0019](../adr/0019-facing-is-scheduler-state.md)). It is what a train
that can run either way needs, and what switching needs: the panel should read
true before you drag anywhere.

A gesture of its own rather than a departure end named inside the drag. The
press location is the panel's last free motion, and a drag cannot say "turn
around and stay put", which is the whole case. A menu also says what it does
before you commit, which suits a gesture whose entire effect is one arrow
rotating, and no motion the drag uses can reach it: a plain click on a train's
own block is already the drag's cancel. Not "Reverse", which is the throttle's
word; this moves nothing. The same gesture is offered in the throttle view,
where the slider it must be at rest for is ([THROTTLE.md](THROTTLE.md)); the
human driver's controls hang there rather than on this menu.

Over bare paper, over an empty block, or with no session joined no menu opens,
and neither does the browser's own, which the drawing suppresses throughout.
A **second right-click is the first one over again**, and an open menu makes
no difference to it: the overlay that menu drops over the page — the one a
press outside is dismissed by — takes the press, puts the menu down, and hands
it on to whatever is under the point, so the menu opens on the train that was
clicked and the browser's own still does not
([#180](https://github.com/rails49/control/issues/180),
`ui/src/ui/dismissal.ts`). Any menu that wears the overlay gets it.

The menu a forwarded press opens is a menu like any other: it drops a live
overlay, and a left press outside it takes it down and reaches nothing
underneath, exactly as after a first right-click. Worth saying because it is
the *same* overlay, the two menus falling and rising too fast for the one in
between to be drawn ([#186](https://github.com/rails49/control/issues/186)).

**Turn around** is **greyed while that train has a request in flight**,
meaning any request from submit to completion, and **Cancel request** is
greyed while it has none. This is the panel's one pre-judgement of a
gesture, against the filter-free drag, and it earns the exception: a disabled
item says the train is busy, where silence says nothing. Reversing under a
queued request would produce a lie, since the request still departs the end the
facing named when it was composed: the train the arrow now points one way would
leave the other
([#295](https://github.com/rails49/control/issues/295)). A **rejected**
request leaves the train idle, its marker still on screen but nothing left to
move it, and that is precisely when you want to turn around. The scheduler
drops such a gesture anyway, a stale page always being able to send one.

An open menu outlives what it is about: the train it was greyed for can run
its request to completion and be somewhere else by the time the item ungreys,
and the session it would write to can go away under it. So the menu is taken
down when the train leaves the block it was opened over, and when the broker
goes, rather than turning a train around in a block nobody clicked or
publishing into a client that is reconnecting.

The panel is mouse-and-keyboard first. Touch works where the browser gives
it, iOS Safari raising `contextmenu` on a long press, and the drag that same
press began is cancelled. A press on a train takes hold of it with a finger as
with a mouse. A tap on a point is looser than a click, because a fingertip
covers about a square and rolls as it lifts: it need not land on the point,
but throws the offered point whose centre is nearest it within one grid
square, and it stays a tap for 12 screen pixels of movement where a click
allows 4. Two fingers pinch to zoom about their midpoint and pan by moving
together, as in the editor ([EDITOR.md#canvas](EDITOR.md#canvas), #894); the
second finger landing abandons the drag or the throw the first began, as a
cancel, so nothing is submitted.

**A click on a point throws it**
([ADR-0068](../adr/0068-a-person-throws-a-point-and-the-dispatcher-drops-it-on-a-lit-road.md)),
for testing: that an address moves the point it is wired to, and throwing
again a point that stuck. A plain left press on an unlit point that carries an
address, released on it without moving, publishes `tc49/dispatch/point_wanted`
with the address and the other position from the one drawn — `thrown` where
none is known. A press on a train takes hold of the train first, so dragging
one across a point throws nothing. A lit point, a point wearing an address a
lit point also wears (two symbols may share one), and a point with no address
offer no click: no pointer cursor, and a click publishes nothing. That is the
dispatcher's own rule, which drops the request when any point wearing the
address is lit; the dispatcher is still the one that judges, the panel's
picture of the lit roads being able to be a moment old, and a request it drops
is not reported. The panel does not move the drawn position itself: it follows
`wanted/point` when `layout` writes it. Shunting a train off its route is not
what this is for — trains still move only on granted routes, and reversal
happens only between requests, at rest.

**A click on a button or a toggle presses it** (ADR-0087, #929), whatever
the track power: a widget is not the railroad's, and a person may want the
lights on with the track dead. A widget is drawn over the symbols, so a plain
left press on one is the widget's before it is a train's or a point's, and a
release on the same widget, without moving further than a click allows, is
the press. A **button** publishes its payload on `tc49/ui/button/<name>`, once
per press and not retained. A **toggle** publishes the payload of the other
position from the one it shows on `tc49/ui/state/toggle/<name>`, retained, and
its `on` payload where it shows neither, a default it shows counting as the
position; the knob moves when the row comes back, not on the press. A text
widget is not pressed: its words may run over the track, so a press on them
is what is under them, a train or a point (#939). Control sends
the payload and reads none of it: it goes out as it was typed, never through
`JSON.stringify`, and what it does is the listener's business.

## Implementation

The asset store already has an HTTP face, built for the editor and belonging
to the store ([EDITOR.md](EDITOR.md#implementation)). The bus the panel reads
is the broker, reached over a WebSocket at `/mqtt` on the page's own origin
with MQTT.js as the client
([ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
decision 4): the browser is a participant like every app, and there is no
relay of ours in front of it. `?broker=` names one somewhere else and is the
whole of the page's configuration. Validation stays in the existing Python
validator, and the front end shares the editor's stack and symbol library.

**The broker says which railroad it is.** One broker runs one railroad, and
the layout interface publishes its name on `tc49/layout/state/railroad`
(ADR-0059, decision 2,
[#371](https://github.com/rails49/control/issues/371)). The session reads
that row, and the app has the loaded railroad (`ui/src/model/railroad.ts`)
read the drawing and the review off the store — so the picture and what feeds
it can never be two railroads. A row naming `""` is no railroad loaded: the
session leaves, the loaded railroad reads no roster, and the band says `no railroad loaded`; the editor and the stock view
hold nothing for it either (#734). The band names this row's railroad, which
is the one the editor holds (ADR-0072, decision 3).
Which railroad that is, is a person's choice made while the apps run: the
Railroad tab of the settings dialog behind the band's gear publishes
`tc49/layout/railroad_wanted` and this view carries the
press, the layout interface answers it and the row moves
([ADR-0060](../adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)).
The press loads nothing by itself: with power on it drains the track first and
asks once the row reads `off` (ADR-0085, decision 5), and a gesture nothing
answers leaves the page where it was. The dialog closes once the page holds
the new drawing and the dispatcher has said `state/allocation` since the row
named it, and the page then shows this view (EDITOR.md). The page subscribes
`tc49/#` and publishes only the browser-writable rows. With anonymous clients
a broker cannot tell a page from an app, so that set is convention rather than
enforcement, and it is what keeps ADR-0036's single-minter argument holding.

**A widget's row is read before anything is read as JSON.** Every other
topic the page hears carries a JSON object, and the session reads it as one;
a widget's payload is raw (ADR-0087, decision 4), so the session takes
anything under `tc49/ui/` first, keeps a state row as the text it arrived as,
and lets a button's press go by. A payload there that is not JSON is neither
an error nor dropped, and changes no other row.

**A page joins in the middle of a cold start.** The retained rows arrive as
the subscription lands, which may be before the store has answered for the
documents the model is built from — so what arrives in between is held and
applied the moment there is a model, rather than dropped for the want of one
that was seconds away. Nothing republishes a retained row for a late reader.

**A box driving a command station** runs the **physical binding** — the
`layout` app with the `dccex` translator beside it, where a simulated box runs
`simulator` instead ([layout](../layout/README.md),
[`docs/dccex/README.md`](https://github.com/rails49/dccex/blob/main/docs/dccex/README.md) in
[`rails49/dccex`](https://github.com/rails49/dccex), where the translator
lives). No app's command line names the railroad: a person loads one from the
settings dialog's Railroad tab while the apps run, the store records which, and the box
comes back on that one
([ADR-0060](../adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md),
[ADR-0072](../adr/0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md)).

**That box sees only what somebody types.** No camera publishes a detector's
level on a physical railroad yet, so for the first train a person supplies the
readings: a line typed at `tc49 readings` — `<block>.<end> <level>`, the levels
being `occupied`, `clear` and `unknown` — is published as the row a detector
would write, and `layout` folds a typed pair into `block_occupied` and
`block_vacated` exactly as it folds a camera's
([#315](https://github.com/rails49/control/issues/315)). The panel is told
nothing about who typed it: what it is served is the sensor row, retained like
any other, and the arrival that follows. **It is not a panel gesture** — a
device row is not one of the browser-writable rows — and a page grows no
control for one: a detector stands in
for hardware, not for a person's hand. Until a camera publishes, an arrival
nobody types never comes, so a granted move rolls on; the run comes up
**held** like every other, which is the whole of the safety mechanism, and the
banner says where the railroad's readings come from. The banner also counts how
many of the railroad's trains carry an address and how many do not, because a
move for a train whose cars carry none writes no traction row at all.

**A broker that went is not a reason to reload the page.** There is no choice
left for a person to make, so getting back in is nobody's press: MQTT.js
reconnects on its own, **every three seconds**, and resubscribes — and a fresh
subscription is answered with every retained row, so the page comes back on
the dispatcher's own picture rather than on an empty layout
([ADR-0032](../adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
Three seconds is long enough not to hammer a port nothing is listening on and
short enough to land while the operator is still looking at the tab.

The store's retry is not this view's. What stock a railroad owns is its asset
and no topic carries it (ADR-0039), so a roster read the store did not answer
is made again on the same interval until it lands, by the loaded railroad
(`ui/src/model/railroad.ts`), which reads the drawing and the stock view's
documents again on the same one timer. A refusal is read once. The interval is
`RETRY_MS` in `ui/src/model/store.ts`, where it is argued and where a test reads
it rather than spelling 3000.

**The band reports the wait rather than the page looking dead.** It has no
word for the link either way ([#517](https://github.com/rails49/control/issues/517)):
a broker that is answering is the ordinary case and says nothing, so the one
time the link speaks is the time it is down. What stands there is the trouble
the last failure named — *no broker at ws://…/mqtt — is the bus running?* where
there is nothing at the address or where the connection has closed under a live
run. What a failed roster read said stands there too, the loaded railroad's,
and clears when a read lands.

The words name the address and ask the one question a person can act on. A bare
*not connected* leaves them with a working app and no idea which of several
containers is down; the broker is the first hop and the only one this page opens
itself, the store being asked over HTTP and saying so in its own words, so
naming it is naming what to look at. `gone` in `ui/src/model/session.ts` is the
sentence, exported so a test reads it rather than respelling it — the same
reason `RETRY_MS` is read off its module. It is said on `close` as well as on
`error`, so a page that loses the broker mid-run does not go quiet just because
the connection opened once.

**A call to the store fails in three ways and the words say which**
([#411](https://github.com/rails49/control/issues/411)). *Nothing answered* —
`fetch` rejects, the connection refused — is *the store is not answering — run
`tc49 serve`*: the store is what is missing and starting it is the fix. *An
answer that is not the store's* — a status with a body that is not JSON, which
is what a proxy's own 404 page or a 502 from one whose upstream is down looks
like from here — says what was asked and what came back: *GET
/rosters/toy/trains answered 404*, with the status text where the browser gives
one. It guesses at no cause; this side does not know there is a proxy. *The
store's refusal* is the store's own words, passed through. Which of the three
it was is decided once in `ui/src/model/store.ts` and every screen shows the
result — the one fixed string that used to stand here sent a person after a
store that was up and answering, the proxy in front of it having answered with
its own page ([#405](https://github.com/rails49/control/issues/405)).

**A run comes up with an empty layout and held.** There is nothing on the
rails until a person puts something there: every train the railroad owns is in
the roster pane, and the placing gesture is honoured at any power
([ADR-0037](../adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md),
[ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)). A **scenario** is
the harness's file and never reaches the browser: `bench/replay.py`
replays one as the gestures a person would make, over these same topics.

Beyond the name, joining takes everything off the bus. Placement, locks,
routes and live requests come from the dispatcher's retained picture;
**facing**, which is scheduler state and on no dispatcher topic at all
([ADR-0019](../adr/0019-facing-is-scheduler-state.md)), comes from the
scheduler's own retained topic. Both are written by apps that are always
running, so there is no cold start to seed, and no topic describes the run — a
topic that did would be the transport describing itself (#67). The one thing the
view takes from the store is the loaded railroad's roster
(`GET /rosters/<railroad>/trains`, read by `ui/src/model/railroad.ts`) — what stock there is and how long each train is,
an asset rather than a fact about the run, which is the line
[ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)
already draws. Everything else is derived from the bus: the state topics carry
the whole picture, facing included, so the model is fed by `apply` and by
nothing else.

A railroad just loaded needs no handshake either. Every app cleared the rows
it owned and republished them (ADR-0060), so the broker holds the new
railroad's retained picture and hands it over on subscribe like any other —
placement, facing and aspects among it. There is no registration and no swap
to request: those were the bridge's, and it is gone
([ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)).

A run paces itself on a wall clock: the simulator's transit delays are
the railroad's tempo, and the period only sets how often the loop
takes what the broker's network thread left waiting
([ADR-0047](../adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
On the physical binding the tempo is the trains, and the period also bounds
how soon a settled detector level is acted on. The knob is each app's own
`--period`, set where the app is started, so it is not the panel's to turn.

**A panel may join a run already going.** The broker answers a subscription
with each state topic's retained value before any event, so the page opens on
the dispatcher's own picture —
standing trains, locks, committed routes, live requests off
`tc49/dispatch/state/allocation`, aspects off `state/aspects`, what the
detectors dispute off `state/disputed`, facing off
`tc49/schedule/state/facing` — rather than on an empty layout
([ADR-0032](../adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
Rejoining is not recovery: nothing was lost, and the dispatcher was
holding the truth the whole time
([SYSTEM.md](../SYSTEM.md#interruptions)).

**The page keeps the later of two state values.** Every state payload carries
a stamp, `at`, and the model applies the one with the later stamp whichever
order the two arrive in — equal replaces, an earlier one is ignored, and a
value carrying no stamp is taken and starts the ordering again (BUS.md,
the bus; [#240](https://github.com/rails49/control/issues/240)). A page is a
consumer of state topics like any other, and a pair the wire handed over
backwards would leave a person looking at aspects the railroad has moved on
from, or at rails the page says are dead over live track. Events pass
straight through: a repeated sensor reading re-asserts a level. The stamps go
when the model starts over.

**A run outlives any one app's process.** The broker holds the retained rows
and each app adopts its own coming up, so a restarted app opens on the
placement and facing the last one left rather than on an empty layout
(BUS.md, the bus;
[ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 3). The page reads nothing new for it: placement arrives on
`state/allocation` and facing on `state/facing` exactly as they do on a
rejoin. What the picture gains is `crossing`, train → the transit it was
crossing when everything stopped: a placement hint with no route behind it,
drawn in the blocks as above, and the one train the dispatcher cannot
place on its own. It comes up **held**, so nothing moves before the placement
has been checked
([ADR-0037](../adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
Restart is not rejoin and neither is recovery
([SYSTEM.md](../SYSTEM.md#interruptions)).

`wrong_origin` still stands
([ADR-0021](../adr/0021-a-bad-request-is-answered-not-raised.md)) — a drag
composed while a train is moving can still name a block it has left by the
time the request lands — but it stops being the ordinary consequence of
opening the page.

Request ids are not the page's business at all. The scheduler mints them from
one undivided counter, so a reload, a second tab and a rejoining page are all
incapable of re-using an id the dispatcher has seen — which is a fresh page
having nothing to re-use, rather than a page minting carefully
([ADR-0033](../adr/0033-a-request-id-is-unique-not-meaningful.md),
[ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)).

The front end keeps the editor's model/component split. `model/panel.ts` turns
bus payloads into render state and holds no scheduler state: facing arrives on
its topic and ids arrive on `request_submitted`. `model/drag.ts` turns pointer
positions into an arrival-end set or a cancel, DOM-free and tested the way the
editor's gesture model is; `trainAt` there is the one question the press and
the right-click share, so the two can never disagree about which train was
clicked. It answers the same `Machine` (`model/machine.ts`) the editor's
`Gesture` does, so the canvas drives one gesture sequence and converts pixels
into squares in one place; composing the drop into a frame and writing it to
the bus stays this view's, the model naming the train and the ends and nothing
else. `tc-menu` renders the items it is given, the editor and the run view
each working out their own list. `model/scene.ts` is what the drawing alone
answers: the frame a fit and an export are drawn in, an arrow's pose, and
which symbol an address is worn by. The session is `model/session.ts`, held by
the app ([#756](https://github.com/rails49/control/issues/756)): the page's one
connection, the railroad the row names, the rows held until the documents
land, the panel model it feeds, power and the driving mode, and every frame
the page sends. `tc-panel` reads the model
off it, hands the canvas an overlay, hands `tc-roster` the railroad's roster
marked with where the run has each train, and gives the session the gestures
it composes. Where a drag from the pane landed is asked of the canvas, which is
what turns a client pixel into a point on the drawing.

**The component gets a suite where only mounting it can see the answer.** Each
rule is tested at its own seam — `trainAt` in `drag.test.ts`, `shows` and
`inFlight` in `panel.test.ts`, `litLast` in `inspect.test.ts` — and not one of
them can say whether this view asked. So `reversal.test.ts` mounts the app in
this view and drives the right-click, and `run.test.ts` walks the session: a
menu offered over a train's block and nowhere else, the browser's own menu
suppressed either way, one `reversal_wanted` and no second frame, a refusal
shown in the band rather than swallowed, and a menu coming down when the train
leaves the block or the session goes. The session's own rules — the power and
driving presses, the rows held for the documents, and that a frame changing
nothing the app shows leaves `status` and `cabs` the same objects — are driven
against the broker double with no DOM in `session.test.ts`. The last of the
menu's is
the shape both bugs
[#124](https://github.com/rails49/control/issues/124) found in Chrome took,
and catching that shape is what the suite is for
([#157](https://github.com/rails49/control/issues/157)). It walks the session
going away as well, on fake timers so nothing waits three seconds: a store
that would not answer for the roster is asked again when the interval is up,
one try is ever waiting, and a read that lands ends the tries
([#183](https://github.com/rails49/control/issues/183)). The session they run
against — the toy railroad, the broker double and the app joined to it — is
`ui/test/support/session.ts`, written once for every suite that needs one. The
double stands where MQTT.js does, answering a subscription with the rows it
holds retained, because what a suite about the run view has to drive is the
broker's side of it.

The railroad it paints is not its own: the app holds it and hands over the
drawing and the review (ADR-0038). The name comes the other way — the session
reads it off the broker's retained row and the app loads the documents — and
the connection is opened once the app is on the page, for as long as it is
there.

The chrome is the band and the rail the editor also wears (#84,
[EDITOR.md](EDITOR.md#the-band),
[ADR-0073](../adr/0073-the-chrome-comes-from-look.md)), both `@rails49/look`'s.
The **band** is the whole system's: the railroad the app has loaded and
whether it is *unsaved*, the health area — the store or the broker not
answering, a fault the hardware reports on the supply, how far the run has
got, and a store that is not being backed up
([EDITOR.md](EDITOR.md#the-band)) — and the fast clock, then the
**driving control**, the last of its items, and track power, a power toggle whose colour says where the supply
stands and a stop sign beside it; then the gear and Help
([org ADR-0020](https://github.com/rails49/.github/blob/main/docs/adr/0020-the-bands-right-ends-with-the-gear-and-help.md)).
The **rail** is the views, and then this view's document's: zoom out, zoom in
and fit as icon buttons, and nothing after them.

**Nothing that is going right reads in the band**
([#517](https://github.com/rails49/control/issues/517)). It carried six entries
with five of them saying the ordinary thing, and a status line that is always
full is one nobody reads. Track power is the colour of the power toggle
rather than a word repeating it; a frozen drawing has no word either, the
Edit view not opening with power on and its button's title saying why
([#891](https://github.com/rails49/control/issues/891)); and the link has no
word at all.

**The driving control is one press and no confirmation**, where GO and HOLD
were
([ADR-0079](../adr/0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md)).
It is a `look-band-press`, the last of the band's items just before track
power, and it is there in every view: the mode is the whole railroad's, not a
view's
([#871](https://github.com/rails49/control/issues/871),
[#873](https://github.com/rails49/control/issues/873), org
[ADR-0020](https://github.com/rails49/.github/blob/main/docs/adr/0020-the-bands-right-ends-with-the-gear-and-help.md)).
It shows the railroad's driving mode by its glyph and tooltip rather than a
word or a colour — a person (`person-fill`) for manual, a robot (`robot`) for
automatic — and a press publishes `tc49/layout/driving_wanted` naming the
other one. It draws `tc49/layout/state/driving` off the picture rather than
the last press, so a gesture that did not land leaves the glyph where it was,
and it is dead, showing the person, with no
session joined and until `layout` has said the mode. `layout` accepts the
gesture at any power, so power does not grey it. `model/commands.ts`
`driving()` decides what it shows.

**The band says where power stands**, reading `tc49/layout/state/power`: the
power toggle is green for `on`, pulses green for `draining` and is dimmed for
`off`, and its tooltip says which
([ADR-0078](../adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
Until the station has said where power stands the control is dead and says
*Waiting for the station*.

**The band shows what the hardware says is wrong with the supply**, in the
health area beside the store and the broker
([#602](https://github.com/rails49/control/issues/602)). The session reads
`tc49/layout/state/device/track` into the panel model
(`ui/src/model/panel.ts`), one of the two device rows a view reads with
`device/sensor` above, and keeps the free-text `reason` alone: `power` there is one translator's
reading of its own hardware, and what the picture draws is the railroad-wide
`state/power` that `layout` folds it into. The reason is what nothing else
carries. A district reaches no topic, so a trip the command station cut itself
is said there or not at all, and that frame reads `power: on` while the rest of
the railroad is powered
([ADR-0050](../adr/0050-broken-hardware-is-reported-never-worked-around.md),
[BUS.md](../BUS.md#device-vocabulary)). So it is read whichever way the supply
stands, shown verbatim, and cleared by a frame that carries no reason. It is
ordered like every other state row — the row is named `device/track` the way
`tc49.lib.trace` names a device row, where `track` alone would not tell it from
the `wanted/track` that `layout` writes on a press (`model/trace.ts`,
[ADR-0043](../adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).

**The power toggle and the stop sign command power**, on
`tc49/layout/power_wanted`
([ADR-0078](../adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md),
[ADR-0073](../adr/0073-the-chrome-comes-from-look.md)). The toggle asks for
`draining` from `on`, and for `on` from `off` or `draining`: one press turns
the railroad on, one starts the drain, and one during a drain ends it. The
stop sign asks for `off`, the emergency stop: power straight off, without a
drain. look's control says what was pressed in its own words — the toggle
`off` from `on` and `on` otherwise, the stop sign `stopped` — and `asked()`
in `model/commands.ts` turns those into the railroad's. They stand in the band
beside the reading they act on, because power is the whole railroad's and no
document's. They are dead with *Waiting for the station* before the station
has said where power stands and while the broker is not answering, a press it
would swallow being a press that did nothing. `supply()` in
`model/commands.ts` decides what the control shows. The stop sign is not
greyed when power already reads `off`: the gesture names where power should
stand rather than asking for a change, so a press that agrees with where it
stands is not a race. The topic is `layout`'s because `layout` is what
answers it, and `layout` answers by writing the desired power of the device
vocabulary — a page never reaches a translator.

**The stop sign is one click with no confirmation**: an emergency stop that
asks "are you sure?" is not one, and a train it leaves between blocks carries
on with its move when power is back `on`. **ON saves first**
while the loaded railroad has unsaved edits and power is off, since this view
draws the open drawing: the drawing is written, and `on` is sent once the
apps have built it. With power on or draining it never waits
([EDITOR.md](EDITOR.md#track-power-freezes-the-drawing),
[ADR-0085](../adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md)).

**ON waits for a valid drawing.** While the loaded railroad reads
`built: false` the toggle is dead from `off` and from `draining` with *Fix
the drawing first*, and a press sends no `power_wanted`: the apps built
nothing from the saved drawing, and trains would run under a build that is
not the drawing the store holds. From `on` the toggle is the drain, and it
and the stop sign stay live, a supply that is on being one a person may
always take off
([ADR-0085](../adr/0085-the-editor-saves-when-it-is-left-and-a-railroad-can-be-named-without-being-built.md),
decision 4, [#886](https://github.com/rails49/control/issues/886)).

**The drain is `layout`'s, and the page waits for nothing.** The toggle
publishes `power_wanted: draining` and stops there: `layout` switches the
supply off once `tc49/dispatch/state/moving` says no train is moving, and what
the toggle then shows is `state/power` reading `off`
([ADR-0078](../adr/0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md)).
While power reads `draining` the toggle pulses green and the stop sign stays
live. A drain that never lands leaves the railroad powered and the toggle
still saying so. The page reads `state/moving` into the panel model
(`Panel.moving`) and decides nothing on it.

**This view has no control of its own.** The session select it used to carry
is gone: the broker says which railroad is on screen and the app loads it
([#371](https://github.com/rails49/control/issues/371)), and the one control
that asks for another is the band's, both views being of one railroad
(ADR-0038, ADR-0060). What its header still draws is the trains a rebuild
took off, and only while there are any.

**A rebuild that took trains off says which, one line each.** A rebuild under
the same name places a train again only where its block is still in the
drawing and still holds it
([ADR-0071](../adr/0071-a-rebuild-under-the-same-name-keeps-the-placements.md)),
and the dispatcher lists the rest on `tc49/dispatch/state/unfit`. The view
draws a line per train in its header — *`<train>: block <block> is
gone`* or *`<train>: block <block> is shorter than the train — place it
again`* — and nothing while the list is empty. The dispatcher drops a train
from the list once it is placed, so the lines go as a person puts the trains
back, and the view keeps no copy of its own
([#709](https://github.com/rails49/control/issues/709)).

**The run view's one source is the bus.** It could read a recorded trace and
step through it, which is how it was built before there was anything live to
join and how its colours were looked at afterwards. Both reasons expired,
and the chrome that took — a drawings list, a file opener, a transport and a
rate in boundaries per second — is most of what made this view's row hard to
merge into a shell's, all of it meaningless to an operator
([ADR-0038](../adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
Traces stay exactly as
[ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md) has
them: the tap records every event, metrics derive from recordings, and
benchmarks assert byte-identical replays. That is analysis, and analysis is
the harness's.
