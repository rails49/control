"""Tests of `tests/invariants.py`: when each invariant is asserted (ADR-0096)."""

import pytest

from tc49.dispatcher import FullRoute, Incremental
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.invariants import ALLOCATION, ASPECTS, MOVING, POWER
from tests.generate import LAYOUTS, ROSTERS
from tests.harness import StrategyFactory
from tests.invariants import checked

MEET = "single-track-meet"


def bus(strategy: StrategyFactory = Incremental) -> InProcessBus:
    """A bus being checked, which already says nothing is moving: a missing
    `moving` row reads as true (`payload.moving`)."""
    watched = InProcessBus(Clock())
    watched.publish(MOVING, {"moving": False})
    checked(watched, LAYOUTS[MEET], ROSTERS[MEET], strategy)
    watched.drain()
    return watched


def placed(holder: str) -> Payload:
    return {"trains": {"t1": "w_main"}, "crossing": {}, "locks": {"w_main": holder}}


def test_one_apps_invariant_fails_at_the_message_that_breaks_it() -> None:
    watched = bus()
    watched.publish(ALLOCATION, placed("t2"))
    with pytest.raises(AssertionError, match="ADR-0076"):
        watched.drain()


def test_a_cross_app_invariant_waits_for_nothing_left_to_deliver() -> None:
    watched = bus()
    seen: list[str] = []
    watched.subscribe("#", lambda topic, payload: seen.append(topic))
    # Power off before the aspects follow is a moment, not a breach.
    watched.publish(ASPECTS, {"aspects": {"w_main.B": "clear"}})
    watched.publish(POWER, {"power": "off"})
    with pytest.raises(AssertionError, match="with nothing left to deliver"):
        watched.drain()
    assert seen == [MOVING, ASPECTS, POWER]


def test_two_blocks_ahead_is_not_asked_of_full_route() -> None:
    route = ["west_1", "west_throat.from_1", "w_main", "west_switch.to_up"]
    route += ["loop_up", "east_switch.from_up", "e_main"]
    picture: Payload = {
        "trains": {"t1": "west_1"},
        "crossing": {},
        "locks": {resource: "t1" for resource in route},
        "requests": [{"id": "r1", "train": "t1", "dest": ["e_main.A"], "route": route}],
    }
    watched = bus(FullRoute)
    watched.publish(ALLOCATION, picture)
    watched.drain()

    held = bus(Incremental)
    held.publish(ALLOCATION, picture)
    with pytest.raises(AssertionError, match="ADR-0026"):
        held.drain()
