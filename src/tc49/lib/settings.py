"""The railroad's settings: what a person sets for one railroad and the
railroad keeps, so far only the **point gap** (#1125, #1126) — and the shape
of `tc49/layout/state/settings`, which says them beside the driver's speeds
and the installation's throttle silence (#1130).

`layout` says them on `tc49/layout/state/settings`, takes a person's change
on `tc49/layout/settings_wanted`, and keeps them in the store beside the
railroad's other documents, `layouts/<railroad>.settings.yaml`. The store
checks the document `layout` reads it with, so the shape is here and not in
either app (ADR-0013).
"""

import math
from dataclasses import dataclass
from typing import Any, cast

POINT_GAP_S = 0.5
"""How long `layout` waits after a point command before it sends the next one
or lets go the move waiting on it, in seconds, where a railroad keeps none:
half a second, long enough for a solenoid's CDU to recharge and most of a
stall motor's travel (#1127)."""

POINT_GAP_MAX_S = 5.0
"""The longest point gap a person may set, in seconds. A point that has not
moved in five seconds has not moved."""


SPEEDS: dict[str, float] = {"clear": 0.6, "caution": 0.3}
"""What `clear` and `caution` are worth as a speed, a fraction of the
locomotive's maximum, where a railroad sets none (ADR-0025, ADR-0079). The
railroad's, since how fast its trains should run depends on its stock and
scale (#1130)."""

THROTTLE_SILENCE_MIN_S = 2.0
"""The shortest throttle silence, in seconds. A throttle says
`throttle_alive` once a second, so anything shorter lets go of a train
between two of them from a throttle that is still there."""

THROTTLE_SILENCE_MAX_S = 60.0
"""The longest throttle silence, in seconds: a phone gone for a minute has
gone, and the train it held should not roll on unwatched."""


def speed(value: object) -> float | None:
    """`value` as one of the driver's speeds, or None where it is not one: a
    finite fraction of the locomotive's maximum above `0` and at most `1`
    (#1131)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # Written so that `nan`, which compares false with everything, fails.
    if not 0 < value <= 1:
        return None
    return float(value)


def throttle_silence(value: object) -> float | None:
    """`value` as a throttle silence, or None where it is not one: a finite
    number from `THROTTLE_SILENCE_MIN_S` to `THROTTLE_SILENCE_MAX_S`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # Written so that `nan`, which compares false with everything, fails.
    if not THROTTLE_SILENCE_MIN_S <= value <= THROTTLE_SILENCE_MAX_S:
        return None
    return float(value)


def point_gap(value: object) -> float | None:
    """`value` as a point gap, or None where it is not one: a finite number
    from `0` to `POINT_GAP_MAX_S`. A bool is no number, though Python counts
    it one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # Written so that `nan`, which compares false with everything, fails.
    if not (math.isfinite(value) and 0 <= value <= POINT_GAP_MAX_S):
        return None
    return float(value)


@dataclass(frozen=True)
class KeptSettings:
    """What a railroad keeps of its settings: the point gap, in seconds."""

    point_gap: float = POINT_GAP_S

    def document(self) -> dict[str, float]:
        """The store's document, and the payload `state/settings` carries."""
        return {"point_gap": self.point_gap}


def kept_settings(doc: object) -> KeptSettings:
    """The `KeptSettings` a store document says, or `ValueError` or
    `TypeError` naming what is wrong with it: `point_gap` in range and
    nothing else."""
    if not isinstance(doc, dict):
        raise TypeError("settings are a document of 'point_gap'")
    fields = cast(dict[str, Any], doc)
    if set(fields) != {"point_gap"}:
        raise ValueError(f"settings have 'point_gap', not {sorted(map(str, fields))}")
    gap = point_gap(fields["point_gap"])
    if gap is None:
        raise ValueError(
            f"settings 'point_gap' is {fields['point_gap']!r},"
            f" not a number of seconds from 0 to {POINT_GAP_MAX_S:g}"
        )
    return KeptSettings(gap)


def said(kept: KeptSettings, throttle_silence_s: float) -> dict[str, object]:
    """The payload of `tc49/layout/state/settings`: the railroad's point gap
    and speeds, and the installation's throttle silence, every field always
    present (#1130). The speeds are `SPEEDS` until a person can set them."""
    return {
        "point_gap": kept.point_gap,
        "speeds": dict(SPEEDS),
        "throttle_silence": throttle_silence_s,
    }
