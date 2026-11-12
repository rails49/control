"""Each invariant of `tc49.lib.invariants` over literal rows: one view where it
holds and one where it is breached, on a railroad of the library; and each
history invariant over a literal message sequence, one where it holds and one
where it is breached (ADR-0096). The rules over `layout`'s rows run on the
bench railroad of `tests/layout/railroad.py`, which has points and addressed
locomotives where the library's railroads have neither."""

from collections.abc import Callable
from typing import Any, cast

import pytest

from tc49.lib.bus import Payload
from tc49.lib.invariants import (
    ALIGN,
    ALLOCATION,
    ASPECTS,
    CANCEL_WANTED,
    DEVICE_LINK,
    DEVICE_TRACK,
    DISPUTED,
    DRIVING,
    FACING,
    HISTORY_INVARIANTS,
    INVARIANTS,
    LOCK_RELEASED,
    MOVE,
    MOVE_GRANTED,
    MOVING,
    OVERDUE,
    PLACEMENT_WANTED,
    POWER,
    POWER_WANTED,
    QUIET,
    RAILROAD,
    REQUEST_CANCELLED,
    REQUEST_COMPLETED,
    ROUTE_CHOSEN,
    TAKEN,
    TRAIN_PLACED,
    TRAIN_REMOVED,
    UNFIT,
    UNKNOWN_SENSORS,
    WANTED_POINT,
    WANTED_TRACK,
    WANTED_TRACTION,
    Record,
    View,
    adr_0001_pass_through,
    adr_0002_route_is_fixed,
    adr_0006_no_conflicting_transits,
    adr_0007_route_ends_at_an_arrival,
    adr_0019_facing_turns_on_a_move,
    adr_0019_terminal_facing,
    adr_0022_points_set_for_the_crossing,
    adr_0025_grant_shows_its_aspect,
    adr_0025_move_at_the_aspects_speed,
    adr_0026_two_blocks_ahead,
    adr_0029_block_with_its_transit,
    adr_0031_no_traction_before_align,
    adr_0039_unplaced_has_no_facing,
    adr_0047_no_grant_while_crossing,
    adr_0047_traction_from_the_near_end,
    adr_0048_disputed_lists_contradictions,
    adr_0049_no_grant_after_cancel,
    adr_0049_placed_has_no_request,
    adr_0052_no_traction_without_facing,
    adr_0052_sign_composed,
    adr_0054_traction_zeroed_at_start,
    adr_0060_new_railroad_only_while_off,
    adr_0062_drain_ends_at_a_stand,
    adr_0062_moving_to_the_tail,
    adr_0062_moving_while_crossing,
    adr_0063_power_follows_the_hardware,
    adr_0069_removed_is_stopped,
    adr_0071_placed_where_it_fits,
    adr_0071_unfit_is_not_placed,
    adr_0074_comes_up_off,
    adr_0076_crossing_is_placed,
    adr_0076_occupied_is_locked,
    adr_0076_placed_holds_its_block,
    adr_0077_not_into_occupied,
    adr_0077_placement_releases_its_own,
    adr_0077_released_on_the_tail,
    adr_0078_cut_leaves_the_railroad_at_rest,
    adr_0078_nothing_commits_without_power,
    adr_0079_holder_changes_by_release,
    adr_0079_manual_untaken_stands,
    adr_0080_after_follows,
    adr_0080_listed_by_priority,
    adr_0080_placed_into_a_free_block,
    adr_0081_arrival_stops_the_train,
    adr_0081_release_in_automatic,
    adr_0084_sign_changes_through_zero,
    adr_0089_one_train_a_throttle,
    adr_0093_aspects_along_the_locks,
    adr_0093_stop_without_power,
    adr_0097_no_departure_before_the_report,
    cross_app,
)
from tests.generate import LAYOUTS, ROSTERS
from tests.layout.railroad import railroad, stock

MEET = "single-track-meet"
YARD = "crossover-yard"
BENCH = "bench"

RAILROADS = {**LAYOUTS, BENCH: railroad()}
STOCK = {**ROSTERS, BENCH: stock()}

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


def traction(addr: str) -> str:
    return f"{WANTED_TRACTION}/{addr}"


def point(addr: str) -> str:
    return f"{WANTED_POINT}/{addr}"


# The bench railroad: `single`, one locomotive on address 3, standing in up_w
# and crossing to dn_e over `crossover.to_dn`, which throws points 12 and 13.
CROSSING: Rows = {
    ALLOCATION: allocation(
        {"single": "up_w"},
        crossing={"single": "crossover.to_dn"},
        locks={"up_w": "single", "crossover.to_dn": "single", "dn_e": "single"},
    )
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
        adr_0022_points_set_for_the_crossing,
        BENCH,
        CROSSING
        | {
            point("12"): {"addr": "12", "position": "thrown"},
            point("13"): {"addr": "13", "position": "thrown"},
        },
        CROSSING
        | {
            point("12"): {"addr": "12", "position": "thrown"},
            point("13"): {"addr": "13", "position": "closed"},
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
        {
            ALLOCATION: allocation(
                {"t1": "west_1"}, crossing={"t1": "west_throat.from_1"}
            ),
            MOVING: {"moving": False},
        },
    ),
    (
        adr_0063_power_follows_the_hardware,
        BENCH,
        {
            POWER: {"power": "on"},
            DEVICE_TRACK: {"power": "on"},
            f"{DEVICE_LINK}/dccex": {"id": "dccex", "link": "up"},
        },
        {
            POWER: {"power": "on"},
            DEVICE_TRACK: {"power": "on"},
            f"{DEVICE_LINK}/dccex": {"id": "dccex", "link": "down"},
        },
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
        adr_0076_occupied_is_locked,
        MEET,
        {
            ALLOCATION: {
                **allocation({"t1": "w_main"}, locks={"w_main": "t1"}),
                "occupied": {"t1": ["w_main"]},
            }
        },
        {
            ALLOCATION: {
                **allocation({"t1": "w_main"}, locks={"w_main": "t1"}),
                "occupied": {"t1": ["w_main", "loop_up"]},
            }
        },
    ),
    (
        adr_0080_after_follows,
        MEET,
        {ALLOCATION: allocation(requests=[request("r1"), request("r2", after="r1")])},
        {ALLOCATION: allocation(requests=[request("r2", after="r1"), request("r1")])},
    ),
    (
        adr_0089_one_train_a_throttle,
        BENCH,
        {TAKEN: {"taken": {"single": "t-1", "topped": "t-2"}}},
        {TAKEN: {"taken": {"single": "t-1", "topped": "t-1"}}},
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
    return View(rows, RAILROADS[layout_id], STOCK[layout_id])


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
    topics = (ALLOCATION, ASPECTS, FACING, MOVING, POWER, UNFIT, DRIVING, TAKEN)
    rows: Rows = {
        topic: {"trains": 7, "locks": "x", "requests": [None, {"route": 3}]}
        for topic in (*topics, DEVICE_TRACK, f"{DEVICE_LINK}/x", traction("3"))
    }
    for invariant in INVARIANTS:
        invariant.breaches(view(MEET, rows))
        invariant.breaches(view(BENCH, rows))


def test_a_crossing_with_both_sensors_unknown_is_not_moving() -> None:
    """`layout` stopped it, so the row reads false with the crossing still on
    the picture. Only with both sensors listed, and only for a move a route says
    (#1152, #1171)."""
    rows = started({"west_1": "t1", "west_throat.from_1": "t1", "w_main": "t1"}) | {
        MOVING: {"moving": False}
    }
    rows[ALLOCATION] = {**rows[ALLOCATION], "crossing": {"t1": "west_throat.from_1"}}
    listed = {
        UNKNOWN_SENSORS: {"sensors": [{"sensor": "w_main.A"}, {"sensor": "w_main.B"}]}
    }
    entry = {UNKNOWN_SENSORS: {"sensors": [{"sensor": "w_main.A"}]}}
    far = {UNKNOWN_SENSORS: {"sensors": [{"sensor": "w_main.B"}]}}

    assert adr_0062_moving_while_crossing(view(MEET, rows | listed)) == []
    assert adr_0062_moving_while_crossing(view(MEET, rows | entry))
    assert adr_0062_moving_while_crossing(view(MEET, rows | far))
    assert adr_0062_moving_while_crossing(view(MEET, rows))


def test_a_crossing_train_listed_overdue_is_not_moving() -> None:
    """`layout` stopped it for not arriving within the allowance, and only a
    person can end its move (#1191)."""
    rows = started({"west_1": "t1", "west_throat.from_1": "t1", "w_main": "t1"}) | {
        MOVING: {"moving": False}
    }
    rows[ALLOCATION] = {**rows[ALLOCATION], "crossing": {"t1": "west_throat.from_1"}}
    late = {OVERDUE: {"trains": [{"train": "t1", "into": "w_main", "reason": "x"}]}}

    assert adr_0062_moving_while_crossing(view(MEET, rows | late)) == []
    assert adr_0062_moving_while_crossing(view(MEET, rows))


def test_a_held_crossing_with_both_sensors_unknown_is_moving() -> None:
    """`layout` stops no train a throttle holds, so it runs on between two
    unknown sensors and `moving` is owed (#1187)."""
    rows = started({"west_1": "t1", "west_throat.from_1": "t1", "w_main": "t1"}) | {
        MOVING: {"moving": False},
        UNKNOWN_SENSORS: {"sensors": [{"sensor": "w_main.A"}, {"sensor": "w_main.B"}]},
    }
    rows[ALLOCATION] = {**rows[ALLOCATION], "crossing": {"t1": "west_throat.from_1"}}
    held = {TAKEN: {"taken": {"t1": "throttle-1"}}}

    assert adr_0062_moving_while_crossing(view(MEET, rows | held))
    assert adr_0062_moving_while_crossing(view(MEET, rows)) == []


def test_depth_counts_up_to_a_block_out_of_use_in_the_aspects() -> None:
    """Two ahead locked from west_1, but the second is out of use: `caution`
    there, and `stop` at the signal over the move into it (#1152)."""
    rows = started(AHEAD_TWO) | {
        POWER: {"power": "on"},
        ASPECTS: {"aspects": {"west_1.B": "caution", "w_main.B": "stop"}},
    }
    listed = {UNKNOWN_SENSORS: {"sensors": [{"sensor": "loop_up.A"}]}}

    assert (
        breaches_over(adr_0093_aspects_along_the_locks, MEET, rows | listed, []) == []
    )
    assert breaches_over(adr_0093_aspects_along_the_locks, MEET, rows, [])


def test_depth_counts_up_to_a_block_reading_occupied_in_the_aspects() -> None:
    """Two ahead locked from west_1, and a locomotive on the second: `caution`
    there, and `stop` at the signal over the move into it (#1160)."""
    rows = started(AHEAD_TWO) | {
        POWER: {"power": "on"},
        ASPECTS: {"aspects": {"west_1.B": "caution", "w_main.B": "stop"}},
    }
    stray = [read("loop_up")]

    assert breaches_over(adr_0093_aspects_along_the_locks, MEET, rows, stray) == []
    assert breaches_over(adr_0093_aspects_along_the_locks, MEET, rows, [])


def test_a_clear_reading_under_a_train_leaves_its_aspects_lit() -> None:
    """A clear reading disputes nothing, so the signals along its route show
    what its locks say (#1164)."""
    rows = started(AHEAD_TWO) | {POWER: {"power": "on"}}
    lit = {ASPECTS: {"aspects": {"west_1.B": "clear", "w_main.B": "caution"}}}

    assert (
        breaches_over(
            adr_0093_aspects_along_the_locks, MEET, rows | lit, [read("west_1", False)]
        )
        == []
    )


def test_depth_counts_past_a_block_a_train_explains_in_the_aspects() -> None:
    """The block ahead reads occupied and is the residue of the train's own
    removal, so it is explained and depth counts on through it (#1164)."""
    rows = started(AHEAD_TWO) | {POWER: {"power": "on"}}
    lit = {ASPECTS: {"aspects": {"west_1.B": "clear", "w_main.B": "caution"}}}
    lifted = [
        (TRAIN_REMOVED, {"train": "t1"}),
        placed("t1", "west_1"),
        read("loop_up"),
    ]

    assert (
        breaches_over(adr_0093_aspects_along_the_locks, MEET, rows | lit, lifted) == []
    )


AHEAD_ONE = {k: v for k, v in AHEAD_TWO.items() if k != "west_switch.to_up"}
"""One ahead, and loop_up locked without the transit into it."""


def test_a_block_the_train_occupies_is_not_held_ahead() -> None:
    """loop_up is on t1's route and locked to it without the transit into it.
    On its `occupied` list it is a block t1 occupies, not one it holds ahead
    (#1230)."""
    locked = started(AHEAD_ONE)
    occupies = {
        ALLOCATION: {
            **locked[ALLOCATION],
            "occupied": {"t1": ["west_1", "loop_up"]},
        }
    }

    assert adr_0029_block_with_its_transit(view(MEET, occupies)) == []
    assert adr_0029_block_with_its_transit(view(MEET, locked))


def test_depth_counts_a_block_only_with_its_transit_in_the_aspects() -> None:
    """loop_up is locked to t1 and the transit into it is not, so the depth
    from west_1 is one: `caution` there, `stop` over the move into loop_up
    (#1230)."""
    rows = started(AHEAD_ONE) | {POWER: {"power": "on"}}
    caution = {ASPECTS: {"aspects": {"west_1.B": "caution", "w_main.B": "stop"}}}
    clear = {ASPECTS: {"aspects": {"west_1.B": "clear", "w_main.B": "caution"}}}

    assert (
        breaches_over(adr_0093_aspects_along_the_locks, MEET, rows | caution, []) == []
    )
    assert breaches_over(adr_0093_aspects_along_the_locks, MEET, rows | clear, [])


def test_a_train_refused_its_next_move_lights_nothing_in_the_aspects() -> None:
    """Two ahead locked, and refused the move into the first of them: `stop`
    along its route is the right answer, and only with the refusal on its
    request (#1160)."""
    rows = started(AHEAD_TWO) | {POWER: {"power": "on"}}
    refused = {
        ALLOCATION: allocation(
            {"t1": "west_1"},
            locks=AHEAD_TWO,
            requests=[
                request(route=ROUTE)
                | {
                    "refused": {
                        "reason": "unsafe",
                        "obstacles": [{"resource": "e_main", "holder": ""}],
                    }
                }
            ],
        )
    }
    stopped = {ASPECTS: {"aspects": {"west_1.B": "stop", "w_main.B": "stop"}}}
    lit = {ASPECTS: {"aspects": {"west_1.B": "clear", "w_main.B": "caution"}}}

    assert (
        breaches_over(
            adr_0093_aspects_along_the_locks, MEET, rows | refused | stopped, []
        )
        == []
    )
    assert breaches_over(
        adr_0093_aspects_along_the_locks, MEET, rows | refused | lit, []
    )
    assert breaches_over(adr_0093_aspects_along_the_locks, MEET, rows | stopped, [])


def test_an_invariant_over_one_apps_topics_is_not_cross_app() -> None:
    by_name = {invariant.breaches.__name__: invariant for invariant in INVARIANTS}
    assert not cross_app(by_name["adr_0076_placed_holds_its_block"])
    assert cross_app(by_name["adr_0062_moving_while_crossing"])
    assert cross_app(by_name["adr_0039_unplaced_has_no_facing"])
    assert cross_app(by_name["adr_0093_stop_without_power"])
    assert not cross_app(by_name["adr_0089_one_train_a_throttle"])
    assert cross_app(by_name["adr_0022_points_set_for_the_crossing"])


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


def sensor(end: str, occupied: bool = True) -> tuple[str, Payload]:
    """A sensor's settled level (#1168)."""
    return (
        f"tc49/layout/state/settled/sensor/{end}",
        {"addr": end, "occupancy": "occupied" if occupied else "clear"},
    )


def read(block: str, occupied: bool = True) -> tuple[str, Payload]:
    """The level of the sensor at the block's `A` end, for a rule about the
    block and not about which end."""
    return sensor(f"{block}.A", occupied)


def listing(*ends: str) -> tuple[str, Payload]:
    """`state/unknown_sensors`, naming these."""
    return (
        "tc49/layout/state/unknown_sensors",
        {"sensors": [{"sensor": end, "reason": "x", "reported": True} for end in ends]},
    )


def placed(train: str, block: str) -> tuple[str, Payload]:
    return (TRAIN_PLACED, {"train": train, "block": block})


STANDING: Rows = {
    ALLOCATION: allocation({"single": "up_w"}, locks={"up_w": "single"}),
    FACING: {"facing": {"single": "up_w.A-to-B"}},
    POWER: {"power": "on"},
    DRIVING: {"driving": "automatic"},
    TAKEN: {"taken": {}},
}
"""`single` standing in up_w, nose to its B end, on a live railroad in
`automatic`."""

TO_DN: tuple[str, Payload] = (
    MOVE_GRANTED,
    {
        "id": "r1",
        "train": "single",
        "transit": "crossover.to_dn",
        "into": "dn_e",
        "aspect": "caution",
    },
)
ALIGNED: tuple[str, Payload] = (
    ALIGN,
    {
        "connection": "crossover",
        "transit": "to_dn",
        "points": [
            {"addr": "12", "position": "thrown", "reported": False},
            {"addr": "13", "position": "thrown", "reported": False},
        ],
    },
)


def moved(speed: float = 0.3) -> tuple[str, Payload]:
    return (
        MOVE,
        {
            "train": "single",
            "connection": "crossover",
            "transit": "to_dn",
            "into": "dn_e",
            "speed": speed,
        },
    )


def wrote(addr: str, speed: float) -> tuple[str, Payload]:
    return (traction(addr), {"addr": addr, "speed": speed})


REPORTED: tuple[str, Payload] = (
    ALIGN,
    {
        "connection": "crossover",
        "transit": "to_dn",
        "points": [
            {"addr": "12", "position": "thrown", "reported": True},
            {"addr": "13", "position": "thrown", "reported": False},
        ],
    },
)
"""The same way with point 12 reported (ADR-0097)."""


def lies(addr: str, position: str) -> tuple[str, Payload]:
    return (
        f"tc49/layout/state/device/point/{addr}",
        {"addr": addr, "position": position},
    )


RUNNING: Rows = STANDING | {traction("3"): {"addr": "3", "speed": 0.3}}
STARTED: Messages = [TO_DN, ALIGNED, moved(), wrote("3", 0.3)]

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
        adr_0025_move_at_the_aspects_speed,
        BENCH,
        STANDING,
        [TO_DN, moved(0.3), TO_DN, moved(0.3)],
        [TO_DN, moved(0.3), TO_DN, moved(0.5)],
    ),
    (
        adr_0031_no_traction_before_align,
        BENCH,
        STANDING,
        [moved(), ALIGNED, wrote("3", 0.3)],
        [moved(), wrote("3", 0.3)],
    ),
    (
        adr_0097_no_departure_before_the_report,
        BENCH,
        STANDING,
        [REPORTED, moved(), lies("12", "thrown"), wrote("3", 0.3)],
        [REPORTED, moved(), lies("12", "closed"), wrote("3", 0.3)],
    ),
    (
        adr_0047_no_grant_while_crossing,
        MEET,
        PLACED,
        [GRANT, LEFT, ONWARD],
        [GRANT, ONWARD],
    ),
    (
        adr_0047_traction_from_the_near_end,
        BENCH,
        STANDING,
        STARTED,
        [placed("single", "up_e"), *STARTED],
    ),
    (
        adr_0048_disputed_lists_contradictions,
        MEET,
        ON | {DISPUTED: {"blocks": []}} | PLACED,
        [
            read("west_1", False),
            read("loop_up"),
            (DISPUTED, {"blocks": ["loop_up"]}),
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
        adr_0052_sign_composed,
        BENCH,
        STANDING,
        STARTED,
        [TO_DN, ALIGNED, moved(), wrote("3", -0.3)],
    ),
    (
        adr_0052_no_traction_without_facing,
        BENCH,
        STANDING,
        STARTED,
        [(FACING, {"facing": {"single": "dn_e.A-to-B"}}), *STARTED],
    ),
    (
        adr_0054_traction_zeroed_at_start,
        BENCH,
        {traction("3"): {"addr": "3", "speed": 0.3}},
        [(RAILROAD, {"name": "bench"}), wrote("3", 0.0), moved()],
        [(RAILROAD, {"name": "bench"}), moved()],
    ),
    (
        adr_0060_new_railroad_only_while_off,
        BENCH,
        {RAILROAD: {"name": "bench"}, POWER: {"power": "on"}},
        [(POWER, {"power": "off"}), (RAILROAD, {"name": "yard"})],
        [(RAILROAD, {"name": "yard"})],
    ),
    (
        adr_0062_moving_to_the_tail,
        MEET,
        PLACED | {MOVING: {"moving": True}},
        [GRANT, sensor("w_main.A"), (MOVING, {"moving": True})],
        [GRANT, sensor("w_main.A"), (MOVING, {"moving": False})],
    ),
    (
        adr_0062_drain_ends_at_a_stand,
        MEET,
        {POWER: {"power": "draining"}, MOVING: {"moving": True}},
        [(MOVING, {"moving": False}), (WANTED_TRACK, {"power": "off"})],
        [(WANTED_TRACK, {"power": "off"})],
    ),
    (
        adr_0069_removed_is_stopped,
        BENCH,
        RUNNING,
        [(TRAIN_REMOVED, {"train": "single"}), wrote("3", 0.0)],
        [(TRAIN_REMOVED, {"train": "single"})],
    ),
    (
        adr_0074_comes_up_off,
        BENCH,
        {},
        [
            (RAILROAD, {"name": "bench"}),
            (WANTED_TRACK, {"power": "off"}),
            (POWER, {"power": "off"}),
        ],
        [
            (RAILROAD, {"name": "bench"}),
            (WANTED_TRACK, {"power": "off"}),
            (POWER, {"power": "on"}),
        ],
    ),
    (
        adr_0077_not_into_occupied,
        MEET,
        PLACED,
        # The first: a reading still in flight when the grant was made.
        [read("w_main"), GRANT],
        [read("w_main"), (QUIET, {}), GRANT],
    ),
    (
        adr_0077_released_on_the_tail,
        MEET,
        PLACED,
        # The transit with the block never seen to clear: a train placed beyond
        # its exit sensor.
        [GRANT, sensor("w_main.A"), sensor("w_main.A", False), LEFT],
        # The transit at the head in, which is what this replaced.
        [
            GRANT,
            sensor("w_main.A"),
            (LOCK_RELEASED, {"train": "t1", "resources": ["west_throat.from_1"]}),
        ],
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
        adr_0078_cut_leaves_the_railroad_at_rest,
        BENCH,
        RUNNING | {WANTED_TRACK: {"power": "on"}},
        [
            (POWER_WANTED, {"power": "off"}),
            wrote("3", 0.0),
            (WANTED_TRACK, {"power": "off"}),
            (POWER, {"power": "off"}),
        ],
        [
            (POWER_WANTED, {"power": "off"}),
            (WANTED_TRACK, {"power": "off"}),
            (POWER, {"power": "off"}),
        ],
    ),
    (
        adr_0079_manual_untaken_stands,
        BENCH,
        STANDING
        | {
            DRIVING: {"driving": "manual"},
            traction("3"): {"addr": "3", "speed": 0.3},
        },
        [TO_DN],
        [TO_DN, sensor("dn_e.B")],
    ),
    (
        adr_0079_holder_changes_by_release,
        BENCH,
        {TAKEN: {"taken": {"single": "t-1"}}},
        [(TAKEN, {"taken": {}}), (TAKEN, {"taken": {"single": "t-2"}})],
        [(TAKEN, {"taken": {"single": "t-2"}})],
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
    (
        adr_0081_arrival_stops_the_train,
        BENCH,
        STANDING,
        [*STARTED, sensor("dn_e.B"), wrote("3", 0.0)],
        [*STARTED, sensor("dn_e.B")],
    ),
    (
        adr_0081_release_in_automatic,
        BENCH,
        RUNNING | {TAKEN: {"taken": {"single": "t-1"}}},
        # No move outstanding: the train stops.
        [(TAKEN, {"taken": {}}), wrote("3", 0.0)],
        [(TAKEN, {"taken": {}})],
    ),
    (
        adr_0084_sign_changes_through_zero,
        BENCH,
        {},
        [wrote("3", 0.3), wrote("3", 0.0), wrote("3", -0.3)],
        [wrote("3", 0.3), wrote("3", -0.3)],
    ),
    (
        adr_0093_aspects_along_the_locks,
        MEET,
        # Two ahead from west_1, one from w_main, none from loop_up.
        started(AHEAD_TWO) | ON,
        [(ASPECTS, {"aspects": {"west_1.B": "clear", "w_main.B": "caution"}})],
        [(ASPECTS, {"aspects": {"west_1.B": "clear", "w_main.B": "clear"}})],
    ),
]


def breaches_over(
    breaches: Breaches, layout_id: str, rows: Rows, messages: Messages
) -> list[str]:
    """What `breaches` finds over `messages` from `rows`, as the helper runs
    it: each message before the record observes it, then `QUIET`."""
    record = Record(RAILROADS[layout_id], rows, STOCK[layout_id])
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


def test_a_released_train_stopped_overdue_is_not_reported() -> None:
    """A train `layout` stopped for not arriving within the allowance is
    listed on `state/overdue` before its `0.0`, and the release invariant
    leaves it out; one the row does not list is still reported (#1190)."""
    held = STANDING | {TAKEN: {"taken": {"single": "t-1"}}}
    released: Messages = [*STARTED, (TAKEN, {"taken": {}})]
    listed: tuple[str, Payload] = (
        OVERDUE,
        {"trains": [{"train": "single", "into": "dn_e", "reason": "no arrival"}]},
    )
    late: Messages = [*released, listed, wrote("3", 0.0)]
    assert breaches_over(adr_0081_release_in_automatic, BENCH, held, late) == []
    stopped: Messages = [*released, wrote("3", 0.0)]
    assert breaches_over(adr_0081_release_in_automatic, BENCH, held, stopped) == [
        "single released mid-move and stopped"
    ]


def test_a_reading_crossing_a_grant_counts_for_its_move() -> None:
    """The readings on the bus when the grant was made: the dispatcher hears
    them after it, so they are the ones the move ends on (#1154)."""
    crossed = [sensor("w_main.A"), sensor("w_main.A", False), GRANT, LEFT]
    assert breaches_over(adr_0077_released_on_the_tail, MEET, PLACED, crossed) == []
    out = [sensor("west_1.B", False), GRANT, (LOCK_RELEASED, ONLY_THE_BLOCK)]
    assert breaches_over(adr_0077_released_on_the_tail, MEET, PLACED, out) == []


ONLY_THE_BLOCK: Payload = {"train": "t1", "resources": ["west_1"]}
ONLY_THE_TRANSIT: Payload = {"train": "t1", "resources": ["west_throat.from_1"]}


def test_a_block_is_released_after_its_exit_reads_occupied_then_clear() -> None:
    released = (LOCK_RELEASED, ONLY_THE_BLOCK)
    tail = [sensor("west_1.B"), sensor("west_1.B", False)]
    assert (
        breaches_over(
            adr_0077_released_on_the_tail, MEET, PLACED, [GRANT, *tail, released]
        )
        == []
    )
    assert breaches_over(
        adr_0077_released_on_the_tail,
        MEET,
        PLACED,
        [GRANT, sensor("west_1.B"), sensor("w_main.A"), released],
    )


def test_a_block_left_by_an_older_move_goes_at_a_later_moves_entry_clear() -> None:
    later = [GRANT, sensor("w_main.A"), ONWARD, sensor("loop_up.A")]
    released = (
        LOCK_RELEASED,
        {"train": "t1", "resources": ["west_1", "west_throat.from_1"]},
    )
    assert (
        breaches_over(
            adr_0077_released_on_the_tail,
            MEET,
            PLACED,
            [*later, sensor("loop_up.A", False), released],
        )
        == []
    )
    assert (
        len(
            breaches_over(
                adr_0077_released_on_the_tail, MEET, PLACED, [*later, released]
            )
        )
        == 2
    )


def test_a_transit_is_not_released_at_a_later_moves_exit_clear() -> None:
    assert breaches_over(
        adr_0077_released_on_the_tail,
        MEET,
        PLACED,
        [
            GRANT,
            sensor("w_main.A"),
            ONWARD,
            sensor("w_main.B"),
            sensor("w_main.B", False),
            (LOCK_RELEASED, ONLY_THE_TRANSIT),
        ],
    )


def test_a_request_completes_at_its_entry_clear_or_its_far_sensor() -> None:
    completed = (REQUEST_COMPLETED, {"id": "r1"})
    for end in (
        [sensor("w_main.A"), sensor("w_main.A", False)],
        [sensor("w_main.B")],
    ):
        assert (
            breaches_over(
                adr_0077_released_on_the_tail, MEET, PLACED, [GRANT, *end, completed]
            )
            == []
        )
    assert breaches_over(
        adr_0077_released_on_the_tail,
        MEET,
        PLACED,
        [GRANT, sensor("w_main.A"), completed],
    )


def test_a_placement_and_a_withdrawal_are_outside_the_release_rule() -> None:
    wanted = (PLACEMENT_WANTED, {"train": "t1", "block": "up_e"})
    assert (
        breaches_over(
            adr_0077_released_on_the_tail, MEET, PLACED, [GRANT, wanted, LEFT]
        )
        == []
    )
    assert (
        breaches_over(
            adr_0077_released_on_the_tail,
            MEET,
            PLACED,
            [
                GRANT,
                (CANCEL_WANTED, {"id": "r1"}),
                (
                    "tc49/layout/move_withdrawn",
                    {"train": "t1", "transit": "west_throat.from_1", "into": "w_main"},
                ),
                (LOCK_RELEASED, ONLY_THE_TRANSIT),
            ],
        )
        == []
    )


def test_moving_is_owed_until_the_end_of_the_move_and_not_past_it() -> None:
    falls = (MOVING, {"moving": False})
    rows = PLACED | {MOVING: {"moving": True}}
    for end in (
        [sensor("w_main.A"), sensor("w_main.A", False)],
        [sensor("w_main.B")],
        [listing("w_main.A", "w_main.B")],
    ):
        assert (
            breaches_over(adr_0062_moving_to_the_tail, MEET, rows, [GRANT, *end, falls])
            == []
        )
    assert breaches_over(
        adr_0062_moving_to_the_tail, MEET, rows, [GRANT, listing("w_main.A"), falls]
    )


def test_moving_is_owed_for_no_move_of_a_train_listed_overdue() -> None:
    """A train `state/overdue` lists owes no `moving`, whatever its move's
    sensors read (#1191)."""
    falls = (MOVING, {"moving": False})
    rows = PLACED | {MOVING: {"moving": True}}
    late = (OVERDUE, {"trains": [{"train": "t1", "into": "w_main", "reason": "x"}]})

    assert (
        breaches_over(adr_0062_moving_to_the_tail, MEET, rows, [GRANT, late, falls])
        == []
    )
    assert breaches_over(adr_0062_moving_to_the_tail, MEET, rows, [GRANT, falls])


def test_moving_is_owed_for_a_held_move_between_both_sensors_listed() -> None:
    """A train a throttle holds runs on between two unknown sensors (#1187)."""
    falls = (MOVING, {"moving": False})
    rows = PLACED | {MOVING: {"moving": True}}
    held = (TAKEN, {"taken": {"t1": "throttle-1"}})
    listed = listing("w_main.A", "w_main.B")

    assert breaches_over(
        adr_0062_moving_to_the_tail, MEET, rows, [GRANT, held, listed, falls]
    )
    assert (
        breaches_over(adr_0062_moving_to_the_tail, MEET, rows, [GRANT, listed, falls])
        == []
    )


def test_the_entry_sensor_owes_no_stop() -> None:
    """A train stops at its far sensor, so one running past its entry sensor
    breaks nothing, even with its block's own event out (#1169)."""
    run = [*STARTED, read("dn_e"), sensor("dn_e.A"), sensor("dn_e.A", False)]

    assert breaches_over(adr_0081_arrival_stops_the_train, BENCH, STANDING, run) == []


def test_a_further_move_owes_nothing_for_the_block_it_passed() -> None:
    """A further move replaces what was started, so the far sensor it passes
    owes no stop; the block it now enters does (#1169)."""
    rows: Rows = {
        ALLOCATION: allocation({"single": "west_1"}),
        FACING: {"facing": {"single": "west_1.A-to-B"}},
    }
    record = Record(RAILROADS[MEET], rows, STOCK[BENCH])
    onward: Messages = [
        (
            MOVE,
            {
                "train": "single",
                "connection": "west_throat",
                "transit": "from_1",
                "into": "w_main",
                "speed": 0.3,
            },
        ),
        wrote("3", 0.3),
        (FACING, {"facing": {"single": "w_main.A-to-B"}}),
        (
            MOVE,
            {
                "train": "single",
                "connection": "west_switch",
                "transit": "to_up",
                "into": "loop_up",
                "speed": 0.3,
            },
        ),
        wrote("3", 0.3),
        sensor("w_main.B"),
    ]
    for topic, payload in onward:
        record.observe(topic, payload)

    assert record.arrived == {}
    record.observe(*sensor("loop_up.B"))
    assert record.arrived == {"3": "single"}


def _heard(*messages: tuple[str, Payload]) -> Record:
    """A record of `single` on the bench, having heard these."""
    record = Record(RAILROADS[BENCH], STANDING, STOCK[BENCH])
    for topic, payload in messages:
        record.observe(topic, payload)
    return record


def test_a_move_is_under_way_from_the_grant_to_its_far_sensor() -> None:
    """Rule 11: past the entry sensor and past the tail it is still going."""
    assert not _heard().under_way("single")
    assert _heard(TO_DN).under_way("single")
    assert _heard(TO_DN, sensor("dn_e.A")).under_way("single")
    assert _heard(TO_DN, sensor("dn_e.A"), sensor("dn_e.A", False)).under_way("single")
    assert _heard(TO_DN, sensor("dn_e.A", False)).under_way("single")
    assert not _heard(TO_DN, sensor("dn_e.B")).under_way("single")


def test_a_move_reading_nothing_at_its_far_sensor_ends_on_its_entry_sensor() -> None:
    """With the far sensor listed the tail clearing is the arrival, whichever
    comes first; with it listed and the tail not in, it goes on."""
    head = sensor("dn_e.A")
    tail = sensor("dn_e.A", False)
    gone = listing("dn_e.B")

    assert _heard(TO_DN, gone, head).under_way("single")
    assert not _heard(TO_DN, gone, head, tail).under_way("single")
    assert not _heard(TO_DN, head, tail, gone).under_way("single")
    assert _heard(TO_DN, gone, tail).under_way("single")
    assert _heard(TO_DN, head, tail, listing("dn_e.A")).under_way("single")


def test_a_move_stops_being_under_way_on_a_placement_or_a_removal() -> None:
    assert not _heard(TO_DN, placed("single", "up_e")).under_way("single")
    assert not _heard(TO_DN, (TRAIN_REMOVED, {"train": "single"})).under_way("single")


BACK: tuple[str, Payload] = (
    MOVE,
    {
        "train": "single",
        "connection": "crossover",
        "transit": "to_dn",
        "into": "up_w",
        "speed": 0.3,
    },
)
"""`single` asked back out by the end it came into dn_e at."""


def test_a_move_held_for_reversing_is_not_started_by_a_caution_drop() -> None:
    """A speed written with it held is the drop, on the move under way: only
    the arrival lets the held move start (#1169)."""
    record = _heard(*STARTED, sensor("dn_e.A"), BACK)

    assert record.starts("3") == []
    record.observe(*wrote("3", 0.3))
    assert "single" in record.commanded

    record.observe(*sensor("dn_e.B"))
    assert [train for train, _commanded in record.starts("3")] == ["single"]


def test_a_move_out_through_the_far_end_is_not_held() -> None:
    onward: tuple[str, Payload] = (
        MOVE,
        {
            "train": "single",
            "connection": "crossover",
            "transit": "straight",
            "into": "up_e",
            "speed": 0.3,
        },
    )
    assert [train for train, _ in _heard(*STARTED, onward).starts("3")] == ["single"]


def test_reported_points_are_checked_until_the_tail_is_in() -> None:
    """Its entry sensor occupied then clear, and the train is past the points
    whatever the block behind says (ADR-0097, #1169)."""
    aligned: tuple[str, Payload] = (
        ALIGN,
        {
            "connection": "crossover",
            "transit": "to_dn",
            "points": [{"addr": "12", "position": "thrown", "reported": True}],
        },
    )
    at_point: tuple[str, Payload] = (
        "tc49/layout/state/device/point/12",
        {"addr": "12", "position": "thrown"},
    )
    run = [TO_DN, aligned, at_point, moved(), wrote("3", 0.3)]
    assert _heard(*run, sensor("dn_e.A")).started["single"].reported == (
        ("12", "thrown"),
    )
    assert (
        _heard(*run, sensor("dn_e.A"), sensor("dn_e.A", False))
        .started["single"]
        .reported
        == ()
    )


def test_a_move_a_person_ran_past_its_entry_sensor_has_no_start_left() -> None:
    """Released after its head is in, the train has left its near end, so the
    speed it is given next is no start from there (#1169)."""
    moving = [TO_DN, ALIGNED, (TAKEN, {"taken": {"single": "t-1"}}), moved()]
    record = _heard(*moving, sensor("dn_e.A"))

    assert record.commanded == {}
    assert record.started["single"].far == "dn_e.B"


def test_a_move_held_for_a_reported_point_has_not_begun_at_its_entry_sensor() -> None:
    """A person ran the train in while `layout` holds the move for a point not
    yet reported (ADR-0097, decision 6): released then it is owed a 0, the move
    having not started, until the point says where it lies (#1170)."""
    aligned: tuple[str, Payload] = (
        ALIGN,
        {
            "connection": "crossover",
            "transit": "to_dn",
            "points": [{"addr": "12", "position": "thrown", "reported": True}],
        },
    )
    moving = [TO_DN, aligned, (TAKEN, {"taken": {"single": "t-1"}}), moved()]
    record = _heard(*moving, sensor("dn_e.A"))

    assert record.started == {}
    assert record.waits("single")
    assert record.under_way("single")


THROTTLED: Rows = RUNNING | {TAKEN: {"taken": {"single": "t-1"}}}
"""`single` running under a person's throttle."""


def test_a_person_running_past_the_entry_sensor_begins_the_move_at_the_report() -> None:
    """Head in first and the point after: nothing else begins the move, a
    throttle-held train getting no speed from `layout`, which still writes the
    `0.0` at the far sensor (#1179)."""
    run = [TO_DN, REPORTED, moved(), sensor("dn_e.A"), lies("12", "thrown")]
    far = sensor("dn_e.B")

    assert breaches_over(
        adr_0081_arrival_stops_the_train, BENCH, THROTTLED, [*run, far]
    )
    assert (
        breaches_over(
            adr_0081_arrival_stops_the_train,
            BENCH,
            THROTTLED,
            [*run, far, wrote("3", 0.0)],
        )
        == []
    )


def test_the_point_reporting_first_begins_the_move_at_the_entry_sensor() -> None:
    run = [TO_DN, REPORTED, moved(), lies("12", "thrown"), sensor("dn_e.A")]
    far = sensor("dn_e.B")

    assert breaches_over(
        adr_0081_arrival_stops_the_train, BENCH, THROTTLED, [*run, far]
    )
    assert (
        breaches_over(
            adr_0081_arrival_stops_the_train,
            BENCH,
            THROTTLED,
            [*run, far, wrote("3", 0.0)],
        )
        == []
    )


def test_a_report_begins_nothing_for_a_train_no_throttle_holds() -> None:
    """This app drives it, so its speed write is what begins the move."""
    record = _heard(TO_DN, REPORTED, moved(), sensor("dn_e.A"), lies("12", "thrown"))

    assert record.started == {}
    assert "single" in record.commanded


def test_a_report_begins_no_move_held_for_reversing() -> None:
    """The move under way goes on owing its stop at its own far sensor."""
    record = Record(RAILROADS[BENCH], THROTTLED, STOCK[BENCH])
    for topic, payload in [
        TO_DN,
        ALIGNED,
        moved(),
        sensor("dn_e.A"),
        REPORTED,
        BACK,
        sensor("up_w.B"),
        lies("12", "thrown"),
    ]:
        record.observe(topic, payload)

    assert record.started["single"].far == "dn_e.B"
    assert "single" in record.commanded


def test_a_report_of_another_position_begins_nothing() -> None:
    """The move still waits for the position its `align` asked."""
    record = Record(RAILROADS[BENCH], THROTTLED, STOCK[BENCH])
    for topic, payload in [
        TO_DN,
        REPORTED,
        moved(),
        sensor("dn_e.A"),
        lies("12", "closed"),
    ]:
        record.observe(topic, payload)

    assert record.started == {}
    assert record.waits("single")


def test_a_report_begins_nothing_before_the_head_is_in() -> None:
    record = Record(RAILROADS[BENCH], THROTTLED, STOCK[BENCH])
    for topic, payload in [TO_DN, REPORTED, moved(), lies("12", "thrown")]:
        record.observe(topic, payload)

    assert record.started == {}
    assert "single" in record.commanded


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
            for layout_id in (MEET, BENCH):
                breaches_over(
                    invariant.breaches,
                    layout_id,
                    {topic: payload for topic in topics if "/state/" in topic},
                    [(topic, payload) for topic in sorted(topics)],
                )


def test_which_history_invariants_are_cross_app() -> None:
    by_name = {
        invariant.breaches.__name__: invariant for invariant in HISTORY_INVARIANTS
    }
    assert not cross_app(by_name["adr_0002_route_is_fixed"])
    assert not cross_app(by_name["adr_0080_placed_into_a_free_block"])
    assert cross_app(by_name["adr_0048_disputed_lists_contradictions"])
    assert cross_app(by_name["adr_0019_facing_turns_on_a_move"])
    assert not cross_app(by_name["adr_0084_sign_changes_through_zero"])
    assert not cross_app(by_name["adr_0078_cut_leaves_the_railroad_at_rest"])
    assert cross_app(by_name["adr_0069_removed_is_stopped"])


def test_the_release_invariant_reads_state_overdue() -> None:
    """It leaves out a train `state/overdue` lists, so it names the topic
    among its reads; `layout` writes it, so the classification is unchanged
    (#1197)."""
    by_name = {
        invariant.breaches.__name__: invariant for invariant in HISTORY_INVARIANTS
    }
    release = by_name["adr_0081_release_in_automatic"]
    assert OVERDUE in release.reads
    assert cross_app(release)


def test_the_moving_invariants_read_state_taken() -> None:
    """Both count a train `state/taken` names as moving between two unknown
    sensors, so each names the topic among its reads and in its rule; the
    classification is unchanged (#1201)."""
    by_name = {
        invariant.breaches.__name__: invariant
        for invariant in (*INVARIANTS, *HISTORY_INVARIANTS)
    }
    for name in ("adr_0062_moving_while_crossing", "adr_0062_moving_to_the_tail"):
        invariant = by_name[name]
        assert TAKEN in invariant.reads
        assert "`state/taken`" in invariant.states
        assert cross_app(invariant)


def test_a_retained_railroad_handed_again_is_no_start() -> None:
    """A late subscriber on `#` is handed `state/railroad` and then
    `state/power` as they stand, which is not `layout` coming up."""
    rows: Rows = {
        RAILROAD: {"name": "bench"},
        POWER: {"power": "on"},
        traction("3"): {"addr": "3", "speed": 0.3},
    }
    replayed: Messages = [(RAILROAD, {"name": "bench"}), (POWER, {"power": "on"})]
    for breaches in (adr_0074_comes_up_off, adr_0054_traction_zeroed_at_start):
        assert breaches_over(breaches, BENCH, rows, [*replayed, moved()]) == []


WITHDRAWN: Messages = [
    TO_DN,
    (CANCEL_WANTED, {"id": "r1"}),
    (
        "tc49/layout/move_withdrawn",
        {"train": "single", "transit": "crossover.to_dn", "into": "dn_e"},
    ),
]
"""`single`'s move granted, cancelled, and taken back before its `move`
came (#1080)."""


def test_a_move_withdrawn_before_it_came_is_dropped_when_it_does() -> None:
    """`layout` drops the late `move`, so it starts nothing: a later write to
    the train's address is no move's, and no sign is checked against it."""
    late: Messages = [*WITHDRAWN, ALIGNED, moved(), wrote("3", -0.3)]

    assert breaches_over(adr_0052_sign_composed, BENCH, STANDING, late) == []


def test_a_placement_clears_a_withdrawal_waiting_for_its_move() -> None:
    record = Record(RAILROADS[BENCH], STANDING, STOCK[BENCH])
    for topic, payload in [*WITHDRAWN, placed("single", "up_w"), moved()]:
        record.observe(topic, payload)

    assert list(record.commanded) == ["single"]


NONE_DISPUTED: Payload = {"blocks": []}
DISPUTES: Rows = {DISPUTED: NONE_DISPUTED} | PLACED


def test_a_row_with_a_trains_key_is_a_breach_of_disputed() -> None:
    """The row is blocks only (#1164), whatever else it gets right."""
    assert breaches_over(
        adr_0048_disputed_lists_contradictions,
        MEET,
        DISPUTES,
        [(DISPUTED, {"trains": [], "blocks": []})],
    ) == ["disputed cannot be read"]


def test_a_block_held_ahead_is_named_and_missing_it_is_a_breach() -> None:
    """A lock explains nothing, so a reading on a block held ahead is on the
    row, and a row without it is breached (#1164)."""
    rows = started(AHEAD_TWO) | {DISPUTED: NONE_DISPUTED}
    stray = read("loop_up")

    assert breaches_over(adr_0048_disputed_lists_contradictions, MEET, rows, [stray])
    assert (
        breaches_over(
            adr_0048_disputed_lists_contradictions,
            MEET,
            rows,
            [stray, (DISPUTED, {"blocks": ["loop_up"]})],
        )
        == []
    )


@pytest.mark.parametrize(
    ("rows", "messages"),
    [
        pytest.param(DISPUTES, [read("west_1")], id="recorded in the block"),
        pytest.param(
            {
                DISPUTED: NONE_DISPUTED,
                ALLOCATION: {
                    **allocation({"t1": "west_1"}, locks={"west_1": "t1"}),
                    "occupied": {"t1": ["west_1", "west_throat.from_1"]},
                },
            },
            [GRANT, read("west_1")],
            id="the block the train occupies",
        ),
        pytest.param(DISPUTES, [GRANT, read("w_main")], id="the move's arrival"),
        pytest.param(
            {
                DISPUTED: {"blocks": []},
                ALLOCATION: allocation(locks={"w_main": "t1"}),
            },
            [read("w_main")],
            id="residue in the rows",
        ),
        pytest.param(
            {
                DISPUTED: {"blocks": []},
                ALLOCATION: allocation(
                    {"t1": "west_1"}, locks={"west_1": "t1", "w_main": "t1"}
                ),
            },
            [(TRAIN_REMOVED, {"train": "t1"}), read("w_main")],
            id="residue of a removal",
        ),
        pytest.param(
            {
                DISPUTED: {"blocks": []},
                ALLOCATION: allocation(
                    {"t1": "w_main"},
                    {"t1": "west_throat.from_1"},
                    locks={"w_main": "t1"},
                ),
            },
            [read("west_1")],
            id="a restored crossing",
        ),
    ],
)
def test_a_block_a_train_explains_is_no_dispute(rows: Rows, messages: Messages) -> None:
    """Each of the four explained cases: an empty row holds, and one listing the
    block is breached (#1164)."""
    block = cast(dict[str, str], messages[-1][1])["addr"].partition(".")[0]
    assert (
        breaches_over(adr_0048_disputed_lists_contradictions, MEET, rows, messages)
        == []
    )
    assert breaches_over(
        adr_0048_disputed_lists_contradictions,
        MEET,
        rows,
        [*messages, (DISPUTED, {"blocks": [block]})],
    )


def test_a_clear_reading_is_no_dispute() -> None:
    """Not on the row at any power value, and a row naming it is breached
    (#1164)."""
    clear = read("west_1", False)
    assert (
        breaches_over(adr_0048_disputed_lists_contradictions, MEET, DISPUTES, [clear])
        == []
    )
    assert breaches_over(
        adr_0048_disputed_lists_contradictions,
        MEET,
        DISPUTES,
        [clear, (DISPUTED, {"blocks": ["west_1"]})],
    )
