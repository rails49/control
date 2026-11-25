"""The timetable document: what it reads as, what it refuses, the order its
entries are held in and the arithmetic on its times (#1345).

At the module and through no store: a parsed document in, the value or the
refusal out, and the value back to a document.
"""

from dataclasses import replace
from typing import Any

import pytest

from tc49.lib.timetable import Entry, Timetable, TrainStart, read_timetable


def hm(hours: int, minutes: int) -> int:
    """A time of day in seconds since midnight."""
    return (hours * 60 + minutes) * 60


def document(**over: Any) -> dict[str, Any]:
    """The example of #1345: one train, two runs and a turn-round between."""
    return {
        "timetable": "evening",
        "layout": "crossover-yard",
        "start": "06:00",
        "trains": {"freight_1": {"at": "yard_w", "facing": "A-to-B"}},
        "entries": [
            {
                "at": "06:02",
                "train": "freight_1",
                "to": ["dn_e", "up_e"],
                "dwell": 2,
                "description": "meets the express",
            },
            {"at": "06:10", "train": "freight_1", "turn": True},
            {"at": "06:12", "train": "freight_1", "to": ["yard_w.B"]},
        ],
    } | over


def test_a_timetable_is_its_start_its_trains_and_its_entries() -> None:
    assert read_timetable(document()) == Timetable(
        name="evening",
        layout="crossover-yard",
        start=hm(6, 0),
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
    """The example without one of its five fields."""
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
        # All five fields and nothing else.
        (less("timetable"), "timetable"),
        (less("layout"), "layout"),
        (less("start"), "start"),
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
        (entry(**RUN | {"at": 362}), "at"),
        (entry(**RUN | {"at": "6:02"}), "at"),
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


@pytest.mark.parametrize("name", ["", "late/evening", ".evening"])
def test_a_timetable_takes_no_name_that_is_not_a_path_segment(name: str) -> None:
    """A rename is the value under a new name, and the same rule holds."""
    read = read_timetable(document())

    with pytest.raises(ValueError, match="'timetable'"):
        replace(read, name=name)


@pytest.mark.parametrize("time", [hm(6, 0) + 30, -60, hm(24, 0)])
def test_a_time_that_is_not_a_minute_of_the_day_is_refused(time: int) -> None:
    """`"HH:MM"` says no seconds, so a value holding some would not be read
    back as written."""
    with pytest.raises(ValueError, match="'at'"):
        Entry(at=time, train="freight_1")
    with pytest.raises(ValueError, match="'start'"):
        replace(read_timetable(document()), start=time)
