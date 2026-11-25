"""The timetable's release rule: what the scheduler is told in, the entries to
release and the state row out (#1345, #1351).

A state is built by hand, told events, and asked what is due. Nothing here
has a bus. The timetable starts at 06:00 unless a test says otherwise, and
`at("06:02")` is that time of day in seconds.
"""

import ast
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import tc49.scheduler.release
from tc49.lib.timetable import Entry, Timetable, TrainStart
from tc49.scheduler.release import (
    CANCELLED,
    COMPLETED,
    ENDED,
    HELD,
    LATER,
    LOADED,
    OUT,
    OVER,
    REJECTED,
    RUNNING,
    SKIPPED,
    Progress,
    Release,
    State,
    announced,
    clocked,
    due,
    ended,
    placed,
    powered,
    released,
    restarted,
    row,
    started,
    starts,
    turned,
)
from tests.system.test_app_boundaries import tc49_imports


def test_the_release_rule_imports_only_lib() -> None:
    """It has no bus: nothing of `tc49.lib.bus`, and no app."""
    source = Path(tc49.scheduler.release.__file__).read_text()
    names = tc49_imports(ast.parse(source))

    assert names
    assert all(name.startswith("tc49.lib.") for name in names)
    assert "tc49.lib.bus" not in names


def at(hh_mm: str) -> int:
    """`"HH:MM"` as seconds since midnight."""
    hours, minutes = hh_mm.split(":")
    return (int(hours) * 60 + int(minutes)) * 60


def running(*entries: Entry, start: str = "06:00") -> State:
    """A timetable of `entries` that has just started, with its trains on the
    layout and power on."""
    timetable = Timetable("evening", "crossover-yard", at(start), {}, entries)
    return State(
        timetable,
        RUNNING,
        time=0,
        power="on",
        placed=frozenset(entry.train for entry in entries),
    )


def loaded(*entries: Entry, positioning: tuple[str, ...] = ()) -> State:
    """A timetable of `entries` just loaded, with power off and its trains on
    the layout, and a request to a start block out under each id in
    `positioning`."""
    return State(
        running(*entries).timetable,
        LOADED,
        positioning=positioning,
        placed=frozenset(entry.train for entry in entries),
        in_flight=dict.fromkeys(positioning, "freight"),
    )


def states(state: State) -> list[str]:
    """Each entry's state, in order."""
    return [progress.state for progress in state.progress]


def test_an_entry_is_released_when_the_clock_reaches_its_time() -> None:
    entry = Entry(at("06:02"), "freight", ("dn_e", "up_e"))
    state = clocked(running(entry), at("06:01") + 59, 1)

    assert due(state) == ()

    state = clocked(state, at("06:02"), 1)

    assert due(state) == (Release(0, entry),)


def test_an_entry_the_scheduler_released_is_not_due_again() -> None:
    entry = Entry(at("06:02"), "freight", ("dn_e",))
    state = clocked(running(entry), at("06:02"), 1)

    state = released(state, 0, "freight-ab-1")

    assert due(state) == ()
    assert due(clocked(state, at("06:03"), 1)) == ()


def test_an_entry_is_later_until_it_is_due_and_then_held_or_out() -> None:
    first = Entry(at("06:02"), "freight", ("dn_e",))
    second = Entry(at("06:05"), "freight", ("yard_w",))
    state = clocked(running(first, second), at("06:01"), 1)

    assert states(state) == [LATER, LATER]

    state = released(clocked(state, at("06:06"), 1), 0, "freight-ab-1")

    assert states(state) == [OUT, HELD]
    assert state.progress[0].request == "freight-ab-1"


def test_a_late_trains_next_entry_leaves_as_soon_as_the_one_before_ends() -> None:
    first = Entry(at("06:02"), "freight", ("dn_e",))
    second = Entry(at("06:05"), "freight", ("yard_w",))
    state = clocked(running(first, second), at("06:02"), 1)
    state = released(state, 0, "freight-ab-1")

    state = clocked(state, at("06:09"), 1)

    assert due(state) == ()

    state = ended(state, "freight-ab-1", COMPLETED)

    assert due(state) == (Release(1, second),)
    assert state.progress[0] == Progress(ENDED, "freight-ab-1", 9 * 60)


def test_two_trains_entries_do_not_wait_on_each_other() -> None:
    freight = Entry(at("06:02"), "freight", ("dn_e",))
    express = Entry(at("06:02"), "express", ("up_w",))
    express_on = Entry(at("06:03"), "express", ("yard_e",))
    freight_on = Entry(at("06:03"), "freight", ("yard_w",))
    state = running(freight, express, express_on, freight_on)
    state = clocked(state, at("06:04"), 1)

    assert due(state) == (Release(0, freight), Release(1, express))

    state = released(state, 0, "freight-ab-1")

    assert due(state) == (Release(1, express),)

    state = released(state, 1, "express-ab-1")
    state = ended(state, "express-ab-1", COMPLETED)

    assert due(state) == (Release(2, express_on),)


def test_a_dwell_holds_the_trains_next_entry_back_from_the_arrival() -> None:
    first = Entry(at("06:02"), "freight", ("dn_e",), dwell=2)
    second = Entry(at("06:05"), "freight", ("yard_w",))
    state = released(clocked(running(first, second), at("06:02"), 1), 0, "f-1")
    state = ended(clocked(state, at("06:10"), 1), "f-1", COMPLETED)

    assert due(state) == ()
    assert states(state) == [ENDED, HELD]
    assert due(clocked(state, at("06:11") + 59, 1)) == ()
    assert due(clocked(state, at("06:12"), 1)) == (Release(1, second),)


@pytest.mark.parametrize(
    ("how", "became"), [(REJECTED, REJECTED), (CANCELLED, CANCELLED)]
)
def test_a_rejected_or_cancelled_entry_is_not_retried_and_has_no_dwell(
    how: str, became: str
) -> None:
    """The train's later entries are still released."""
    first = Entry(at("06:02"), "freight", ("dn_e",), dwell=5)
    second = Entry(at("06:02"), "freight", ("yard_w",))
    state = released(clocked(running(first, second), at("06:02"), 1), 0, "f-1")

    state = ended(state, "f-1", how)

    assert state.progress[0] == Progress(became, "f-1")
    assert due(state) == (Release(1, second),)


def test_a_train_off_the_layout_has_its_entry_skipped_and_runs_once_placed() -> None:
    first = Entry(at("06:02"), "freight", ("dn_e",), dwell=5)
    second = Entry(at("06:05"), "freight", ("yard_w",))
    state = placed(running(first, second), frozenset())

    state = clocked(state, at("06:02"), 1)

    assert due(state) == ()
    assert states(state) == [SKIPPED, LATER]

    state = clocked(placed(state, frozenset({"freight"})), at("06:05"), 1)

    assert states(state) == [SKIPPED, HELD]
    assert due(state) == (Release(1, second),)


def test_an_entry_is_not_skipped_for_a_train_whose_entry_before_is_out() -> None:
    """It is skipped when it would be released, not when it is due."""
    first = Entry(at("06:02"), "freight", ("dn_e",))
    second = Entry(at("06:03"), "freight", ("yard_w",))
    state = released(clocked(running(first, second), at("06:02"), 1), 0, "f-1")

    state = clocked(placed(state, frozenset()), at("06:04"), 1)

    assert states(state) == [OUT, HELD]

    state = ended(state, "f-1", CANCELLED)

    assert states(state) == [CANCELLED, SKIPPED]


def test_nothing_is_released_or_skipped_before_the_trains_placed_are_told() -> None:
    entry = Entry(at("06:02"), "freight", ("dn_e",))
    state = State(running(entry).timetable, RUNNING, time=0)

    state = clocked(state, at("06:02"), 1)

    assert due(state) == ()
    assert states(state) == [HELD]
    assert due(placed(state, frozenset({"freight"}))) == (Release(0, entry),)


def test_a_turn_round_waits_while_its_train_has_a_request_in_flight() -> None:
    """Whoever submitted it. The entry after the turn-round leaves at once."""
    turn = Entry(at("06:02"), "freight")
    onward = Entry(at("06:02"), "freight", ("yard_w",))
    state = announced(running(turn, onward), "freight-9", "freight")

    state = clocked(state, at("06:03"), 1)

    assert due(state) == ()
    assert states(state) == [HELD, HELD]

    state = ended(state, "freight-9", COMPLETED)

    assert due(state) == (Release(0, turn),)

    state = turned(state, 0)

    assert state.progress[0] == Progress(ENDED)
    assert due(state) == (Release(1, onward),)


def test_an_entry_with_to_does_not_wait_for_a_persons_request() -> None:
    entry = Entry(at("06:02"), "freight", ("dn_e",))
    state = announced(running(entry), "freight-9", "freight")

    assert due(clocked(state, at("06:02"), 1)) == (Release(0, entry),)


def test_a_turn_round_waits_for_a_request_of_another_entry_of_its_train() -> None:
    """A person's drag recorded after it: the entry is out and later in the
    list."""
    turn = Entry(at("06:02"), "freight")
    dragged = Entry(at("06:01"), "freight", ("dn_e",), dwell=3)
    state = released(clocked(running(dragged, turn), at("06:01"), 1), 0, "f-1")
    state = ended(state, "f-1", COMPLETED)
    recorded = Entry(at("06:03"), "freight", ("up_e",))
    assert state.timetable is not None
    state = replace(
        state,
        timetable=state.timetable.added(recorded),
        progress=(*state.progress, Progress(OUT, "f-2")),
        in_flight={"f-2": "freight"},
    )

    state = clocked(state, at("06:04"), 1)

    assert states(state) == [ENDED, HELD, OUT]
    assert due(state) == ()
    assert due(ended(state, "f-2", REJECTED)) == (Release(1, turn),)


def test_a_clock_set_forward_makes_the_entries_passed_over_due_in_order() -> None:
    first = Entry(at("06:10"), "freight", ("dn_e",))
    express = Entry(at("07:00"), "express", ("up_w",))
    second = Entry(at("07:30"), "freight", ("yard_w",))
    beyond = Entry(at("08:30"), "express", ("yard_e",))
    state = clocked(running(first, express, second, beyond), at("06:05"), 1)

    state = clocked(state, at("08:05"), 1)

    assert state.time == 2 * 3600 + 5 * 60
    assert due(state) == (Release(0, first), Release(1, express))

    state = ended(released(state, 0, "f-1"), "f-1", COMPLETED)

    assert due(state) == (Release(1, express), Release(2, second))


def test_a_clock_set_back_moves_nothing_until_it_passes_where_it_had_been() -> None:
    """So nothing is released twice."""
    first = Entry(at("06:02"), "freight", ("dn_e",))
    second = Entry(at("06:10"), "freight", ("yard_w",))
    state = released(clocked(running(first, second), at("06:02"), 1), 0, "f-1")
    state = clocked(ended(state, "f-1", CANCELLED), at("06:08"), 1)

    for time in (at("05:50"), at("06:02"), at("06:07") + 59):
        state = clocked(state, time, 1)

        assert state.time == 8 * 60
        assert due(state) == ()
        assert states(state) == [CANCELLED, LATER]

    state = clocked(state, at("06:10"), 1)

    assert state.time == 10 * 60
    assert due(state) == (Release(1, second),)


def test_a_clock_set_12_hours_or_more_forward_reads_as_a_set_back() -> None:
    entry = Entry(at("09:00"), "freight", ("dn_e",))
    state = clocked(running(entry), at("06:08"), 1)

    assert clocked(state, at("18:08"), 1).time == 8 * 60
    assert due(clocked(state, at("19:00"), 1)) == ()
    assert clocked(state, at("18:07"), 1).time == 12 * 3600 + 7 * 60


def test_a_timetable_is_over_24_hours_after_its_start_and_releases_no_more() -> None:
    first = Entry(at("06:02"), "freight", ("dn_e",))
    last = Entry(at("05:58"), "express", ("up_w",))
    state = running(first, last)
    for time in (at("17:00"), at("04:00"), at("05:59")):
        state = clocked(state, time, 60)

    assert state.phase == RUNNING
    assert due(state) == (Release(0, first), Release(1, last))

    state = clocked(state, at("06:00"), 60)

    assert state.phase == OVER
    assert due(state) == ()
    assert states(state) == [HELD, HELD]
    assert due(clocked(state, at("06:05"), 60)) == ()


def test_a_timetable_whose_entries_have_all_ended_is_still_running() -> None:
    entry = Entry(at("06:02"), "freight", ("dn_e",))
    state = released(clocked(running(entry), at("06:02"), 1), 0, "f-1")

    state = clocked(ended(state, "f-1", COMPLETED), at("09:00"), 1)

    assert state.phase == RUNNING


def test_a_loaded_timetable_starts_when_its_requests_to_start_blocks_have_ended() -> (
    None
):
    """However they ended, and only with power on."""
    state = powered(loaded(positioning=("f-8", "f-9")), "on")

    state = ended(state, "f-8", COMPLETED)

    assert state.positioning == ("f-9",)
    assert not starts(state)

    state = ended(state, "f-9", REJECTED)

    assert state.positioning == ()
    assert starts(state)


@pytest.mark.parametrize("reads", ["off", "draining"])
def test_a_loaded_timetable_does_not_start_until_power_reads_on(reads: str) -> None:
    state = powered(loaded(), reads)

    assert not starts(state)
    assert starts(powered(state, "on"))


def test_a_loaded_timetable_starts_when_a_person_asks() -> None:
    """With a request to a start block still out and power off."""
    state = loaded(positioning=("f-9",))

    assert not starts(state)
    assert starts(state, asked=True)

    state = started(state)

    assert state.phase == RUNNING
    assert state.positioning == ("f-9",)
    assert ended(state, "f-9", COMPLETED).positioning == ()


def test_only_a_loaded_timetable_starts() -> None:
    entry = Entry(at("06:02"), "freight", ("dn_e",))
    over = replace(running(entry), phase=OVER)

    for state in (State(power="on"), running(entry), over):
        assert not starts(state)
        assert not starts(state, asked=True)


def test_a_loaded_timetable_releases_nothing_and_its_entries_read_later() -> None:
    entry = Entry(at("06:00"), "freight", ("dn_e",))
    state = clocked(powered(loaded(entry, positioning=("f-9",)), "on"), at("09:30"), 1)

    assert due(state) == ()
    assert states(state) == [LATER]


def test_after_a_start_the_run_begins_at_the_row_that_reads_the_start_time() -> None:
    """A row said before the clock was set reads the old time and moves
    nothing. An entry at the start time is due at the start."""
    first = Entry(at("06:00"), "freight", ("dn_e",))
    second = Entry(at("06:02"), "express", ("up_w",))
    state = clocked(powered(loaded(first, second), "on"), at("09:30"), 1)

    state = started(state)

    assert state.time == 0
    assert due(state) == (Release(0, first),)

    state = clocked(state, at("09:30") + 1, 1)

    assert state.time == 0
    assert due(state) == (Release(0, first),)

    state = clocked(clocked(state, at("06:00"), 1), at("06:02"), 1)

    assert state.time == 2 * 60
    assert due(state) == (Release(0, first), Release(1, second))


@pytest.mark.parametrize(
    ("past", "speed_up", "time"), [(2, 1, 2), (3, 1, 0), (120, 60, 120), (121, 60, 0)]
)
def test_after_a_start_a_row_up_to_two_beats_past_the_start_time_begins_the_run(
    past: int, speed_up: float, time: int
) -> None:
    state = started(powered(loaded(), "on"))

    assert clocked(state, at("06:00") + past, speed_up).time == time


def every_state() -> State:
    """A timetable 20 minutes into its run with an entry in each of the seven
    states. `local` is off the layout, and a person started it with the
    request that takes `local` to its start block still out."""
    timetable = Timetable(
        "evening",
        "crossover-yard",
        at("06:00"),
        {"freight": TrainStart("yard_w", "A-to-B")},
        (
            Entry(at("06:01"), "freight", ("dn_e", "up_e"), 2, "meets the express"),
            Entry(at("06:02"), "express", ("up_w",)),
            Entry(at("06:03"), "express", ("yard_e.A",)),
            Entry(at("06:04"), "local", ("dn_w",)),
            Entry(at("06:05"), "freight"),
            Entry(at("06:06"), "freight", ("yard_w.B",)),
            Entry(at("06:07"), "freight", ("dn_e",)),
            Entry(at("06:30"), "express", ("up_e",)),
        ),
    )
    return State(
        timetable,
        RUNNING,
        record=True,
        time=20 * 60,
        positioning=("local-ab-1",),
        progress=(
            Progress(ENDED, "freight-ab-1", 5 * 60),
            Progress(REJECTED, "express-ab-1"),
            Progress(CANCELLED, "express-ab-2"),
            Progress(SKIPPED),
            Progress(ENDED),
            Progress(OUT, "freight-ab-2"),
            Progress(),
            Progress(),
        ),
        power="on",
        placed=frozenset({"freight", "express"}),
        in_flight={"local-ab-1": "local", "freight-ab-2": "freight"},
    )


def test_the_state_row_has_the_timetable_and_each_entrys_state() -> None:
    """The fields #1345 lists under "The bus". `request` is on an entry that
    went out as a request, and `ended` on one that ended by arrival."""
    said = row(every_state())

    assert said == {
        "timetable": "evening",
        "phase": "running",
        "record": True,
        "start": "06:00",
        "trains": {"freight": {"at": "yard_w", "facing": "A-to-B"}},
        "positioning": ["local-ab-1"],
        "entries": [
            {
                "at": "06:01",
                "train": "freight",
                "to": ["dn_e", "up_e"],
                "dwell": 2,
                "description": "meets the express",
                "state": "ended",
                "request": "freight-ab-1",
                "ended": 300,
            },
            {
                "at": "06:02",
                "train": "express",
                "to": ["up_w"],
                "state": "rejected",
                "request": "express-ab-1",
            },
            {
                "at": "06:03",
                "train": "express",
                "to": ["yard_e.A"],
                "state": "cancelled",
                "request": "express-ab-2",
            },
            {"at": "06:04", "train": "local", "to": ["dn_w"], "state": "skipped"},
            {"at": "06:05", "train": "freight", "turn": True, "state": "ended"},
            {
                "at": "06:06",
                "train": "freight",
                "to": ["yard_w.B"],
                "state": "out",
                "request": "freight-ab-2",
            },
            {"at": "06:07", "train": "freight", "to": ["dn_e"], "state": "held"},
            {"at": "06:30", "train": "express", "to": ["up_e"], "state": "later"},
        ],
    }
    assert json.loads(json.dumps(said)) == said


def test_the_state_row_with_no_timetable_loaded_has_the_name_null_alone() -> None:
    """The state keeps what it is told for the timetable loaded next."""
    state = clocked(powered(State(), "on"), at("06:00") + 30, 1)
    state = announced(placed(state, frozenset({"freight"})), "freight-9", "freight")

    assert row(state) == {"timetable": None}
    assert due(state) == ()
    assert not starts(state)
    assert (state.clock, state.power) == (at("06:00") + 30, "on")
    assert state.placed == {"freight"}
    assert ended(state, "freight-9", COMPLETED).in_flight == {}


def test_a_state_takes_one_progress_for_each_entry() -> None:
    timetable = running(Entry(at("06:02"), "freight", ("dn_e",))).timetable

    with pytest.raises(ValueError, match="2 for 1 entries"):
        State(timetable, RUNNING, progress=(Progress(), Progress()))


def test_a_restart_releases_nothing_the_row_says_has_gone_out() -> None:
    """The state is built from the row and the document, and takes how far
    the timetable has run from the first clock row."""
    before = every_state()
    assert before.timetable is not None

    state = restarted(json.loads(json.dumps(row(before))), before.timetable)

    assert state is not None
    assert state.timetable == before.timetable
    assert (state.phase, state.record, state.time) == (RUNNING, True, None)
    assert state.positioning == ("local-ab-1",)
    assert state.progress[:6] == before.progress[:6]
    assert states(state)[6:] == [LATER, LATER]

    state = placed(state, frozenset({"freight", "express"}))
    state = clocked(state, at("06:29"), 1)

    assert state.time == 29 * 60
    assert states(state) == states(before)
    assert due(state) == ()
    assert due(clocked(state, at("06:30"), 1)) == (
        Release(7, before.timetable.entries[7]),
    )


def test_a_restart_takes_the_time_from_the_clock_within_the_day() -> None:
    before = running(Entry(at("05:58"), "freight", ("dn_e",)))
    assert before.timetable is not None
    state = restarted(row(before), before.timetable)
    assert state is not None

    state = clocked(state, at("05:59") + 30, 1)

    assert state.time == 24 * 3600 - 30


def test_a_restart_keeps_the_rows_entries_where_the_documents_differ() -> None:
    """And the document's railroad, which the row does not say."""
    before = every_state()
    assert before.timetable is not None
    document = Timetable("evening", "crossover-yard", at("07:00"), {}, ())

    state = restarted(row(before), document)

    assert state is not None
    assert state.timetable == before.timetable


def test_a_restart_puts_a_rows_entries_in_order_with_their_progress() -> None:
    before = every_state()
    assert before.timetable is not None
    said = row(before)
    said["entries"].reverse()

    state = restarted(said, before.timetable)

    assert state is not None
    assert state.timetable == before.timetable
    assert state.progress[:6] == before.progress[:6]


def test_a_restart_from_a_row_that_is_over_stays_over() -> None:
    before = replace(every_state(), phase=OVER)
    assert before.timetable is not None

    state = restarted(row(before), before.timetable)

    assert state is not None
    state = clocked(placed(state, frozenset({"express"})), at("06:30"), 1)
    assert state.phase == OVER
    assert due(state) == ()


def _with(**fields: object) -> dict[str, Any]:
    return row(every_state()) | fields


def _without(field: str) -> dict[str, Any]:
    said = row(every_state())
    del said[field]
    return said


def _with_entry(**fields: object) -> dict[str, Any]:
    said = row(every_state())
    said["entries"][0] |= fields
    return said


@pytest.mark.parametrize(
    "said",
    [
        None,
        "evening",
        {"timetable": None},
        _with(timetable="morning"),
        _with(phase="paused"),
        _with(record="yes"),
        _with(start=360),
        _with(trains=[]),
        _with(positioning="local-ab-1"),
        _with(positioning=[7]),
        _with(entries={}),
        _with(entries=["06:01"]),
        _without("phase"),
        _without("entries"),
        _with_entry(state="late"),
        _with_entry(request=7),
        _with_entry(ended="06:05"),
        _with_entry(ended=True),
        _with_entry(at="6:01"),
        _with_entry(turn=True),
    ],
)
def test_a_row_that_cannot_be_read_restarts_no_timetable(said: object) -> None:
    document = every_state().timetable
    assert document is not None

    assert restarted(said, document) is None
