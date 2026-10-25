# Every signal along a train's locked blocks shows its aspect, and a passed signal shows stop

Part of [#1024](https://github.com/rails49/control/issues/1024). Qualifies
[ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md).

ADR-0025 reads an aspect as "may the train in this block leave via this end",
and `aspects()` lights one signal per train: the exit of the block it stands
in. Every other end shows `stop`, including an end whose block beyond is
already locked to the train. While a move is outstanding the dispatcher counts
the train as standing in its origin, so the signal it has passed stays `clear`
until the rear clears the origin block
([ADR-0077](0077-a-train-is-not-sent-into-a-block-that-reads-occupied-and-a-move-ends-on-both-readings.md)).
On the layout on 2026-10-25 the second signal along a train's locked blocks
showed red until the train reached it.

SBB does it differently. The Swiss rules (BAV, FDV R 300.1–.15, edition
A2024):

- A route is set, locked, and then its signals are cleared (R 300.6 §1.1). No
  rule holds a station signal at stop until the train approaches, so an exit
  signal is often clear before the train is at the platform.
- A main signal shows stop in its normal position, block signals included
  (R 300.2 §5.1.1).
- A signal announces the next one (§5.1.6), and a stop is always announced on
  the signal before it (§5.2.3). So every set route's signal shows proceed,
  not only the first.
- "Nach dem Befahren werden die Signale auf Halt gestellt" (R 300.6 §1.1). In
  general practice the signal goes to stop when the train enters the first
  section beyond it.

## Decision

1. **An aspect answers "may a train that reaches this end leave by it".** For
   each train, the exit signal of every block on its route, from the block the
   dispatcher records it in through its last locked block, shows the ADR-0025
   aspect counted from that block: `clear` with two or more blocks beyond it
   locked to the train, `caution` with one, `stop` with none. Every other end
   shows `stop`, as before. A block has one holder, so no end is set by two
   trains.
2. **A passed signal shows `stop` once the next block reads occupied**, which
   is when the dispatcher records the train there, not when the move ends. The
   block behind stays locked until its own detectors read clear (ADR-0077,
   unchanged).
3. A held run ([ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md))
   and power not `on`
   ([ADR-0078](0078-power-is-on-draining-or-off-and-replaces-go-and-hold.md))
   still put every signal to `stop`.
4. The aspect a grant carries does not change: it is the aspect at the end
   the move leaves by.

## Consequences

- Lock depth stays at two
  ([ADR-0026](0026-two-blocks-ahead-is-full-speed.md)), so in front of a train
  there is at most one `clear` and one `caution`, then `stop`.
- Lineside signal heads, the panel and the throttle show the same values, all
  from `tc49/dispatch/state/aspects`. PANEL.md's reading of a signal changes
  with this ADR.
- A person driving by hand can see an exit signal clear before the train is
  at the platform, and stops there because the timetable says so, as on SBB.
  The automated driver reads its grant, not the signals ahead, and stops where
  its route ends.
- Facing moves to the next block at the same reading
  ([#1025](https://github.com/rails49/control/issues/1025)), so the throttle switches
  to the next signal when the passed one goes to `stop`.

## Considered

- **One signal per train, as before.** A person reads red over a block the
  train holds, and a lineside signal does what no SBB signal does.
- **The passed signal goes to `stop` when the move ends.** It leaves a green
  signal behind the train while the rear is still in the block, which a
  following train's driver could read as permission.
- **Clear signals into blocks on the committed route that are not locked.**
  SBB clears a signal only once its route is locked, and an unlocked block can
  still go to another train.
- **Lock deeper so more signals clear.** That is the dispatcher's deadlock and
  throughput setting (ADR-0026,
  [ADR-0029](0029-a-lock-held-ahead-is-a-block-the-check-must-see.md)), not a
  signalling question.
