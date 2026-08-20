"""Reading a payload from outside, where both apps read the same one (#127).

Anything at all can be published on a topic a person's page writes, so a
payload is **read** rather than trusted, and reading it **never raises**
(ADR-0034): a field that is missing or the wrong shape fails the read whole,
and what a failed read is worth is the caller's — an answer where there is an
id to address, a drop where there is not.

The scheduler reads a gesture off `tc49/ui/request_wanted`, the dispatcher a
request off `tc49/schedule/request_submitted`. The two differ by the id and
the departure end the scheduler adds (ADR-0036) and agree on the two fields a
gesture is, so those two are read here and each app keeps its own shape. The
scheduler's other leaf, `tc49/ui/reversal_wanted`, names a train and nothing
else, and is read here for the same reason: nothing raises.
"""

from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True)
class Gesture:
    """The train and arrival ends a payload names: a gesture whole, and the
    part of a request that is one."""

    train: str
    arrivals: tuple[str, ...]


def gesture(payload: object) -> Gesture | None:
    """The gesture the payload names, or None where it names none."""
    if not isinstance(payload, dict):
        return None
    train, dest = (
        cast(dict[str, object], payload).get(key) for key in ("train", "dest")
    )
    if not isinstance(train, str) or not isinstance(dest, list):
        return None
    ends = cast(list[object], dest)
    if not all(isinstance(end, str) for end in ends):
        return None
    return Gesture(train, tuple(cast(list[str], ends)))


def reversal(payload: object) -> str | None:
    """The train a reversal gesture names, or None where it names none.

    A train is the whole payload: turning around at rest moves nothing, so
    there is no destination to state and no departure end to choose.
    """
    if not isinstance(payload, dict):
        return None
    train = cast(dict[str, object], payload).get("train")
    return train if isinstance(train, str) else None
