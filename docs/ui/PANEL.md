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
Terminology follows [CONTEXT.md](../../CONTEXT.md).

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
labels, the arrows, the aspects, the markers and the drag's rings. It arrives
as one overlay object worked out in `model/panel.ts`, so the component still
computes nothing.

**So the run view has zoom, pan and fit**, on the same keys and the same bar
buttons as the editor — `+`, `−`, `0`. It had none of the three while it drew
its own picture fitted to the sheet, which is what a railroad too large to see
at once cost.

**The railroad's roster is listed in the left pane.** The shell has one
left-pane slot and each view fills it: the editor's palette, this view's
`tc-roster` ([#169](https://github.com/rails49/control/issues/169)). A row is
a train's name, its length, and where the run has it — the block it stands in,
*crossing a transit* where it stands in none (on the layout all the same), or
*off the layout*. Ordered by name, so the list does
not reshuffle as the railroad moves.

A railroad's **roster** is every train it owns, whether on the layout or off
it ([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)), so the pane is
fed from two places: `GET /rosters/<railroad>` for what there is and how long
each train is, and `tc49/dispatch/state/allocation` for which of them the run
has. Two sources because they are two things — the store serves the railroad's
assets, the bus carries the run
([ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)) —
and the pane is handed one list. A train the picture has and the roster does
not still gets a row: it is on the layout, and hiding it would hide what the
operator can see. The roster is read when the session is joined and forgotten
when it is left: a page told nothing must not claim every train is off the
layout.

Trains standing nowhere have rows because those rows are what there is to drag
back onto the railroad. It is also the pane that unfreezes the drawing
([EDITOR.md](EDITOR.md#trains-on-the-layout-freeze-the-drawing)): while a
session has trains placed the editing view is read-only, and taking the last
one off is what ends that.

**A train between two blocks is drawn on the connection**, midway between the
two block ends its transit joins, and stands in no block. The picture's
`crossing` is what says so, train to the transit taking it out of the block
`trains` still names: the block the sensors last confirmed it in, which keeps
its lock and its colour and loses the name and the arrow
([#154](https://github.com/rails49/control/issues/154)).

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

A live session is the one that locks that way: `tc49 live` assembles its
dispatcher with `Incremental`, so a page joining a session is watching an
incremental run
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

There are no sensor dots at block ends. `block_occupied` and `block_vacated`
carry a block, and the layout interface publishes anonymous occupancy and
never asserts train identity. RocRail's two dots depict per-end detection,
which is finer than anything on this bus. Train identity is reconstructed
from `lock_granted`, exactly as the dispatcher does. Direction is not derived
here at all: it is the train's **facing**, read off
`tc49/schedule/state/facing`, which the scheduler keeps from the entry end of
each granted transit and from a committed route's departure end
([ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md)). A
train that has never moved has an arrow for the same reason a moved one does.
The value is the run the train would make across its block, `<block>.A-to-B`
or `<block>.B-to-A` (CONTEXT.md, **Facing**), and the arrow points at the end
that run comes out at — B for `A-to-B` — which is the whole of the reading.

**Point positions are read off `align`.** The command carries the points it
needs as address-and-position pairs
([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md)), and the
panel holds the drawing, so an address maps back to the symbol wearing it.
Two points wearing one address lie the same way, and an address no symbol
wears is ignored. A point stays where the last command naming it left it,
`align` speaking for one transit only. Each is drawn in its position, the road
the other position offers faint, so a turnout shows its straight road or its
diverging one and a slip's tick says which road it has. The panel infers
nothing, which supersedes the inference
[ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md) put here.
It still shows commanded position, not measured position, so a point that
failed to throw looks fine. Reported position becomes worth adding if hardware
with point feedback ever exists; the owner's points do not report. Only a
drawing whose points carry addresses can show any of this, and
[`gotthard/positions`](../../scenarios/gotthard/positions.scenario.yaml)
is the scenario that does — one train across two junctions, which is the
picture to run when the styling is what is being looked at (#130).

**Signals are part of the block symbol.** A block carries a signal at each
end, always, so there is nothing to place and nothing in the drawing to
record. A signal governs departures through one block end, and routes are
strict pass-throughs with no reversal within a route, so a signal at
`claro_2.B` can only mean "may the train in `claro_2` leave via B".

**The panel derives no aspect.** The dispatcher publishes one — `stop`,
`caution` or `clear`, read off how far ahead it has locked — on a last-value
topic naming every signalled end, and the panel renders what it is told
([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
An aspect is a function of locks the dispatcher holds and routes it committed,
so a second party working it out is a second authority to disagree with.

Two questions the panel's own locked-ahead derivation raised are answered by
not arising. Whether an end the standing train does not face may show anything
but red: the dispatcher knows the committed route, so it knows the one end a
train may leave by, and every other end shows `stop` because nothing is locked
beyond it. And the middle aspect, which the binary derivation could not
produce at all: the dispatcher counts the depth, so `caution` and `clear` are
simply two different counts.

An end that leads nowhere carries no signal and the dispatcher does not name
it, so the panel draws none — no rule here, just an end absent from the map.

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
the train enters through, as [CONTEXT.md](../../CONTEXT.md) defines it — and
the middle third names both, "either way round". Dropping on the train's own
block cancels. The departure end is never part of the gesture: it is the
train's **facing** end, which the scheduler holds and the dispatcher never
sees ([ADR-0019](../adr/0019-facing-is-scheduler-state.md)). Neither is the
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
`train_removed`, which the picture follows.

Both are **greyed while the run is running** and the pane says why. A
placement is accepted only while the run is **held**: the dispatcher grants
against its picture of where the trains are, and a block that fills or empties
under it invalidates what it has already granted. This is a second
pre-judgement beside the right-click's, and it earns the exception for the
same reason — a still row says the run is running, where a swallowed gesture
says nothing. A drop with no block under it — back on the pane, or on bare
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

The gesture that ends a request **without** moving the train,
`tc49/dispatch/cancel_wanted`, is the panel's to place and is not drawn yet.
Neither is `tc49/dispatch/request_cancelled` read yet: a request the panel is
following and somebody ends stays in its list until the train is dragged
again, which is the reading to add with the gesture.

The two gestures a **throttle** rides on,
`tc49/layout/mode_wanted` and `tc49/layout/throttle_wanted`, are drawn — in a
view of their own, [THROTTLE.md](THROTTLE.md)
([#207](https://github.com/rails49/control/issues/207),
[#291](https://github.com/rails49/control/issues/291)). Taking a train in a
throttle and turning it are a person's actions on a UI like any other, and
`INBOUND` is this app's write surface. The socket they go out on is this
view's: there is one session per page and this is what joins it, so the
throttle asks and the run view writes.

**Right-clicking** the block a train stands in opens a menu with one item,
**Turn around**, which publishes `tc49/schedule/reversal_wanted` (`{train}`). The
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
where the lever it must be at rest for is ([THROTTLE.md](THROTTLE.md)); the
human driver's controls hang there rather than on this menu.

Over bare paper, over an empty block, or with no session joined no menu opens,
and neither does the browser's own, which the drawing suppresses throughout.
A **second right-click is the first one over again**, and an open menu makes
no difference to it: the overlay that menu drops over the page — the one a
press outside is dismissed by — takes the press, puts the menu down, and hands
it on to whatever is under the point, so the menu opens on the train that was
clicked and the browser's own still does not
([#180](https://github.com/rails49/control/issues/180),
`ui/src/ui/dismissal.ts`). It holds for the bar's menus and the band's picker
too: all three wear the one overlay.

The menu a forwarded press opens is a menu like any other: it drops a live
overlay, and a left press outside it takes it down and reaches nothing
underneath, exactly as after a first right-click. Worth saying because it is
the *same* overlay, the two menus falling and rising too fast for the one in
between to be drawn ([#186](https://github.com/rails49/control/issues/186)).

The item is **greyed while that train has a request in flight**, meaning any
request from submit to completion. This is the panel's one pre-judgement of a
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
down when the train leaves the block it was opened over, and when the bridge
link drops, rather than turning a train around in a block nobody clicked or
sending into a closed socket.

The panel is mouse-and-keyboard. Touch works where the browser gives it, iOS
Safari raising `contextmenu` on a long press, but is not designed for; the one
care taken is cancelling the drag that same press began.

Manual turnout throwing is not offered. RocRail allows it because it owns
manual shunting, which this model excludes: trains move only on granted
routes and reversal happens only between requests, at rest. A turnout now has
an address a command could name
([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md)), so what
rules this out is no longer the absence of one: a second authority deciding
what is safe would sit alongside the dispatcher.

## Implementation

The asset store already has an HTTP face, built for the editor and belonging
to the store ([EDITOR.md](EDITOR.md#implementation)). The panel adds the other
half: a bridge from `tc49/#` to the browser over a WebSocket. That is not a
store operation and does not live with one. Validation stays in the existing
Python validator. The MQTT transport switch later changes only what the bridge
subscribes to. The front end shares the editor's stack and symbol library.

**The loaded railroad is the session.** A run is built from a railroad and
nothing else ([#171](https://github.com/rails49/control/issues/171)), so the
band's picker is the only thing that sets which one, and the run view has no
session of its own to pick. The loaded railroad rides in the socket path —
`ws://localhost:5173/live/gotthard` — so the one choice says both which
drawing to render and which railroad feeds it. A socket opened without it would render
one railroad on another's events, which is what a session whose railroad was
fixed at launch allowed (#148). Switching is a reconnect, which is what
joining already was. No inbound topic carries any of it: the set stays exactly
the browser-writable rows that ADR-0034's broker ACL will grant, and that is what
keeps ADR-0036's single-minter argument holding.

`tc49 live` takes the railroad as an optional argument. With none it comes up
idle on its port waiting to be told; with one it starts running that railroad
and the band may still switch it. Naming the running railroad joins it
mid-run. Naming another tears the assembly down, builds a fresh one for that
railroad, and closes any client still on the old path — one operator, one
railroad. **A client the session closes lets go of it entirely**: it holds no
run, so the roster empties and the drawing thaws rather than freezing on a
picture nobody is maintaining. Naming a railroad that does not exist gets an
`{"error": …}` frame and a close, with the running railroad untouched: a typo
must not take a live session down. A run outlives its clients, so closing the
browser leaves the railroad running and Ctrl-C ends the session.

**A session that went is not a reason to reload the page.** There is no choice
left for a person to make — the loaded railroad *is* the session, and the
band's picker says nothing about a name it is already showing — so the page
tries the same railroad again on its own, **every three seconds**, until it is
joined or another railroad is loaded. Three seconds is long enough not to
hammer a port nothing is listening on and short enough to land while the
operator is still looking at the tab: one already open is on a restarted `tc49
live` about three seconds after its bridge answers, with nothing pressed. Only
one try is ever waiting, so a picker pressed during the wait does not start a
second, and a try that comes round to a session joined by then leaves it
alone. What runs is the same `join` any other way in runs, so a
session reached this way is a session reached any other way — the roster read
afresh, the run's retained state drained on connect
([ADR-0032](../adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
The interval is `RETRY_MS` in `ui/src/ui/tc-panel.ts`, where it is argued and
where a test reads it rather than spelling 3000.

**The band reports the wait rather than the page looking dead.** The
*connected* badge belongs to a joined session and goes with it, so while the
session is gone the band says nothing about the bridge — *not connected* is
what a joined session whose socket is not answering says, not what a page
between tries says. What stands there instead is the trouble the last failure
named: *no session at ws://…/toy — run `tc49 live`* where the bridge went, and
*the store is not answering — run `tc49 serve`* where a try got no roster. A
close with nothing failing behind it — the session switching railroads under
the page — names none of that, and the band is quiet until a try lands. The
badge is back at *connected* when one does.

**A run comes up with an empty layout and held.** There is nothing on the
rails until a person puts something there: every train the railroad owns is in
the roster pane, and the run is held so the placing gesture is honoured
([ADR-0037](../adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md),
[ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)). A **scenario** is
the harness's file and never reaches the browser: `tc49 live --scenario`
replays one as the gestures a person would make, over these same topics.

Beyond the name, joining takes everything off the bus. Placement, locks,
routes and live requests come from the dispatcher's retained picture;
**facing**, which is scheduler state and on no dispatcher topic at all
([ADR-0019](../adr/0019-facing-is-scheduler-state.md)), comes from the
scheduler's own retained topic. Both are written by apps that are always
running, so there is no cold start to seed, and no topic describes the run — a
topic that did would be the bridge describing itself (#67). The one thing the
view reads from the store is the loaded railroad's roster
(`GET /rosters/<railroad>`) — what stock there is and how long each train is,
an asset rather than a fact about the run, which is the line
[ADR-0010](../adr/0010-asset-store-serves-coarse-read-only-documents.md)
already draws. Everything else is derived from the bus: the state topics carry
the whole picture, facing included, so the model is fed by `apply` and by
nothing else.

A railroad the session has just built needs no handshake either. Its
`last_values` are empty, so there is nothing to seed: the client is
registered, the swap requested, and the new run's opening drain delivers
placement, facing and aspects as live frames, in order.

A session paces itself on a wall clock: the simulator's transit delays are
the railroad's tempo, and `tc49 live --period` only sets how often the loop
polls for commands arriving over the bridge
([ADR-0047](../adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
The knob is the session's and applies to every railroad it runs, so it is
not the panel's to turn: a joined panel names the railroad and nothing
else.

**A panel may join a session already running.** On connect, the path naming
the railroad that is running, the bridge sends each state topic's last value
before any live frame, so the page opens on the dispatcher's own picture —
standing trains, locks, committed routes, live requests off
`tc49/dispatch/state/allocation`, aspects off `state/aspects`, what the
detectors dispute off `state/disputed`, facing off
`tc49/schedule/state/facing` — rather than on an empty layout
([ADR-0032](../adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
Rejoining is not recovery: nothing was lost, and the dispatcher was
holding the truth the whole time
([CONTEXT.md](../../CONTEXT.md#interruptions)).

**The page keeps the later of two state values.** Every state payload carries
a stamp, `at`, and the model applies the one with the later stamp whichever
order the two arrive in — equal replaces, an earlier one is ignored, and a
value carrying no stamp is taken and starts the ordering again (SYSTEM.md,
the bus; [#240](https://github.com/rails49/control/issues/240)). A page is a
consumer of state topics like any other, and a pair the wire handed over
backwards would leave a person looking at aspects the railroad has moved on
from, or at rails the page says are dead over live track. Events pass
straight through: a repeated sensor reading re-asserts a level. The stamps go
when the model starts over, a rejoined page meeting a session whose clock
starts where that session did.

**A session may outlive its process**, `tc49 live --state <path>`. The bus
keeps its retained values there and each app adopts its own coming up, so a
restart opens on the placement and facing the last session left rather than
on an empty layout (SYSTEM.md, the bus). `<path>` itself is never written.
Each railroad gets `<stem>.<railroad><suffix>` beside it, **one file per
railroad**, because a session keeps the one path while the panel may switch
railroads all evening, and train names do not tell two layouts apart. The
panel reads nothing new for it: placement arrives on `state/allocation` and
facing on `state/facing` exactly as they do on a rejoin. What the picture
gains is `crossing`, train → the transit it was crossing when everything
stopped: a placement hint with no route behind it, drawn on the connection as
above, and the one train the session cannot place on its own. A restored
session comes up **held**, so nothing moves before the placement has been
checked
([ADR-0037](../adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
Restart is not rejoin and neither is recovery
([CONTEXT.md](../../CONTEXT.md#interruptions)).

The relay's `{"error": …}` frames reach the band as trouble rather than being
dropped: a refused inbound frame and a path naming no railroad are the only
answers a page ever gets when a session says no.

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
which symbol an address is worn by. `tc-panel` holds the session, feeds the
model, hands the canvas an overlay, hands `tc-roster` the railroad's roster
marked with where the run has each train, and sends. Where a drag from the
pane landed is asked of the canvas, which is what turns a client pixel into a
point on the drawing.

**The component gets a suite where only mounting it can see the answer.** Each
rule is tested at its own seam — `trainAt` in `drag.test.ts`, `standsIn` and
`inFlight` in `panel.test.ts`, `litLast` in `inspect.test.ts` — and not one of
them can say whether this view asked. So `reversal.test.ts` mounts the app in
this view and drives the right-click, and `run.test.ts` walks the session: a
menu offered over a train's block and nowhere else, the browser's own menu
suppressed either way, one `reversal_wanted` and no second frame, a refusal
shown in the band rather than swallowed, and a menu coming down when the train
leaves the block or the session goes. The last of those is the shape both bugs
[#124](https://github.com/rails49/control/issues/124) found in Chrome took,
and catching that shape is what the suite is for
([#157](https://github.com/rails49/control/issues/157)). It walks the session
going away as well, on fake timers so nothing waits three seconds: a drop
makes one try, on the railroad that is loaded and no other; a second ask
inside the interval leaves the waiting try where it is; and a try that comes
round to a session joined meanwhile does nothing
([#183](https://github.com/rails49/control/issues/183)). The session they run
against — the toy railroad, the fake bridge, and the app joined to it — is
`ui/test/support/session.ts`, written once for every suite that needs one.

The railroad it paints is not its own: the app holds it and hands over the
drawing and the review (ADR-0038). Joining a session names a railroad, so this
view asks the app for it and opens the socket once it is on screen — which is
also what keeps a frame from arriving before there is a model to apply it to,
the drain a join opens with being the whole of the run's picture.

The chrome is two rows the editor also wears (#84,
[EDITOR.md](EDITOR.md#the-band)). The **band** is the whole system's: the
railroad the app has loaded and the picker that loads another, the unsaved
dot, the health area — the store not answering, the bridge, whether the rails
have power, how far the run has got, whether the trains standing here have
frozen the drawing — the three track-power presses beside that reading, and
the view selector. The **bar** is this
view's document's: a `View` menu carrying zoom and fit, those three pinned as
icon buttons at its right end, and **HOLD/GO**.

**HOLD and GO are one press and no confirmation.** The button says HOLD while
the run is running and GO while it is held, which is what the press will do,
and a clearly labelled button is the explicit GO
([ADR-0037](../adr/0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
It draws `tc49/dispatch/state/run` off the picture rather than the last press,
so a gesture that did not land leaves the value where it was, and it is dead
with no session joined and until the dispatcher has said where the run stands.
The gesture is `tc49/dispatch/run_wanted`, which names where the run should stand
rather than asking for a change: two presses of the same value are not a race.

**The band says whether the rails have power**, reading
`tc49/layout/state/power` beside the bridge and the session clock, and it says
which of the two ways of standing still it is: *emergency stop* for `stopped`
and *power off* for `off`. The person recovering clears the one and switches
the other back on, which are different actions
([ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
With no session joined it says nothing, a drawing having no rails to have
power.

**ON, STOP and OFF command the supply**, on `tc49/layout/power_wanted`
([ADR-0051](../adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)).
They stand in the band beside the reading they act on, because track power is
the whole railroad's and no document's, and they are drawn only on a joined
session — a drawing has no rails to power — and are dead while the bridge is
not answering, a press it would swallow being a press that did nothing. None
is greyed by the value it would write: like `run_wanted`, the gesture names
where the supply should stand rather than asking for a change, so a press that
agrees with where it stands is not a race. The topic is `layout`'s because
`layout` is what answers it, and `layout` answers by writing the desired power
of the device vocabulary — a page never reaches a translator.

**STOP is one click with no confirmation**, for the reason HOLD is: an
emergency stop that asks "are you sure?" is not one, and `stopped` is cheap to
recover from with the points still where you left them. **ON** writes nothing
on `run_wanted`: returning to `on` releases nothing on its own (ADR-0041), so
an explicit GO still follows.

**OFF is the drain trigger, never an immediate cut.** The press publishes
`tc49/dispatch/run_wanted: draining`, watches `tc49/dispatch/state/run` reach
`held`, and publishes `power_wanted: off` only then; both are topics this view
already writes, so `layout` never subscribes to the dispatcher. A run that
already reads `held` has nothing left to drain, so the supply goes at once.
While the wait is outstanding the button reads *DRAINING…* and is dead, and a
run that never settles leaves the railroad powered and the button still saying
so — the case an abrupt cut would have hidden. **ON is the way out of a wait**:
it abandons the outstanding cut as well as writing its own frame, a supply
going away out of a press the person has moved on from being the surprise this
button exists to avoid. A session that goes away takes the wait with it. The
`draining` value itself, and the dispatcher's launch gate, are the
dispatcher's half of the same decision
([#294](https://github.com/rails49/control/issues/294)): it launches nothing
more, lets what is crossing finish, and writes the `held` this button is
waiting for.

**GO is greyed while the power is not `on`.** The dispatcher drops such a
release, so a live button would be one that does nothing. It carries no
explanation of its own: the band beside it says which, the way the greyed
*Turn around* says *this train is busy* by being greyed at all. HOLD is
untouched — it asks for less, and there is no state of the rails in which a
person may not ask for it. A session that has said where the run stands and
nothing about power still offers GO: the dispatcher takes `on` until the
layout says otherwise, and the button says what it would do rather than
guessing at silence.

**A release says what is still disputed.** Pressing GO with the disputed set
non-empty is allowed and nothing is blocked — the person decides, not the
check — and the view writes what was outstanding beside the press, in the same
words the marks under the blocks use. It has to be words: `state/disputed` is
empty while the run is running, so the amber marks go with the hold and the
sentence is what is left of them. It stands as long as the run it was a
decision about is running, and a fresh hold is a fresh decision
([#153](https://github.com/rails49/control/issues/153)).

**This view has no control of its own.** The session select it used to carry
is gone: the band's picker is the only thing that says which railroad is on
screen, and the run view joins whatever is loaded
([#171](https://github.com/rails49/control/issues/171)). What its header still
draws is the release notice, and only while there is one.

**The run view's one source is the bus.** It could read a recorded trace and
step through it, which is how it was built before `tc49 live` and the bridge
existed and how its colours were looked at afterwards. Both reasons expired,
and the chrome that took — a drawings list, a file opener, a transport and a
rate in boundaries per second — is most of what made this view's row hard to
merge into a shell's, all of it meaningless to an operator
([ADR-0038](../adr/0038-the-ui-is-one-app-with-views-of-one-railroad.md)).
Traces stay exactly as
[ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md) has
them: the tap records every event, metrics derive from recordings, and
benchmarks assert byte-identical replays. That is analysis, and analysis is
the harness's.
