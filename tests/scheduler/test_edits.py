"""A person changes and deletes a timetable's entries and renames the loaded
timetable (#1345, #1354).

Built as `tests/scheduler/test_recording.py` is, with its helpers: gestures
are published at a `Scheduler` on the in-process bus, and the test reads the
state row and the document the store was given.
"""

from typing import Any

from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.lib.fast_clock import DAY_S
from tc49.lib.timetable import Timetable, read_timetable
from tc49.scheduler import Scheduler
from tests.scheduler.test_recording import (
    TIMETABLE,
    Store,
    allocation,
    at,
    clock,
    drag,
    entries,
    power,
    recording,
    restarted,
    row,
    say,
)
from tests.scheduler.test_scheduler import NONCE, seeded, yard

ENTRY_WANTED = "tc49/schedule/entry_wanted"
RENAME_WANTED = "tc49/schedule/timetable_rename_wanted"

FREIGHT = {"at": "06:02", "train": "freight_1", "to": ["dn_e", "up_e"]}
EXPRESS = {"at": "06:05", "train": "express_2", "to": ["dn_w"]}


def evening(
    *listed: dict[str, Any], phase: str = "running", repeat: str = "1d00:00"
) -> tuple[Store, InProcessBus]:
    """A scheduler that came up with the timetable `evening` loaded, and the
    store it keeps it in. The timetable starts at 06:00, repeats every
    `repeat` and has the entries `listed`, none of which has gone out. The
    clock reads 06:00 and power is off."""
    document: dict[str, Any] = {
        "timetable": "evening",
        "layout": "crossover-yard",
        "start": "06:00",
        "repeat": repeat,
        "trains": {},
        "entries": list(listed),
    }
    store = Store(read_timetable(document))
    before = InProcessBus(Clock())
    allocation(before)
    clock(before, "06:00")
    power(before, "off")
    said: dict[str, Any] = {
        "timetable": "evening",
        "phase": phase,
        "record": False,
        "start": "06:00",
        "repeat": repeat,
        "trains": {},
        "positioning": [],
        "entries": [one | {"state": "later"} for one in listed],
    }
    return store, restarted(store, before.last_values | {TIMETABLE: said})


def change(bus: InProcessBus, was: object, now: object) -> None:
    """A person's change of the entry that reads `was` to `now`, or its
    deletion where `now` is None."""
    say(bus, ENTRY_WANTED, {"was": was, "now": now})


def written(store: Store, name: str = "evening") -> list[dict[str, Any]]:
    """The entries of the document the store holds under `name`."""
    held = store.document(name)
    assert held is not None
    return held["entries"]


def test_a_change_of_dwell_and_description_is_in_the_row_and_the_document() -> None:
    store, bus = evening(FREIGHT, EXPRESS)
    now = FREIGHT | {"dwell": 2, "description": "meets the express"}

    change(bus, FREIGHT, now)

    assert entries(bus) == [now | {"state": "later"}, EXPRESS | {"state": "later"}]
    assert written(store) == [now, EXPRESS]


def test_a_changed_time_moves_the_entry_after_the_ones_that_share_its_minute() -> None:
    local = {"at": "06:05", "train": "local_3", "turn": True}
    last = {"at": "06:09", "train": "express_2", "to": ["up_e"]}
    store, bus = evening(FREIGHT, EXPRESS, local, last)
    now = FREIGHT | {"at": "06:05"}

    change(bus, FREIGHT, now)

    assert written(store) == [EXPRESS, local, now, last]
    assert entries(bus) == [one | {"state": "later"} for one in written(store)]


def test_a_changed_time_on_day_1_is_listed_in_the_time_form() -> None:
    store, bus = evening(FREIGHT, EXPRESS)
    now = FREIGHT | {"at": "1d05:59"}

    change(bus, FREIGHT, now)

    assert written(store) == [EXPRESS, now]
    assert [one["at"] for one in entries(bus)] == ["06:05", "1d05:59"]


def test_a_change_to_a_time_outside_the_repeat_changes_nothing() -> None:
    """Before the start, or at the start plus the repeat or after (#1365)."""
    store, bus = evening(FREIGHT, EXPRESS, repeat="03:00")
    before = row(bus)

    for outside in ("05:59", "09:00", "1d06:02"):
        change(bus, FREIGHT, FREIGHT | {"at": outside})

    assert row(bus) == before
    assert written(store) == [FREIGHT, EXPRESS]


def test_a_restart_takes_the_repeat_from_the_row() -> None:
    """And writes it, as it does the entries where the document's differ."""
    store, bus = evening(FREIGHT, repeat="03:00")
    held = store.document("evening")
    assert held is not None
    store.put_timetable(read_timetable(held | {"repeat": "1d00:00"}))
    rows = bus.last_values

    bus = restarted(store, rows)

    assert row(bus)["repeat"] == "03:00"
    held = store.document("evening")
    assert held is not None
    assert held["repeat"] == "03:00"


def recorded(store: Store) -> tuple[InProcessBus, dict[str, Any], dict[str, Any]]:
    """A recording with a drag of `freight_1` at 06:02 and one of
    `express_2` at 06:05, both out, and each one's entry as the row lists
    it."""
    bus = recording(store)
    clock(bus, "06:02")
    drag(bus, "freight_1", "dn_e")
    clock(bus, "06:05")
    drag(bus, "express_2", "dn_w")
    freight, express = entries(bus)
    return bus, freight, express


def fields(entry: dict[str, Any]) -> dict[str, Any]:
    """An entry of the state row with the document's fields only."""
    return {
        field: value
        for field, value in entry.items()
        if field not in ("state", "request", "ended")
    }


def asked(bus: InProcessBus) -> list[str]:
    """The topic of each `cancel_wanted` and `request_submitted` published
    from now on."""
    seen: list[str] = []
    for leaf in ("cancel_wanted", "request_submitted"):
        bus.subscribe(f"tc49/dispatch/{leaf}", lambda topic, _: seen.append(topic))
    return seen


def test_a_change_to_an_entry_that_is_out_keeps_its_state_and_request() -> None:
    """The time and the dwell change. The request is left alone: nothing is
    cancelled and nothing submitted."""
    store = Store()
    bus, freight, express = recorded(store)
    seen = asked(bus)
    now = fields(freight) | {"at": "06:07", "dwell": 3}

    change(bus, fields(freight), now)

    assert entries(bus) == [
        express,
        now | {"state": "out", "request": freight["request"]},
    ]
    assert written(store, "untitled") == [fields(express), now]
    assert seen == []


def test_a_deleted_entry_is_gone_from_the_row_and_the_document() -> None:
    store, bus = evening(FREIGHT, EXPRESS)

    change(bus, FREIGHT, None)

    assert entries(bus) == [EXPRESS | {"state": "later"}]
    assert written(store) == [EXPRESS]


def test_deleting_an_entry_that_is_out_leaves_its_request_alone() -> None:
    """Nothing is cancelled. The entry left keeps its own state and
    request."""
    store = Store()
    bus, freight, express = recorded(store)
    seen = asked(bus)

    change(bus, fields(freight), None)

    assert entries(bus) == [express]
    assert written(store, "untitled") == [fields(express)]
    assert seen == []


def test_of_two_entries_equal_in_every_field_the_first_is_changed() -> None:
    """Two drags of one train to one block in one minute. The second request
    follows the first, and the entries differ in nothing the document has."""
    store = Store()
    bus = recording(store)
    drag(bus, "freight_1", "dn_e")
    drag(bus, "freight_1", "dn_e")
    first, second = entries(bus)
    assert fields(first) == fields(second)
    now = fields(first) | {"description": "the first of two"}

    change(bus, fields(first), now)

    assert entries(bus) == [first | now, second]
    assert written(store, "untitled") == [now, fields(second)]

    change(bus, fields(second), None)

    assert entries(bus) == [first | now]


def test_a_was_that_spells_out_a_dwell_of_0_names_the_entry_that_leaves_it_out() -> (
    None
):
    store, bus = evening(FREIGHT, EXPRESS)

    change(bus, FREIGHT | {"dwell": 0, "description": ""}, None)

    assert written(store) == [EXPRESS]


def test_a_was_equal_to_no_entry_changes_nothing() -> None:
    """One field off, in each field."""
    held = FREIGHT | {"dwell": 2, "description": "meets the express"}
    store, bus = evening(held, EXPRESS)
    before = row(bus)

    for other in (
        {"at": "06:03"},
        {"train": "express_2"},
        {"to": ["dn_e"]},
        {"dwell": 3},
        {"description": "meets the local"},
    ):
        change(bus, held | other, held | {"dwell": 9})
        change(bus, held | other, None)
    change(bus, {"at": "06:02", "train": "freight_1", "turn": True}, None)

    assert row(bus) == before
    assert written(store) == [held, EXPRESS]


def test_a_gesture_that_cannot_be_read_changes_nothing() -> None:
    """A `now` or a `was` that is no entry of a timetable document, a `was`
    with the row's `state`, and a gesture with no `now`."""
    store, bus = evening(FREIGHT, EXPRESS)
    before = row(bus)

    for now in (
        FREIGHT | {"at": "6:02"},
        FREIGHT | {"dwell": -1},
        FREIGHT | {"dwell": 1.5},
        FREIGHT | {"turn": True},
        FREIGHT | {"to": []},
        FREIGHT | {"description": 7},
        FREIGHT | {"state": "later"},
        {"at": "06:02", "train": "freight_1"},
        "06:02",
    ):
        change(bus, FREIGHT, now)
    change(bus, FREIGHT | {"state": "later"}, None)
    change(bus, None, None)
    say(bus, ENTRY_WANTED, {"was": FREIGHT})
    say(bus, ENTRY_WANTED, {})

    assert row(bus) == before
    assert written(store) == [FREIGHT, EXPRESS]


def test_an_entry_gesture_with_no_timetable_loaded_is_dropped() -> None:
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=Store())

    change(bus, FREIGHT, None)
    change(bus, FREIGHT, EXPRESS)

    assert row(bus) == {"timetable": None}


def test_an_entry_of_a_timetable_that_is_over_can_be_changed_and_deleted() -> None:
    store, bus = evening(FREIGHT, EXPRESS, phase="over")
    now = FREIGHT | {"at": "06:10", "dwell": 2}

    change(bus, FREIGHT, now)
    change(bus, EXPRESS, None)

    assert row(bus)["phase"] == "over"
    assert [fields(one) for one in entries(bus)] == [now]
    assert written(store) == [now]


class Logged(Store):
    """A store that lists what it was asked to write and delete, in order."""

    def __init__(self, *held: Timetable) -> None:
        super().__init__(*held)
        self.asked: list[str] = []

    def put_timetable(self, timetable: Timetable) -> None:
        self.asked.append(f"put {timetable.name}")
        super().put_timetable(timetable)

    def delete_timetable(self, railroad: str, name: str) -> None:
        self.asked.append(f"delete {name}")
        super().delete_timetable(railroad, name)


def rename(bus: InProcessBus, to: object) -> None:
    """A person's rename of the loaded timetable to `to`."""
    say(bus, RENAME_WANTED, {"to": to})


def test_a_rename_writes_the_new_document_deletes_the_old_and_changes_the_row() -> None:
    """The new document is written before the old one is deleted."""
    store = Logged()
    bus, freight, express = recorded(store)
    before = store.document("untitled")
    assert before is not None
    store.asked.clear()

    rename(bus, "evening")

    assert row(bus)["timetable"] == "evening"
    assert entries(bus) == [freight, express]
    assert store.document("evening") == before | {"timetable": "evening"}
    assert store.document("untitled") is None
    assert store.asked == ["put evening", "delete untitled"]


def test_after_a_rename_a_drag_is_recorded_under_the_new_name() -> None:
    """Power is on and `untitled` is not made again."""
    store = Store()
    bus, _, _ = recorded(store)

    rename(bus, "evening")
    clock(bus, "06:09")
    drag(bus, "freight_1", "up_e")

    assert row(bus)["timetable"] == "evening"
    assert [one["at"] for one in written(store)] == ["06:02", "06:05", "06:09"]
    assert list(store.held) == [("crossover-yard", "evening")]


def test_a_rename_to_a_name_the_store_has_is_dropped() -> None:
    """Both documents are as they were."""
    stored = Timetable("evening", "crossover-yard", at("22:00"), DAY_S, {}, ())
    store = Logged(stored)
    bus, _, _ = recorded(store)
    before = store.document("untitled")
    store.asked.clear()

    rename(bus, "evening")

    assert row(bus)["timetable"] == "untitled"
    assert store.document("untitled") == before
    assert store.timetable("crossover-yard", "evening") == stored
    assert store.asked == []


def test_a_rename_to_the_name_the_timetable_has_is_dropped() -> None:
    """The store has it, and it is not deleted."""
    store = Logged()
    bus, _, _ = recorded(store)
    before = store.document("untitled")
    store.asked.clear()

    rename(bus, "untitled")

    assert row(bus)["timetable"] == "untitled"
    assert store.document("untitled") == before
    assert store.asked == []


def test_a_rename_to_no_name_a_timetable_document_takes_is_dropped() -> None:
    store = Logged()
    bus, _, _ = recorded(store)
    store.asked.clear()

    for to in ("a/b", ".hidden", "", 7, None, ["evening"]):
        rename(bus, to)
    say(bus, RENAME_WANTED, {})
    say(bus, RENAME_WANTED, {"timetable": "evening"})

    assert row(bus)["timetable"] == "untitled"
    assert list(store.held) == [("crossover-yard", "untitled")]
    assert store.asked == []


def test_a_rename_with_no_timetable_loaded_is_dropped() -> None:
    store = Logged()
    bus = InProcessBus(Clock())
    Scheduler(bus, yard(), seeded(), nonce=NONCE, store=store)

    rename(bus, "evening")

    assert row(bus) == {"timetable": None}
    assert store.asked == []


def test_a_rename_where_the_store_cannot_read_that_name_is_dropped() -> None:
    """The store has a document of that name, which does not read."""
    store = Unread()
    bus, _, _ = recorded(store)
    store.asked.clear()

    rename(bus, "evening")

    assert row(bus)["timetable"] == "untitled"
    assert store.asked == []


class Unread(Logged):
    """A store whose document named `evening` does not read."""

    def timetable(self, railroad: str, name: str) -> Timetable | None:
        if name == "evening":
            raise ValueError("timetable 'evening': 'start' is 360")
        return super().timetable(railroad, name)
