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
`claro_2.B` can only mean "may the train in `claro_2` leave via B". A signal
at an end that leads only to a terminal governs a departure no train can make
and is worth hiding, once the rest is settled.

The aspect rule is **locked-ahead**: green if the resource beyond that end is
currently locked to the train standing there. That is what a real signal
means, it reuses the lock ledger the panel already maintains for
reserved-block shading, and it stays stable while a train runs. Deriving the
aspect from `grant_refused` instead would require a per-train state machine
over an event topic and would describe the dispatcher's state rather than the
railway's.

**In the end state the panel derives no aspect at all.** The dispatcher
publishes it — `stop`, `approach` or `clear`, read off how far ahead it has
locked — and the panel renders what it is told
([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
Locked-ahead survives as the rule, one level up, and two things that are the
panel's problem here stop being anyone's: the middle aspect, which no
derivation from the lock ledger can produce, and whether an end the standing
train does not face may show anything but red.

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

Joining a session needs one thing the bus cannot supply. The placement locks
were published before any browser connected, and **facing** is on no topic at
all ([ADR-0019](../adr/0019-facing-is-scheduler-state.md)). The panel
therefore reads the scenario from the store (`GET /scenarios`,
`GET /scenarios/<id>`) and seeds stock, placement and facing from it.
Everything after that is derived from the bus exactly as a replay derives it,
which is why one panel model serves both. Facing stays determined from there:
a train faces away from the end it entered through, so the next drag departs
nose-first with no bookkeeping.

A session ticks on a wall clock, one knob: `tc49 live --period`. The default
is 2 seconds, picked by watching the panel rather than by argument.

**A panel joins at the start of a session.** The bridge holds no backlog, so a
browser that connects after a train has moved shows it in its scenario block,
and a drag then states a departure block the dispatcher knows is wrong. That
drag comes back rejected, reason `wrong_origin`, spelled out at the request's
endpoints like any other rejection
([ADR-0021](../adr/0021-a-bad-request-is-answered-not-raised.md)). The session
survives, but the page does not recover: only the bus can say where that train
stands, and under exclusive modes the train moves only if this panel moves it.
A misplaced train is therefore undraggable for the rest of the session. The
alternative would be the bridge describing the run, which
[SYSTEM.md](../SYSTEM.md) rules out.

Within one page the panel does hold its ground: leaving and rejoining keeps
what the bus has shown and re-seeds only trains it knows nothing about, and
the request ids carry on rather than starting over. Relatedly, nothing tells
the panel which scenario the session is running, so the operator picks it.

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
