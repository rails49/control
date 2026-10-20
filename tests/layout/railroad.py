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
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC
from tc49.lib.layout import Layout
from tc49.lib.roster import FORWARD, REVERSE, Car, Coupled, Roster, Train

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
POWER_WANTED = "tc49/layout/power_wanted"
DRIVING_WANTED = "tc49/layout/driving_wanted"
TAKE_WANTED = "tc49/layout/take_wanted"
THROTTLE_ALIVE = "tc49/layout/throttle_alive"
THROTTLE_WANTED = "tc49/layout/throttle_wanted"
PLACED = "tc49/dispatch/train_placed"
REMOVED = "tc49/dispatch/train_removed"
ASPECTS = "tc49/dispatch/state/aspects"
MOVING = "tc49/dispatch/state/moving"
FACING = "tc49/schedule/state/facing"

BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"
RAILROAD = "tc49/layout/state/railroad"
POWER = "tc49/layout/state/power"
DRIVING = "tc49/layout/state/driving"
TAKEN = "tc49/layout/state/taken"
DEVICE_SENSOR = "tc49/layout/state/device/sensor"
WANTED_TRACTION = "tc49/layout/state/wanted/traction"
WANTED_POINT = "tc49/layout/state/wanted/point"
WANTED_SIGNAL = "tc49/layout/state/wanted/signal"
WANTED_TRACK = "tc49/layout/state/wanted/track"
DEVICE_TRACK = "tc49/layout/state/device/track"
DEVICE_LINK = "tc49/layout/state/device/link"

POINTS: dict[str, list[dict[str, str]]] = {
    # The way over the crossover throws two, one of which the straight way
    # wants the other way about.
    "to_dn": [
        {"addr": "12", "position": "thrown"},
        {"addr": "13", "position": "thrown"},
    ],
    "straight": [{"addr": "12", "position": "closed"}],
}


def document() -> dict[str, Any]:
    """A layout document with signals at three ends and points on both ways."""
    return {
        "layout": "bench",
        "units": "mm",
        "blocks": {
            "up_w": {"length": 1000, "signals": {"B": "40"}},
            "up_e": {"length": 1000, "signals": {"A": "41"}},
            "dn_e": {"length": 1000, "signals": {"A": "41"}},
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


def loco(addr: str | None) -> Car:
    """One locomotive of the bench's stock, addressed or not. A car with no
    `addr` has no decoder and can be told nothing, which is a real car and the
    only kind the library rosters hold (ADR-0045)."""
    return Car("bench-600", "locomotive", 600, addr=addr)


def stock() -> Roster:
    """The trains this railroad owns, drawn here as the railroad is: no
    committed roster addresses a car, the addresses being a fact of the
    physical stock rather than of a document anyone shares (ADR-0030).

    `freight_1` is the suite's ordinary train and carries **no** address —
    what most of these suites drive is a train nothing can be sent to, which
    is the case the traction write leaves alone. The three below it are what
    the traction suite drives: one addressed locomotive, a top-and-tail set
    with a `reverse` locomotive at the tail, and a set whose van has no
    decoder.
    """
    return Roster(
        "bench",
        {
            "freight_1": Train((Coupled(loco(None)),)),
            "single": Train((Coupled(loco("3")),)),
            "topped": Train((Coupled(loco("3")), Coupled(loco("4"), REVERSE))),
            "van": Train((Coupled(loco("3")), Coupled(loco(None), FORWARD))),
        },
    )


class Unstamped(InProcessBus):
    """A bus that stamps nothing, so a value carries the stamp it was handed.

    What a binding on the other side of a broker can put on a topic, and what
    it takes to stage the reordering MQTT permits: the in-process bus stamps
    from a clock that only goes forwards, so a pair cannot arrive backwards
    on it (ADR-0008, #240). Two suites stage it — the aspects and the sensor
    rows — so it lives here beside the rest of the wiring.
    """

    def _stamped(self, payload: Payload) -> Payload:
        return payload


def wired(
    settling_s: float = SETTLING_S, driving: str = AUTOMATIC
) -> tuple[InProcessBus, LayoutInterface, Clock]:
    """A fresh app on a fresh bus with the clock the two of them share, its
    startup cascade delivered: the railroad is up, dark, and has heard nothing
    from the hardware.

    Switched to `automatic` unless `driving` says otherwise. The app comes up
    `manual` (ADR-0079), where it writes no traction for a train no throttle
    holds, and what most of these suites drive is the grant this app turns
    into a speed.

    The clock comes back because the settling time is measured against it and
    the suite drives it directly — nothing here sleeps (#288)."""
    clock = Clock()
    bus = InProcessBus(clock)
    app = LayoutInterface(bus, railroad(), stock(), clock, settling_s)
    bus.drain()
    if driving == AUTOMATIC:
        switches(bus, AUTOMATIC)
    return bus, app, clock


def build(driving: str = AUTOMATIC) -> tuple[InProcessBus, LayoutInterface]:
    """The same, for a suite with no business with time."""
    bus, app, _clock = wired(driving=driving)
    return bus, app


def heard(bus: InProcessBus, topic_filter: str) -> list[tuple[str, Payload]]:
    """Everything published under `topic_filter` from here on, in order —
    plus whatever retained value a state filter is owed on subscribing."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe(topic_filter, lambda topic, payload: seen.append((topic, payload)))
    return seen


def commanded(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every traction write from here on, in order."""
    return heard(bus, WANTED_TRACTION + "/#")


def speeds(written: list[tuple[str, Payload]]) -> list[tuple[str, float]]:
    """Those writes as address and speed, which is what these suites assert:
    the stamp and the repeated address are the row's shape rather than this
    write's news, and the address on the topic is the one in the payload."""
    return [
        (str(payload["addr"]), float(payload["speed"])) for _topic, payload in written
    ]


def occupancy(bus: InProcessBus) -> list[tuple[str, Payload]]:
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


def energised(bus: InProcessBus) -> None:
    """The hardware reporting a live railroad, which is the only thing that
    puts `state/power` on `on`."""
    bus.publish(DEVICE_TRACK, {"power": "on"})
    bus.drain()


def moves(bus: InProcessBus, moving: bool) -> None:
    """The dispatcher stating whether any train is moving — the row a drain
    ends on (ADR-0078)."""
    bus.publish(MOVING, {"moving": moving})
    bus.drain()


def stand(bus: InProcessBus, train: str, block: str) -> None:
    """A hand put a train down and the dispatcher accepted it."""
    bus.publish(PLACED, {"train": train, "block": block})
    bus.drain()


def removed(bus: InProcessBus, train: str) -> None:
    """A hand lifted the train off and the dispatcher accepted it."""
    bus.publish(REMOVED, {"train": train})
    bus.drain()


def faces(bus: InProcessBus, **facing: str) -> None:
    """The scheduler saying which way each train points, as it holds it: the
    run each would make across its block (ADR-0019). The whole map, since that
    is what the state topic carries."""
    bus.publish(FACING, {"facing": dict(facing)})
    bus.drain()


THROTTLE = "t-1"
"""The id the suite's throttle minted when its page opened."""


def switches(bus: InProcessBus, driving: str) -> None:
    """A person switching the railroad's driving mode (ADR-0079)."""
    bus.publish(DRIVING_WANTED, {"driving": driving})
    bus.drain()


def takes(bus: InProcessBus, train: str, throttle: str = THROTTLE) -> None:
    """A throttle taking a train (ADR-0079)."""
    bus.publish(TAKE_WANTED, {"train": train, "throttle": throttle})
    bus.drain()


def gives(bus: InProcessBus, train: str) -> None:
    """The train released, whoever holds it: the gesture a throttle makes
    letting go and a panel makes forcing it."""
    bus.publish(TAKE_WANTED, {"train": train, "throttle": None})
    bus.drain()


def alive(bus: InProcessBus, throttle: str = THROTTLE) -> None:
    """A throttle saying it is still there."""
    bus.publish(THROTTLE_ALIVE, {"throttle": throttle})
    bus.drain()


def turns(
    bus: InProcessBus, train: str, speed: float, throttle: str = THROTTLE
) -> None:
    """A person's lever, signed for the train — positive is the way the train
    points, whichever way round its locomotives are wired."""
    bus.publish(THROTTLE_WANTED, {"train": train, "speed": speed, "throttle": throttle})
    bus.drain()


def align(bus: InProcessBus, connection: str, transit: str) -> None:
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


def move(
    bus: InProcessBus,
    train: str,
    connection: str,
    transit: str,
    into: str,
    speed: float | None = 1.0,
) -> None:
    """The command the driver sends: a train across a transit into a block,
    and how fast — a magnitude, the sign being the interface's to compose. A
    `speed` of None is the frame that states none, which the reader allows and
    this app has nothing to send for."""
    payload: Payload = {
        "train": train,
        "connection": connection,
        "transit": transit,
        "into": into,
    }
    if speed is not None:
        payload["speed"] = speed
    bus.publish(MOVE, payload)
    bus.drain()


def reads(bus: InProcessBus, end: str, level: str, reason: str | None = None) -> None:
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
    bus: InProcessBus, app: LayoutInterface, clock: Clock, after: float = SETTLING_S
) -> None:
    """The settling time passing and the loop's owner acting on it, which is
    the whole of what drives the debounce."""
    elapse(clock, after)
    app.settle()
    bus.drain()
