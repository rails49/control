"""Each invariant of `tc49.lib.invariants` over literal rows: one view where it
holds and one where it is breached, on a railroad of the library; and each
history invariant over a literal message sequence, one where it holds and one
where it is breached (ADR-0096)."""

from collections.abc import Callable
from typing import Any

import pytest

from tc49.lib.bus import Payload
from tc49.lib.invariants import (
    ALLOCATION,
    ASPECTS,
    BLOCK_OCCUPIED,
    BLOCK_VACATED,
    CANCEL_WANTED,
    DISPUTED,
    FACING,
    HISTORY_INVARIANTS,
    INVARIANTS,
    LOCK_RELEASED,
    MOVE_GRANTED,
    MOVING,
    POWER,
    POWER_WANTED,
    QUIET,
    REQUEST_CANCELLED,
    ROUTE_CHOSEN,
    TRAIN_PLACED,
    UNFIT,
    Record,
    View,
    adr_0001_pass_through,
    adr_0002_route_is_fixed,
    adr_0006_no_conflicting_transits,
    adr_0007_route_ends_at_an_arrival,
    adr_0019_facing_turns_on_a_move,
    adr_0019_terminal_facing,
    adr_0025_grant_shows_its_aspect,
    adr_0026_two_blocks_ahead,
    adr_0029_block_with_its_transit,
    adr_0039_unplaced_has_no_facing,
    adr_0047_no_grant_while_crossing,
    adr_0048_disputed_lists_contradictions,
    adr_0048_unexplained_drains,
    adr_0049_no_grant_after_cancel,
    adr_0049_placed_has_no_request,
    adr_0062_drain_ends_at_a_stand,
    adr_0062_moving_while_crossing,
    adr_0071_placed_where_it_fits,
    adr_0071_unfit_is_not_placed,
    adr_0076_crossing_is_placed,
    adr_0076_placed_holds_its_block,
    adr_0077_move_ends_on_both_readings,
    adr_0077_not_into_occupied,
    adr_0077_placement_releases_its_own,
    adr_0078_nothing_commits_without_power,
    adr_0080_after_follows,
    adr_0080_listed_by_priority,
    adr_0080_placed_into_a_free_block,
    adr_0093_aspects_along_the_locks,
    adr_0093_stop_without_power,
    cross_app,
)
from tests.generate import LAYOUTS, ROSTERS

MEET = "single-track-meet"
YARD = "crossover-yard"

# single-track-meet, terminal to terminal across the loop: west_1, w_main,
# loop_up, e_main, east_1, arriving by east_1.A.
ROUTE = [
    "west_1",
    "west_throat.from_1",
    "w_main",
    "west_switch.to_up",
    "loop_up",
    "east_switch.from_up",
    "e_main",
    "east_throat.to_1",
    "east_1",
]

Rows = dict[str, Payload]


def allocation(
    trains: dict[str, str] | None = None,
    crossing: dict[str, str] | None = None,
    locks: dict[str, str] | None = None,
    requests: list[dict[str, Any]] | None = None,
) -> Payload:
    return {
        "trains": trains or {},
        "crossing": crossing or {},
        "locks": locks or {},
        "requests": requests or [],
    }


def request(
    rid: str = "r1",
    train: str = "t1",
    route: list[str] | None = None,
    dest: list[str] | None = None,
    after: str | None = None,
) -> dict[str, Any]:
    return {
        "id": rid,
        "train": train,
        "depart": None if after else "west_1.B",
        "dest": dest or ["east_1.A"],
        **({} if after is None else {"after": after}),
        **({} if route is None else {"route": route}),
    }


def started(
    locks: dict[str, str],
    route: list[str] | None = None,
    dest: list[str] | None = None,
) -> Rows:
    """t1 in west_1 on ROUTE, or `route`, holding `locks`."""
    return {
        ALLOCATION: allocation(
            {"t1": "west_1"},
            locks=locks,
            requests=[request(route=route or ROUTE, dest=dest)],
        )
    }


AHEAD_TWO = {
    "west_1": "t1",
    "west_throat.from_1": "t1",
    "w_main": "t1",
    "west_switch.to_up": "t1",
    "loop_up": "t1",
}

CASES: list[tuple[Callable[[View], list[str]], str, Rows, Rows]] = [
    (
        adr_0001_pass_through,
        MEET,
        started(AHEAD_TWO),
        # Into w_main by A and back out by A, to west_2.
        started(
            AHEAD_TWO,
            route=["west_1", "west_throat.from_1", "w_main", "west_throat.from_2"]
            + ["west_2"],
        ),
    ),
    (
        adr_0006_no_conflicting_transits,
        YARD,
        # `dn_straight` and `up_straight` are listed concurrent.
        {
            ALLOCATION: allocation(
                locks={"crossover.dn_straight": "a", "crossover.up_straight": "b"}
            )
        },
        {
            ALLOCATION: allocation(
                locks={"crossover.dn_straight": "a", "crossover.dn_to_up": "b"}
            )
        },
    ),
    (
        adr_0007_route_ends_at_an_arrival,
        MEET,
        started(AHEAD_TWO),
        started(AHEAD_TWO, dest=["east_2.A", "east_1.B"]),
    ),
    (
        adr_0019_terminal_facing,
        MEET,
        {
            ALLOCATION: allocation({"t1": "west_1"}),
            FACING: {"facing": {"t1": "west_1.A-to-B"}},
        },
        {
            ALLOCATION: allocation({"t1": "west_1"}),
            FACING: {"facing": {"t1": "west_1.B-to-A"}},
        },
    ),
    (
        adr_0026_two_blocks_ahead,
        MEET,
        started(AHEAD_TWO),
        started(AHEAD_TWO | {"east_switch.from_up": "t1", "e_main": "t1"}),
    ),
    (
        adr_0029_block_with_its_transit,
        MEET,
        started(AHEAD_TWO),
        started({k: v for k, v in AHEAD_TWO.items() if k != "west_switch.to_up"}),
    ),
    (
        adr_0039_unplaced_has_no_facing,
        MEET,
        {
            ALLOCATION: allocation({"t1": "w_main"}),
            FACING: {"facing": {"t1": "w_main.A-to-B"}},
        },
        {ALLOCATION: allocation(), FACING: {"facing": {"t1": "w_main.A-to-B"}}},
    ),
    (
        adr_0062_moving_while_crossing,
        MEET,
        {
            ALLOCATION: allocation(
                {"t1": "west_1"}, crossing={"t1": "west_throat.from_1"}
            ),
            MOVING: {"moving": True},
        },
        {ALLOCATION: allocation({"t1": "west_1"}), MOVING: {"moving": True}},
    ),
    (
        adr_0071_placed_where_it_fits,
        MEET,
        # t1 is 1200 long, `blocker` 1000; east_2 is 1200.
        {ALLOCATION: allocation({"t1": "east_2", "blocker": "west_2"})},
        {ALLOCATION: allocation({"t1": "east_2", "blocker": "nowhere"})},
    ),
    (
        adr_0071_unfit_is_not_placed,
        MEET,
        {
            ALLOCATION: allocation({"t1": "w_main"}),
            UNFIT: {"trains": [{"train": "t2", "block": "gone", "why": "gone"}]},
        },
        {
            ALLOCATION: allocation({"t2": "w_main"}),
            UNFIT: {"trains": [{"train": "t2", "block": "gone", "why": "gone"}]},
        },
    ),
    (
        adr_0076_placed_holds_its_block,
        MEET,
        {ALLOCATION: allocation({"t1": "w_main"}, locks={"w_main": "t1"})},
        {ALLOCATION: allocation({"t1": "w_main"}, locks={"w_main": "t2"})},
    ),
    (
        adr_0076_crossing_is_placed,
        MEET,
        {
            ALLOCATION: allocation(
                {"t1": "west_1"}, crossing={"t1": "west_throat.from_1"}
            )
        },
        {ALLOCATION: allocation(crossing={"t1": "west_throat.from_1"})},
    ),
    (
        adr_0080_after_follows,
        MEET,
        {ALLOCATION: allocation(requests=[request("r1"), request("r2", after="r1")])},
        {ALLOCATION: allocation(requests=[request("r2", after="r1"), request("r1")])},
    ),
    (
        adr_0093_aspects_along_the_locks,
        MEET,
        # Two ahead from west_1, one from w_main, none from loop_up.
        started(AHEAD_TWO)
        | {
            POWER: {"power": "on"},
            ASPECTS: {"aspects": {"west_1.B": "clear", "w_main.B": "caution"}},
        },
        started(AHEAD_TWO)
        | {
            POWER: {"power": "on"},
            ASPECTS: {"aspects": {"west_1.B": "clear", "w_main.B": "clear"}},
        },
    ),
    (
        adr_0093_stop_without_power,
        MEET,
        {
            POWER: {"power": "draining"},
            ASPECTS: {"aspects": {"west_1.B": "stop", "w_main.B": "stop"}},
        },
        {
            POWER: {"power": "off"},
            ASPECTS: {"aspects": {"west_1.B": "clear", "w_main.B": "stop"}},
        },
    ),
]


def view(layout_id: str, rows: Rows) -> View:
    return View(rows, LAYOUTS[layout_id], ROSTERS[layout_id])


@pytest.mark.parametrize(
    "breaches, layout_id, holds, breached",
    CASES,
    ids=[case[0].__name__ for case in CASES],
)
def test_an_invariant_holds_and_is_breached(
    breaches: Callable[[View], list[str]], layout_id: str, holds: Rows, breached: Rows
) -> None:
    assert breaches(view(layout_id, holds)) == []
    assert len(breaches(view(layout_id, breached))) == 1


def test_every_invariant_has_its_cases() -> None:
    assert [invariant.breaches for invariant in INVARIANTS] == [
        case[0] for case in CASES
    ]


def test_each_function_is_named_for_its_adr() -> None:
    for invariant in INVARIANTS:
        assert invariant.breaches.__name__.startswith(f"adr_{invariant.adr}_")


def test_an_unreadable_row_breaks_no_reader() -> None:
    rows: Rows = {
        topic: {"trains": 7, "locks": "x", "requests": [None, {"route": 3}]}
        for topic in (ALLOCATION, ASPECTS, FACING, MOVING, POWER, UNFIT)
    }
    for invariant in INVARIANTS:
        invariant.breaches(view(MEET, rows))


def test_an_invariant_over_one_apps_topics_is_not_cross_app() -> None:
    by_name = {invariant.breaches.__name__: invariant for invariant in INVARIANTS}
    assert not cross_app(by_name["adr_0076_placed_holds_its_block"])
    assert not cross_app(by_name["adr_0062_moving_while_crossing"])
    assert cross_app(by_name["adr_0039_unplaced_has_no_facing"])
    assert cross_app(by_name["adr_0093_stop_without_power"])


# -- the history invariants ---------------------------------------------------

Messages = list[tuple[str, Payload]]
Breaches = Callable[[Record, View, str, Payload], list[str]]

ON: Rows = {POWER: {"power": "on"}}
PLACED: Rows = {ALLOCATION: allocation({"t1": "west_1"}, locks={"west_1": "t1"})}
GRANT: tuple[str, Payload] = (
    MOVE_GRANTED,
    {
        "id": "r1",
        "train": "t1",
        "transit": "west_throat.from_1",
        "into": "w_main",
        "aspect": "caution",
    },
)
ONWARD: tuple[str, Payload] = (
    MOVE_GRANTED,
    {
        "id": "r1",
        "train": "t1",
        "transit": "west_switch.to_up",
        "into": "loop_up",
        "aspect": "caution",
    },
)
LEFT: tuple[str, Payload] = (
    LOCK_RELEASED,
    {"train": "t1", "resources": ["west_1", "west_throat.from_1"]},
)
CHOSEN: tuple[str, Payload] = (ROUTE_CHOSEN, {"id": "r1", "route": ROUTE})


def read(block: str, occupied: bool = True) -> tuple[str, Payload]:
    return (BLOCK_OCCUPIED if occupied else BLOCK_VACATED, {"block": block})


def placed(train: str, block: str) -> tuple[str, Payload]:
    return (TRAIN_PLACED, {"train": train, "block": block})


HISTORY_CASES: list[tuple[Breaches, str, Rows, Messages, Messages]] = [
    (
        adr_0002_route_is_fixed,
        MEET,
        {},
        [CHOSEN, (ALLOCATION, allocation(requests=[request(route=ROUTE)]))],
        [CHOSEN, (ALLOCATION, allocation(requests=[request(route=ROUTE[:3])]))],
    ),
    (
        adr_0019_facing_turns_on_a_move,
        MEET,
        {FACING: {"facing": {"t1": "west_1.A-to-B"}}},
        [GRANT, (FACING, {"facing": {"t1": "w_main.A-to-B"}})],
        [CHOSEN, (FACING, {"facing": {"t1": "w_main.A-to-B"}})],
    ),
    (
        adr_0025_grant_shows_its_aspect,
        MEET,
        ON,
        [GRANT, (ASPECTS, {"aspects": {"west_1.B": "caution"}})],
        [GRANT, (ASPECTS, {"aspects": {"west_1.B": "clear"}})],
    ),
    (
        adr_0047_no_grant_while_crossing,
        MEET,
        PLACED,
        [GRANT, LEFT, ONWARD],
        [GRANT, ONWARD],
    ),
    (
        adr_0048_unexplained_drains,
        MEET,
        ON | PLACED,
        [read("loop_up"), (POWER_WANTED, {"power": "draining"})],
        [read("loop_up")],
    ),
    (
        adr_0048_disputed_lists_contradictions,
        MEET,
        {POWER: {"power": "off"}, DISPUTED: {"trains": [], "blocks": []}} | PLACED,
        [
            read("west_1", False),
            read("loop_up"),
            (DISPUTED, {"trains": ["t1"], "blocks": ["loop_up"]}),
        ],
        [read("west_1", False), read("loop_up")],
    ),
    (
        adr_0049_placed_has_no_request,
        MEET,
        {ALLOCATION: allocation({"t1": "west_1"}, requests=[request()])},
        [
            (REQUEST_CANCELLED, {"id": "r1", "reason": "displaced"}),
            placed("t1", "w_main"),
        ],
        [placed("t1", "w_main")],
    ),
    (
        adr_0049_no_grant_after_cancel,
        MEET,
        PLACED,
        [GRANT, LEFT, ONWARD, (CANCEL_WANTED, {"id": "r1"})],
        [GRANT, (CANCEL_WANTED, {"id": "r1"}), LEFT, ONWARD],
    ),
    (
        adr_0062_drain_ends_at_a_stand,
        MEET,
        {POWER: {"power": "draining"}, MOVING: {"moving": True}},
        [(MOVING, {"moving": False}), (POWER, {"power": "off"})],
        [(POWER, {"power": "off"})],
    ),
    (
        adr_0077_not_into_occupied,
        MEET,
        PLACED,
        [GRANT],
        [read("w_main"), GRANT],
    ),
    (
        adr_0077_move_ends_on_both_readings,
        MEET,
        PLACED,
        # In the other order from the usual one: a short train.
        [GRANT, read("west_1", False), read("w_main"), LEFT],
        [GRANT, read("w_main"), LEFT],
    ),
    (
        adr_0077_placement_releases_its_own,
        MEET,
        # A broken table: t1 stands in a block t2 holds.
        {ALLOCATION: allocation({"t1": "west_1"}, locks={"west_1": "t2"})},
        [
            placed("t1", "w_main"),
            (
                ALLOCATION,
                allocation({"t1": "w_main"}, locks={"west_1": "t2", "w_main": "t1"}),
            ),
        ],
        [
            placed("t1", "w_main"),
            (ALLOCATION, allocation({"t1": "w_main"}, locks={"w_main": "t1"})),
        ],
    ),
    (
        adr_0078_nothing_commits_without_power,
        MEET,
        {POWER: {"power": "off"}} | PLACED,
        [(POWER, {"power": "on"}), GRANT],
        [GRANT],
    ),
    (
        adr_0080_listed_by_priority,
        MEET,
        # Every train of the library roster has the same priority.
        {ALLOCATION: allocation(requests=[request("r1")])},
        [
            (
                ALLOCATION,
                allocation(requests=[request("r1"), request("r2", train="t2")]),
            )
        ],
        [
            (
                ALLOCATION,
                allocation(requests=[request("r2", train="t2"), request("r1")]),
            )
        ],
    ),
    (
        adr_0080_placed_into_a_free_block,
        MEET,
        {
            ALLOCATION: allocation(
                {"t1": "west_1", "t2": "east_1"},
                locks={"west_1": "t1", "east_1": "t2"},
            )
        },
        [placed("t1", "w_main")],
        [placed("t1", "east_1")],
    ),
]


def breaches_over(
    breaches: Breaches, layout_id: str, rows: Rows, messages: Messages
) -> list[str]:
    """What `breaches` finds over `messages` from `rows`, as the helper runs
    it: each message before the record observes it, then `QUIET`."""
    record = Record(LAYOUTS[layout_id], rows)
    found: list[str] = []
    for topic, payload in [*messages, (QUIET, {})]:
        found += breaches(record, view(layout_id, record.rows), topic, payload)
        record.observe(topic, payload)
    return found


@pytest.mark.parametrize(
    "breaches, layout_id, rows, holds, breached",
    HISTORY_CASES,
    ids=[case[0].__name__ for case in HISTORY_CASES],
)
def test_a_history_invariant_holds_and_is_breached(
    breaches: Breaches, layout_id: str, rows: Rows, holds: Messages, breached: Messages
) -> None:
    assert breaches_over(breaches, layout_id, rows, holds) == []
    assert len(breaches_over(breaches, layout_id, rows, breached)) == 1


def test_every_history_invariant_has_its_cases() -> None:
    assert [invariant.breaches for invariant in HISTORY_INVARIANTS] == [
        case[0] for case in HISTORY_CASES
    ]


def test_each_history_function_is_named_for_its_adr() -> None:
    for invariant in HISTORY_INVARIANTS:
        assert invariant.breaches.__name__.startswith(f"adr_{invariant.adr}_")


def test_an_unreadable_message_breaks_no_history_reader() -> None:
    junk: list[Payload] = [
        {"trains": 7, "locks": "x", "requests": [None, {"route": 3}]},
        {"id": 3, "train": None, "resources": "x", "block": 4, "route": 5},
    ]
    topics = {topic for invariant in HISTORY_INVARIANTS for topic in invariant.reads}
    for invariant in HISTORY_INVARIANTS:
        for payload in junk:
            breaches_over(
                invariant.breaches,
                MEET,
                {topic: payload for topic in topics if "/state/" in topic},
                [(topic, payload) for topic in sorted(topics)],
            )


def test_which_history_invariants_are_cross_app() -> None:
    by_name = {
        invariant.breaches.__name__: invariant for invariant in HISTORY_INVARIANTS
    }
    assert not cross_app(by_name["adr_0002_route_is_fixed"])
    assert not cross_app(by_name["adr_0080_placed_into_a_free_block"])
    assert cross_app(by_name["adr_0048_unexplained_drains"])
    assert cross_app(by_name["adr_0019_facing_turns_on_a_move"])
