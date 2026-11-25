"""What a sensor's reading says about a move whose readings are still
expected (#1171, #1333).

For a move out of block X through end `exit`, over a transit, into block Y
through end `entry`, with `far` the end of Y opposite `entry`, the readings
say four things (GOALS.md):

- the tail has left X: `exit` read occupied, at the grant or since, then clear;
- the head is in Y: `entry` read occupied, or `far` where `entry` was
  `unknown` as the train passed;
- the whole train is in Y: `entry` read clear after the head is in;
- the head is at the far sensor: `far` read occupied.

Any other reading says nothing about the move: a short train stands between
its block's sensors and both read clear. A reading is occupied or clear; an
`unknown` sensor is the caller's to handle.

`follow` gives the facts and nothing else. What a fact comes to, releasing
track or stopping a train, is the app's that asked. The dispatcher's
`Following` extends `Seen`.
"""

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Seen:
    """What has been read of a move so far. The flags are keyword-only, so a
    record that extends this one keeps its own fields first."""

    exit_read: bool = field(default=False, kw_only=True)  # `exit` read occupied
    head_in: bool = field(default=False, kw_only=True)  # `entry` or `far` read occupied
    at_far: bool = field(default=False, kw_only=True)  # `far` read occupied


@dataclass(frozen=True)
class Facts:
    """What one reading made true of a move."""

    tail_out: bool = False
    head_in: bool = False
    whole_in: bool = False
    at_far: bool = False


def follow[S: Seen](
    seen: S, *, exit: str | None, entry: str, far: str, sensor: str, occupied: bool
) -> tuple[S, Facts]:
    """`seen` updated by `sensor` reading `occupied` or clear, and the facts
    that reading gives. The head is in only once; the tail out, the whole
    train in and the far sensor are given at each reading that says them.
    `exit` is None for a move followed in the entered block only, as
    `layout`'s crossing is: no reading then gives the tail out."""
    if occupied:
        if sensor == exit:
            return replace(seen, exit_read=True), Facts()
        if sensor in (entry, far):
            at_far = sensor == far
            facts = Facts(head_in=not seen.head_in, at_far=at_far)
            return replace(seen, head_in=True, at_far=seen.at_far or at_far), facts
        return seen, Facts()
    if sensor == exit:
        return seen, Facts(tail_out=seen.exit_read)
    if sensor == entry:
        return seen, Facts(whole_in=seen.head_in)
    return seen, Facts()
