# A reverser moves only with the lever at 0

Part of [#852](https://github.com/rails49/control/issues/852) and
[#847](https://github.com/rails49/control/issues/847). Measured in
[#859](https://github.com/rails49/control/issues/859).

A person can switch a throttle's reverser while the train moves. The throttle
then sends the same speed with the other sign, and `layout` and the dccex
translator pass it to the decoder unchanged: `<t 10 76 1>` is followed by
`<t 10 76 0>`. On the real layout, loco 10 alone took ±0.6 every 3 s by
ramping down through 0 and back up with no jolt; at ±1.0 it stopped fast and
ran the other way. Behind a long train, cars can leave the rails.

How hard a decoder reverses depends on its make and its deceleration (CV4).
The roster records neither. Nothing on the railroad reports that a train has
stopped: there is no speed feedback, only the block-end sensors.

## Decision

1. **The throttle view's reverser is live only with the slider at 0.**
   Switching it sends nothing; the next slider input carries the new sign.
2. **`layout` changes a train's direction only after the holding throttle has
   sent 0.** A `throttle_wanted` whose sign is opposite to the last nonzero
   speed written for the train writes `0.0` to each addressed car instead, and
   so does every later frame of that sign until the throttle sends `0`.

## Consequences

- To reverse, a person pulls the slider to 0, waits for the train to stop,
  and switches the reverser.
- A person who switches while the train still coasts on momentum, and then
  raises the slider, reverses a rolling train. The person sees the train;
  nothing else can.
- Every client on the bus gets rule 2, not only the throttle view.

## Considered

- **Send the flip and let the decoder ramp.** The result depends on decoder
  settings the system does not know.
- **Send 0, wait a fixed time, then the new direction.** The wait is a guess
  at CV4.
- **Drop a flipped frame in `layout`.** A person pulling back to stop would
  not be heard.
