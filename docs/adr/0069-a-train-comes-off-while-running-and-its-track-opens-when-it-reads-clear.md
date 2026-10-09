# A train comes off while running, and its track opens when it reads clear

The contract is [#668](https://github.com/rails49/control/issues/668); the
work is [#669](https://github.com/rails49/control/issues/669),
[#670](https://github.com/rails49/control/issues/670),
[#671](https://github.com/rails49/control/issues/671) and
[#672](https://github.com/rails49/control/issues/672). Amends
[ADR-0039](0039-a-train-may-be-off-the-layout.md).

ADR-0039 accepted a placement only while the run is held, in both directions.
That kept a person from taking a train off the layout once the run was going:
the panel greyed the drag, and a train between two blocks had no marker to
drag at all. On the layout a person lifts a train whenever they need to, and
the drag should work the same before and after the train starts moving.

## Decision

1. **Taking a train off the layout is accepted in any run state.** A
   `placement_wanted` with `block: null` cancels the train's requests
   (`removed`, [ADR-0049](0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md))
   and takes it out of `block_of` and off any transit, held or running.
2. **Putting a train on a block still needs the run held.** That direction
   takes a lock, and ADR-0039's reason applies to it unchanged.
3. **Of what the removed train held, each block that reads occupied stays
   held by it until it reads clear.** The transit it was crossing stays held
   until both its blocks have opened. Everything else is released at once,
   including a block that reads clear or that the layout has said nothing
   about. The same rule applies while held.
4. **A clear reading on a block held by a train that is not standing in it
   and not moving out of it is explained.** It releases that block and does
   not hold the run.
5. **The removed train may be put back into a block it still holds.** Any
   other train is refused there until it reads clear.
6. **`layout` sets speed 0 on the train's decoders on `train_removed`**, and
   forgets any move of that train in flight.
7. **The simulator reports clear, on `train_removed`, every block its own
   detectors last reported occupied for that train**, and drops that train's
   scheduled readings. It stands in for the hand.
8. **The panel lets a marker be dragged to the roster pane in any run state**,
   and a train between two blocks can be picked up from where it is drawn.

## Why the track waits for the detectors

Removal frees track, and freeing track while the dispatcher is granting is
what a cancellation already does. The danger is a gesture made before the
hand, or with no hand at all: the dispatcher would route another train into a
block the loco still stands in. Holding the block until it reads clear lets
the steel confirm the lift, which is how every other release works. A block
with no reading has nothing to wait for, as everywhere else in the dispatcher.

## Alternatives not taken

- **The gesture holds the run.** Safe, and one lifted loco would stop every
  other train until someone presses GO.
- **Release everything at once.** A gesture made before the lift, or a loco
  left standing, leaves an occupied block the dispatcher believes free.
- **Treat a clear reading under a standing train with no move as a lift.** A
  detector that drops out under a dirty wheel reads the same, and would free a
  block a train still stands in.

## Consequences

- Lifting first and dragging second holds the run, as before: the clear
  reading arrives while the train still stands in the block with no move
  under way ([ADR-0048](0048-an-unexplained-reading-holds-the-run.md)). The
  drag then works on the held run.
- A train mid-move that moves on into another block before it stops reads
  occupied in a block nothing holds, and the run holds.
- A removed train holding a block is drawn as that block locked by it, with no
  marker. The held run's dispute check does not name the block, since a train
  claims it.
- A drain can complete while a removed train still holds track: it is neither
  active nor crossing.
