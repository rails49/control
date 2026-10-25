# `layout` holds a move until its facing names the block the train departs

Resolves [#1041](https://github.com/rails49/control/issues/1041). Amends
[ADR-0052](0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md),
section "A missing facing drops the move".

Two apps react to one arrival. The scheduler moves the train's facing to the
block entered when the allocation records it there (#1025), and the driver
turns the next `move_granted` into a `move`. They are separate processes, and
the bus promises no order between two writers
([BUS.md](../BUS.md#the-bus), "Order from one publisher"). Under ADR-0052 a
`move` that reached `layout` first was dropped. On the railroad, a train with
an address stopped in the block it had entered, kept its locks, and its
request never completed. A locomotive running alone, which clears its origin
before the next block reads occupied, does this in normal running.

## Decision

1. **A `move` for a train with an address, whose facing `layout` cannot use
   for the block the train departs, is held, not dropped.** That covers the
   three cases ADR-0052 dropped: no facing published for the train, a facing
   this build cannot read (#241), and a facing naming another block.
2. **A held move ends as a move held for its `align` does.** It runs when a
   facing naming the departed block arrives. A second `move` for the same
   transit replaces it. When it runs, the checks applied then may drop it, as
   for a train taken off or placed elsewhere meanwhile.
3. **No timer.** A held move waits as long as the facing takes, including
   while the scheduler is down.

The rest of ADR-0052 stands: the sign is composed in `layout` and nowhere
else, and nothing guesses a facing.

## Consequences

- On the railroad the train stands at the start of its next move for as long
  as the facing lags, then runs the right way.
- With the scheduler down, a granted train waits and sets off when the
  scheduler is back, as a move held for its `align` and every move kept
  through `off` already does (ADR-0078).
- No other app changes. The scheduler stays the only writer of facing, and
  the driver stays without state.

## Rejected

- **The driver waits for the facing.** It would give the driver state it is
  designed not to have.
- **The move carries the facing.** Rejected in ADR-0052, for the same reason.
- **The dispatcher grants only once facing names the origin.** The dispatcher
  would read scheduler state, and every move would wait for one more message
  between apps.
- **A time limit on the hold.** It needs a value and a rule for what follows,
  and what follows is the stopped train this ADR removes.
