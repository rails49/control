"""The scheduler records a person's drags as a timetable (#1345, #1352).

Gestures, clock rows, power rows and the dispatcher's announcements are
published at a `Scheduler` on the in-process bus, with a store client the
test supplies. The test reads `request_submitted`, the state row and the
document the store was given.

The railroad is crossover-yard, with `freight_1` in `yard_w` and `express_2`
in `up_e`.
"""

from typing import Any

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.fast_clock import DAY_S
from tc49.lib.timetable import Timetable, TrainStart
from tc49.scheduler import Scheduler
from tests.harness import Recording, subscribed_before_publishing
from tests.scheduler.test_scheduler import NONCE, collect, seeded, yard

TIMETABLE = "tc49/schedule/state/timetable"
CLOCK = "tc49/layout/state/clock"
CLOCK_WANTED = "tc49/layout/clock_wanted"
POWER = "tc49/layout/state/power"
ALLOCATION = "tc49/dispatch/state/allocation"
SUBMITTED = "tc49/dispatch/request_submitted"

NOTHING_LOADED = {"timetable": None}


class Store:
    """The store client a test hands the scheduler: the timetables it holds,
    by railroad and name."""

    def __init__(self, *held: Timetable) -> None:
        self.held = {(one.layout, one.name): one for one in held}

    def timetable(self, railroad: str, name: str) -> Timetable | None:
        return self.held.get((railroad, name))

    def put_timetable(self, timetable: Timetable) -> None:
        self.held[timetable.layout, timetable.name] = timetable

    def delete_timetable(self, railroad: str, name: str) -> None:
        self.held.pop((railroad, name), None)

    def document(self, name: str) -> dict[str, Any] | None:
        """The document held under `name` for crossover-yard, or None."""
        held = self.timetable("crossover-yard", name)
        return None if held is None else held.document()


def at(hh_mm: str, seconds: int = 0) -> int:
    """`"HH:MM"` and `seconds` past it, in seconds since midnight."""
    hours, minutes = hh_mm.split(":")
    return (int(hours) * 60 + int(minutes)) * 60 + seconds


def say(bus: InProcessBus, topic: str, payload: Payload) -> None:
    """One message as anything on the bus publishes it, delivered."""
    bus.publish(topic, payload)
    bus.drain()


def clock(bus: InProcessBus, hh_mm: str, seconds: int = 0) -> None:
    """The layout binding's clock row at that time of day."""
    say(bus, CLOCK, {"time": at(hh_mm, seconds), "speed_up": 1.0})


def power(bus: InProcessBus, reads: str) -> None:
    say(bus, POWER, {"power": reads})


STANDING = {"freight_1": "yard_w", "express_2": "up_e"}


def allocation(
    bus: InProcessBus,
    trains: dict[str, str] | None = None,
    requests: tuple[tuple[str, str], ...] = (),
) -> None:
    """The dispatcher's allocation row: where each train stands, and the
    requests it lists, each an id and its train."""
    say(
        bus,
        ALLOCATION,
        {
            "trains": STANDING if trains is None else trains,
            "crossing": {},
            "occupied": {},
            "locks": {},
            "requests": [
                {"id": request, "train": train, "depart": None, "dest": []}
                for request, train in requests
            ],
        },
    )


WANTED = "tc49/schedule/request_wanted"
REVERSAL = "tc49/schedule/reversal_wanted"
TIMETABLE_WANTED = "tc49/schedule/timetable_wanted"
RECORD_WANTED = "tc49/schedule/timetable_record_wanted"


def drag(bus: InProcessBus, train: str, *dest: str) -> None:
    """A person's drag of `train` to `dest`."""
    say(bus, WANTED, {"train": train, "dest": list(dest)})


def entries(bus: InProcessBus) -> list[dict[str, Any]]:
    """The timetable row's entries."""
    return row(bus)["entries"]


def row(bus: InProcessBus) -> dict[str, Any]:
    """The timetable row as the bus holds it, less its stamp."""
    said = dict(bus.last_values[TIMETABLE])
    del said["at"]
    return said


def recording(store: Store, hh_mm: str = "06:00", seconds: int = 30) -> InProcessBus:
    """A scheduler with both trains placed, power on and the clock at that
    time, so `untitled` has just been made."""
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=store)
    allocation(bus)
    clock(bus, hh_mm, seconds)
    power(bus, "on")
    return bus


def test_with_power_on_and_a_clock_row_untitled_is_made_and_written() -> None:
    store = Store()
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=store)
    allocation(bus)
    clock(bus, "06:00", 30)

    assert row(bus) == NOTHING_LOADED

    power(bus, "on")

    assert row(bus) == {
        "timetable": "untitled",
        "phase": "running",
        "record": True,
        "start": "06:00",
        "repeat": "1d00:00",
        "trains": {
            "express_2": {"at": "up_e", "facing": "B-to-A"},
            "freight_1": {"at": "yard_w", "facing": "A-to-B"},
        },
        "positioning": [],
        "entries": [],
    }
    assert store.document("untitled") == {
        "timetable": "untitled",
        "layout": "crossover-yard",
        "start": "06:00",
        "repeat": "1d00:00",
        "trains": {
            "express_2": {"at": "up_e", "facing": "B-to-A"},
            "freight_1": {"at": "yard_w", "facing": "A-to-B"},
        },
        "entries": [],
    }


def test_a_new_timetable_puts_the_clock_on_day_0_at_its_time_of_day() -> None:
    """To the second, so the face does not move when recording begins. So
    does one a person makes by name."""
    store = Store()
    bus = InProcessBus(Clock())
    seen = collect(bus, CLOCK_WANTED)
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=store)
    allocation(bus)
    say(bus, CLOCK, {"time": 2 * DAY_S + at("06:00", 30), "speed_up": 1.0})

    power(bus, "on")

    assert [payload for _, payload in seen] == [{"time": at("06:00", 30)}]
    assert row(bus)["start"] == "06:00"

    power(bus, "off")
    say(bus, CLOCK, {"time": DAY_S + at("07:15", 59), "speed_up": 1.0})
    say(bus, TIMETABLE_WANTED, {"timetable": "evening", "new": True})

    assert [payload for _, payload in seen] == [
        {"time": at("06:00", 30)},
        {"time": at("07:15", 59)},
    ]


def test_a_scheduler_given_no_store_publishes_no_timetable_row() -> None:
    bus = InProcessBus(Clock())
    seen = collect(bus, TIMETABLE)
    Scheduler(bus, yard(), seeded(), nonce=NONCE)
    allocation(bus)
    clock(bus, "06:00", 30)
    power(bus, "on")

    assert seen == []
    assert TIMETABLE not in bus.last_values


def test_a_train_off_the_layout_is_left_out_of_a_new_timetables_trains() -> None:
    """`express_2` has a facing and stands in no block the allocation
    names."""
    store = Store()
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=store)
    allocation(bus, {"freight_1": "yard_w"})
    clock(bus, "06:00")
    power(bus, "on")

    assert row(bus)["trains"] == {"freight_1": {"at": "yard_w", "facing": "A-to-B"}}


def test_untitled_waits_for_an_allocation_row() -> None:
    """Where the trains stand is read off it."""
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=Store())
    clock(bus, "06:00")
    power(bus, "on")

    assert row(bus) == NOTHING_LOADED

    allocation(bus)

    assert row(bus)["timetable"] == "untitled"
    assert row(bus)["start"] == "06:00"


def test_untitled_replaces_the_one_the_store_has() -> None:
    stored = Timetable("untitled", "crossover-yard", at("22:00"), DAY_S, {}, ())
    store = Store(stored)

    recording(store)

    held = store.document("untitled")
    assert held is not None
    assert held["start"] == "06:00"


def test_a_drag_is_recorded_at_the_clocks_minute_and_written() -> None:
    """The request is the one a drag gets with no store: the same id,
    departure end and `dest`. The entry keeps `to` as the gesture gave it:
    the bare block goes out as both of its ends and is recorded bare."""
    store = Store()
    bus = recording(store)
    seen = collect(bus, SUBMITTED)
    clock(bus, "06:02", 10)

    drag(bus, "freight_1", "dn_e", "up_e.A")

    plain = InProcessBus(Clock())
    without = collect(plain, SUBMITTED)
    Scheduler(plain, yard(), seeded(), nonce=NONCE)
    drag(plain, "freight_1", "dn_e", "up_e.A")
    assert [payload for _, payload in seen] == [payload for _, payload in without]
    assert [payload for _, payload in seen] == [
        {
            "id": f"freight_1-{NONCE}-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["dn_e.A", "dn_e.B", "up_e.A"],
        }
    ]
    assert entries(bus) == [
        {
            "at": "06:02",
            "train": "freight_1",
            "to": ["dn_e", "up_e.A"],
            "state": "out",
            "round": 0,
            "request": f"freight_1-{NONCE}-1",
        }
    ]
    held = store.document("untitled")
    assert held is not None
    assert held["entries"] == [
        {"at": "06:02", "train": "freight_1", "to": ["dn_e", "up_e.A"]}
    ]


def test_a_drag_after_midnight_is_recorded_on_day_1() -> None:
    """Started at 23:58, the clock reads 1d00:01 three minutes later, and the
    entry is at its start plus the time since its start (#1365)."""
    store = Store()
    bus = recording(store, "23:58", 0)
    clock(bus, "24:01", 20)

    drag(bus, "freight_1", "dn_e")

    assert [one["at"] for one in entries(bus)] == ["1d00:01"]
    assert [one["at"] for one in written_entries(store)] == ["1d00:01"]


def written_entries(store: Store) -> list[dict[str, Any]]:
    held = store.document("untitled")
    assert held is not None
    return held["entries"]


def test_a_drag_of_a_train_the_scheduler_cannot_compose_adds_no_entry() -> None:
    bus = recording(Store())
    seen = collect(bus, SUBMITTED)

    drag(bus, "ghost", "dn_e")

    assert seen == []
    assert entries(bus) == []


def test_a_turn_round_applied_is_recorded_as_ended() -> None:
    store = Store()
    bus = recording(store)
    clock(bus, "06:10")

    say(bus, REVERSAL, {"train": "express_2"})

    assert bus.last_values["tc49/schedule/state/facing"]["facing"]["express_2"] == (
        "up_e.A-to-B"
    )
    assert entries(bus) == [
        {
            "at": "06:10",
            "train": "express_2",
            "turn": True,
            "state": "ended",
            "round": 0,
        }
    ]
    held = store.document("untitled")
    assert held is not None
    assert held["entries"] == [{"at": "06:10", "train": "express_2", "turn": True}]


def test_a_turn_round_dropped_for_a_request_in_flight_is_not_recorded() -> None:
    bus = recording(Store())
    drag(bus, "freight_1", "dn_e")

    say(bus, REVERSAL, {"train": "freight_1"})

    assert [one["train"] for one in entries(bus) if one.get("turn")] == []
    assert len(entries(bus)) == 1


def test_a_recorded_entry_follows_its_request_to_the_end() -> None:
    """Completed, rejected and cancelled, and the cancelled entry is still
    in the document."""
    store = Store()
    bus = recording(store, "06:00", 0)
    for train, dest in (("freight_1", "dn_e"), ("express_2", "dn_w")):
        drag(bus, train, dest)
    say(bus, REVERSAL, {"train": "freight_1"})  # dropped: a request in flight
    first, second = (one["request"] for one in entries(bus))
    clock(bus, "06:07", 30)

    say(bus, "tc49/dispatch/request_completed", {"id": first})
    say(bus, "tc49/dispatch/request_cancelled", {"id": second, "reason": "asked"})

    assert [(one["state"], one.get("ended")) for one in entries(bus)] == [
        ("ended", at("06:07", 30)),
        ("cancelled", None),
    ]

    drag(bus, "freight_1", "up_e")
    third = entries(bus)[2]["request"]
    say(bus, "tc49/dispatch/request_rejected", {"id": third, "reason": "unreachable"})

    assert [one["state"] for one in entries(bus)] == ["ended", "cancelled", "rejected"]
    held = store.document("untitled")
    assert held is not None
    assert held["entries"] == [
        {"at": "06:00", "train": "freight_1", "to": ["dn_e"]},
        {"at": "06:00", "train": "express_2", "to": ["dn_w"]},
        {"at": "06:07", "train": "freight_1", "to": ["up_e"]},
    ]


def test_with_record_off_a_drag_is_a_request_with_no_entry() -> None:
    store = Store()
    bus = recording(store)
    seen = collect(bus, SUBMITTED)

    say(bus, RECORD_WANTED, {"record": False})
    drag(bus, "freight_1", "dn_e")

    assert row(bus)["record"] is False
    assert len(seen) == 1
    assert entries(bus) == []

    say(bus, RECORD_WANTED, {"record": True})
    drag(bus, "express_2", "dn_w")

    assert row(bus)["record"] is True
    assert len(seen) == 2
    assert [one["train"] for one in entries(bus)] == ["express_2"]
    held = store.document("untitled")
    assert held is not None
    assert held["entries"] == [{"at": "06:00", "train": "express_2", "to": ["dn_w"]}]


def test_a_record_gesture_that_cannot_be_read_is_dropped() -> None:
    bus = recording(Store())

    say(bus, RECORD_WANTED, {"record": "off"})

    assert row(bus)["record"] is True


def place(bus: InProcessBus, train: str, block: str) -> None:
    """A train placed in `block`, as the dispatcher announces it: the fact,
    then an allocation row with the train in that block beside the two
    trains where they stand."""
    say(bus, "tc49/dispatch/train_placed", {"train": train, "block": block})
    allocation(bus, {**STANDING, train: block})


def test_a_train_placed_while_recording_is_added_to_the_trains() -> None:
    """At its block and the facing the scheduler holds for it, which for a
    train placed from off the layout is `B-to-A`."""
    store = Store()
    bus = recording(store)

    place(bus, "shunter", "up_w")

    assert row(bus)["trains"] == {
        "express_2": {"at": "up_e", "facing": "B-to-A"},
        "freight_1": {"at": "yard_w", "facing": "A-to-B"},
        "shunter": {"at": "up_w", "facing": "B-to-A"},
    }
    held = store.document("untitled")
    assert held is not None
    assert held["trains"]["shunter"] == {"at": "up_w", "facing": "B-to-A"}


def test_a_train_placed_with_record_off_is_added_once_record_is_on() -> None:
    store = Store()
    bus = recording(store)
    say(bus, RECORD_WANTED, {"record": False})

    place(bus, "shunter", "up_w")

    assert "shunter" not in row(bus)["trains"]
    held = store.document("untitled")
    assert held is not None
    assert "shunter" not in held["trains"]

    say(bus, RECORD_WANTED, {"record": True})

    assert row(bus)["trains"]["shunter"] == {"at": "up_w", "facing": "B-to-A"}
    held = store.document("untitled")
    assert held is not None
    assert held["trains"]["shunter"] == {"at": "up_w", "facing": "B-to-A"}


def test_a_train_named_and_placed_again_elsewhere_keeps_its_line() -> None:
    """`freight_1` is taken off and placed in `up_w`."""
    store = Store()
    bus = recording(store)
    say(bus, "tc49/dispatch/train_removed", {"train": "freight_1"})
    allocation(bus, {"express_2": "up_e"})

    place(bus, "freight_1", "up_w")

    assert row(bus)["trains"]["freight_1"] == {"at": "yard_w", "facing": "A-to-B"}
    held = store.document("untitled")
    assert held is not None
    assert held["trains"]["freight_1"] == {"at": "yard_w", "facing": "A-to-B"}


def test_a_removal_leaves_the_trains_as_they_were() -> None:
    store = Store()
    bus = recording(store)
    before = row(bus)["trains"]

    say(bus, "tc49/dispatch/train_removed", {"train": "express_2"})
    allocation(bus, {"freight_1": "yard_w"})

    assert row(bus)["trains"] == before
    held = store.document("untitled")
    assert held is not None
    assert held["trains"] == before


def test_a_train_placed_where_a_named_train_starts_is_added() -> None:
    """`freight_1` starts in `yard_w`, is taken off, and `shunter` is placed
    there. `yard_w.A` is a buffer stop, so `shunter` faces `A-to-B`."""
    bus = recording(Store())
    say(bus, "tc49/dispatch/train_removed", {"train": "freight_1"})
    allocation(bus, {"express_2": "up_e"})

    say(bus, "tc49/dispatch/train_placed", {"train": "shunter", "block": "yard_w"})
    allocation(bus, {"express_2": "up_e", "shunter": "yard_w"})

    assert row(bus)["trains"] == {
        "express_2": {"at": "up_e", "facing": "B-to-A"},
        "freight_1": {"at": "yard_w", "facing": "A-to-B"},
        "shunter": {"at": "yard_w", "facing": "A-to-B"},
    }


def test_a_train_placed_while_a_timetable_is_loaded_is_not_added() -> None:
    """With Record switched on, as a `loaded` timetable adds no entry for a
    drag either."""
    trains = {
        "freight_1": TrainStart("yard_w", "A-to-B"),
        "express_2": TrainStart("up_e", "B-to-A"),
    }
    store = Store(
        Timetable("evening", "crossover-yard", at("06:00"), DAY_S, trains, ())
    )
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=store)
    allocation(bus)
    clock(bus, "05:40")
    power(bus, "off")
    say(bus, TIMETABLE_WANTED, {"timetable": "evening"})
    say(bus, RECORD_WANTED, {"record": True})
    assert (row(bus)["phase"], row(bus)["record"]) == ("loaded", True)

    place(bus, "shunter", "up_w")

    assert "shunter" not in row(bus)["trains"]
    held = store.document("evening")
    assert held is not None
    assert "shunter" not in held["trains"]


def test_a_train_placed_after_a_restart_waits_for_the_first_clock_row() -> None:
    store = Store()
    rows = retained(store)
    del rows[CLOCK]
    bus = restarted(store, rows)

    place(bus, "shunter", "up_w")

    assert "shunter" not in row(bus)["trains"]

    clock(bus, "06:09")

    assert row(bus)["trains"]["shunter"] == {"at": "up_w", "facing": "B-to-A"}


def test_a_new_timetable_by_name_is_made_with_power_off() -> None:
    """It takes the place of the one loaded, which stays in the store."""
    store = Store()
    bus = recording(store)
    drag(bus, "freight_1", "dn_e")
    power(bus, "off")
    clock(bus, "07:15", 59)

    say(bus, TIMETABLE_WANTED, {"timetable": "evening", "new": True})

    assert row(bus) == {
        "timetable": "evening",
        "phase": "running",
        "record": True,
        "start": "07:15",
        "repeat": "1d00:00",
        "trains": {
            "express_2": {"at": "up_e", "facing": "B-to-A"},
            "freight_1": {"at": "yard_w", "facing": "A-to-B"},
        },
        "positioning": [],
        "entries": [],
    }
    held = store.document("evening")
    assert held is not None
    assert (held["start"], held["entries"]) == ("07:15", [])
    before = store.document("untitled")
    assert before is not None
    assert len(before["entries"]) == 1


def test_a_new_timetable_replaces_one_of_that_name_loaded_or_stored() -> None:
    stored = Timetable("evening", "crossover-yard", at("22:00"), DAY_S, {}, ())
    store = Store(stored)
    bus = recording(store)
    power(bus, "off")

    say(bus, TIMETABLE_WANTED, {"timetable": "evening", "new": True})

    held = store.document("evening")
    assert held is not None
    assert held["start"] == "06:00"

    clock(bus, "06:30")
    say(bus, TIMETABLE_WANTED, {"timetable": "evening", "new": True})

    assert row(bus)["start"] == "06:30"
    held = store.document("evening")
    assert held is not None
    assert held["start"] == "06:30"


def test_a_new_timetable_asked_for_with_power_on_is_dropped() -> None:
    store = Store()
    bus = recording(store)

    say(bus, TIMETABLE_WANTED, {"timetable": "evening", "new": True})

    assert row(bus)["timetable"] == "untitled"
    assert store.document("evening") is None


def test_a_timetable_gesture_the_scheduler_cannot_act_on_is_dropped() -> None:
    """One without `new` for a name the store does not have; one that
    cannot be read; and a name no timetable document takes."""
    store = Store()
    bus = recording(store)
    power(bus, "off")

    for payload in (
        {"timetable": "evening"},
        {"timetable": "evening", "new": "yes"},
        {"new": True},
        {"timetable": "a/b", "new": True},
        {"timetable": ".hidden", "new": True},
    ):
        say(bus, TIMETABLE_WANTED, payload)

    assert row(bus)["timetable"] == "untitled"
    assert list(store.held) == [("crossover-yard", "untitled")]


def test_the_row_is_written_when_it_changes_and_not_each_second() -> None:
    bus = recording(Store())
    seen = collect(bus, TIMETABLE)
    bus.drain()
    seen.clear()

    for seconds in range(31, 40):
        clock(bus, "06:00", seconds)

    assert seen == []


def test_a_change_of_an_entrys_state_alone_does_not_write_the_document() -> None:
    store = Counting()
    bus = recording(store)
    drag(bus, "freight_1", "dn_e")
    assert store.puts == 2

    say(bus, "tc49/dispatch/request_completed", {"id": entries(bus)[0]["request"]})

    assert entries(bus)[0]["state"] == "ended"
    assert store.puts == 2


class Counting(Store):
    """A store that counts the documents it was given."""

    puts = 0

    def put_timetable(self, timetable: Timetable) -> None:
        self.puts += 1
        super().put_timetable(timetable)


def retained(store: Store) -> dict[str, Payload]:
    """What a broker holds after a recording with one drag by each train,
    `freight_1`'s completed, and the scheduler gone: its two rows, and the
    clock, power and allocation rows, the last listing no request."""
    bus = recording(store, "06:00", 0)
    drag(bus, "freight_1", "dn_e")
    clock(bus, "06:04")
    say(bus, "tc49/dispatch/request_completed", {"id": entries(bus)[0]["request"]})
    drag(bus, "express_2", "dn_w")
    return bus.last_values


def restarted(store: Store, rows: dict[str, Payload]) -> InProcessBus:
    """A scheduler built on a bus holding `rows`, as after a restart."""
    bus = InProcessBus(Clock())
    for topic, value in rows.items():
        bus.publish(topic, value)
    bus.drain()
    Scheduler(bus, yard(), nonce="again", store=store)
    bus.drain()
    return bus


def test_a_restart_comes_up_with_the_timetable_and_records_after_its_entries() -> None:
    store = Store()
    rows = retained(store)
    express = rows[TIMETABLE]["entries"][1]["request"]
    rows[ALLOCATION] = rows[ALLOCATION] | {
        "requests": [{"id": express, "train": "express_2"}]
    }

    bus = restarted(store, rows)

    assert [(one["at"], one["state"]) for one in entries(bus)] == [
        ("06:00", "ended"),
        ("06:04", "out"),
    ]
    assert (row(bus)["timetable"], row(bus)["record"]) == ("untitled", True)

    clock(bus, "06:09")
    drag(bus, "freight_1", "up_e")

    assert [(one["at"], one["train"], one["state"]) for one in entries(bus)] == [
        ("06:00", "freight_1", "ended"),
        ("06:04", "express_2", "out"),
        ("06:09", "freight_1", "out"),
    ]
    held = store.document("untitled")
    assert held is not None
    assert [one["at"] for one in held["entries"]] == ["06:00", "06:04", "06:09"]

    say(bus, "tc49/dispatch/request_completed", {"id": express})

    assert entries(bus)[1] == {
        "at": "06:04",
        "train": "express_2",
        "to": ["dn_w"],
        "state": "ended",
        "round": 0,
        "request": express,
        "ended": at("06:09"),
    }


def test_after_a_restart_an_entry_whose_request_is_not_listed_has_ended() -> None:
    """The request ended while the scheduler was down. A later allocation
    row ends nothing: a request is submitted before the dispatcher lists
    it."""
    store = Store()
    rows = retained(store)

    bus = restarted(store, rows)

    assert [(one["state"], one.get("ended")) for one in entries(bus)] == [
        ("ended", at("06:04")),
        ("ended", None),
    ]

    drag(bus, "freight_1", "up_e")
    allocation(bus)

    assert entries(bus)[2]["state"] == "out"


def test_a_restart_keeps_the_rows_entries_where_the_documents_differ() -> None:
    """And writes them: the scheduler is the one writer of a loaded
    timetable."""
    store = Store()
    rows = retained(store)
    edited = Timetable("untitled", "crossover-yard", at("06:00"), DAY_S, {}, ())
    store.put_timetable(edited)

    bus = restarted(store, rows)

    assert [one["at"] for one in entries(bus)] == ["06:00", "06:04"]
    held = store.document("untitled")
    assert held is not None
    assert [one["at"] for one in held["entries"]] == ["06:00", "06:04"]


def test_a_restart_with_no_document_in_the_store_loads_no_timetable() -> None:
    rows = retained(Store())
    rows[POWER] = {"power": "off"}

    bus = restarted(Store(), rows)

    assert row(bus) == NOTHING_LOADED


def test_a_restart_from_a_row_it_cannot_read_loads_no_timetable() -> None:
    store = Store()
    rows = retained(store)
    rows[POWER] = {"power": "off"}
    rows[TIMETABLE] = rows[TIMETABLE] | {"phase": "paused"}

    bus = restarted(store, rows)

    assert row(bus) == NOTHING_LOADED


def test_a_restart_with_a_document_the_store_cannot_read_loads_no_timetable() -> None:
    rows = retained(Store())
    rows[POWER] = {"power": "off"}

    bus = restarted(Unreadable(), rows)

    assert row(bus) == NOTHING_LOADED


class Unreadable(Store):
    """A store where a document it was not made with does not read."""

    def timetable(self, railroad: str, name: str) -> Timetable | None:
        if (railroad, name) not in self.held:
            raise ValueError(f"timetable {name!r}: 'start' is 360")
        return super().timetable(railroad, name)


def test_the_subscriptions_are_live_before_the_timetable_row_goes_out() -> None:
    bus = Recording()

    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=Store())

    subscribed_before_publishing(bus)
    assert f"subscribe {CLOCK}" in bus.calls
    assert f"subscribe {POWER}" in bus.calls
    assert f"publish {TIMETABLE}" in bus.calls


def test_a_scheduler_given_no_store_subscribes_neither_clock_nor_power() -> None:
    bus = Recording()

    Scheduler(bus, yard(), seeded(), nonce=NONCE)

    assert bus.calls[:2] == ["subscribe tc49/dispatch/#", "subscribe tc49/schedule/#"]
    assert not [call for call in bus.calls[2:] if call.startswith("subscribe")]
