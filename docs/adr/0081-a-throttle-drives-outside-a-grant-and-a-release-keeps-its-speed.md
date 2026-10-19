# A throttle drives outside a grant, and a release keeps its speed

Part of [#847](https://github.com/rails49/control/issues/847).
Supersedes decisions 6 and 7 of
[ADR-0079](0079-the-railroad-has-one-driving-mode-and-a-train-one-throttle.md).

A person standing at a platform could not back a train up a few centimetres:
the lever did nothing until the dispatcher granted a move, and a move means a
new request. A train released in `automatic` jumped at once to the driver's
speed for its grant, so a train a person had been running slowly lurched.

## Decision

1. **A throttle drives the train it holds at any time,** granted move or not.
   It may run the train either way, nose-first or tail-first, as a driver
   with a reverser can on a real locomotive.
2. **Leaving the block is the person's responsibility.** Nothing in the
   software stops a held train at its block's ends. A train that leaves shows
   up as an unexplained reading and drains the railroad.
3. **The end of a granted move still stops the train.** `layout` writes `0.0`
   at the move's sensor whoever is driving, and the lever returns to rest. The
   person may move off again after it.
4. **Dead rails refuse the lever,** as before
   ([ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
5. **Released in `manual`, a train stops.** `layout` writes `0.0`.
6. **Released in `automatic`, a train keeps the speed the person left** until
   its move ends at the sensor. The next grant runs at the driver's speeds.
   With no move outstanding, or dead rails, `layout` writes `0.0`, so no speed
   waits on a row for the power to come back.

## Consequences

- ADR-0079's consequence that a shunting mistake cannot drain the railroad no
  longer holds. A person can drain it by driving out of the block.
- The speed of a released train changes at the next grant's start, from rest,
  where the decoder's momentum ramps it.

## Considered

- **Let the lever move a train only within its own block.** Nothing detects
  where in its block a train is, so the software cannot tell a train backing
  to the platform end from one about to leave.
- **A "Go to" list on the throttle that makes a request.** It moves a train
  to another block, not a few centimetres. Requests stay with the run view and
  the scheduler for now.
