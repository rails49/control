"""A train with no further grant stops at its block's far sensor (#1169).

Run on a line of four blocks, `w`, `x`, `y` and `z`, each entered at `.A` and
left at `.B`, so a further move has somewhere to go: a train crossing into `x`
comes in at `x.A`, the entry sensor, and stops at `x.B`, the far sensor.

Unless a test is about the `caution` drop, every far end shows `clear`, so the
only speeds written are the move's and the stops.
"""

import pytest

from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.invariants import Record, View, adr_0084_sign_changes_through_zero
from tc49.lib.inventory import AUTOMATIC, MANUAL
from tc49.lib.layout import Layout
from tests.layout.railroad import (
    ASPECTS,
    PLACED,
    POWER_WANTED,
    REMOVED,
    SETTINGS_WANTED,
    UNKNOWN_SENSORS,
    align,
    commanded,
    drains,
    energised,
    faces,
    gives,
    heard,
    lies,
    move,
    reads,
    settle,
    speeds,
    stand,
    stock,
    switches,
    takes,
    turns,
)

ENTRY = "x.A"
FAR = "x.B"
CLEAR = 0.6
CAUTION = 0.3
BLOCKS = ("w", "x", "y", "z")
WITHDRAW_WANTED = "tc49/layout/withdraw_wanted"
MOVE_WITHDRAWN = "tc49/layout/move_withdrawn"
Written = list[tuple[str, Payload]]


def line() -> Layout:
    return Layout.from_document(
        {
            "layout": "line",
            "blocks": {block: {"length": 1000} for block in BLOCKS},
            "connections": {
                "wx": {"transits": {"t": ["w.B", "x.A"]}},
                "xy": {"transits": {"t": ["x.B", "y.A"]}},
                "yz": {"transits": {"t": ["y.B", "z.A"]}},
            },
        }
    )


class Rig:
    """The app on the line, a train standing in `w` and every far end `clear`.

    `heard` is every traction write since the rig was built, or since a test
    cleared it."""

    def __init__(
        self, driving: str = AUTOMATIC, train: str = "single", far_clear: bool = True
    ) -> None:
        self.clock = Clock()
        self.bus = InProcessBus(self.clock)
        self.app = LayoutInterface(self.bus, line(), stock(), self.clock, point_gap=0.0)
        self.bus.drain()
        for block in BLOCKS:
            reads(self.bus, f"{block}.A", "clear")
            reads(self.bus, f"{block}.B", "clear")
        self.settle()
        self.clock.now = 0.0
        if driving == AUTOMATIC:
            switches(self.bus, AUTOMATIC)
        energised(self.bus)
        self.train = train
        stand(self.bus, train, "w")
        faces(self.bus, **{train: "w.A-to-B"})
        if far_clear:
            self.shows({f"{block}.B": "clear" for block in BLOCKS})
        self.heard: Written = commanded(self.bus)
        self.bus.drain()
        self.heard.clear()

    def settle(self) -> None:
        settle(self.bus, self.app, self.clock)

    def shows(self, aspects: dict[str, str]) -> None:
        """The dispatcher's whole picture of the signals."""
        self.bus.publish(ASPECTS, {"aspects": aspects})
        self.bus.drain()

    def crosses(self, into: str = "x", speed: float = CLEAR) -> None:
        """The move into `into`, from the block before it on the line."""
        connection = f"{BLOCKS[BLOCKS.index(into) - 1]}{into}"
        align(self.bus, connection, "t")
        move(self.bus, self.train, connection, "t", into, speed)

    def backs(self, into: str = "w", speed: float = CLEAR) -> None:
        """The move back into `into`, from the block after it on the line."""
        connection = f"{into}{BLOCKS[BLOCKS.index(into) + 1]}"
        align(self.bus, connection, "t")
        move(self.bus, self.train, connection, "t", into, speed)

    def read(self, end: str, level: str = "occupied") -> None:
        """A sensor's level, standing."""
        reads(self.bus, end, level)
        self.settle()

    def unknown(self, *ends: str) -> None:
        """These sensors reporting `unknown` until it stands."""
        for end in ends:
            reads(self.bus, end, "unknown", "a test")
        self.settle()

    def wrote(self) -> list[tuple[str, float]]:
        return speeds(self.heard)

    def takes_out(self) -> list[tuple[str, float]]:
        """What was written since last asked."""
        written = speeds(self.heard)
        self.heard.clear()
        return written


def crossing(driving: str = AUTOMATIC, train: str = "single") -> Rig:
    """A train running into `x`, the speed it was given already taken out."""
    rig = Rig(driving, train)
    rig.crosses()
    rig.takes_out()
    return rig


def stopped() -> list[tuple[str, float]]:
    return [("3", 0.0)]


def given(speed: float = CLEAR) -> list[tuple[str, float]]:
    return [("3", speed)]


# -- the arrival ---------------------------------------------------------------


def test_the_far_sensor_stops_a_train_with_no_further_grant() -> None:
    rig = crossing(train="topped")

    rig.read(ENTRY)
    assert rig.wrote() == []
    rig.read(ENTRY, "clear")
    assert rig.wrote() == []

    rig.read(FAR)
    assert rig.wrote() == [("8", 0.0), ("4", 0.0)]


def test_the_far_sensor_deletes_the_crossing() -> None:
    """Its reading a second time, after a clear, is about nothing."""
    rig = crossing()
    rig.read(FAR)
    rig.takes_out()
    rig.read(FAR, "clear")
    rig.read(FAR)
    assert rig.wrote() == []


def test_a_throttle_is_stopped_at_the_far_sensor_and_its_next_frame_is_written() -> (
    None
):
    rig = crossing()
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.4)
    rig.takes_out()

    rig.read(ENTRY)
    assert rig.wrote() == []
    rig.read(FAR)
    assert rig.takes_out() == stopped()
    turns(rig.bus, "single", 0.4)
    assert rig.wrote() == given(0.4)


def test_with_the_far_sensor_unknown_the_tail_clearing_stops_the_train() -> None:
    rig = crossing()
    rig.unknown(FAR)
    rig.read(ENTRY)
    assert rig.wrote() == []
    rig.read(ENTRY, "clear")
    assert rig.wrote() == stopped()


def test_the_far_sensor_going_unknown_with_the_tail_in_stops_the_train_at_once() -> (
    None
):
    rig = crossing()
    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    assert rig.wrote() == []
    rig.unknown(FAR)
    assert rig.wrote() == stopped()


def test_the_crossing_a_tail_clearing_ended_stays_for_its_far_sensor() -> None:
    """It still ends at the far sensor, with no second stop."""
    rig = crossing()
    rig.unknown(FAR)
    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    rig.takes_out()

    rig.read(FAR)

    assert rig.wrote() == []


# -- both sensors unknown ------------------------------------------------------


def test_the_entry_sensor_going_unknown_alone_leaves_the_far_sensor_to_stop_it() -> (
    None
):
    rig = crossing()
    rig.unknown(ENTRY)
    assert rig.wrote() == []
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_both_going_unknown_stops_the_train() -> None:
    rig = crossing()
    rig.unknown(ENTRY)
    assert rig.wrote() == []
    rig.unknown(FAR)
    assert rig.wrote() == stopped()


def test_a_move_acted_on_with_both_unknown_writes_no_speed() -> None:
    rig = Rig()
    rig.unknown(ENTRY, FAR)
    rig.crosses()
    assert rig.wrote() == []
    assert rig.app.position["single"] == "x"


@pytest.mark.parametrize("ends", [(ENTRY,), (FAR,), (ENTRY, FAR)])
def test_a_train_a_throttle_holds_is_stopped_for_neither(ends: tuple[str, ...]) -> None:
    rig = crossing()
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.4)
    rig.takes_out()
    rig.unknown(*ends)
    assert rig.wrote() == []


def blind() -> Rig:
    """A train stopped for both sensors going unknown."""
    rig = crossing()
    rig.unknown(ENTRY, FAR)
    rig.takes_out()
    return rig


def test_blind_then_the_entry_sensor_occupied_gives_the_speed_until_it_clears() -> None:
    rig = blind()
    rig.read(ENTRY)
    assert rig.takes_out() == given()
    rig.read(ENTRY, "clear")
    assert rig.wrote() == stopped()


def test_blind_then_the_entry_sensor_clear_with_the_head_in_is_the_arrival() -> None:
    """The head read in before the sensors went, the train stays stopped."""
    rig = crossing()
    rig.read(ENTRY)
    rig.unknown(ENTRY, FAR)
    rig.takes_out()

    rig.read(ENTRY, "clear")

    assert rig.takes_out() == stopped()
    # Stopped for good: nothing that comes back gives the speed again.
    rig.read(FAR, "clear")
    assert rig.wrote() == []


def test_blind_then_the_entry_sensor_clear_with_no_head_in_gives_the_speed() -> None:
    rig = blind()
    rig.read(ENTRY, "clear")
    assert rig.wrote() == given()


def test_the_accepted_case_of_a_train_no_sensor_ever_read() -> None:
    """The entry sensor goes unknown as the train passes it, the far sensor
    then goes too, and the entry sensor returns clear having never read it: the
    speed is given back, and nothing stops the train unless the far sensor
    returns."""
    rig = crossing()
    rig.unknown(ENTRY)
    rig.unknown(FAR)
    rig.takes_out()

    rig.read(ENTRY, "clear")
    assert rig.takes_out() == given()

    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_blind_then_the_far_sensor_occupied_is_the_arrival() -> None:
    rig = blind()
    rig.read(FAR)
    assert rig.takes_out() == stopped()
    rig.read(ENTRY, "clear")
    assert rig.wrote() == []


def test_blind_then_the_far_sensor_clear_gives_the_speed() -> None:
    rig = blind()
    rig.read(FAR, "clear")
    assert rig.wrote() == given()


@pytest.mark.parametrize("end, level", [(ENTRY, "clear"), (ENTRY, "occupied")])
def test_a_sensor_returning_when_the_train_was_never_stopped_writes_nothing(
    end: str, level: str
) -> None:
    """A train a person left running slowly does not lurch (ADR-0081, decision
    6)."""
    rig = crossing()
    rig.unknown(end)
    rig.read(end, level)
    assert rig.wrote() == []


def test_the_far_sensor_returning_clear_when_never_stopped_writes_nothing() -> None:
    rig = crossing()
    rig.unknown(FAR)
    rig.read(FAR, "clear")
    assert rig.wrote() == []


# -- a further move ------------------------------------------------------------


def onward(rig: Rig) -> None:
    """The train in `x` granted on into `y`, where a facing names `x`."""
    faces(rig.bus, **{rig.train: "x.A-to-B"})
    rig.crosses("y")


def test_a_further_move_runs_through_with_no_stop_and_still_deletes_the_crossing() -> (
    None
):
    rig = crossing()
    rig.read(ENTRY)
    onward(rig)
    assert rig.takes_out() == given()

    rig.read(FAR)

    assert rig.wrote() == []


def test_after_a_further_move_the_later_far_sensor_stops_the_train() -> None:
    rig = crossing()
    onward(rig)
    rig.takes_out()
    rig.read(FAR)
    rig.read("y.A")
    assert rig.wrote() == []
    rig.read("y.B")
    assert rig.wrote() == stopped()


def test_a_further_move_a_throttle_holds_stops_at_no_far_sensor() -> None:
    rig = crossing()
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.4)
    onward(rig)
    rig.takes_out()

    rig.read(FAR)

    assert rig.wrote() == []


def test_a_further_move_in_manual_is_nobodys_and_the_old_far_sensor_still_stops() -> (
    None
):
    """Without this a train nobody is driving runs on through the next block at
    its last speed (ADR-0079)."""
    rig = crossing()
    switches(rig.bus, MANUAL)
    onward(rig)
    assert rig.wrote() == []

    rig.read(FAR)

    assert rig.wrote() == stopped()


def test_a_later_crossing_reached_by_a_switch_carries_the_earlier_through() -> None:
    rig = crossing()
    switches(rig.bus, MANUAL)
    onward(rig)
    switches(rig.bus, AUTOMATIC)
    assert rig.takes_out() == given()

    rig.read(FAR)

    assert rig.wrote() == []


def test_a_later_crossing_reached_by_a_take_carries_the_earlier_through() -> None:
    rig = crossing()
    switches(rig.bus, MANUAL)
    onward(rig)
    takes(rig.bus, "single")

    rig.read(FAR)

    assert rig.wrote() == []


def test_a_stale_crossing_keeps_no_earlier_place() -> None:
    """The crossings into `x` and `y` left standing, their far sensors unknown,
    and the train coming back into `x`: the new crossing goes in last, so it is
    the one a release finds outstanding, and not the old one into `y`."""
    rig = Rig()
    rig.crosses("x")
    rig.unknown(FAR)
    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    onward(rig)
    rig.unknown("y.B")
    rig.read("y.A")
    rig.read("y.A", "clear")
    faces(rig.bus, single="y.A-to-B")
    rig.backs("x")
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.0)
    rig.takes_out()

    gives(rig.bus, "single")

    assert rig.wrote() == given(-CLEAR)


# -- a move that reverses the train ---------------------------------------------


def adr_0084_holds(written: Written) -> None:
    record = Record(line(), {}, stock())
    view = View({}, line(), stock())
    for topic, payload in written:
        assert adr_0084_sign_changes_through_zero(record, view, topic, payload) == []
        record.observe(topic, payload)


def reversing() -> tuple[Rig, Written]:
    """A train running into `x` asked straight back out through `x.A`, and
    every write from its start. The train's facing still names `x` run A to
    B, so the way back is propelled, the other sign."""
    rig = Rig()
    every = commanded(rig.bus)
    rig.crosses()
    faces(rig.bus, single="x.A-to-B")
    rig.backs()
    return rig, every


def test_a_move_back_through_the_entry_end_waits_for_the_far_sensor() -> None:
    rig, every = reversing()
    assert speeds(every) == given()
    assert rig.app.position["single"] == "x"

    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    assert speeds(every) == given()
    assert rig.app.position["single"] == "x"

    rig.read(FAR)
    assert speeds(every) == [("3", CLEAR), ("3", 0.0), ("3", -CLEAR)]
    assert rig.app.position["single"] == "w"
    adr_0084_holds(every)


def test_the_same_with_the_far_sensor_unknown_on_the_entry_sensor_clearing() -> None:
    rig, every = reversing()
    rig.unknown(FAR)
    rig.read(ENTRY)
    assert speeds(every) == given()

    rig.read(ENTRY, "clear")

    assert speeds(every) == [("3", CLEAR), ("3", 0.0), ("3", -CLEAR)]
    adr_0084_holds(every)


def test_the_same_with_the_far_sensor_going_unknown_after_the_tail() -> None:
    """The speed goes out after the list that says why the train stopped."""
    rig, every = reversing()
    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    rig.unknown(FAR)
    assert speeds(every) == [("3", CLEAR), ("3", 0.0), ("3", -CLEAR)]
    adr_0084_holds(every)


def test_a_train_a_throttle_holds_is_not_held() -> None:
    rig = crossing()
    takes(rig.bus, "single")
    faces(rig.bus, single="x.A-to-B")
    rig.backs()
    assert rig.app.position["single"] == "w"
    assert rig.wrote() == []


def test_a_move_out_through_the_far_end_is_not_held() -> None:
    rig = crossing()
    onward(rig)
    assert rig.app.position["single"] == "y"
    assert rig.wrote() == given()


def test_a_second_move_for_the_transit_replaces_the_one_held() -> None:
    rig, every = reversing()
    rig.backs(speed=CAUTION)
    rig.read(FAR)
    assert speeds(every) == [("3", CLEAR), ("3", 0.0), ("3", -CAUTION)]


def test_a_move_held_under_a_cut_is_kept_and_judged_again_on_on() -> None:
    """The kept rule comes first. Here the train stopped under the cut and the
    far sensor has read, so `on` finds no reason to hold it."""
    rig = crossing()
    rig.bus.publish(POWER_WANTED, {"power": "off"})
    rig.bus.drain()
    faces(rig.bus, single="x.A-to-B")
    rig.backs()
    assert rig.app.position["single"] == "x"
    rig.read(FAR)
    rig.takes_out()

    rig.bus.publish(POWER_WANTED, {"power": "on"})
    rig.bus.drain()
    energised(rig.bus)

    assert rig.app.position["single"] == "w"
    assert set(rig.wrote()) == {("3", -CLEAR)}


def test_a_move_kept_under_a_cut_is_held_on_on_with_the_train_still_going() -> None:
    """Its far sensor not read: `on` gives the train its speed, and holds the
    move for the arrival as it would have on any other day."""
    rig = crossing()
    rig.bus.publish(POWER_WANTED, {"power": "off"})
    rig.bus.drain()
    faces(rig.bus, single="x.A-to-B")
    rig.backs()
    rig.takes_out()

    rig.bus.publish(POWER_WANTED, {"power": "on"})
    rig.bus.drain()
    energised(rig.bus)

    assert rig.app.position["single"] == "x"
    assert set(rig.takes_out()) == {("3", CLEAR)}

    rig.read(FAR)

    assert rig.wrote() == [("3", 0.0), ("3", -CLEAR)]
    assert rig.app.position["single"] == "w"


def test_a_withdrawal_drops_the_move_held() -> None:
    """Only a train standing gives a move back, so this one stopped for both
    its sensors going unknown."""
    rig = crossing()
    faces(rig.bus, single="x.A-to-B")
    rig.backs()
    rig.unknown(ENTRY, FAR)
    answered = heard(rig.bus, MOVE_WITHDRAWN)
    rig.bus.publish(
        WITHDRAW_WANTED, {"train": "single", "transit": "wx.t", "into": "w"}
    )
    rig.bus.drain()
    assert [topic for topic, _payload in answered] == [MOVE_WITHDRAWN]
    rig.takes_out()

    rig.read(FAR)

    assert rig.app.position["single"] == "x"
    assert all(speed == 0.0 for _addr, speed in rig.wrote())


def asks_back(rig: Rig, into: str = "w") -> list[tuple[str, Payload]]:
    """The dispatcher asking for the held move back, and every answer from here
    on. The transit is the one the move back over `wx` crosses."""
    answered = heard(rig.bus, MOVE_WITHDRAWN)
    rig.bus.publish(
        WITHDRAW_WANTED, {"train": "single", "transit": "wx.t", "into": into}
    )
    rig.bus.drain()
    return answered


THE_MOVE_BACK = {"train": "single", "transit": "wx.t", "into": "w"}


def test_a_withdrawal_with_the_train_running_waits_for_the_far_sensor() -> None:
    rig, every = reversing()
    answered = asks_back(rig)
    assert answered == []
    assert speeds(every) == given()

    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    assert answered == []
    assert speeds(every) == given()

    rig.read(FAR)

    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]
    assert speeds(every)[0] == ("3", CLEAR)
    assert {speed for _addr, speed in speeds(every)[1:]} == {0.0}
    assert rig.app.position["single"] == "x"


def test_a_withdrawal_with_the_far_sensor_unknown_waits_for_the_entry_sensor() -> None:
    rig, every = reversing()
    rig.unknown(FAR)
    answered = asks_back(rig)
    rig.read(ENTRY)
    assert answered == []

    rig.read(ENTRY, "clear")

    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]
    assert {speed for _addr, speed in speeds(every)[1:]} == {0.0}
    assert rig.app.position["single"] == "x"


def test_a_withdrawal_with_the_far_sensor_going_unknown_answers_after_the_list() -> (
    None
):
    """The answer goes out after the list that says why the train stopped."""
    rig, every = reversing()
    asks_back(rig)
    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    told: list[str] = []
    for topic in (UNKNOWN_SENSORS, MOVE_WITHDRAWN):
        rig.bus.subscribe(topic, lambda topic, _payload: told.append(topic))
    rig.bus.drain()
    told.clear()

    rig.unknown(FAR)

    assert told[-1] == MOVE_WITHDRAWN
    assert told.count(MOVE_WITHDRAWN) == 1
    assert UNKNOWN_SENSORS in told
    assert {speed for _addr, speed in speeds(every)[1:]} == {0.0}
    assert rig.app.position["single"] == "x"


def test_a_withdrawal_with_a_throttle_taking_the_train_answers_at_the_far_sensor() -> (
    None
):
    rig, _every = reversing()
    answered = asks_back(rig)
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.4)
    rig.takes_out()
    assert answered == []

    rig.read(FAR)

    assert {speed for _addr, speed in rig.takes_out()} == {0.0}
    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]
    turns(rig.bus, "single", 0.4)
    assert rig.wrote() == given(0.4)


def test_a_withdrawal_across_a_cut_answers_at_the_far_sensor() -> None:
    rig, every = reversing()
    answered = asks_back(rig)
    rig.bus.publish(POWER_WANTED, {"power": "off"})
    rig.bus.drain()
    rig.bus.publish(POWER_WANTED, {"power": "on"})
    rig.bus.drain()
    energised(rig.bus)
    assert answered == []
    assert speeds(every)[-1] == ("3", CLEAR)
    every.clear()

    rig.read(FAR)

    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]
    assert every and {speed for _addr, speed in speeds(every)} == {0.0}
    assert rig.app.position["single"] == "x"


@pytest.mark.parametrize(
    "topic, payload",
    [
        (PLACED, {"train": "single", "block": "z"}),
        (REMOVED, {"train": "single"}),
    ],
)
def test_a_placement_and_a_removal_take_the_withdrawal_with_the_move(
    topic: str, payload: Payload
) -> None:
    rig, every = reversing()
    answered = asks_back(rig)
    rig.bus.publish(topic, payload)
    rig.bus.drain()
    every.clear()

    rig.read(FAR)

    assert answered == []
    assert every == []


def test_a_placement_leaves_no_withdrawal_for_the_same_move_granted_later() -> None:
    rig, every = reversing()
    answered = asks_back(rig)
    stand(rig.bus, "single", "w")
    faces(rig.bus, single="w.A-to-B")
    rig.crosses()
    faces(rig.bus, single="x.A-to-B")
    rig.backs()

    rig.read(FAR)

    assert answered == []
    assert speeds(every)[-1] == ("3", -CLEAR)


def test_a_withdrawal_naming_another_into_is_not_kept() -> None:
    rig, every = reversing()
    answered = asks_back(rig, into="z")

    rig.read(FAR)

    assert answered == []
    assert speeds(every)[-2:] == [("3", 0.0), ("3", -CLEAR)]
    assert rig.app.position["single"] == "w"


def test_a_second_move_naming_another_into_leaves_the_withdrawal_standing() -> None:
    """Its near end is in the block the train left, so `_cross` drops it and
    the move asked back is still the one held."""
    rig, every = reversing()
    answered = asks_back(rig)
    align(rig.bus, "wx", "t")
    move(rig.bus, "single", "wx", "t", "x", CAUTION)
    assert answered == []
    assert speeds(every) == given()

    rig.read(FAR)

    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]
    assert {speed for _addr, speed in speeds(every)[1:]} == {0.0}


def test_a_running_train_whose_move_is_not_held_gets_no_answer() -> None:
    rig = crossing()
    answered = heard(rig.bus, MOVE_WITHDRAWN)
    rig.bus.publish(
        WITHDRAW_WANTED, {"train": "single", "transit": "wx.t", "into": "x"}
    )
    rig.bus.drain()
    assert answered == []
    assert rig.wrote() == []

    rig.read(FAR)

    assert answered == []


def test_a_withdrawal_with_both_sensors_gone_stands_until_the_arrival() -> None:
    rig, every = reversing()
    answered = asks_back(rig)
    rig.unknown(ENTRY, FAR)
    assert answered == []
    assert speeds(every)[-1] == ("3", 0.0)

    rig.read(FAR)

    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]
    assert {speed for _addr, speed in speeds(every)[1:]} == {0.0}


def test_a_second_ask_answered_standing_leaves_no_withdrawal_behind() -> None:
    """Answered at once by the train standing, so the next move back over that
    transit is not the one this ask was about."""
    rig, every = reversing()
    answered = asks_back(rig)
    rig.unknown(ENTRY, FAR)
    rig.bus.publish(WITHDRAW_WANTED, THE_MOVE_BACK)
    rig.bus.drain()
    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]

    rig.read(FAR)
    faces(rig.bus, single="x.A-to-B")
    rig.bus.drain()
    every.clear()
    rig.backs()

    assert [payload for _topic, payload in answered] == [THE_MOVE_BACK]
    assert speeds(every) == given(-CLEAR)


@pytest.mark.parametrize(
    "topic, payload, where",
    [
        (PLACED, {"train": "single", "block": "z"}, "z"),
        (REMOVED, {"train": "single"}, None),
    ],
)
def test_a_placement_and_a_removal_drop_the_move_held(
    topic: str, payload: Payload, where: str | None
) -> None:
    rig, every = reversing()
    rig.bus.publish(topic, payload)
    rig.bus.drain()
    every.clear()

    rig.read(FAR)

    assert every == []
    assert rig.app.position.get("single") == where


# -- the caution drop ----------------------------------------------------------


def cautioned(train: str = "single", speed: float = CLEAR) -> Rig:
    """A train running into `x` with no aspect said: its far end reads `stop`."""
    rig = Rig(train=train, far_clear=False)
    rig.crosses(speed=speed)
    rig.takes_out()
    return rig


def aspects(rig: Rig, far: str) -> None:
    rig.bus.publish(ASPECTS, {"aspects": {FAR: far}})
    rig.bus.drain()


def test_the_head_in_with_the_far_end_at_stop_drops_each_car_to_caution() -> None:
    rig = cautioned("topped")
    rig.read(ENTRY)
    assert rig.wrote() == [("8", CAUTION), ("4", -CAUTION)]


def test_the_far_end_not_at_stop_writes_nothing() -> None:
    rig = Rig(far_clear=False)
    aspects(rig, "caution")
    rig.crosses()
    rig.takes_out()
    rig.read(ENTRY)
    assert rig.wrote() == []


def test_a_train_at_caution_or_slower_writes_nothing() -> None:
    for speed in (CAUTION, 0.2):
        rig = cautioned(speed=speed)
        rig.read(ENTRY)
        assert rig.wrote() == []


def test_the_far_end_going_to_stop_after_the_head_is_in_writes_it() -> None:
    rig = crossing()
    rig.read(ENTRY)
    assert rig.wrote() == []
    aspects(rig, "stop")
    assert rig.wrote() == given(CAUTION)


def test_the_far_end_going_to_stop_after_the_tail_is_in_writes_it() -> None:
    rig = crossing()
    rig.read(ENTRY)
    rig.read(ENTRY, "clear")
    aspects(rig, "stop")
    assert rig.wrote() == given(CAUTION)


def test_the_far_end_going_to_stop_before_the_head_is_in_writes_nothing() -> None:
    rig = crossing()
    aspects(rig, "stop")
    assert rig.wrote() == []
    rig.read(ENTRY)
    assert rig.wrote() == given(CAUTION)


def test_a_far_end_with_no_signal_counts_as_stop() -> None:
    """A value naming every signalled end and not this one."""
    rig = Rig(far_clear=False)
    rig.shows({"y.B": "clear"})
    rig.crosses()
    rig.takes_out()
    rig.read(ENTRY)
    assert rig.wrote() == given(CAUTION)


def test_a_train_a_throttle_holds_keeps_the_persons_speed() -> None:
    rig = cautioned()
    takes(rig.bus, "single")
    turns(rig.bus, "single", CLEAR)
    rig.takes_out()
    rig.read(ENTRY)
    aspects(rig, "stop")
    assert rig.wrote() == []


def test_on_after_a_cut_gives_the_lowered_speed() -> None:
    rig = cautioned()
    rig.read(ENTRY)
    rig.bus.publish(POWER_WANTED, {"power": "off"})
    rig.bus.drain()
    rig.takes_out()

    rig.bus.publish(POWER_WANTED, {"power": "on"})
    rig.bus.drain()

    assert rig.wrote() == given(CAUTION)


def test_a_release_running_at_clear_with_the_far_end_at_stop_drops_to_caution() -> None:
    rig = cautioned()
    takes(rig.bus, "single")
    rig.read(ENTRY)
    assert rig.wrote() == []
    gives(rig.bus, "single")
    assert rig.takes_out() == given(CAUTION)
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_a_release_at_a_slow_speed_is_not_raised() -> None:
    """It never raises a speed: the train runs at the person's, under
    `caution`, whatever the grant was worth."""
    rig = cautioned()
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.1)
    rig.read(ENTRY)
    rig.takes_out()
    gives(rig.bus, "single")
    assert rig.wrote() == []


def test_a_release_running_back_the_other_way_changes_no_sign() -> None:
    """A train a person left running away from its far sensor has no need of
    the drop, and a sign is not changed without a 0 (ADR-0084)."""
    rig = cautioned()
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.0)
    turns(rig.bus, "single", -CLEAR)
    rig.read(ENTRY)
    rig.takes_out()
    gives(rig.bus, "single")
    assert rig.wrote() == []


def test_a_caution_changed_in_the_settings_holds_from_the_next_check() -> None:
    rig = cautioned()
    rig.bus.publish(SETTINGS_WANTED, {"speeds": {"caution": 0.2}})
    rig.bus.drain()
    rig.read(ENTRY)
    assert rig.wrote() == given(0.2)


def test_the_drop_is_on_the_crossing_for_whatever_gives_the_speed_next() -> None:
    """Stopped for the sensors and given its speed back: the lowered one."""
    rig = cautioned()
    rig.read(ENTRY)
    rig.unknown(ENTRY, FAR)
    rig.takes_out()
    rig.read(FAR, "clear")
    assert rig.wrote() == given(CAUTION)


# -- what keys off `outstanding` -------------------------------------------------


def between_sensors(driving: str = AUTOMATIC) -> Rig:
    """A train with its head past the entry sensor."""
    rig = crossing(driving=driving)
    rig.read(ENTRY)
    rig.takes_out()
    return rig


def test_a_withdrawal_is_refused_once_the_head_is_in() -> None:
    """A train nothing drove, in `manual`, standing past its entry sensor: no
    answer, the cancel waiting for the sensors."""
    rig = between_sensors(MANUAL)
    answered = heard(rig.bus, MOVE_WITHDRAWN)
    rig.bus.publish(
        WITHDRAW_WANTED, {"train": "single", "transit": "wx.t", "into": "x"}
    )
    rig.bus.drain()
    assert answered == []


def test_a_withdrawal_before_the_head_is_in_is_answered() -> None:
    rig = crossing(driving=MANUAL)
    answered = heard(rig.bus, MOVE_WITHDRAWN)
    rig.bus.publish(
        WITHDRAW_WANTED, {"train": "single", "transit": "wx.t", "into": "x"}
    )
    rig.bus.drain()
    assert [topic for topic, _payload in answered] == [MOVE_WITHDRAWN]


def test_a_switch_to_automatic_drives_a_train_standing_between_its_sensors() -> None:
    rig = between_sensors(MANUAL)
    switches(rig.bus, AUTOMATIC)
    assert rig.takes_out() == given()
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_a_switch_to_automatic_gives_the_lowered_speed_where_it_is_due() -> None:
    rig = Rig(driving=MANUAL, far_clear=False)
    rig.crosses()
    rig.read(ENTRY)
    switches(rig.bus, AUTOMATIC)
    assert rig.wrote() == given(CAUTION)


def test_a_switch_to_manual_lets_a_train_run_on_to_the_arrival() -> None:
    rig = between_sensors()
    switches(rig.bus, MANUAL)
    assert rig.wrote() == []
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_a_take_between_the_sensors_writes_nothing_and_the_arrival_writes_0() -> None:
    rig = between_sensors()
    takes(rig.bus, "single")
    assert rig.wrote() == []
    rig.read(FAR)
    assert rig.takes_out() == stopped()
    turns(rig.bus, "single", 0.4)
    assert rig.wrote() == given(0.4)


def test_a_release_in_manual_stops_it_and_the_crossing_stays_outstanding() -> None:
    rig = between_sensors(MANUAL)
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.4)
    rig.takes_out()
    gives(rig.bus, "single")
    assert rig.takes_out() == stopped()

    switches(rig.bus, AUTOMATIC)

    assert rig.wrote() == given()


def test_a_release_in_automatic_running_keeps_the_persons_speed() -> None:
    rig = between_sensors()
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.4)
    rig.takes_out()
    gives(rig.bus, "single")
    assert rig.wrote() == []
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_a_release_in_automatic_standing_is_given_its_grants_speed() -> None:
    rig = between_sensors()
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.0)
    rig.takes_out()
    gives(rig.bus, "single")
    assert rig.takes_out() == given()
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_on_after_a_cut_gives_a_train_between_its_sensors_its_speed() -> None:
    rig = between_sensors()
    rig.bus.publish(POWER_WANTED, {"power": "off"})
    rig.bus.drain()
    rig.takes_out()
    rig.bus.publish(POWER_WANTED, {"power": "on"})
    rig.bus.drain()
    assert rig.takes_out() == given()
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_a_drain_lets_a_train_between_its_sensors_run_to_the_far_sensor() -> None:
    rig = between_sensors()
    drains(rig.bus)
    assert rig.wrote() == []
    rig.read(FAR)
    assert rig.wrote() == stopped()


def test_a_wrong_report_stops_a_train_between_its_sensors_with_the_tail_out() -> None:
    rig = Rig()
    align_reported(rig)
    move(rig.bus, "single", "wx", "t", "x", CLEAR)
    rig.read(ENTRY)
    rig.takes_out()
    lies(rig.bus, "20", "closed")
    assert rig.takes_out() == stopped()
    # And stays out of it: the point has moved under a train it was held for.
    rig.read(FAR, "clear")
    assert rig.wrote() == []


def align_reported(rig: Rig) -> None:
    """The way into `x` asked for, over a reported point that lies there."""
    lies(rig.bus, "20", "thrown")
    rig.bus.publish(
        "tc49/layout/align",
        {
            "connection": "wx",
            "transit": "t",
            "points": [{"addr": "20", "position": "thrown", "reported": True}],
        },
    )
    rig.bus.drain()
