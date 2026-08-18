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

**Turnout positions are inferred from `align`.** The panel holds the drawing,
so it can work out which turnouts a transit traverses. This needs no turnout
identity in the app, no new bus topic, and no change to
[SYSTEM.md](../SYSTEM.md)'s position that the transit-to-turnout-positions
table is private hardware configuration. It shows commanded position, not
measured position, so a point that failed to throw would look fine. Reported
position becomes worth adding if hardware with point feedback ever exists
([ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md)).

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
with its reason spelled out (`no_fit`, `no_entry`, `unreachable`).

The panel therefore **is** a scheduler, and modes are exclusive: a run uses
the file scheduler or the panel, never both
([ADR-0016](../adr/0016-the-panel-is-a-scheduler.md)). That preserves the
single-writer rule and the single deterministic id minter. Scenario runs keep
byte-identical replay; panel runs make no such claim. Later the
panel-scheduler can preload a scenario and also take clicks, which is still
one writer.

Manual turnout throwing is not offered. RocRail allows it because it owns
manual shunting, which this model excludes: trains move only on granted
routes and reversal happens only between requests, at rest. There is also no
turnout identity for a command to address, and a second authority deciding
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
and a drag then states a departure block the dispatcher knows is wrong. The
dispatcher raises on that rather than rejecting it, which stops the session:
the check was written when the only writer was an authored file, where a
disagreement is a slip worth failing loudly on. With a browser writing, it
needs to be an answer instead. Tracked in #73; nothing in the panel can
fix it, because answering it means either the bridge describing the run —
which [SYSTEM.md](../SYSTEM.md) rules out — or the dispatcher replying rather
than raising.

Within one page the panel does hold its ground: leaving and rejoining keeps
what the bus has shown and re-seeds only trains it knows nothing about, and
the request ids carry on rather than starting over. Relatedly, nothing tells
the panel which scenario the session is running, so the operator picks it.

The front end keeps the editor's model/component split. `model/panel.ts` turns
bus payloads into render state and holds the scheduler's own state, meaning
facing and the request ids it mints. `model/drag.ts` turns pointer positions
into an arrival-end set or a cancel, DOM-free and tested the way the editor's
gesture model is. `tc-panel` converts pixels into squares, paints, and sends.

A first panel can render a recorded trace file with no server at all, which
is immediately useful for reviewing past benchmark runs.
