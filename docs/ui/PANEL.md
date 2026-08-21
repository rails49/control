# Dispatch panel

The live panel: watching the railroad in real time and asking for trains to be
moved. Built after the [editor](EDITOR.md), as the order of work had it.
Decisions that bind it:
[ADR-0036](../adr/0036-the-scheduler-is-an-app-the-panel-is-a-view.md), which
made it a view rather than the scheduler it began as
([ADR-0016](../adr/0016-the-panel-is-a-scheduler.md)),
[ADR-0035](../adr/0035-a-topic-has-one-writing-role.md), and
[ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md).
Terminology follows [CONTEXT.md](../../CONTEXT.md).

## What it shows

The panel renders the drawing ([DRAWING.md](../store/DRAWING.md)) with live
state on top. Blocks show colour for state, a label for the train, an arrow
for direction. Reserved-but-empty blocks get a distinct fill, so a committed
route reads as a lit path.

A request renders in three layers, each appearing when the bus first makes it
true. **Requested** (from `request_submitted`): the train, its departure end,
and the candidate arrival ends — endpoints only, since no route exists yet
and drawing a predicted one would be a second pathfinder that lies whenever
the dispatcher disagrees. **Committed** (from `route_chosen`): the chosen
route as a lit path in a planned tint. **Held** (from `lock_granted` /
`lock_released`): the reserved-block shading and signals described below.

A committed route lights **whole**: its blocks, the legs of the symbols its
transits cross, and the wires those transits are drawn over. Without the
wires a route through a junction reads as scattered lit frogs, and a route
across a joint — a way crossing no symbol that declares a transit — lights
nothing at all between its two blocks. Which wires a transit runs over is the
store's own rule (`Drawing.wires_on`), transcribed into `model/inspect.ts` and
applied one transit at a time, never over a union of everything lit: a wire
between two non-block symbols is what merges them into one junction, so a
union has no transit to attribute a wire to. The store proves the rule exact
against every railroad it holds, which is what the front end's cheaper copy
rests on. Lit wires are emitted after unlit ones, as the artwork already emits
lit legs last, so a crossing unlit wire cannot half hide one.

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
[`beb-gotthard/positions`](../../scenarios/beb-gotthard/positions.scenario.yaml)
is the scenario that does — one train across two junctions, which is the
picture to run when the styling is what is being looked at (#130).

**Signals are part of the block symbol.** A block carries a signal at each
end, always, so there is nothing to place and nothing in the drawing to
record. A signal governs departures through one block end, and routes are
strict pass-throughs with no reversal within a route, so a signal at
`claro_2.B` can only mean "may the train in `claro_2` leave via B".

**The panel derives no aspect.** The dispatcher publishes one — `stop`,
`approach` or `clear`, read off how far ahead it has locked — on a last-value
topic naming every signalled end, and the panel renders what it is told
([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
An aspect is a function of locks the dispatcher holds and routes it committed,
so a second party working it out is a second authority to disagree with.

Two questions the panel's own locked-ahead derivation raised are answered by
not arising. Whether an end the standing train does not face may show anything
but red: the dispatcher knows the committed route, so it knows the one end a
train may leave by, and every other end shows `stop` because nothing is locked
beyond it. And the middle aspect, which the binary derivation could not
produce at all: the dispatcher counts the depth, so `approach` and `clear` are
simply two different counts.

An end that leads nowhere carries no signal and the dispatcher does not name
it, so the panel draws none — no rule here, just an end absent from the map.

![A live session mid-run: a drag from south to claro_3's middle third](images/live-drag.png)

## What it does

The panel is read-only apart from gesturing, and it gestures in two ways: a
drag, which asks for a train to be moved, and a right-click, which turns one
around where it stands.

**Dragging** a train from its block to a destination block publishes
`tc49/ui/request_wanted` — `{train, dest}` — and the scheduler composes the
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
`wrong_origin`, `unknown_train`, `unknown_block`, `malformed`). The last
three answer a payload the dispatcher could not read as a request; an honest
drag cannot produce one, and the page that can is a stale one, a race or a
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
scheduler, and which of them a session has is configuration. Scenario runs
keep byte-identical replay; a run carrying gestures makes no such claim, and a
benchmark run receives none.

A gesture the scheduler cannot compose is **dropped in silence** and lives in
the trace. It carries no id, so there is nothing to address an answer to, and
the panel renders the roster from the run — so an honest drag cannot produce
one ([ADR-0034](../adr/0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

**Right-clicking** the block a train stands in opens a menu with one item,
**Turn around**, which publishes `tc49/ui/reversal_wanted` (`{train}`). The
scheduler flips that train's **facing** to the other end of the same block and
the arrow turns. That is the whole of the feedback: nothing moves, no request
is composed, and no `tc49/dispatch` topic carries anything. Facing is
otherwise fully determined once placed, routes being strict pass-throughs, and
deliberate reversal at rest is the one exception
([ADR-0019](../adr/0019-facing-is-scheduler-state.md)). It is what a train
that can run either way needs, and what switching needs: the panel should read
true before you drag anywhere.

A gesture of its own rather than a departure end named inside the drag. The
press location is the panel's last free motion, and a drag cannot say "turn
around and stay put", which is the whole case. A menu also says what it does
before you commit, which suits a gesture whose entire effect is one arrow
rotating, and no motion the drag uses can reach it: a plain click on a train's
own block is already the drag's cancel. Not "Reverse", which is the throttle's
word; this moves nothing. The menu is where the human driver's throttle will
hang later, when `tc49/ui` grows its third leaf.

Over bare paper, over an empty block, or with no session joined no menu opens,
and neither does the browser's own, which the drawing suppresses throughout.
The item is **greyed while that train has a request in flight**, meaning any
request from submit to completion. This is the panel's one pre-judgement of a
gesture, against the filter-free drag, and it earns the exception: a disabled
item says the train is busy, where silence says nothing. Reversing under a
queued request would produce a lie, since the request still departs the old
end and `route_chosen` turns the arrow back when it launches. A **rejected**
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

Joining a session takes everything off the bus. Placement, locks, routes and
live requests come from the dispatcher's retained picture; **facing**, which
is scheduler state and on no dispatcher topic at all
([ADR-0019](../adr/0019-facing-is-scheduler-state.md)), comes from the
scheduler's own retained topic. Both are written by apps that are always
running, so there is no cold start to seed: the panel reads the scenario from
the store (`GET /scenarios`, `GET /scenarios/<id>`) for one thing only, which
drawing to render, nothing retained saying which railroad a session runs and a
topic that did being the bridge describing the run (#67). Everything else is
derived from the bus exactly as a replay derives it, which is why one panel
model serves both — a trace carries the state topics too, so a replay gets
facing from the same place a live session does.

A session ticks on a wall clock, one knob: `tc49 live --period`. The default
is 10 seconds, picked by watching the panel rather than by argument: a
boundary moves trains, grants and releases locks, realigns points and changes
aspects, and at the 2 seconds this started out as the next one landed before
a person had finished reading the last. The replay transport is a different
number — a rate in boundaries per second — and keeps its own.

**A panel may join a session already running.** On connect the bridge sends
each state topic's last value before any live frame, so the page opens on the
dispatcher's own picture — standing trains, locks, committed routes, live
requests off `tc49/dispatch/state/allocation`, aspects off
`state/aspects`, facing off `tc49/schedule/state/facing` — rather than on
where the scenario says the railroad started
([ADR-0032](../adr/0032-a-joining-client-is-served-the-runs-retained-state.md)).
The scenario seeds a cold start only, where there is no retained value to
prefer. Rejoining is not recovery: nothing was lost, and the dispatcher was
holding the truth the whole time ([CONTEXT.md](../../CONTEXT.md#interruptions)).

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
its topic and ids arrive on `request_submitted`. `model/drag.ts` turns pointer positions
into an arrival-end set or a cancel, DOM-free and tested the way the editor's
gesture model is; `trainAt` there is the one question the press and the
right-click share, so the two can never disagree about which train was
clicked. `tc-menu` renders the items it is given, the editor and the panel
each working out their own list. `model/scene.ts` is what the drawing alone answers: the
viewBox, an arrow's pose, and which symbol an address is worn by. `tc-panel`
converts pixels into squares, paints, and sends.

The header is two rows (#84). The top one is the band the editor also wears
(`tc-header`, [EDITOR.md](EDITOR.md#the-band)): the railroad's name, the mode,
and the status that is nobody's mistake — the bridge link, the boundary, and
the trouble message. The row below keeps the things you press. The editor's menu
bar (#85) is not repeated here; the panel has no File to fill.

The mode is the half of the band only the panel has. Replay and live are
exclusive — a page shows a recorded run or a running one — and which one
you were in was inferrable only from whichever select you last touched. The
band says it, and says *nothing joined* where neither source is feeding — a
railroad picked with no trace open and no session joined. A replay names its
trace file beside the mode, that being what says which run is on screen rather
than merely which railroad.

A first panel can render a recorded trace file with no server at all, which
is immediately useful for reviewing past benchmark runs.
