# Dispatch panel

The live panel: watching the railroad in real time and submitting requests.
Built after the [editor](EDITOR.md), as the order of work had it. Decisions
that bind it: [ADR-0016](../adr/0016-the-panel-is-a-scheduler.md) and
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

There are no sensor dots at block ends. `block_occupied` and `block_vacated`
carry a block, and the layout interface publishes anonymous occupancy and
never asserts train identity. RocRail's two dots depict per-end detection,
which is finer than anything on this bus. Train identity is reconstructed
from `lock_granted`, exactly as the dispatcher does; direction comes from the
chosen route or the entry end of the last granted transit.

**Turnout positions are read off `align`.** The command carries the points it
needs as address-and-position pairs
([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md)), and the
panel holds the drawing, so an address maps back to the symbol wearing it. The
panel infers nothing, which supersedes the inference
[ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md) put here.
It still shows commanded position, not measured position, so a point that
failed to throw looks fine. Reported position becomes worth adding if hardware
with point feedback ever exists; the owner's turnouts do not report.

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

The panel is read-only apart from submitting requests. **Dragging** a train
from its block to a destination block publishes `request_submitted`, the
existing topic in the existing `schedule` role, and the dispatcher answers
with `request_admitted` or `request_rejected`. The block's outer thirds name
one arrival end — the end the train enters through, as
[CONTEXT.md](../../CONTEXT.md) defines it — and the middle third names both,
"either way round". Dropping on the train's own block cancels. The departure
end is never part of the gesture: it is the train's **facing** end, scheduler
state the dispatcher never sees
([ADR-0019](../adr/0019-facing-is-scheduler-state.md)). One drag names one
block, so multi-block arrival sets
([ADR-0007](../adr/0007-requests-name-a-set-of-arrival-ends.md)) are deferred,
not dropped; drag supersedes the click sequence this page first recorded.

The drag is **filter-free**: the panel never grays out targets or pre-judges
fit or reachability. Every drop submits, the dispatcher stays the sole
feasibility authority, and a rejection renders at the request's endpoints
with its reason spelled out (`no_fit`, `no_entry`, `unreachable`,
`wrong_origin`).

The panel therefore **is** a scheduler, and modes are exclusive: a run uses
the file scheduler or the panel, never both
([ADR-0016](../adr/0016-the-panel-is-a-scheduler.md)). That preserves the
single-writer rule and the single deterministic id minter. Scenario runs keep
byte-identical replay; panel runs make no such claim. Later the
panel-scheduler can preload a scenario and also take clicks, which is still
one writer.

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
scheduler's own retained topic. The panel still reads the scenario from the
store (`GET /scenarios`, `GET /scenarios/<id>`) for stock, and for placement
and facing where a session is starting cold and there is nothing retained to
prefer. Everything after that is derived from the bus exactly as a replay
derives it, which is why one panel model serves both. Facing stays determined
from there: a train faces away from the end it entered through, so the next
drag departs nose-first with no bookkeeping.

A session ticks on a wall clock, one knob: `tc49 live --period`. The default
is 2 seconds, picked by watching the panel rather than by argument.

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

Request ids do not carry on across a reload and no longer need to: the panel
mints them per page, unique by construction, so a fresh page cannot re-use an
id the dispatcher has seen
([ADR-0033](../adr/0033-a-request-id-is-unique-not-meaningful.md)).

The front end keeps the editor's model/component split. `model/panel.ts` turns
bus payloads into render state and holds the scheduler's own state, meaning
facing and the request ids it mints. `model/drag.ts` turns pointer positions
into an arrival-end set or a cancel, DOM-free and tested the way the editor's
gesture model is. `tc-panel` converts pixels into squares, paints, and sends.

The header is two rows (#84). The top one is the band the editor also wears
(`tc-header`, [EDITOR.md](EDITOR.md#the-band)): the railroad's name, the mode,
and the status that is nobody's mistake — the bridge link, the tick, and the
trouble message. The row below keeps the things you press. The editor's menu
bar (#85) is not repeated here; the panel has no File to fill.

The mode is the half of the band only the panel has. Replay and live are
exclusive ([ADR-0016](../adr/0016-the-panel-is-a-scheduler.md)), and which one
you were in was inferrable only from whichever select you last touched. The
band says it, and says *nothing joined* where neither source is feeding — a
railroad picked with no trace open and no session joined. A replay names its
trace file beside the mode, that being what says which run is on screen rather
than merely which railroad.

A first panel can render a recorded trace file with no server at all, which
is immediately useful for reviewing past benchmark runs.
