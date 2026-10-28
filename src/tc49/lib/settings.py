"""The railroad's settings: what a person sets for one railroad and the
railroad keeps, so far only the **point gap** (#1125, #1126).

`layout` says them on `tc49/layout/state/settings`, takes a person's change
on `tc49/layout/settings_wanted`, and keeps them in the store beside the
railroad's other documents, `layouts/<railroad>.settings.yaml`. The store
checks the document `layout` reads it with, so the shape is here and not in
either app (ADR-0013).
"""

import math
from dataclasses import dataclass
from typing import Any, cast

POINT_GAP_S = 0.0
"""How long `layout` waits after a point command before it sends the next one
or lets go the move waiting on it, in seconds, where a railroad keeps none:
`0`, no wait (#1125)."""

POINT_GAP_MAX_S = 5.0
"""The longest point gap a person may set, in seconds. A point that has not
moved in five seconds has not moved."""


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
