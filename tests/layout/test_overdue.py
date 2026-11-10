"""A train this app drives that does not arrive within the arrival allowance is
stopped where it is and listed on `state/overdue` (ADR-0040, #1190).

Run on a line of four blocks, `w`, `x`, `y` and `z`, each entered at `.A` and
left at `.B`: a train crossing into `x` comes in at `x.A`, the entry sensor, and
arrives at `x.B`, the far sensor. The way into `x` throws point 12, which a
test about a wrong point report marks reported (ADR-0097).

The clock runs a whole second at a time, every sensor reporting the level it
holds at each step, so no crossing stops for a silent sensor, and the app
settles once a step. A reading's half-second settling time lands it on the
next whole second, and nothing sleeps.
"""

from tc49.layout import LayoutInterface
from tc49.layout.interface import ARRIVAL_ALLOWANCE_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC, MANUAL
from tc49.lib.layout import Layout
from tests.layout.railroad import (
    ALIGN,
    ASPECTS,
    DEVICE_TRACK,
    OVERDUE,
    POWER,
    POWER_WANTED,
    SETTINGS_WANTED,
    WANTED_TRACTION,
    commanded,
    energised,
    faces,
    gives,
    heard,
    lies,
    move,
    reads,
    removed,
    speeds,
    stand,
    stock,
    switches,
    takes,
    turns,
)

BLOCKS = ("w", "x", "y", "z")
ENTRY = "x.A"
FAR = "x.B"
GRANTED = 0.5
CAUTION = 0.3
SETTLING = 0.5
ALLOWANCE = ARRIVAL_ALLOWANCE_S
NEVER_SILENT_S = 1e9
"""No throttle here goes silent: a release is a test's own gesture."""


def line() -> Layout:
    return Layout.from_document(
        {
            "layout": "line",
            "blocks": {block: {"length": 1000} for block in BLOCKS},
            "connections": {
                "wx": {
                    "transits": {"t": ["w.B", "x.A"]},
                    "points": {"t": [{"addr": "12", "position": "closed"}]},
                },
                "xy": {"transits": {"t": ["x.B", "y.A"]}},
                "yz": {"transits": {"t": ["y.B", "z.A"]}},
            },
        }
    )


class Rig:
    """The app on the line, `train` standing in `w` on a live railroad.

    `written` is every traction write and `rows` every `state/overdue` since
    the rig was built."""

    def __init__(
        self,
        train: str = "single",
        driving: str = AUTOMATIC,
        allowance: float = ALLOWANCE,
    ) -> None:
        self.clock = Clock()
        self.bus = InProcessBus(self.clock)
        self.app = LayoutInterface(
            self.bus,
            line(),
            stock(),
            self.clock,
            SETTLING,
            NEVER_SILENT_S,
            point_gap=0.0,
            arrival_allowance_s=allowance,
        )
        self.bus.drain()
        self.levels = {f"{block}.{end}": "clear" for block in BLOCKS for end in "AB"}
        self.report()
        self.clock.advance(SETTLING)
        self.app.settle()
        self.bus.drain()
        self.clock.now = 0.0
        if driving == AUTOMATIC:
            switches(self.bus, AUTOMATIC)
        energised(self.bus)
        self.train = train
        stand(self.bus, train, "w")
        faces(self.bus, **{train: "w.A-to-B"})
        self.written = commanded(self.bus)
        self.rows = heard(self.bus, OVERDUE)
        self.bus.drain()
        self.rows.clear()

    def report(self) -> None:
        """Every sensor saying the level it holds."""
        for end, level in self.levels.items():
            reads(self.bus, end, level, "a test" if level == "unknown" else None)

    def to(self, at: float) -> None:
        """The clock run to `at`, a second at a time, every sensor heard and
        the app settling at each step."""
        while self.clock.now < at:
            self.clock.advance(min(self.clock.now + 1.0, at))
            self.report()
            self.app.settle()
            self.bus.drain()

    def read(self, end: str, level: str = "occupied") -> None:
        """A sensor saying a new level, which it then holds: it stands at the
        next whole second."""
        self.levels[end] = level
        reads(self.bus, end, level, "a test" if level == "unknown" else None)

    def crosses(
        self, into: str = "x", speed: float = GRANTED, reported: bool = False
    ) -> None:
        """The move into `into` from the block before it, its `align` first,
        point 12 reported where `reported` says and lying as asked."""
        connection = f"{BLOCKS[BLOCKS.index(into) - 1]}{into}"
        points: list[Payload] = (
            [{"addr": "12", "position": "closed", "reported": reported}]
            if connection == "wx"
            else []
        )
        self.bus.publish(
            ALIGN, {"connection": connection, "transit": "t", "points": points}
        )
        self.bus.drain()
        if reported:
            lies(self.bus, "12", "closed")
        move(self.bus, self.train, connection, "t", into, speed)

    def onward(self) -> None:
        """The train granted on from `x` into `y`."""
        faces(self.bus, **{self.train: "x.A-to-B"})
        self.crosses("y")

    def wrote(self) -> list[tuple[str, float]]:
        return speeds(self.written)

    def listed(self) -> list[Payload]:
        """The trains the row lists now, less the stamp."""
        return list(self.bus.last_values[OVERDUE]["trains"])


def overdue_row(into: str = "x", allowance: float = ALLOWANCE) -> list[Payload]:
    return [
        {
            "train": "single",
            "into": into,
            "reason": f"no arrival for {allowance:g} s",
        }
    ]


def overdue(into: str = "x") -> Rig:
    """`single` granted into `x` at 0 and stopped at the allowance."""
    rig = Rig()
    rig.crosses()
    rig.to(ALLOWANCE)
    assert rig.listed() == overdue_row(into)
    return rig


def nothing_nonzero_after_the_stop(rig: Rig, stop: int) -> None:
    """No speed but `0.0` written after the `stop`th write, which is the stop,
    and the train still listed."""
    assert rig.wrote()[stop] == ("3", 0.0)
    assert all(speed == 0.0 for _addr, speed in rig.wrote()[stop:])
    assert rig.listed() == overdue_row()


# -- the allowance -----------------------------------------------------------


def test_at_the_allowance_the_train_is_stopped_and_listed() -> None:
    rig = Rig()
    said = heard(rig.bus, "tc49/layout/state/#")
    rig.crosses()
    rig.to(ALLOWANCE - 0.01)
    assert rig.wrote() == [("3", GRANTED)]
    assert rig.listed() == []
    assert rig.rows == []
    said.clear()
    rig.to(ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == overdue_row()
    assert len(rig.rows) == 1
    topics = [topic for topic, _payload in said]
    assert topics.index(OVERDUE) < topics.index(f"{WANTED_TRACTION}/3")
    rig.to(2 * ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert len(rig.rows) == 1


def test_the_allowance_is_the_one_the_app_was_given() -> None:
    rig = Rig(allowance=10.0)
    rig.crosses()
    rig.to(9.99)
    assert rig.listed() == []
    rig.to(10.0)
    assert rig.listed() == overdue_row(allowance=10.0)


def test_an_allowance_a_person_sets_holds_from_the_next_check() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(30.0)
    rig.bus.publish(SETTINGS_WANTED, {"arrival_allowance": 20.0})
    rig.bus.drain()
    assert rig.listed() == []
    rig.to(31.0)
    assert rig.listed() == overdue_row(allowance=20.0)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]


def test_a_longer_allowance_a_person_sets_names_itself_at_the_stop() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(30.0)
    rig.bus.publish(SETTINGS_WANTED, {"arrival_allowance": 90.0})
    rig.bus.drain()
    rig.to(89.99)
    assert rig.listed() == []
    rig.to(90.0)
    assert rig.listed() == overdue_row(allowance=90.0)


# -- the arrival -------------------------------------------------------------


def test_the_far_sensor_before_the_allowance_lists_nothing() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(30.0)
    rig.read(FAR)
    rig.to(3 * ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == []
    assert rig.rows == []


def test_the_far_sensor_settling_at_the_deadline_is_the_arrival() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(ALLOWANCE - SETTLING)
    rig.read(FAR)
    rig.to(ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == []
    assert rig.rows == []


def test_the_caution_drop_does_not_restart_the_clock() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    rig.read(ENTRY)
    rig.to(11.0)
    assert rig.wrote() == [("3", GRANTED), ("3", CAUTION)]
    rig.to(ALLOWANCE - 0.01)
    assert rig.listed() == []
    rig.to(ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED), ("3", CAUTION), ("3", 0.0)]
    assert rig.listed() == overdue_row()


# -- the power ---------------------------------------------------------------


def presses(rig: Rig, word: str) -> None:
    rig.bus.publish(POWER_WANTED, {"power": word})
    rig.bus.drain()


def test_after_a_cut_and_on_the_allowance_runs_from_the_on() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    presses(rig, "off")
    rig.to(20.0)
    presses(rig, "on")
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0), ("3", GRANTED)]
    rig.to(20.0 + ALLOWANCE - 0.01)
    assert rig.listed() == []
    rig.to(20.0 + ALLOWANCE)
    assert rig.listed() == overdue_row()
    assert rig.wrote()[-1] == ("3", 0.0)


def test_off_for_longer_than_the_allowance_lists_nothing() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    presses(rig, "off")
    rig.to(10.0 + 3 * ALLOWANCE)
    assert rig.listed() == []
    assert rig.rows == []


def test_a_supply_trip_stops_the_clock_and_the_supply_back_starts_it() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    rig.bus.publish(DEVICE_TRACK, {"power": "off"})
    rig.bus.drain()
    rig.to(200.0)
    assert rig.listed() == []
    energised(rig.bus)
    assert rig.bus.last_values[POWER]["power"] == "on"
    rig.to(200.0 + ALLOWANCE - 0.01)
    assert rig.listed() == []
    assert rig.wrote() == [("3", GRANTED)]
    rig.to(200.0 + ALLOWANCE)
    assert rig.listed() == overdue_row()
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]


# -- a wrong point report ----------------------------------------------------


def test_a_train_held_for_a_wrong_point_report_is_listed_at_the_allowance() -> None:
    rig = Rig()
    rig.crosses(reported=True)
    rig.to(10.0)
    lies(rig.bus, "12", "thrown")
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    rig.to(ALLOWANCE - 0.01)
    assert rig.listed() == []
    rig.to(ALLOWANCE)
    assert rig.listed() == overdue_row()
    lies(rig.bus, "12", "closed")
    rig.to(ALLOWANCE + 10.0)
    assert all(speed == 0.0 for _addr, speed in rig.wrote()[1:])
    assert rig.listed() == overdue_row()


# -- both sensors unknown ----------------------------------------------------


def test_a_train_standing_for_both_sensors_unknown_is_not_listed() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    rig.read(ENTRY, "unknown")
    rig.read(FAR, "unknown")
    rig.to(200.0)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == []
    rig.read(FAR, "clear")
    rig.to(201.0)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0), ("3", GRANTED)]
    rig.to(201.0 + ALLOWANCE - 0.01)
    assert rig.listed() == []
    rig.to(201.0 + ALLOWANCE)
    assert rig.listed() == overdue_row()
    assert rig.wrote()[-1] == ("3", 0.0)


def test_a_move_acted_on_with_both_sensors_unknown_is_not_timed() -> None:
    rig = Rig()
    rig.read(ENTRY, "unknown")
    rig.read(FAR, "unknown")
    rig.to(1.0)
    rig.crosses()
    rig.to(200.0)
    assert rig.wrote() == []
    assert rig.listed() == []


# -- who drives --------------------------------------------------------------


def test_a_take_mid_move_writes_nothing_and_lists_nothing() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    takes(rig.bus, "single")
    rig.to(3 * ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED)]
    assert rig.listed() == []


def test_a_release_leaving_the_train_running_starts_the_allowance() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    takes(rig.bus, "single")
    rig.to(20.0)
    gives(rig.bus, "single")
    rig.to(20.0 + ALLOWANCE - 0.01)
    assert rig.wrote() == [("3", GRANTED)]
    assert rig.listed() == []
    rig.to(20.0 + ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == overdue_row()


def test_a_release_of_a_standing_train_starts_the_allowance_at_its_speed() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    takes(rig.bus, "single")
    turns(rig.bus, "single", 0.0)
    rig.to(20.0)
    gives(rig.bus, "single")
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0), ("3", GRANTED)]
    rig.to(20.0 + ALLOWANCE - 0.01)
    assert rig.listed() == []
    rig.to(20.0 + ALLOWANCE)
    assert rig.listed() == overdue_row()


def test_a_train_a_throttle_holds_is_never_listed() -> None:
    rig = Rig()
    takes(rig.bus, "single")
    rig.crosses()
    turns(rig.bus, "single", 0.4)
    rig.to(3 * ALLOWANCE)
    assert rig.wrote() == [("3", 0.4)]
    assert rig.listed() == []
    assert rig.rows == []


def test_a_switch_to_manual_mid_move_still_stops_at_the_allowance() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    switches(rig.bus, MANUAL)
    rig.to(ALLOWANCE)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == overdue_row()


def test_a_train_with_no_addressed_car_is_never_listed() -> None:
    rig = Rig(train="freight_1")
    rig.crosses()
    rig.to(3 * ALLOWANCE)
    assert rig.listed() == []
    assert rig.rows == []


def test_a_move_in_manual_no_throttle_holds_is_never_listed() -> None:
    rig = Rig(driving=MANUAL)
    rig.crosses()
    rig.to(3 * ALLOWANCE)
    assert rig.wrote() == []
    assert rig.listed() == []


# -- a further move ----------------------------------------------------------


def test_a_further_move_gets_a_full_allowance_from_its_own_speed() -> None:
    rig = Rig()
    rig.crosses()
    rig.to(10.0)
    rig.onward()
    rig.to(10.0 + ALLOWANCE - 0.01)
    assert rig.wrote() == [("3", GRANTED), ("3", GRANTED)]
    assert rig.listed() == []
    rig.to(10.0 + ALLOWANCE)
    assert rig.listed() == overdue_row("y")


# -- after the stop ----------------------------------------------------------


def test_on_after_a_cut_gives_a_listed_train_no_speed() -> None:
    rig = overdue()
    presses(rig, "off")
    presses(rig, "on")
    rig.to(3 * ALLOWANCE)
    nothing_nonzero_after_the_stop(rig, 1)


def test_manual_and_back_to_automatic_gives_a_listed_train_no_speed() -> None:
    rig = overdue()
    switches(rig.bus, MANUAL)
    switches(rig.bus, AUTOMATIC)
    rig.to(3 * ALLOWANCE)
    nothing_nonzero_after_the_stop(rig, 1)


def test_a_sensor_back_after_both_unknown_gives_a_listed_train_no_speed() -> None:
    rig = overdue()
    rig.read(ENTRY, "unknown")
    rig.read(FAR, "unknown")
    rig.to(ALLOWANCE + 10.0)
    rig.read(FAR, "clear")
    rig.to(3 * ALLOWANCE)
    nothing_nonzero_after_the_stop(rig, 1)


def test_a_further_move_gives_a_listed_train_no_speed() -> None:
    rig = overdue()
    rig.onward()
    rig.to(3 * ALLOWANCE)
    nothing_nonzero_after_the_stop(rig, 1)


def test_new_aspects_give_a_listed_train_no_speed() -> None:
    rig = overdue()
    rig.bus.publish(ASPECTS, {"aspects": {FAR: "clear"}})
    rig.bus.drain()
    rig.read(ENTRY)
    rig.to(3 * ALLOWANCE)
    nothing_nonzero_after_the_stop(rig, 1)


# -- leaving the row ---------------------------------------------------------


def test_the_far_sensor_takes_a_listed_train_off() -> None:
    rig = overdue()
    rig.read(FAR)
    rig.to(ALLOWANCE + 1.0)
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0), ("3", 0.0)]
    assert rig.listed() == []
    rig.read(FAR, "clear")
    rig.to(ALLOWANCE + 2.0)
    rig.read(FAR)
    rig.to(ALLOWANCE + 3.0)
    assert len(rig.wrote()) == 3


def test_the_entry_sensor_with_the_far_one_unknown_takes_it_off() -> None:
    rig = overdue()
    rig.read(FAR, "unknown")
    rig.read(ENTRY)
    rig.to(ALLOWANCE + 1.0)
    assert rig.listed() == overdue_row()
    rig.read(ENTRY, "clear")
    rig.to(ALLOWANCE + 2.0)
    assert rig.listed() == []
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0), ("3", 0.0)]


def test_the_far_sensor_going_unknown_with_the_tail_in_takes_it_off() -> None:
    rig = overdue()
    rig.read(ENTRY)
    rig.to(ALLOWANCE + 1.0)
    rig.read(ENTRY, "clear")
    rig.to(ALLOWANCE + 2.0)
    assert rig.listed() == overdue_row()
    rig.read(FAR, "unknown")
    rig.to(ALLOWANCE + 3.0)
    assert rig.listed() == []
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0), ("3", 0.0)]


def test_a_take_takes_it_off_and_the_lever_drives_on() -> None:
    rig = overdue()
    takes(rig.bus, "single")
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == []
    turns(rig.bus, "single", 0.4)
    assert rig.wrote()[-1] == ("3", 0.4)
    rig.read(FAR)
    rig.to(ALLOWANCE + 1.0)
    assert rig.wrote()[-1] == ("3", 0.0)
    assert rig.listed() == []


def test_a_placement_takes_it_off_with_no_write() -> None:
    rig = overdue()
    stand(rig.bus, "single", "w")
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0)]
    assert rig.listed() == []
    assert len(rig.rows) == 2


def test_a_removal_writes_its_stop_and_takes_it_off() -> None:
    rig = overdue()
    removed(rig.bus, "single")
    assert rig.wrote() == [("3", GRANTED), ("3", 0.0), ("3", 0.0)]
    assert rig.listed() == []
    assert len(rig.rows) == 2


# -- the row -----------------------------------------------------------------


def test_a_settle_with_nothing_changed_publishes_no_row() -> None:
    rig = overdue()
    assert len(rig.rows) == 1
    rig.to(3 * ALLOWANCE)
    assert len(rig.rows) == 1


def test_two_trains_listed_in_one_call_are_one_row_sorted_by_train() -> None:
    rig = Rig(train="topped")
    stand(rig.bus, "single", "y")
    faces(rig.bus, topped="w.A-to-B", single="y.A-to-B")
    rig.crosses()
    rig.train = "single"
    rig.crosses("z")
    rig.to(ALLOWANCE)
    assert len(rig.rows) == 1
    assert [entry["train"] for entry in rig.listed()] == ["single", "topped"]
    assert [entry["into"] for entry in rig.listed()] == ["z", "x"]
