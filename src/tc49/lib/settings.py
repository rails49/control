"""The settings a person sets from the Settings dialog: the railroad's, its
**point gap** and the driver's **speeds** (#1125, #1126, #1132), and the
installation's, its **throttle silence** (#1132) and **sensor silence**
(#1149) — and the shape of
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

SENSOR_SILENCE_S = 3.0
"""How long a sensor may go unheard, in seconds, where the installation keeps
none (`installation.yaml`, #1149). A report comes at least once a second, so
one missed report is not a failure; at N-scale 60 km/h, 3 s is about 31 cm of
travel."""

SENSOR_SILENCE_MIN_S = 2.0
"""The shortest sensor silence, in seconds: anything shorter calls a sensor
unheard over one missed report."""

SENSOR_SILENCE_MAX_S = 60.0
"""The longest sensor silence, in seconds, the longest a throttle may go
unheard too."""


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


def sensor_silence(value: object) -> float | None:
    """`value` as a sensor silence, or None where it is not one: a finite
    number from `SENSOR_SILENCE_MIN_S` to `SENSOR_SILENCE_MAX_S`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # Written so that `nan`, which compares false with everything, fails.
    if not SENSOR_SILENCE_MIN_S <= value <= SENSOR_SILENCE_MAX_S:
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
    throttle silence and the sensor silence, in seconds (#1132, #1149)."""

    throttle_silence: float = THROTTLE_SILENCE_S
    sensor_silence: float = SENSOR_SILENCE_S

    def document(self) -> dict[str, float]:
        """The store's document."""
        return {
            "throttle_silence": self.throttle_silence,
            "sensor_silence": self.sensor_silence,
        }


def kept_installation(doc: object) -> KeptInstallation:
    """The `KeptInstallation` a store document says, or `ValueError` or
    `TypeError` naming what is wrong with it: `throttle_silence`,
    `sensor_silence` or both, each in range, and nothing else. One left out is
    its default, so a document written before there was a sensor silence
    reads as it did (#1149)."""
    if not isinstance(doc, dict):
        raise TypeError(
            "the installation's settings are a document of 'throttle_silence'"
            " and 'sensor_silence'"
        )
    fields = cast(dict[str, Any], doc)
    if not fields or not set(fields) <= {"throttle_silence", "sensor_silence"}:
        raise ValueError(
            "the installation's settings have 'throttle_silence' or"
            f" 'sensor_silence', not {sorted(map(str, fields))}"
        )
    throttle = throttle_silence(fields.get("throttle_silence", THROTTLE_SILENCE_S))
    if throttle is None:
        raise ValueError(
            f"'throttle_silence' is {fields['throttle_silence']!r}, not a number"
            f" of seconds from {THROTTLE_SILENCE_MIN_S:g}"
            f" to {THROTTLE_SILENCE_MAX_S:g}"
        )
    sensor = sensor_silence(fields.get("sensor_silence", SENSOR_SILENCE_S))
    if sensor is None:
        raise ValueError(
            f"'sensor_silence' is {fields['sensor_silence']!r}, not a number"
            f" of seconds from {SENSOR_SILENCE_MIN_S:g}"
            f" to {SENSOR_SILENCE_MAX_S:g}"
        )
    return KeptInstallation(throttle, sensor)


def said(kept: KeptSettings, installation: KeptInstallation) -> dict[str, object]:
    """The payload of `tc49/layout/state/settings`: the railroad's point gap
    and speeds, and the installation's throttle silence and sensor silence,
    every field always present (#1130, #1149)."""
    return {
        "point_gap": kept.point_gap,
        "speeds": dict(kept.speeds),
        "throttle_silence": installation.throttle_silence,
        "sensor_silence": installation.sensor_silence,
    }


def taken(
    kept: KeptSettings, installation: KeptInstallation, wanted: "SettingsWanted"
) -> tuple[KeptSettings, KeptInstallation, list[KeptSettings | KeptInstallation]]:
    """The settings as they stand once a person's `settings_wanted` is
    taken, the rule both bindings of the layout interface take it by
    (#1126, #1132, #1140, #1149): the railroad's, the installation's, and the
    documents to keep — the railroad's where the gesture set the gap or a
    speed, the installation's where it set either silence. A field left out,
    and a speed left out of `speeds`, keeps its value."""
    changed: list[KeptSettings | KeptInstallation] = []
    if wanted.point_gap is not None or wanted.speeds is not None:
        kept = KeptSettings(
            kept.point_gap if wanted.point_gap is None else wanted.point_gap,
            {**kept.speeds, **(wanted.speeds or {})},
        )
        changed.append(kept)
    if wanted.throttle_silence is not None or wanted.sensor_silence is not None:
        installation = KeptInstallation(
            (
                installation.throttle_silence
                if wanted.throttle_silence is None
                else wanted.throttle_silence
            ),
            (
                installation.sensor_silence
                if wanted.sensor_silence is None
                else wanted.sensor_silence
            ),
        )
        changed.append(installation)
    return kept, installation, changed
