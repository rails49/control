"""A sensor not reporting reads unknown, and a train it drives does not arrive
on one (#1151).

The bench railroad's `straight` runs `up_w.B` to `up_e.A`, so a train crossing
into `up_e` comes in at `up_e.A`, the entry sensor, and is fully in at `up_e.B`,
the far one.
"""

from tc49.layout import LayoutInterface
from tc49.layout.interface import SENSOR_SILENCE_S, SETTLING_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC, MANUAL
from tests.layout.railroad import (
    POWER,
    POWER_WANTED,
    SETTINGS_WANTED,
    UNKNOWN_SENSORS,
    align,
    commanded,
    drains,
    elapse,
    energised,
    faces,
    gives,
    heard,
    move,
    moves,
    occupancy,
    reads,
    report,
    sensors,
    settle,
    speeds,
    stand,
    switches,
    takes,
    turns,
    wired,
)

BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"

ENTRY = "up_e.A"
FAR = "up_e.B"
GRANTED = 0.5


def listed(bus: InProcessBus) -> dict[str, tuple[str, bool]]:
    """What the row says now: each sensor's reason and whether it reported."""
    row = bus.last_values[UNKNOWN_SENSORS]["sensors"]
    return {entry["sensor"]: (entry["reason"], entry["reported"]) for entry in row}


def row_from_here_on(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every value of the row from here on, the retained one handed over."""
    rows = heard(bus, UNKNOWN_SENSORS)
    bus.drain()
    rows.clear()
    return rows


def went_silent(
    bus: InProcessBus, app: LayoutInterface, clock: Clock, end: str
) -> None:
    """`end` going unheard for the silence while every other sensor reports
    `clear`, as they all have."""
    elapse(clock, SENSOR_SILENCE_S / 2)
    report(bus, but=(end,))
    elapse(clock, SENSOR_SILENCE_S / 2)
    report(bus, but=(end,))
    app.settle()
    bus.drain()


def crossing(
    driving: str = AUTOMATIC, train: str = "single"
) -> tuple[InProcessBus, LayoutInterface, Clock, list[tuple[str, Payload]]]:
    """A live railroad with `train` granted `up_w` to `up_e`, and every
    traction write from the grant on."""
    bus, app, clock = wired(driving=driving)
    energised(bus)
    stand(bus, train, "up_w")
    faces(bus, **{train: "up_w.A-to-B"})
    align(bus, "crossover", "straight")
    written = commanded(bus)
    move(bus, train, "crossover", "straight", "up_e", speed=GRANTED)
    return bus, app, clock, written


def goes_unknown(
    bus: InProcessBus, app: LayoutInterface, clock: Clock, end: str
) -> None:
    """A report of `unknown` that stands for the settling time."""
    reads(bus, end, "unknown", "no model")
    settle(bus, app, clock)


def comes_back(
    bus: InProcessBus, app: LayoutInterface, clock: Clock, end: str, level: str
) -> None:
    """A report of a level that stands for the settling time."""
    reads(bus, end, level)
    settle(bus, app, clock)


# -- every sensor starts unknown ----------------------------------------------


def test_a_new_layout_lists_every_sensor_and_says_nothing_of_any_block() -> None:
    bus, app, clock = wired(reporting=False)
    seen = occupancy(bus)
    assert listed(bus) == {end: ("no report since start", False) for end in sensors()}
    row = bus.last_values[UNKNOWN_SENSORS]["sensors"]
    assert [entry["sensor"] for entry in row] == sensors()
    settle(bus, app, clock)
    assert seen == []


def test_a_sensor_not_on_the_drawing_is_never_listed() -> None:
    bus, app, clock = wired()
    reads(bus, "elsewhere.A", "unknown", "no model")
    settle(bus, app, clock)
    assert "elsewhere.A" not in listed(bus)


def test_a_sensor_not_on_the_drawing_folds_as_it_did() -> None:
    bus, app, clock = wired()
    seen = occupancy(bus)
    reads(bus, "elsewhere.A", "clear")
    settle(bus, app, clock)
    assert seen == [(BLOCK_VACATED, {"block": "elsewhere"})]


# -- one timer per sensor -----------------------------------------------------


def test_a_sensor_silent_for_the_limit_is_listed_having_reported() -> None:
    bus, app, clock = wired()
    went_silent(bus, app, clock, ENTRY)
    assert listed(bus) == {ENTRY: ("no report for 3 s", True)}


def test_silence_just_under_the_limit_lists_nothing() -> None:
    bus, app, clock = wired()
    elapse(clock, SENSOR_SILENCE_S - 0.01)
    app.settle()
    bus.drain()
    assert listed(bus) == {}


def test_a_report_of_any_kind_restarts_the_timer() -> None:
    bus, app, clock = wired()
    elapse(clock, SENSOR_SILENCE_S - 0.01)
    report(bus)
    elapse(clock, SENSOR_SILENCE_S - 0.01)
    app.settle()
    bus.drain()
    assert listed(bus) == {}


def test_the_limit_is_the_one_the_app_was_given() -> None:
    bus, app, clock = wired(sensor_silence_s=10.0)
    elapse(clock, 9.9)
    report(bus, but=(ENTRY,))
    elapse(clock, 0.1)
    app.settle()
    bus.drain()
    assert listed(bus) == {ENTRY: ("no report for 10 s", True)}


def test_a_limit_a_person_sets_holds_from_the_next_check() -> None:
    bus, app, clock = wired()
    bus.publish(SETTINGS_WANTED, {"sensor_silence": 10.0})
    bus.drain()
    elapse(clock, SENSOR_SILENCE_S)
    app.settle()
    bus.drain()
    assert listed(bus) == {}
    elapse(clock, 10.0 - SENSOR_SILENCE_S)
    app.settle()
    bus.drain()
    assert listed(bus)[ENTRY] == ("no report for 10 s", True)


# -- a reported unknown -------------------------------------------------------


def test_a_reported_unknown_shorter_than_the_settling_time_lists_nothing() -> None:
    bus, app, clock = wired()
    reads(bus, ENTRY, "unknown", "no model")
    settle(bus, app, clock, SETTLING_S / 2)
    assert listed(bus) == {}


def test_a_reported_unknown_that_stands_is_listed_with_its_reason() -> None:
    bus, app, clock = wired()
    goes_unknown(bus, app, clock, ENTRY)
    assert listed(bus) == {ENTRY: ("no model", True)}


def test_a_reported_unknown_with_no_reason_says_so() -> None:
    bus, app, clock = wired()
    reads(bus, ENTRY, "unknown")
    settle(bus, app, clock)
    assert listed(bus) == {ENTRY: ("no reason given", True)}


def test_a_level_within_the_settling_time_cancels_a_reported_unknown() -> None:
    bus, app, clock = wired()
    reads(bus, ENTRY, "unknown", "no model")
    settle(bus, app, clock, SETTLING_S / 2)
    reads(bus, ENTRY, "clear")
    settle(bus, app, clock)
    assert listed(bus) == {}


def test_a_reported_unknown_does_not_cancel_a_level_that_is_settling() -> None:
    bus, app, clock = wired()
    seen = occupancy(bus)
    reads(bus, ENTRY, "occupied")
    settle(bus, app, clock, SETTLING_S / 2)
    reads(bus, ENTRY, "unknown", "no model")
    settle(bus, app, clock, SETTLING_S / 2)
    assert [topic for topic, _payload in seen] == [BLOCK_OCCUPIED]
    assert listed(bus) == {}


def test_a_listed_sensor_says_the_reason_it_last_gave() -> None:
    bus, app, clock = wired()
    went_silent(bus, app, clock, ENTRY)
    goes_unknown(bus, app, clock, ENTRY)
    assert listed(bus) == {ENTRY: ("no model", True)}


# -- coming back --------------------------------------------------------------


def test_a_never_heard_sensor_coming_back_is_taken_off_having_reported() -> None:
    bus, app, clock = wired(reporting=False)
    reads(bus, ENTRY, "clear")
    settle(bus, app, clock)
    assert ENTRY not in listed(bus)
    elapse(clock, SENSOR_SILENCE_S)
    app.settle()
    bus.drain()
    assert listed(bus)[ENTRY] == ("no report for 3 s", True)
    assert listed(bus)[FAR] == ("no report since start", False)


def test_a_level_equal_to_the_one_held_takes_a_sensor_off_once_it_stands() -> None:
    bus, app, clock = wired()
    went_silent(bus, app, clock, ENTRY)
    reads(bus, ENTRY, "clear")
    settle(bus, app, clock, SETTLING_S / 2)
    assert ENTRY in listed(bus)
    settle(bus, app, clock, SETTLING_S / 2)
    assert listed(bus) == {}


def test_coming_off_the_list_publishes_the_row_once() -> None:
    bus, app, clock = wired()
    went_silent(bus, app, clock, ENTRY)
    rows = row_from_here_on(bus)
    reads(bus, ENTRY, "clear")
    reads(bus, ENTRY, "clear")
    settle(bus, app, clock)
    reads(bus, ENTRY, "clear")
    settle(bus, app, clock)
    assert [payload["sensors"] for _topic, payload in rows] == [[]]


def test_a_turn_with_nothing_changed_publishes_no_row() -> None:
    bus, app, clock = wired()
    rows = row_from_here_on(bus)
    report(bus)
    settle(bus, app, clock)
    assert rows == []


def test_every_sensor_coming_back_in_one_turn_is_one_row() -> None:
    bus, app, clock = wired(reporting=False)
    rows = row_from_here_on(bus)
    report(bus)
    settle(bus, app, clock)
    assert [payload["sensors"] for _topic, payload in rows] == [[]]


# -- the level held stands, and unknown creates no events ----------------------


def test_one_sensor_clear_and_the_other_never_heard_publishes_no_vacate() -> None:
    bus, app, clock = wired(reporting=False)
    seen = occupancy(bus)
    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)
    assert seen == []
    reads(bus, "up_e.B", "clear")
    settle(bus, app, clock)
    assert seen == [(BLOCK_VACATED, {"block": "up_e"})]


def test_a_vacate_held_back_waits_for_the_silent_sensor_to_say_clear() -> None:
    bus, app, clock = wired()
    went_silent(bus, app, clock, "up_e.B")
    seen = occupancy(bus)
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)
    assert [topic for topic, _payload in seen] == [BLOCK_OCCUPIED]
    reads(bus, "up_e.B", "clear")
    settle(bus, app, clock)
    assert [topic for topic, _payload in seen] == [BLOCK_OCCUPIED, BLOCK_VACATED]


def test_going_unknown_publishes_no_event() -> None:
    bus, app, clock = wired()
    seen = occupancy(bus)
    goes_unknown(bus, app, clock, "up_e.A")
    went_silent(bus, app, clock, "up_w.A")
    assert seen == []


def test_occupied_from_a_sensor_publishes_with_the_other_unknown() -> None:
    bus, app, clock = wired(reporting=False)
    seen = occupancy(bus)
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    assert [topic for topic, _payload in seen] == [BLOCK_OCCUPIED]


def test_a_level_held_occupied_stands_through_silence() -> None:
    """The train under the silent sensor is still there as far as anyone can
    tell, so the other sensor reading clear vacates nothing."""
    bus, app, clock = wired()
    reads(bus, "up_e.B", "occupied")
    settle(bus, app, clock)
    went_silent(bus, app, clock, "up_e.B")
    seen = occupancy(bus)
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)
    assert seen == []


def test_the_vacate_from_a_completed_move_does_not_wait_for_a_silent_sensor() -> None:
    bus, app, clock, _written = crossing()
    reads(bus, "up_w.A", "occupied")
    settle(bus, app, clock)
    goes_unknown(bus, app, clock, "up_w.B")
    seen = occupancy(bus)
    comes_back(bus, app, clock, ENTRY, "occupied")
    comes_back(bus, app, clock, FAR, "occupied")
    assert (BLOCK_VACATED, {"block": "up_w"}) in seen


# -- the train stops ----------------------------------------------------------


def test_the_entry_sensor_going_unknown_stops_the_train() -> None:
    bus, app, clock, written = crossing()
    assert speeds(written) == [("3", GRANTED)]
    goes_unknown(bus, app, clock, ENTRY)
    assert speeds(written) == [("3", GRANTED), ("3", 0.0)]


def test_the_entry_sensor_going_silent_stops_the_train() -> None:
    bus, app, clock, written = crossing()
    went_silent(bus, app, clock, ENTRY)
    assert speeds(written) == [("3", GRANTED), ("3", 0.0)]


def test_a_reason_changing_while_listed_writes_nothing_more() -> None:
    bus, app, clock, written = crossing()
    went_silent(bus, app, clock, ENTRY)
    goes_unknown(bus, app, clock, ENTRY)
    assert speeds(written) == [("3", GRANTED), ("3", 0.0)]


def test_a_move_acted_on_with_the_entry_sensor_unknown_writes_no_speed() -> None:
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    goes_unknown(bus, app, clock, ENTRY)
    align(bus, "crossover", "straight")
    written = commanded(bus)
    move(bus, "single", "crossover", "straight", "up_e", speed=GRANTED)
    assert written == []
    assert app.position["single"] == "up_e"


def test_only_the_entry_sensor_counts() -> None:
    """With the far sensor unknown the arrival still reads, and the train stops
    there as usual."""
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, FAR)
    assert speeds(written) == [("3", GRANTED)]
    comes_back(bus, app, clock, ENTRY, "occupied")
    assert speeds(written) == [("3", GRANTED), ("3", 0.0)]


def test_a_cut_and_on_gives_no_speed_while_the_entry_sensor_is_unknown() -> None:
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    bus.publish(POWER_WANTED, {"power": "off"})
    bus.drain()
    written.clear()
    bus.publish(POWER_WANTED, {"power": "on"})
    bus.drain()
    assert all(speed == 0.0 for _addr, speed in speeds(written))


def test_a_switch_to_automatic_gives_no_speed_while_the_entry_sensor_is_unknown() -> (
    None
):
    bus, app, clock, written = crossing(driving=MANUAL)
    goes_unknown(bus, app, clock, ENTRY)
    switches(bus, AUTOMATIC)
    assert written == []


def test_a_release_in_automatic_stops_a_running_train_over_the_unknown() -> None:
    bus, app, clock, written = crossing()
    takes(bus, "single")
    turns(bus, "single", 0.2)
    goes_unknown(bus, app, clock, ENTRY)
    written.clear()
    gives(bus, "single")
    assert speeds(written) == [("3", 0.0)]


def test_a_release_in_automatic_gives_a_standing_train_no_speed() -> None:
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    takes(bus, "single")
    written.clear()
    gives(bus, "single")
    assert written == []


# -- it carries on ------------------------------------------------------------


def test_the_entry_sensor_returning_clear_gives_the_granted_speed() -> None:
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    written.clear()
    comes_back(bus, app, clock, ENTRY, "clear")
    assert speeds(written) == [("3", GRANTED)]


def test_a_repeat_after_the_return_writes_nothing_more() -> None:
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    comes_back(bus, app, clock, ENTRY, "clear")
    written.clear()
    comes_back(bus, app, clock, ENTRY, "clear")
    assert written == []


def test_a_move_acted_on_while_unknown_is_given_its_speed_on_the_return() -> None:
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    goes_unknown(bus, app, clock, ENTRY)
    align(bus, "crossover", "straight")
    written = commanded(bus)
    move(bus, "single", "crossover", "straight", "up_e", speed=GRANTED)
    comes_back(bus, app, clock, ENTRY, "clear")
    assert speeds(written) == [("3", GRANTED)]


def test_the_entry_sensor_returning_occupied_is_the_arrival() -> None:
    """The arrival's own `0.0` goes out, as at every arrival, and no speed the
    train would run at: its grant implies nothing more."""
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    written.clear()
    comes_back(bus, app, clock, ENTRY, "occupied")
    assert speeds(written) == [("3", 0.0)]
    written.clear()
    comes_back(bus, app, clock, ENTRY, "clear")
    assert written == []


def test_the_return_carries_on_through_a_drain() -> None:
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    drains(bus)
    moves(bus, True)
    written.clear()
    comes_back(bus, app, clock, ENTRY, "clear")
    assert speeds(written) == [("3", GRANTED)]


def test_under_off_the_return_writes_nothing_and_on_resumes() -> None:
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    bus.publish(POWER_WANTED, {"power": "off"})
    bus.drain()
    written.clear()
    comes_back(bus, app, clock, ENTRY, "clear")
    assert written == []
    bus.publish(POWER_WANTED, {"power": "on"})
    bus.drain()
    assert speeds(written) == [("3", GRANTED)]


def test_in_manual_a_returning_sensor_writes_nothing() -> None:
    bus, app, clock, written = crossing(driving=MANUAL)
    goes_unknown(bus, app, clock, ENTRY)
    comes_back(bus, app, clock, ENTRY, "clear")
    assert written == []


def test_a_train_stopped_then_switched_to_manual_stays_until_automatic() -> None:
    bus, app, clock, written = crossing()
    goes_unknown(bus, app, clock, ENTRY)
    switches(bus, MANUAL)
    written.clear()
    comes_back(bus, app, clock, ENTRY, "clear")
    assert written == []
    switches(bus, AUTOMATIC)
    assert speeds(written) == [("3", GRANTED)]


# -- a train a throttle holds --------------------------------------------------


def test_a_train_a_throttle_holds_keeps_its_speed_through_all_of_it() -> None:
    bus, app, clock, written = crossing()
    takes(bus, "single")
    turns(bus, "single", 0.2)
    written.clear()
    went_silent(bus, app, clock, ENTRY)
    goes_unknown(bus, app, clock, ENTRY)
    goes_unknown(bus, app, clock, FAR)
    comes_back(bus, app, clock, ENTRY, "clear")
    assert written == []


# -- the power ----------------------------------------------------------------


def test_the_power_row_is_untouched_and_on_is_accepted_with_all_unknown() -> None:
    bus, app, clock = wired(reporting=False)
    powers = heard(bus, POWER)
    bus.drain()
    powers.clear()
    elapse(clock, SENSOR_SILENCE_S * 2)
    app.settle()
    bus.drain()
    assert powers == []
    bus.publish(POWER_WANTED, {"power": "on"})
    energised(bus)
    assert [payload["power"] for _topic, payload in powers] == ["on"]
    assert len(listed(bus)) == len(sensors())
