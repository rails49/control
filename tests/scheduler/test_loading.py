"""The scheduler loads a timetable, sends its trains to their start blocks,
starts it and releases its entries (#1345, #1353).

Built as `tests/scheduler/test_recording.py` is: gestures, clock rows, power
rows and the dispatcher's announcements are published at a `Scheduler` on the
in-process bus, with a store client the test supplies. The test reads
`request_submitted`, `clock_wanted`, the state row and the document the store
holds.

The railroad is crossover-yard, with `freight_1` in `yard_w` facing `A-to-B`
and `express_2` in `up_e` facing `B-to-A`. The timetable `evening` starts at
06:00 with `freight_1` in `yard_w`, `express_2` in `dn_w` facing `A-to-B`
and `local_3`, which is off the layout, in `yard_e`.
"""

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.timetable import Entry, Timetable, TrainStart
from tc49.scheduler import Scheduler
from tests.scheduler.test_edits import change
from tests.scheduler.test_recording import (
    ALLOCATION,
    RECORD_WANTED,
    SUBMITTED,
    TIMETABLE,
    TIMETABLE_WANTED,
    Store,
    allocation,
    at,
    clock,
    drag,
    entries,
    power,
    restarted,
    row,
    say,
)
from tests.scheduler.test_scheduler import NONCE, collect, seeded, yard

CLOCK_WANTED = "tc49/layout/clock_wanted"
START_WANTED = "tc49/schedule/timetable_start_wanted"
REJECTED = "tc49/dispatch/request_rejected"
COMPLETED = "tc49/dispatch/request_completed"

TRAINS = {
    "freight_1": TrainStart("yard_w", "A-to-B"),
    "express_2": TrainStart("dn_w", "A-to-B"),
    "local_3": TrainStart("yard_e", "B-to-A"),
}

TO_START = f"express_2-{NONCE}-1"
"""The id of the request that sends `express_2` to its start block."""


def evening(*entries: Entry, trains: dict[str, TrainStart] | None = None) -> Timetable:
    """The timetable `evening` with those entries."""
    return Timetable(
        "evening",
        "crossover-yard",
        at("06:00"),
        TRAINS if trains is None else trains,
        entries,
    )


def standing(store: Store) -> InProcessBus:
    """A scheduler with both trains placed, power off and the clock standing
    at 05:40: nothing is loaded."""
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=store)
    allocation(bus)
    clock(bus, "05:40")
    power(bus, "off")
    return bus


def load(bus: InProcessBus, name: str = "evening") -> None:
    """A person's load of the timetable `name`."""
    say(bus, TIMETABLE_WANTED, {"timetable": name})


def payloads(seen: list[tuple[str, Payload]]) -> list[Payload]:
    return [payload for _, payload in seen]


def test_a_load_sends_each_train_standing_elsewhere_to_its_start_block() -> None:
    """One request, for `express_2`, to the one arrival end that leaves it
    facing as recorded: `dn_w.A` for `A-to-B`. `freight_1` is in its start
    block and `local_3` is off the layout."""
    store = Store(evening(Entry(at("06:02"), "freight_1", ("dn_e",))))
    bus = standing(store)
    seen = collect(bus, SUBMITTED)

    load(bus)

    assert payloads(seen) == [
        {
            "id": TO_START,
            "train": "express_2",
            "depart": "up_e.A",
            "dest": ["dn_w.A"],
        }
    ]
    assert row(bus) == {
        "timetable": "evening",
        "phase": "loaded",
        "record": False,
        "start": "06:00",
        "trains": {
            "freight_1": {"at": "yard_w", "facing": "A-to-B"},
            "express_2": {"at": "dn_w", "facing": "A-to-B"},
            "local_3": {"at": "yard_e", "facing": "B-to-A"},
        },
        "positioning": [TO_START],
        "entries": [
            {"at": "06:02", "train": "freight_1", "to": ["dn_e"], "state": "later"}
        ],
    }


def test_a_train_recorded_facing_b_to_a_is_sent_to_the_b_end() -> None:
    trains = {"express_2": TrainStart("dn_w", "B-to-A")}
    bus = standing(Store(evening(trains=trains)))
    seen = collect(bus, SUBMITTED)

    load(bus)

    assert [payload["dest"] for payload in payloads(seen)] == [["dn_w.B"]]


def test_a_train_in_its_start_block_gets_no_request_whatever_its_facing() -> None:
    """`freight_1` stands in `yard_w` facing `A-to-B`."""
    trains = {"freight_1": TrainStart("yard_w", "B-to-A")}
    bus = standing(Store(evening(trains=trains)))
    seen = collect(bus, SUBMITTED)

    load(bus)

    assert seen == []
    assert (row(bus)["phase"], row(bus)["positioning"]) == ("loaded", [])


def test_a_load_with_power_on_is_dropped() -> None:
    """`untitled` was made when power went on, and stays loaded."""
    bus = standing(Store(evening()))
    power(bus, "on")
    seen = collect(bus, SUBMITTED)

    load(bus)

    assert row(bus)["timetable"] == "untitled"
    assert seen == []


def test_a_load_of_a_name_the_store_does_not_have_leaves_what_was_loaded() -> None:
    bus = standing(Store(evening()))
    load(bus)

    load(bus, "morning")

    assert (row(bus)["timetable"], row(bus)["positioning"]) == ("evening", [TO_START])


def test_a_load_of_a_document_that_does_not_read_leaves_what_was_loaded() -> None:
    store = Unreadable(evening())
    bus = standing(store)
    load(bus)

    load(bus, "broken")

    assert row(bus)["timetable"] == "evening"


class Unreadable(Store):
    """A store whose document `broken` does not read."""

    def timetable(self, railroad: str, name: str) -> Timetable | None:
        if name == "broken":
            raise ValueError("timetable 'broken': 'start' is 360")
        return super().timetable(railroad, name)


def test_a_load_does_not_write_the_document_back() -> None:
    store = Counting(evening())
    bus = standing(store)

    load(bus)

    assert row(bus)["timetable"] == "evening"
    assert store.puts == 0


class Counting(Store):
    """A store that counts the documents it was given."""

    puts = 0

    def put_timetable(self, timetable: Timetable) -> None:
        self.puts += 1
        super().put_timetable(timetable)


def reject(bus: InProcessBus, request: str, reason: str = "unreachable") -> None:
    """The dispatcher's rejection of the request with that id."""
    say(bus, REJECTED, {"id": request, "reason": reason})


AGAIN = f"express_2-{NONCE}-2"
"""The id of the second request that sends `express_2` to its start block."""


def test_a_request_to_a_start_block_rejected_unreachable_is_asked_either_way() -> None:
    """One more request, to both ends of the block. A second rejection is
    followed by nothing."""
    bus = standing(Store(evening()))
    load(bus)
    seen = collect(bus, SUBMITTED)

    reject(bus, TO_START)

    assert payloads(seen) == [
        {
            "id": AGAIN,
            "train": "express_2",
            "depart": "up_e.A",
            "dest": ["dn_w.A", "dn_w.B"],
        }
    ]
    assert row(bus)["positioning"] == [AGAIN]

    reject(bus, AGAIN)

    assert len(seen) == 1
    assert (row(bus)["phase"], row(bus)["positioning"]) == ("loaded", [])


def test_a_request_to_a_start_block_rejected_another_way_is_not_asked_again() -> None:
    bus = standing(Store(evening()))
    load(bus)
    seen = collect(bus, SUBMITTED)

    reject(bus, TO_START, "no_fit")

    assert seen == []
    assert row(bus)["positioning"] == []


def test_the_second_request_is_listed_before_the_first_one_ends() -> None:
    """With power on the timetable would start between the two."""
    bus = standing(Store(evening()))
    load(bus)
    power(bus, "on")
    asked = collect(bus, CLOCK_WANTED)

    reject(bus, TO_START)

    assert asked == []
    assert (row(bus)["phase"], row(bus)["positioning"]) == ("loaded", [AGAIN])


def test_a_request_of_the_timetable_loaded_before_is_not_asked_again() -> None:
    morning = Timetable("morning", "crossover-yard", at("09:00"), {}, ())
    bus = standing(Store(evening(), morning))
    load(bus)
    load(bus, "morning")
    seen = collect(bus, SUBMITTED)

    reject(bus, TO_START)

    assert seen == []
    assert row(bus)["positioning"] == []


def test_the_timetable_starts_when_the_last_request_to_a_start_block_ends() -> None:
    """With power on: `clock_wanted` carries the start time and no speed-up,
    and the row reads `running`."""
    bus = standing(Store(evening()))
    load(bus)
    power(bus, "on")
    asked = collect(bus, CLOCK_WANTED)

    assert asked == []
    assert row(bus)["phase"] == "loaded"

    say(bus, COMPLETED, {"id": TO_START})

    assert payloads(asked) == [{"time": at("06:00")}]
    assert (row(bus)["phase"], row(bus)["positioning"]) == ("running", [])
    assert row(bus)["record"] is False


def test_with_power_off_the_timetable_does_not_start_until_it_reads_on() -> None:
    bus = standing(Store(evening()))
    load(bus)
    asked = collect(bus, CLOCK_WANTED)

    say(bus, COMPLETED, {"id": TO_START})

    assert asked == []
    assert row(bus)["phase"] == "loaded"

    power(bus, "on")

    assert payloads(asked) == [{"time": at("06:00")}]
    assert row(bus)["phase"] == "running"


def test_a_timetable_with_no_train_to_send_starts_when_power_reads_on() -> None:
    bus = standing(Store(evening(trains={})))
    load(bus)
    asked = collect(bus, CLOCK_WANTED)

    power(bus, "on")

    assert payloads(asked) == [{"time": at("06:00")}]
    assert row(bus)["timetable"] == "evening"
    assert row(bus)["phase"] == "running"


def test_a_person_starts_a_loaded_timetable_with_a_request_still_out() -> None:
    """And a second gesture, in the `running` phase, is dropped."""
    bus = standing(Store(evening()))
    load(bus)
    asked = collect(bus, CLOCK_WANTED)

    say(bus, START_WANTED, {})

    assert payloads(asked) == [{"time": at("06:00")}]
    assert (row(bus)["phase"], row(bus)["positioning"]) == ("running", [TO_START])

    say(bus, START_WANTED, {})

    assert len(asked) == 1

    say(bus, COMPLETED, {"id": TO_START})

    assert len(asked) == 1
    assert (row(bus)["phase"], row(bus)["positioning"]) == ("running", [])


def test_a_start_gesture_with_no_timetable_loaded_is_dropped() -> None:
    bus = standing(Store())
    asked = collect(bus, CLOCK_WANTED)

    say(bus, START_WANTED, {})

    assert asked == []


def test_a_load_replaces_the_loaded_timetable_and_leaves_its_requests_alone() -> None:
    """The request of `evening` to a start block is not cancelled, and is
    not one of `morning`'s."""
    morning = Timetable("morning", "crossover-yard", at("09:00"), {}, ())
    bus = standing(Store(evening(), morning))
    load(bus)
    seen = collect(bus, "tc49/dispatch/#")
    bus.drain()
    seen.clear()  # the allocation row the bus holds

    load(bus, "morning")

    assert seen == []
    assert row(bus) == {
        "timetable": "morning",
        "phase": "loaded",
        "record": False,
        "start": "09:00",
        "trains": {},
        "positioning": [],
        "entries": [],
    }


IN_PLACE = {
    "freight_1": TrainStart("yard_w", "A-to-B"),
    "express_2": TrainStart("up_e", "B-to-A"),
}
"""Both trains where they stand, so a load sends neither anywhere."""

FACING = "tc49/schedule/state/facing"


def running(store: Store) -> InProcessBus:
    """A scheduler with `evening` loaded and started, and the clock row that
    reads its start time, 06:00, said."""
    bus = standing(store)
    load(bus)
    power(bus, "on")
    clock(bus, "06:00")
    assert row(bus)["phase"] == "running"
    return bus


def states(bus: InProcessBus) -> list[str]:
    """Each entry's state, in order."""
    return [one["state"] for one in entries(bus)]


def test_an_entry_is_released_at_its_time_as_the_drag_a_person_would_make() -> None:
    """The request is the one a drag of that train to those ends gets from a
    scheduler with no timetable: the same id, departure end and `dest`."""
    entry = Entry(at("06:02"), "freight_1", ("dn_e", "up_e.A"))
    bus = running(Store(evening(entry, trains=IN_PLACE)))
    seen = collect(bus, SUBMITTED)

    clock(bus, "06:01", 59)

    assert seen == []
    assert states(bus) == ["later"]

    clock(bus, "06:02")

    plain = InProcessBus(Clock())
    without = collect(plain, SUBMITTED)
    Scheduler(plain, yard(), seeded(), nonce=NONCE)
    drag(plain, "freight_1", "dn_e", "up_e.A")
    assert payloads(seen) == payloads(without)
    assert payloads(seen) == [
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
            "request": f"freight_1-{NONCE}-1",
        }
    ]

    clock(bus, "06:02", 1)

    assert len(seen) == 1


def test_an_entry_moved_later_before_it_went_out_is_released_at_the_new_time() -> None:
    """And not at the old one (#1354). A person moves the 06:02 entry to
    06:05 while the clock reads 06:01."""
    was = {"at": "06:02", "train": "freight_1", "to": ["dn_e"]}
    entry = Entry(at("06:02"), "freight_1", ("dn_e",))
    store = Store(evening(entry, trains=IN_PLACE))
    bus = running(store)
    seen = collect(bus, SUBMITTED)
    clock(bus, "06:01")

    change(bus, was, was | {"at": "06:05"})
    clock(bus, "06:02")
    clock(bus, "06:04", 59)

    assert seen == []
    assert [(one["at"], one["state"]) for one in entries(bus)] == [("06:05", "later")]

    clock(bus, "06:05")

    assert payloads(seen) == [
        {
            "id": f"freight_1-{NONCE}-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["dn_e.A", "dn_e.B"],
        }
    ]
    assert [(one["at"], one["state"]) for one in entries(bus)] == [("06:05", "out")]
    held = store.document("evening")
    assert held is not None
    assert held["entries"] == [was | {"at": "06:05"}]


def test_an_entry_at_the_start_time_is_released_as_the_timetable_starts() -> None:
    entry = Entry(at("06:00"), "freight_1", ("dn_e",))
    bus = standing(Store(evening(entry, trains=IN_PLACE)))
    load(bus)
    seen = collect(bus, SUBMITTED)

    power(bus, "on")

    assert [payload["train"] for payload in payloads(seen)] == ["freight_1"]
    assert states(bus) == ["out"]


def test_a_released_entry_follows_its_request_to_the_end() -> None:
    first = Entry(at("06:02"), "freight_1", ("dn_e",))
    second = Entry(at("06:02"), "express_2", ("dn_w",))
    bus = running(Store(evening(first, second, trains=IN_PLACE)))
    clock(bus, "06:02")
    freight, express = (one["request"] for one in entries(bus))
    clock(bus, "06:05")

    say(bus, COMPLETED, {"id": freight})
    reject(bus, express)

    assert [(one["state"], one.get("ended")) for one in entries(bus)] == [
        ("ended", 5 * 60),
        ("rejected", None),
    ]


def test_a_turn_round_entry_turns_the_train_and_has_ended() -> None:
    """The train's next entry, due in the same minute, goes out at once by
    the end the turn-round gave it, and the row is written once for the
    two."""
    turn = Entry(at("06:02"), "express_2")
    after = Entry(at("06:02"), "express_2", ("dn_w",))
    store = Store(evening(turn, after, trains=IN_PLACE))
    bus = running(store)
    seen = collect(bus, SUBMITTED)
    rows = collect(bus, TIMETABLE)
    bus.drain()
    rows.clear()  # the row the bus holds
    assert bus.last_values[FACING]["facing"]["express_2"] == "up_e.B-to-A"

    clock(bus, "06:02")

    assert len(rows) == 1
    assert bus.last_values[FACING]["facing"]["express_2"] == "up_e.A-to-B"
    assert entries(bus) == [
        {"at": "06:02", "train": "express_2", "turn": True, "state": "ended"},
        {
            "at": "06:02",
            "train": "express_2",
            "to": ["dn_w"],
            "state": "out",
            "request": f"express_2-{NONCE}-1",
        },
    ]
    assert [payload["depart"] for payload in payloads(seen)] == ["up_e.B"]
    held = store.document("evening")
    assert held is not None
    assert len(held["entries"]) == 2


def test_a_turn_round_entry_waits_while_its_train_has_a_request_in_flight() -> None:
    bus = running(Store(evening(Entry(at("06:02"), "express_2"), trains=IN_PLACE)))
    drag(bus, "express_2", "dn_w")

    clock(bus, "06:02")

    assert states(bus) == ["held"]
    assert bus.last_values[FACING]["facing"]["express_2"] == "up_e.B-to-A"

    say(bus, COMPLETED, {"id": f"express_2-{NONCE}-1"})

    assert states(bus) == ["ended"]
    assert bus.last_values[FACING]["facing"]["express_2"] == "up_e.A-to-B"


def test_an_entry_for_a_train_with_a_persons_request_in_flight_chains_after_it() -> (
    None
):
    entry = Entry(at("06:02"), "freight_1", ("up_e",))
    bus = running(Store(evening(entry, trains=IN_PLACE)))
    drag(bus, "freight_1", "dn_e")
    seen = collect(bus, SUBMITTED)

    clock(bus, "06:02")

    assert payloads(seen) == [
        {
            "id": f"freight_1-{NONCE}-2",
            "train": "freight_1",
            "depart": None,
            "dest": ["up_e.A", "up_e.B"],
            "after": f"freight_1-{NONCE}-1",
        }
    ]
    assert states(bus) == ["out"]


def test_a_dwell_holds_back_the_next_entry_and_not_a_persons_drag() -> None:
    """`freight_1` arrives at 06:04 and stands 5 minutes. A person's drag at
    06:05 is submitted at once. The next entry goes out at 06:09."""
    first = Entry(at("06:02"), "freight_1", ("dn_e",), dwell=5)
    second = Entry(at("06:03"), "freight_1", ("up_e",))
    bus = running(Store(evening(first, second, trains=IN_PLACE)))
    clock(bus, "06:02")
    clock(bus, "06:04")
    say(bus, COMPLETED, {"id": f"freight_1-{NONCE}-1"})
    clock(bus, "06:05")
    seen = collect(bus, SUBMITTED)

    assert states(bus) == ["ended", "held"]

    drag(bus, "freight_1", "yard_e")

    assert [(one["id"], one["dest"]) for one in payloads(seen)] == [
        (f"freight_1-{NONCE}-2", ["yard_e.A", "yard_e.B"])
    ]
    assert states(bus) == ["ended", "held"]

    clock(bus, "06:08", 59)

    assert len(seen) == 1

    clock(bus, "06:09")

    assert [(one["id"], one["dest"]) for one in payloads(seen)][1:] == [
        (f"freight_1-{NONCE}-3", ["up_e.A", "up_e.B"])
    ]
    assert states(bus) == ["ended", "out"]


def test_an_entry_for_a_train_off_the_layout_is_skipped() -> None:
    """`local_3` is in the timetable's `trains` and stands in no block."""
    first = Entry(at("06:02"), "local_3", ("dn_e",))
    second = Entry(at("06:02"), "freight_1", ("dn_e",))
    trains = IN_PLACE | {"local_3": TrainStart("yard_e", "B-to-A")}
    bus = running(Store(evening(first, second, trains=trains)))
    seen = collect(bus, SUBMITTED)

    clock(bus, "06:02")

    assert states(bus) == ["skipped", "out"]
    assert [payload["train"] for payload in payloads(seen)] == ["freight_1"]


def test_with_record_off_a_persons_drag_during_a_run_adds_no_entry() -> None:
    """A load leaves Record off. Switched on, the drag is added and the
    document written."""
    entry = Entry(at("06:02"), "freight_1", ("dn_e",))
    store = Store(evening(entry, trains=IN_PLACE))
    bus = running(store)
    clock(bus, "06:01")

    drag(bus, "express_2", "dn_w")

    assert row(bus)["record"] is False
    assert [one["train"] for one in entries(bus)] == ["freight_1"]

    say(bus, RECORD_WANTED, {"record": True})
    drag(bus, "express_2", "yard_e")

    assert [(one["at"], one["train"], one["state"]) for one in entries(bus)] == [
        ("06:01", "express_2", "out"),
        ("06:02", "freight_1", "later"),
    ]
    held = store.document("evening")
    assert held is not None
    assert held["entries"] == [
        {"at": "06:01", "train": "express_2", "to": ["yard_e"]},
        {"at": "06:02", "train": "freight_1", "to": ["dn_e"]},
    ]


def test_a_released_entry_is_not_recorded_again_with_record_on() -> None:
    entry = Entry(at("06:02"), "freight_1", ("dn_e",))
    turn = Entry(at("06:02"), "express_2")
    store = Store(evening(entry, turn, trains=IN_PLACE))
    bus = running(store)
    say(bus, RECORD_WANTED, {"record": True})

    clock(bus, "06:02")

    assert states(bus) == ["out", "ended"]
    held = store.document("evening")
    assert held is not None
    assert len(held["entries"]) == 2


def test_before_the_start_a_persons_drag_is_a_request_with_no_entry() -> None:
    store = Store(evening(trains=IN_PLACE))
    bus = standing(store)
    load(bus)
    say(bus, RECORD_WANTED, {"record": True})
    seen = collect(bus, SUBMITTED)

    drag(bus, "freight_1", "dn_e")

    assert len(seen) == 1
    assert entries(bus) == []


def test_a_timetable_is_over_24_hours_after_its_start_and_stays_loaded() -> None:
    """Nothing more is released or recorded, and `untitled` is not made in
    its place."""
    entry = Entry(at("05:59"), "freight_1", ("dn_e",))
    bus = running(Store(evening(entry, trains=IN_PLACE)))
    say(bus, RECORD_WANTED, {"record": True})
    seen = collect(bus, SUBMITTED)
    clock(bus, "17:00")
    clock(bus, "04:00")

    assert (row(bus)["phase"], states(bus)) == ("running", ["later"])

    clock(bus, "06:00")

    assert (row(bus)["timetable"], row(bus)["phase"]) == ("evening", "over")
    assert seen == []

    drag(bus, "express_2", "dn_w")
    power(bus, "off")
    power(bus, "on")

    assert (row(bus)["timetable"], row(bus)["phase"]) == ("evening", "over")
    assert [one["train"] for one in entries(bus)] == ["freight_1"]


def test_a_restart_adopts_a_loaded_timetable_and_its_requests_to_start_blocks() -> None:
    """The first allocation row lists the request, so it has not ended."""
    store = Store(evening())
    rows = standing_loaded(store)
    rows[ALLOCATION] = rows[ALLOCATION] | {
        "requests": [{"id": TO_START, "train": "express_2"}]
    }

    bus = restarted(store, rows)
    asked = collect(bus, CLOCK_WANTED)

    assert (row(bus)["phase"], row(bus)["positioning"]) == ("loaded", [TO_START])
    assert row(bus)["record"] is False

    power(bus, "on")

    assert asked == []

    say(bus, COMPLETED, {"id": TO_START})

    assert payloads(asked) == [{"time": at("06:00")}]
    assert row(bus)["phase"] == "running"


def test_after_a_restart_a_request_to_a_start_block_not_listed_has_ended() -> None:
    store = Store(evening())
    rows = standing_loaded(store)

    bus = restarted(store, rows)
    asked = collect(bus, CLOCK_WANTED)

    assert (row(bus)["phase"], row(bus)["positioning"]) == ("loaded", [])

    power(bus, "on")

    assert payloads(asked) == [{"time": at("06:00")}]


def standing_loaded(store: Store) -> dict[str, Payload]:
    """What a broker holds after `evening` was loaded with power off and the
    scheduler gone: its two rows, and the clock, power and allocation rows,
    the last listing no request."""
    bus = standing(store)
    load(bus)
    return bus.last_values


def test_a_restart_goes_on_with_a_running_timetable_from_the_clock() -> None:
    """The entry that went out is not released again, and the next one is
    released at its time."""
    first = Entry(at("06:02"), "freight_1", ("dn_e",))
    second = Entry(at("06:06"), "express_2", ("dn_w",))
    store = Store(evening(first, second, trains=IN_PLACE))
    before = running(store)
    clock(before, "06:02")
    rows = before.last_values
    out = rows["tc49/schedule/state/timetable"]["entries"][0]["request"]
    rows[ALLOCATION] = rows[ALLOCATION] | {
        "requests": [{"id": out, "train": "freight_1"}]
    }

    bus = restarted(store, rows)
    seen = collect(bus, SUBMITTED)
    clock(bus, "06:05")

    assert (row(bus)["phase"], states(bus)) == ("running", ["out", "later"])
    assert seen == []

    clock(bus, "06:06")

    assert [payload["train"] for payload in payloads(seen)] == ["express_2"]
    assert states(bus) == ["out", "out"]


def test_a_scheduler_given_no_store_takes_the_two_gestures_and_does_nothing() -> None:
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE)
    seen = collect(bus, "tc49/#")
    bus.drain()
    seen.clear()  # the rows the bus holds

    load(bus)
    say(bus, START_WANTED, {})

    assert [topic for topic, _ in seen] == [TIMETABLE_WANTED, START_WANTED]
