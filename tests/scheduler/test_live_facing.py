"""Facing against the signals over a live assembly: what a throttle reads the
signal in front of the train off (#1025)."""

from typing import Any

from tc49.lib.layout import block_of, facing_ends
from tests.harness import events, live, press, ticks

WANTED = "tc49/schedule/request_wanted"
SENSORS = ("block_occupied", "block_vacated")


def settled(trace: str) -> list[dict[str, Any]]:
    """The run's picture each time the railroad is about to read a sensor,
    and once at the end: every app has answered the reading before, so this
    is what a person looking at the layout sees between two readings.

    Each picture holds the last facing, allocation and aspects, and the
    grants whose train the allocation has not yet named in the block they
    enter."""
    pictures: list[dict[str, Any]] = []
    now: dict[str, Any] = {"facing": {}, "trains": {}, "aspects": {}, "granted": {}}

    def snapshot() -> None:
        pictures.append({key: dict(value) for key, value in now.items()})

    for line in events(trace):
        event = line["event"]
        if event in SENSORS:
            snapshot()
        elif event == "facing":
            now["facing"] = line["facing"]
        elif event == "aspects":
            now["aspects"] = line["aspects"]
        elif event == "move_granted":
            now["granted"][line["train"]] = line
        elif event == "allocation":
            now["trains"] = line["trains"]
            for train, move in list(now["granted"].items()):
                if line["trains"].get(train) == move["into"]:
                    del now["granted"][train]
    snapshot()
    return pictures


def test_the_facing_points_at_the_signal_the_grant_cleared() -> None:
    """From each grant until the allocation names the train in the block it
    enters, the train's facing names the block it is recorded in and its nose
    is at the end showing the grant's aspect. A facing moved at the grant put
    the nose at the far end of the block ahead, which shows `stop`: a red
    throttle behind a green signal (#1025).

    Two trains, each dragged nose-first over more than one move, so grants
    land both before and after the vacate that ends the move ahead."""
    assembly = live("crossover-yard/meet")
    press(assembly, WANTED, {"train": "freight_1", "dest": ["dn_e.A", "dn_e.B"]})
    press(assembly, WANTED, {"train": "express_2", "dest": ["yard_w.B"]})
    ticks(assembly, 200)

    pictures = settled(assembly.trace)
    grants = [
        line for line in events(assembly.trace) if line["event"] == "move_granted"
    ]
    assert {line["train"] for line in grants} == {"freight_1", "express_2"}
    assert len(grants) > 2
    assert any(picture["granted"] for picture in pictures)
    for picture in pictures:
        for train, block in picture["trains"].items():
            assert block_of(picture["facing"][train]) == block, picture
        for train, move in picture["granted"].items():
            nose = facing_ends(picture["facing"][train])[1]
            assert picture["aspects"][nose] == move["aspect"], picture
    assert not pictures[-1]["granted"]  # every move was taken up
