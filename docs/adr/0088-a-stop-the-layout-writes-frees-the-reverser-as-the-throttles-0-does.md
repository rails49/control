# A stop the layout writes frees the reverser as the throttle's 0 does

Resolves [#962](https://github.com/rails49/control/issues/962). Amends
[ADR-0084](0084-a-reverser-moves-only-with-the-lever-at-0.md), rule 2.

ADR-0084 rule 2 lets `layout` change a train's direction only after the
holding throttle has sent 0. But `layout` also stops trains itself: at the
end of a granted move, at a cut, at a release in `manual`, and when a train
is taken off. The throttle page then shows the slider at 0 without sending
it. The reverser is live again, and a person who switches it and raises the
slider gets a train that will not start, with nothing on the page saying
why.

## Decision

1. **A 0 that `layout` writes to stop a train ends the hold, as the
   throttle's own 0 does.** That covers the arrival at the end of a granted
   move, a cut, a release that stops the train, and a removal.
2. **The 0 that `layout` writes for a refused lever does not end the hold.**
   The person is still pushing the lever the other way; that is what rule 2
   of ADR-0084 refuses.

## Consequences

- After a stop, the next lever frame drives the train either way.
- A person who reverses while the train still coasts after an arrival
  reverses a rolling train. ADR-0084 accepts the same after the throttle's
  own 0.
