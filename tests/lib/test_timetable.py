"""The timetable document: what it reads as, what it refuses, the order its
entries are held in and the time form its times are written in (#1345,
#1365).

At the module and through no store: a parsed document in, the value or the
refusal out, and the value back to a document.
"""

from dataclasses import replace
from typing import Any

import pytest
import yaml

from tc49.lib.timetable import (
    Entry,
    Timetable,
    TrainStart,
    read_entry,
    read_time,
    read_timetable,
    time_text,
)


def hm(hours: int, minutes: int, day: int = 0) -> int:
    """A time in seconds since midnight of day 0."""
    return day * 86400 + (hours * 60 + minutes) * 60


EXAMPLE = """
timetable: evening
layout: crossover-yard
start: "06:00"
repeat: "1d00:00"

trains:
  freight_1: { at: yard_w, facing: A-to-B }

entries:
  - { at: "06:02", train: freight_1, to: [dn_e, up_e], dwell: 2, description: meets the express }
  - { at: "06:10", train: freight_1, turn: true }
  - { at: "06:12", train: freight_1, to: [yard_w.B] }
"""
"""The example of #1345, as the file in the store: one train, two runs and a
turn-round between."""


def document(**over: Any) -> dict[str, Any]:
    """The example as the store parses it, with `over` in place of its
    fields."""
    return yaml.safe_load(EXAMPLE) | over


def test_a_time_left_unquoted_in_the_file_is_refused() -> None:
    """YAML 1.1 reads a bare 12:30 as the number 750."""
    doc = yaml.safe_load(EXAMPLE.replace('"06:00"', "12:30"))

    with pytest.raises(ValueError, match="'start' is 750"):
        read_timetable(doc)


def test_a_timetable_is_its_start_its_trains_and_its_entries() -> None:
    assert read_timetable(document()) == Timetable(
        name="evening",
        layout="crossover-yard",
        start=hm(6, 0),
        repeat=hm(0, 0, day=1),
        trains={"freight_1": TrainStart(at="yard_w", facing="A-to-B")},
        entries=(
            Entry(
                at=hm(6, 2),
                train="freight_1",
                to=("dn_e", "up_e"),
                dwell=2,
                description="meets the express",
            ),
            Entry(at=hm(6, 10), train="freight_1"),
            Entry(at=hm(6, 12), train="freight_1", to=("yard_w.B",)),
        ),
    )


def test_a_timetable_is_written_as_the_document_it_was_read_from() -> None:
    assert read_timetable(document()).document() == document()


def test_a_dwell_of_0_and_an_empty_description_are_left_out_when_written() -> None:
    """Both read as the entry that states neither, so the written document
    reads as an equal value."""
    doc = document(
        entries=[
            {
                "at": "06:02",
                "train": "freight_1",
                "to": ["dn_e"],
                "dwell": 0,
                "description": "",
            }
        ]
    )
    read = read_timetable(doc)

    written = read.document()

    assert written["entries"] == [{"at": "06:02", "train": "freight_1", "to": ["dn_e"]}]
    assert read_timetable(written) == read


def test_a_timetable_may_have_no_trains_and_no_entries() -> None:
    read = read_timetable(document(trains={}, entries=[]))

    assert (read.trains, read.entries) == ({}, ())


def test_a_block_and_a_train_no_railroad_has_are_read() -> None:
    """The module is given no layout and no roster. The track plan gets
    rebuilt, and the dispatcher answers such an entry as it answers any
    request (#1345)."""
    read = read_timetable(
        document(
            trains={"ghost": {"at": "nowhere", "facing": "B-to-A"}},
            entries=[{"at": "06:02", "train": "phantom", "to": ["elsewhere.A"]}],
        )
    )

    assert read.trains == {"ghost": TrainStart("nowhere", "B-to-A")}
    assert read.entries == (Entry(hm(6, 2), "phantom", ("elsewhere.A",)),)


def less(key: str) -> dict[str, Any]:
    """The example without one of its six fields."""
    doc = document()
    del doc[key]
    return doc


def start(**fields: Any) -> dict[str, Any]:
    """The example with its one train's start replaced by `fields`."""
    return document(trains={"freight_1": fields})


def entry(**fields: Any) -> dict[str, Any]:
    """The example with `fields` as its one entry."""
    return document(entries=[fields])


RUN = {"at": "06:02", "train": "freight_1", "to": ["dn_e"]}
"""An entry that reads."""

TURN = {"at": "06:10", "train": "freight_1", "turn": True}
"""A turn-round that reads."""


@pytest.mark.parametrize(
    ("doc", "field"),
    [
        # All six fields and nothing else.
        (less("timetable"), "timetable"),
        (less("layout"), "layout"),
        (less("start"), "start"),
        (less("repeat"), "repeat"),
        (less("trains"), "trains"),
        (less("entries"), "entries"),
        (document(speed_up=8), "speed_up"),
        # Both names are path segments in the store.
        (document(timetable=7), "timetable"),
        (document(timetable=""), "timetable"),
        (document(timetable="late/evening"), "timetable"),
        (document(timetable=".evening"), "timetable"),
        (document(layout=None), "layout"),
        (document(layout=""), "layout"),
        (document(layout="yards/crossover"), "layout"),
        (document(layout=".."), "layout"),
        # A time is "HH:MM" as text. YAML 1.1 reads a bare 12:30 as 750.
        (document(start=750), "start"),
        (document(start="6:00"), "start"),
        (document(start="24:00"), "start"),
        (document(start="06:60"), "start"),
        (document(start="06:00:30"), "start"),
        # The start is on day 0.
        (document(start="0d06:00"), "start"),
        (document(start="1d06:00"), "start"),
        # A time and a length are [<day>d]HH:MM, the day without leading
        # zeros.
        (entry(**RUN | {"at": 750}), "at"),
        (entry(**RUN | {"at": "6:02"}), "at"),
        (entry(**RUN | {"at": "01d06:02"}), "at"),
        (entry(**RUN | {"at": "d06:02"}), "at"),
        (entry(**RUN | {"at": "1 d06:02"}), "at"),
        (entry(**RUN | {"at": "1d24:00"}), "at"),
        (entry(**RUN | {"at": "-1d06:02"}), "at"),
        (document(repeat=10800), "repeat"),
        (document(repeat="3:00"), "repeat"),
        (document(repeat="1d"), "repeat"),
        # A repeat is greater than 0.
        (document(repeat="00:00"), "repeat"),
        (document(repeat="0d00:00"), "repeat"),
        # Every entry lies from the start to before the start plus the
        # repeat.
        (entry(**RUN | {"at": "05:59"}), "at"),
        (entry(**RUN | {"at": "1d06:00"}), "at"),
        (document(repeat="03:00", entries=[RUN | {"at": "09:00"}]), "at"),
        # A train's start is its block and its facing.
        (document(trains=[]), "trains"),
        (document(trains={"": {"at": "yard_w", "facing": "A-to-B"}}), "trains"),
        (document(trains={7: {"at": "yard_w", "facing": "A-to-B"}}), "trains"),
        (document(trains={"freight_1": "yard_w"}), "freight_1"),
        (start(facing="A-to-B"), "at"),
        (start(at="yard_w"), "facing"),
        (start(at="yard_w", facing="A-to-B", length=400), "length"),
        (start(at="", facing="A-to-B"), "at"),
        (start(at=7, facing="A-to-B"), "at"),
        (start(at="yard_w", facing="A"), "facing"),
        (start(at="yard_w", facing="east"), "facing"),
        # An entry has `at`, `train` and one of `to` or `turn: true`.
        (document(entries={}), "entries"),
        (entry(train="freight_1", to=["dn_e"]), "at"),
        (entry(at="06:02", to=["dn_e"]), "train"),
        (entry(**RUN | {"train": ""}), "train"),
        (entry(**RUN | {"train": 7}), "train"),
        (entry(at="06:02", train="freight_1"), "to"),
        (entry(**RUN | {"turn": True}), "turn"),
        (entry(**TURN | {"turn": False}), "turn"),
        (entry(**TURN | {"turn": "yes"}), "turn"),
        (entry(**RUN | {"to": []}), "to"),
        (entry(**RUN | {"to": "dn_e"}), "to"),
        (entry(**RUN | {"to": [""]}), "to"),
        (entry(**RUN | {"to": ["dn_e", 7]}), "to"),
        # A dwell is whole minutes, 0 or more, and goes only with `to`.
        (entry(**RUN | {"dwell": -1}), "dwell"),
        (entry(**RUN | {"dwell": 1.5}), "dwell"),
        (entry(**RUN | {"dwell": True}), "dwell"),
        (entry(**RUN | {"dwell": "2"}), "dwell"),
        (entry(**TURN | {"dwell": 2}), "dwell"),
        (entry(**TURN | {"dwell": 0}), "dwell"),
        (entry(**RUN | {"description": 7}), "description"),
        (entry(**RUN | {"from": "yard_w.B"}), "from"),
    ],
)
def test_a_document_that_breaks_the_shape_is_refused_by_its_field(
    doc: dict[str, Any], field: str
) -> None:
    with pytest.raises((ValueError, TypeError), match=f"'{field}'"):
        read_timetable(doc)


@pytest.mark.parametrize("doc", [None, [], "evening"])
def test_a_timetable_that_is_no_document_is_refused(doc: object) -> None:
    with pytest.raises(TypeError, match="timetable"):
        read_timetable(doc)


def test_a_refusal_says_which_entry_it_is() -> None:
    doc = document(entries=[RUN, "06:10 turn", TURN])

    with pytest.raises(TypeError, match="entry 2"):
        read_timetable(doc)

    doc = document(entries=[RUN, TURN, RUN | {"dwell": -1}])

    with pytest.raises(ValueError, match="entry 3.*'dwell'"):
        read_timetable(doc)


def test_an_entry_is_read_and_written_on_its_own() -> None:
    """As a gesture and the state row carry one, outside any timetable."""
    run_ = read_entry(RUN | {"dwell": 2})
    turn = read_entry(TURN | {"description": "runs round"})

    assert run_ == Entry(hm(6, 2), "freight_1", ("dn_e",), dwell=2)
    assert turn == Entry(hm(6, 10), "freight_1", description="runs round")
    assert (run_.turn, turn.turn) == (False, True)
    assert run_.document() == RUN | {"dwell": 2}
    assert turn.document() == TURN | {"description": "runs round"}


def test_an_entry_read_on_its_own_is_refused_by_its_field() -> None:
    with pytest.raises(ValueError, match="^entry: 'dwell'"):
        read_entry(RUN | {"dwell": -1})


@pytest.mark.parametrize("name", ["", "late/evening", ".evening"])
def test_a_timetable_takes_no_name_that_is_not_a_path_segment(name: str) -> None:
    """A rename is the value under a new name, and the same rule holds."""
    read = read_timetable(document())

    with pytest.raises(ValueError, match="'timetable'"):
        replace(read, name=name)


@pytest.mark.parametrize("time", [hm(6, 0) + 30, -60])
def test_a_time_that_is_not_a_whole_minute_is_refused(time: int) -> None:
    """The time form says no seconds, so a value holding some would not be
    read back as written."""
    with pytest.raises(ValueError, match="'at'"):
        Entry(at=time, train="freight_1")
    with pytest.raises(ValueError, match="'start'"):
        replace(read_timetable(document()), start=time)
    with pytest.raises(ValueError, match="'repeat'"):
        replace(read_timetable(document()), repeat=time)


def test_a_start_is_a_time_on_day_0() -> None:
    with pytest.raises(ValueError, match="'start'"):
        replace(read_timetable(document(entries=[])), start=hm(6, 0, day=1))


def test_a_repeat_of_0_is_refused() -> None:
    with pytest.raises(ValueError, match="'repeat'"):
        replace(read_timetable(document()), repeat=0)


@pytest.mark.parametrize(
    ("text", "time"),
    [
        ("06:00", hm(6, 0)),
        ("0d06:00", hm(6, 0)),
        ("1d06:00", hm(6, 0, day=1)),
        ("1d00:00", hm(0, 0, day=1)),
        ("12d23:59", hm(23, 59, day=12)),
        ("00:00", 0),
    ],
)
def test_a_time_is_read_as_seconds_since_midnight_of_day_0(
    text: str, time: int
) -> None:
    assert read_time(text, "'at'") == time


def test_a_time_is_written_without_the_day_on_day_0() -> None:
    assert [time_text(time) for time in (0, hm(6, 0), hm(6, 0, day=1))] == [
        "00:00",
        "06:00",
        "1d06:00",
    ]
    assert time_text(hm(23, 59, day=12)) == "12d23:59"


def test_an_entry_on_day_1_reads_and_is_written_back() -> None:
    doc = document(entries=[run("0d06:02"), run("1d05:59")])
    read = read_timetable(doc)

    assert [entry.at for entry in read.entries] == [hm(6, 2), hm(5, 59, day=1)]
    assert times(read) == ["06:02", "1d05:59"]
    assert read_timetable(read.document()) == read


def test_an_entry_outside_the_repeat_is_refused_naming_the_range() -> None:
    with pytest.raises(
        ValueError, match="entry 1: 'at' is 05:59, before the start 06:00"
    ):
        read_timetable(entry(**RUN | {"at": "05:59"}))
    with pytest.raises(
        ValueError, match="entry 1: 'at' is 1d06:00, after the last minute 1d05:59"
    ):
        read_timetable(entry(**RUN | {"at": "1d06:00"}))


def run(at: str, train: str = "freight_1", **fields: Any) -> dict[str, Any]:
    """An entry's document: `train` sent to `dn_e` at `at`."""
    return {"at": at, "train": train, "to": ["dn_e"]} | fields


def times(timetable: Timetable) -> list[str]:
    """The entries' times in the order the timetable holds them."""
    return [entry["at"] for entry in timetable.document()["entries"]]


def trains(timetable: Timetable) -> list[str]:
    """The entries' trains in the order the timetable holds them."""
    return [entry.train for entry in timetable.entries]


def test_entries_are_held_in_order_of_their_time() -> None:
    """With a start of 22:00, 1d01:00 comes after 23:00."""
    read = read_timetable(
        document(start="22:00", entries=[run("1d01:00"), run("23:00"), run("22:30")])
    )

    assert times(read) == ["22:30", "23:00", "1d01:00"]


def test_the_last_minute_of_the_repeat_is_listed_last() -> None:
    """With a start of 06:00 and a repeat of a day, 1d05:59 is the last
    minute, and 05:59 is before the start."""
    read = read_timetable(document(entries=[run("1d05:59"), run("06:00")]))

    assert times(read) == ["06:00", "1d05:59"]
    with pytest.raises(ValueError, match="'at'"):
        read_timetable(document(entries=[run("05:59")]))


def test_entries_in_one_minute_keep_the_documents_order() -> None:
    read = read_timetable(
        document(
            entries=[
                run("06:10", "express"),
                run("06:05", "local"),
                run("06:05", "freight_1"),
                run("06:05", "branch"),
            ]
        )
    )

    assert trains(read) == ["local", "freight_1", "branch", "express"]


NIGHT = read_timetable(
    document(
        start="22:00",
        entries=[
            run("22:30", "local"),
            run("23:00", "express"),
            run("23:00", "freight_1"),
            run("1d01:00", "branch"),
        ],
    )
)
"""A timetable that runs over midnight, with two entries in one minute."""


def new(at: int, train: str = "new", **fields: Any) -> Entry:
    """An entry to add: `train` sent to `up_e` at `at`."""
    return Entry(at, train, ("up_e",), **fields)


def test_a_new_entry_goes_after_the_entries_that_share_its_time() -> None:
    added = NIGHT.added(new(hm(23, 0)))

    assert trains(added) == ["local", "express", "freight_1", "new", "branch"]
    assert NIGHT.place(hm(23, 0)) == 3


def test_a_new_entry_goes_after_the_last_entry_before_its_time() -> None:
    """1d00:30 is after 23:00 and before 1d01:00."""
    added = NIGHT.added(new(hm(0, 30, day=1)))

    assert trains(added) == ["local", "express", "freight_1", "new", "branch"]
    assert NIGHT.place(hm(0, 30, day=1)) == 3


def test_a_new_entry_before_every_other_is_first_and_after_every_other_last() -> None:
    assert trains(NIGHT.added(new(hm(22, 0)))) == [
        "new",
        "local",
        "express",
        "freight_1",
        "branch",
    ]
    assert trains(NIGHT.added(new(hm(21, 59, day=1)))) == [
        "local",
        "express",
        "freight_1",
        "branch",
        "new",
    ]
    assert (NIGHT.place(hm(22, 0)), NIGHT.place(hm(21, 59, day=1))) == (0, 4)


def test_a_new_entry_outside_the_repeat_is_refused() -> None:
    with pytest.raises(ValueError, match="'at'"):
        NIGHT.added(new(hm(22, 0, day=1)))


def test_adding_leaves_the_timetable_it_was_added_to_as_it_was() -> None:
    NIGHT.added(new(hm(23, 0)))

    assert trains(NIGHT) == ["local", "express", "freight_1", "branch"]


def test_an_entry_is_removed_by_its_position() -> None:
    """By position because two entries can be equal."""
    assert trains(NIGHT.removed(1)) == ["local", "freight_1", "branch"]


def test_an_entry_replaced_at_the_same_time_stays_where_it_is() -> None:
    """A dwell or a description changed does not move an entry past the
    others in its minute."""
    replaced = NIGHT.replaced(1, new(hm(23, 0), "express", dwell=5))

    assert trains(replaced) == ["local", "express", "freight_1", "branch"]
    assert replaced.entries[1].dwell == 5


def test_an_entry_replaced_at_another_time_moves_to_its_place() -> None:
    later = NIGHT.replaced(0, new(hm(23, 0), "local"))
    earlier = NIGHT.replaced(3, new(hm(22, 30), "branch"))

    assert trains(later) == ["express", "freight_1", "local", "branch"]
    assert trains(earlier) == ["local", "branch", "express", "freight_1"]
