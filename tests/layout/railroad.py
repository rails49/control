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
from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
POWER_WANTED = "tc49/layout/power_wanted"
PLACED = "tc49/dispatch/train_placed"
REMOVED = "tc49/dispatch/train_removed"
ASPECTS = "tc49/dispatch/state/aspects"

POWER = "tc49/layout/state/power"
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


def build() -> tuple[Bus, LayoutInterface]:
    """A fresh app on a fresh bus, its startup cascade delivered: the railroad
    is up, dark, and has heard nothing from the hardware."""
    bus = Bus(Clock())
    app = LayoutInterface(bus, railroad())
    bus.drain()
    return bus, app


def heard(bus: Bus, topic_filter: str) -> list[tuple[str, Payload]]:
    """Everything published under `topic_filter` from here on, in order —
    plus whatever retained value a state filter is owed on subscribing."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe(topic_filter, lambda topic, payload: seen.append((topic, payload)))
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
