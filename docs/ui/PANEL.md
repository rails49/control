# Dispatch panel

Recorded design for the live panel: watching the railroad in real time and
submitting requests. Deliberately after the [editor](EDITOR.md) in the order
of work; nothing here is scheduled. Decisions that bind it:
[ADR-0016](../adr/0016-the-panel-is-a-scheduler.md) and
[ADR-0017](../adr/0017-turnout-position-is-inferred-by-the-panel.md).
Terminology follows [CONTEXT.md](../../CONTEXT.md).

## What it shows

The panel renders the drawing ([DRAWING.md](../store/DRAWING.md)) with live
state on top. Blocks show colour for state, a label for the train, an arrow
for direction. Reserved-but-empty blocks get a distinct fill, so a committed
route reads as a lit path.

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

## What it does

The panel is read-only apart from submitting requests. Clicking a train and
then one or more arrival ends publishes `request_submitted`, the existing
topic in the existing `schedule` role, and the dispatcher answers with
`request_admitted` or `request_rejected`.

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

A first panel can render a recorded trace file with no server at all, which
is immediately useful for reviewing past benchmark runs.
