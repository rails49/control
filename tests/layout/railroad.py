"""The railroad the layout app's suite drives, and the wiring around it.

Drawn here rather than taken from `layouts/`: this is the first app to act on
the hardware a drawing carries, and no committed railroad signals an end
(#286) — what the signals on the bench answer to is a fact of the physical
railroad, and the drawing is its record (ADR-0030). So the suite draws a
railroad that has some, with two ways through one connection and a point
shared between them the way a real crossover shares one.
"""

from typing import Any

from tc49.layout import LayoutInterface
from tc49.layout.interface import SETTLING_S
from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
POWER_WANTED = "tc49/layout/power_wanted"
PLACED = "tc49/dispatch/train_placed"
REMOVED = "tc49/dispatch/train_removed"
ASPECTS = "tc49/dispatch/state/aspects"

BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"
POWER = "tc49/layout/state/power"
DEVICE_SENSOR = "tc49/layout/state/device/sensor"
WANTED_POINT = "tc49/layout/state/wanted/point"
WANTED_SIGNAL = "tc49/layout/state/wanted/signal"
WANTED_TRACK = "tc49/layout/state/wanted/track"
DEVICE_TRACK = "tc49/layout/state/device/track"
DEVICE_LINK = "tc49/layout/state/device/link"

POINTS: dict[str, list[dict[str, str]]] = {
    # The way over the crossover throws two, one of which the straight way
    # wants the other way about.
    "to_dn": [
        {"addr": "dccex/12", "position": "thrown"},
        {"addr": "dccex/13", "position": "thrown"},
    ],
    "straight": [{"addr": "dccex/12", "position": "closed"}],
}


def document() -> dict[str, Any]:
    """A layout document with signals at three ends and points on both ways."""
    return {
        "layout": "bench",
        "units": "mm",
        "blocks": {
            "up_w": {"length": 1000, "signals": {"B": "dccex/40"}},
            "up_e": {"length": 1000, "signals": {"A": "dccex/41"}},
            "dn_e": {"length": 1000, "signals": {"A": "dccex/41"}},
        },
        "connections": {
            "crossover": {
                "transits": {
                    "straight": ["up_w.B", "up_e.A"],
                    "to_dn": ["up_w.B", "dn_e.A"],
                },
                "points": POINTS,
            }
        },
    }


def railroad() -> Layout:
    return Layout.from_document(document())


class Unstamped(Bus):
    """A bus that stamps nothing, so a value carries the stamp it was handed.

    What a binding on the other side of a broker can put on a topic, and what
    it takes to stage the reordering MQTT permits: the milestone-1 bus stamps
    from a clock that only goes forwards, so a pair cannot arrive backwards
    on it (ADR-0008, #240). Two suites stage it — the aspects and the sensor
    rows — so it lives here beside the rest of the wiring.
    """

    def _stamped(self, payload: Payload) -> Payload:
        return payload


def wired(settling_s: float = SETTLING_S) -> tuple[Bus, LayoutInterface, Clock]:
    """A fresh app on a fresh bus with the clock the two of them share, its
    startup cascade delivered: the railroad is up, dark, and has heard nothing
    from the hardware.

    The clock comes back because the settling time is measured against it and
    the suite drives it directly — nothing here sleeps (#288)."""
    clock = Clock()
    bus = Bus(clock)
    app = LayoutInterface(bus, railroad(), clock, settling_s)
    bus.drain()
    return bus, app, clock


def build() -> tuple[Bus, LayoutInterface]:
    """The same, for a suite with no business with time."""
    bus, app, _clock = wired()
    return bus, app


def heard(bus: Bus, topic_filter: str) -> list[tuple[str, Payload]]:
    """Everything published under `topic_filter` from here on, in order —
    plus whatever retained value a state filter is owed on subscribing."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe(topic_filter, lambda topic, payload: seen.append((topic, payload)))
    return seen


def occupancy(bus: Bus) -> list[tuple[str, Payload]]:
    """Every occupancy event from here on, in order. Two subscriptions rather
    than one filter: the two leaves sit beside the commands under
    `tc49/layout/`, and an event topic is never replayed, so what this
    collects is what the fold published after it was asked."""
    seen: list[tuple[str, Payload]] = []
    for leaf in (BLOCK_OCCUPIED, BLOCK_VACATED):
        bus.subscribe(
            leaf, lambda published, payload: seen.append((published, payload))
        )
    return seen


def energised(bus: Bus) -> None:
    """The hardware reporting a live railroad, which is the only thing that
    puts `state/power` on `on`."""
    bus.publish(DEVICE_TRACK, {"power": "on"})
    bus.drain()


def stand(bus: Bus, train: str, block: str) -> None:
    """A hand put a train down and the dispatcher accepted it."""
    bus.publish(PLACED, {"train": train, "block": block})
    bus.drain()


def align(bus: Bus, connection: str, transit: str) -> None:
    """The command the dispatcher sends before each grant, carrying the points
    the way needs — read off the layout, as the dispatcher reads them."""
    bus.publish(
        ALIGN,
        {
            "connection": connection,
            "transit": transit,
            "points": POINTS.get(transit, []),
        },
    )
    bus.drain()


def move(bus: Bus, train: str, connection: str, transit: str, into: str) -> None:
    """The command the driver sends: a train across a transit into a block."""
    bus.publish(
        MOVE,
        {
            "train": train,
            "connection": connection,
            "transit": transit,
            "into": into,
            "speed": 1.0,
        },
    )
    bus.drain()


def reads(bus: Bus, end: str, level: str, reason: str | None = None) -> None:
    """One detector saying what it sees at the block end it watches. A
    `reason` is free text a person reads and rides only with `unknown`."""
    payload: Payload = {"addr": end, "occupancy": level}
    if reason is not None:
        payload["reason"] = reason
    bus.publish(f"{DEVICE_SENSOR}/{end}", payload)
    bus.drain()


def elapse(clock: Clock, seconds: float) -> None:
    """Time passing, driven rather than slept: the run clock takes an instant
    and a settling time is a span, so the addition is said once here."""
    clock.advance(clock.now + seconds)


def settle(
    bus: Bus, app: LayoutInterface, clock: Clock, after: float = SETTLING_S
) -> None:
    """The settling time passing and the loop's owner acting on it, which is
    the whole of what drives the debounce."""
    elapse(clock, after)
    app.settle()
    bus.drain()
