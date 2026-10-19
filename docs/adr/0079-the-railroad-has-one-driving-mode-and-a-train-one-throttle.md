# The railroad has one driving mode, and a train one throttle

Part of [#813](https://github.com/rails49/control/issues/813). Amends
[ADR-0054](0054-the-railroad-comes-up-at-rest-and-points-replay.md) and the
throttle in [THROTTLE.md](../ui/THROTTLE.md).

A train was manual while a throttle had taken it and automatic otherwise.
Nothing recorded which throttle had it, so any page could take, drive or
release any train, and a phone going to sleep left a train running at its
last speed.

## Decision

1. **The railroad has a driving mode, `manual` or `automatic`.** `layout` owns
   it, beside the record of which throttle holds which train. The railroad
   comes up `manual`, and the mode may change at any time.
2. **The dispatcher routes the same in both.** It sets points, clears signals
   and takes locks. The mode decides only who drives.
3. **In `manual` people drive every train.** A train no throttle holds stands
   at its signal. `layout` writes no speed for a granted move unless a throttle
   holds the train.
4. **In `automatic` the `driver` app drives every train no throttle holds.**
   Its speeds are railroad configuration, a fraction of each locomotive's
   maximum: `clear` 0.6 and `caution` 0.3 to start with.
5. **At most one throttle holds a train.** A second take is refused. A
   throttle that goes away releases its trains, and any panel can force a
   release.
6. **Released, a train stops in `manual` and is driven on in `automatic`.**
7. **A throttle drives only within a granted move.** A train with no grant is
   held at speed 0. To shunt, a person drags a request first.
8. **Changing mode.** From `automatic` to `manual` a moving train finishes its
   move into the next block and waits for a person. From `manual` to
   `automatic` the trains no throttle holds carry on.

## Consequences

- Every move on the railroad is one the dispatcher granted, whoever drives.
  A train driven where it was not granted is an unexplained reading.
- A person shunting drags each short move. A shunting mistake does not drain
  the railroad, because the throttle cannot make one.
- Per-locomotive speeds, and anything a driver does beyond two fractions, wait
  for the driver ([GOALS.md](../GOALS.md#driving)).

## Considered

- **The last take wins.** It lets a second person take a train from the first
  without asking.
- **A throttle drives freely.** It is what a throttle does on a layout with no
  software. Here every move out of a block without a grant would drain the
  railroad.
- **In `manual` the dispatcher routes nothing.** A person would then set the
  points too, and the lock table would not describe the steel.
