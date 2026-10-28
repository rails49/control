"""The settings a person sets from the Settings dialog: the railroad's, its
**point gap** and the driver's **speeds** (#1125, #1126, #1132), and the
installation's, its **throttle silence** (#1132) — and the shape of
`tc49/layout/state/settings`, which says them all (#1130).

Both bindings of the layout interface say them on `tc49/layout/state/settings`,
take a person's change on `tc49/layout/settings_wanted` by one rule, `taken`,
and keep each in the store (#1140). `layout` says them on `tc49/layout/state/settings`, takes a person's change
on `tc49/layout/settings_wanted`, and keeps each in the store: the railroad's
beside its other documents, `layouts/<railroad>.settings.yaml`, and the
installation's at the store root, `installation.yaml`, the same whatever
railroad is loaded. The store checks each document `layout` reads it with, so
the shapes are here and not in either app (ADR-0013).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from tc49.lib.payload import SettingsWanted

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

THROTTLE_SILENCE_S = 5.0
"""How long a throttle holding a train may go unheard before `layout` lets go
of its trains, in seconds, where the installation keeps none
(`installation.yaml`, #1132). A throttle says `throttle_alive` once a second,
so this is five of them missed."""

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
    """What a railroad keeps of its settings: the point gap, in seconds, and
    the driver's speeds, `clear` and `caution` (#1132)."""

    point_gap: float = POINT_GAP_S
    speeds: Mapping[str, float] = field(default_factory=lambda: dict(SPEEDS))

    def document(self) -> dict[str, object]:
        """The store's document."""
        return {"point_gap": self.point_gap, "speeds": dict(self.speeds)}


def kept_settings(doc: object) -> KeptSettings:
    """The `KeptSettings` a store document says, or `ValueError` or
    `TypeError` naming what is wrong with it: `point_gap` in range, and
    `speeds`, where given, `clear` and `caution` each in range, and nothing
    else. A document without `speeds` keeps `SPEEDS` (#1132)."""
    if not isinstance(doc, dict):
        raise TypeError("settings are a document of 'point_gap' and 'speeds'")
    fields = cast(dict[str, Any], doc)
    if "point_gap" not in fields or not set(fields) <= {"point_gap", "speeds"}:
        raise ValueError(
            "settings have 'point_gap' and may have 'speeds',"
            f" not {sorted(map(str, fields))}"
        )
    gap = point_gap(fields["point_gap"])
    if gap is None:
        raise ValueError(
            f"settings 'point_gap' is {fields['point_gap']!r},"
            f" not a number of seconds from 0 to {POINT_GAP_MAX_S:g}"
        )
    if "speeds" not in fields:
        return KeptSettings(gap)
    return KeptSettings(gap, _kept_speeds(fields["speeds"]))


def _kept_speeds(stated: object) -> dict[str, float]:
    """The speeds a settings document keeps: `clear` and `caution`, both,
    each above 0 and at most 1, or `ValueError` or `TypeError`."""
    if not isinstance(stated, dict):
        raise TypeError("settings 'speeds' are a document of 'clear' and 'caution'")
    named = cast(dict[str, Any], stated)
    if set(named) != set(SPEEDS):
        raise ValueError(
            "settings 'speeds' have 'clear' and 'caution',"
            f" not {sorted(map(str, named))}"
        )
    speeds: dict[str, float] = {}
    for aspect in SPEEDS:
        fraction = speed(named[aspect])
        if fraction is None:
            raise ValueError(
                f"settings speed '{aspect}' is {named[aspect]!r},"
                " not a fraction above 0 and at most 1"
            )
        speeds[aspect] = fraction
    return speeds


@dataclass(frozen=True)
class KeptInstallation:
    """What the installation keeps of its settings, `installation.yaml`: the
    throttle silence, in seconds (#1132)."""

    throttle_silence: float = THROTTLE_SILENCE_S

    def document(self) -> dict[str, float]:
        """The store's document."""
        return {"throttle_silence": self.throttle_silence}


def kept_installation(doc: object) -> KeptInstallation:
    """The `KeptInstallation` a store document says, or `ValueError` or
    `TypeError` naming what is wrong with it: `throttle_silence` in range and
    nothing else."""
    if not isinstance(doc, dict):
        raise TypeError(
            "the installation's settings are a document of 'throttle_silence'"
        )
    fields = cast(dict[str, Any], doc)
    if set(fields) != {"throttle_silence"}:
        raise ValueError(
            "the installation's settings have 'throttle_silence',"
            f" not {sorted(map(str, fields))}"
        )
    silence = throttle_silence(fields["throttle_silence"])
    if silence is None:
        raise ValueError(
            f"'throttle_silence' is {fields['throttle_silence']!r}, not a number"
            f" of seconds from {THROTTLE_SILENCE_MIN_S:g}"
            f" to {THROTTLE_SILENCE_MAX_S:g}"
        )
    return KeptInstallation(silence)


def said(kept: KeptSettings, throttle_silence_s: float) -> dict[str, object]:
    """The payload of `tc49/layout/state/settings`: the railroad's point gap
    and speeds, and the installation's throttle silence, every field always
    present (#1130)."""
    return {
        "point_gap": kept.point_gap,
        "speeds": dict(kept.speeds),
        "throttle_silence": throttle_silence_s,
    }


def taken(
    kept: KeptSettings, throttle_silence_s: float, wanted: "SettingsWanted"
) -> tuple[KeptSettings, float, list[KeptSettings | KeptInstallation]]:
    """The settings as they stand once a person's `settings_wanted` is
    taken, the rule both bindings of the layout interface take it by
    (#1126, #1132, #1140): the railroad's, the throttle silence, and the
    documents to keep — the railroad's where the gesture set the gap or a
    speed, the installation's where it set the silence. A field left out,
    and a speed left out of `speeds`, keeps its value."""
    changed: list[KeptSettings | KeptInstallation] = []
    if wanted.point_gap is not None or wanted.speeds is not None:
        kept = KeptSettings(
            kept.point_gap if wanted.point_gap is None else wanted.point_gap,
            {**kept.speeds, **(wanted.speeds or {})},
        )
        changed.append(kept)
    if wanted.throttle_silence is not None:
        throttle_silence_s = wanted.throttle_silence
        changed.append(KeptInstallation(throttle_silence_s))
    return kept, throttle_silence_s, changed
