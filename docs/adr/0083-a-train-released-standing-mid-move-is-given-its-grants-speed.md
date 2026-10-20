# A train released standing mid-move is given its grant's speed

Part of [#847](https://github.com/rails49/control/issues/847).
Supersedes decision 6 of
[ADR-0081](0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)
where the speed the person left is 0.

A person takes a train in `automatic`, a move is granted, and the person
releases the train without moving the lever. Under ADR-0081 decision 6 the
train keeps the speed the person left, which is 0. It stands, holds its route,
and never reaches its sensor. Nothing reports it.

## Decision

1. **Released in `automatic` with a move outstanding and live rails, a train
   whose last written speed is 0, or that has none written, is given its
   grant's speed,** as a release did before ADR-0081. Zeros written at
   startup and at a cut count as written.
2. **A train moving when released keeps the person's speed** until its move
   ends at the sensor, as ADR-0081 decision 6 says.

## Consequences

- A train left standing mid-move starts from rest when released, where the
  decoder's momentum ramps it. That is the case ADR-0081's consequences
  already accept.
- A person who wants a train to stay put mid-move holds it. A release hands
  the move back to the driver.

## Considered

- **Follow ADR-0081 as written.** The train stands with its route held until
  someone drives it to the sensor.
- **Raise any speed below the grant's to the grant's.** A train a person was
  running slowly lurches, which is what ADR-0081 was written to stop.
