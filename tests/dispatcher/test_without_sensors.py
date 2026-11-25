"""A railroad run without sensors (#1314, #1319).

While `tc49/layout/state/settings` says `without_sensors: true` the dispatcher
ignores sensor readings. A request that starts locks its whole route and sets
all its points in one `align`, and no move is granted: a person drives the
train with a throttle. The run ends by a cancel, a placement or a removal.

Driven at the bus on `reversing-loops`, the one railroad whose points carry
addresses, with the bus invariants checked. `mover` stands in C4, and its one
route to A2 runs through j2 and then j1. j1 is one junction in which nearly
every transit conflicts with every other, so `crosser`, in A1 and asking for
CW, conflicts with `mover`'s route at that connection alone. `loner`, in C7
and asking for C3b, runs on free track through j3; `sharer`, in CE1 and asking
for C3b too, enters it through j5, so it shares that block with `loner`'s
route and no connection.
"""

from typing import Any

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.dispatcher import Dispatcher, FullRoute, Incremental
from tc49.lib.bus import Payload
from tc49.lib.layout import Layout
from tc49.lib.scenario import TrainSpec
from tests.harness import (
    events,
    leaves,
    load,
    minted,
    movings,
    press,
    retaining,
    settled,
    stock,
)
from tests.invariants import check

REQUEST_WANTED = "tc49/schedule/request_wanted"
SETTINGS_WANTED = "tc49/layout/settings_wanted"
UNKNOWN_SENSORS = "tc49/layout/state/unknown_sensors"
ALLOCATION = "tc49/dispatch/state/allocation"
ASPECTS = "tc49/dispatch/state/aspects"
DISPUTED = "tc49/dispatch/state/disputed"
MOVING = "tc49/dispatch/state/moving"
POWER = "tc49/layout/state/power"
POWER_WANTED = "tc49/layout/power_wanted"
SETTINGS = "tc49/layout/state/settings"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
POINT_WANTED = "tc49/dispatch/point_wanted"

Strategy = type[Incremental | FullRoute]
each_strategy = pytest.mark.parametrize("strategy", [Incremental, FullRoute])

ROUTE = ["C4", "j2.C4_A__CE2_A", "CE2", "j1.A2_A__CE2_B", "A2"]
"""`mover`'s one route to A2, origin first."""

POINTS = [
    {"addr": "110", "position": "thrown", "reported": False},
    {"addr": "111", "position": "thrown", "reported": False},
    {"addr": "101", "position": "closed", "reported": False},
    {"addr": "102", "position": "thrown", "reported": False},
    {"addr": "105", "position": "thrown", "reported": False},
]
"""The points of j2's and then j1's transit on that route, in route order."""

STOOD = {
    "mover": TrainSpec("C4", "B-to-A"),
    "crosser": TrainSpec("A1", "B-to-A"),
    "sharer": TrainSpec("CE1", "B-to-A"),
    "loner": TrainSpec("C7", "B-to-A"),
}


def drawing() -> Layout:
    layout, _, _ = load("reversing-loops/positions")
    return layout


def railroad(strategy: Strategy = Incremental, *trains: str) -> Assembly:
    """`reversing-loops` with `mover` and each of `trains` standing as
    `STOOD` has them, power on, the invariants checked, and the settings
    saying `without_sensors`."""
    names = ("mover", *trains)
    assembly = assemble_live(
        drawing(),
        stock(**dict.fromkeys(names, 250)),
        {name: STOOD[name] for name in names},
        strategy,
    )
    check(assembly, strategy)
    press(assembly, SETTINGS_WANTED, {"without_sensors": True})
    return assembly


def every_sensor_unknown(assembly: Assembly) -> None:
    press(
        assembly,
        UNKNOWN_SENSORS,
        {
            "sensors": [
                {"sensor": f"{block}.{end}", "reason": "never heard", "reported": True}
                for block in sorted(assembly.layout.blocks)
                for end in "AB"
            ]
        },
    )


def wants(assembly: Assembly, train: str, dest: str) -> None:
    press(assembly, REQUEST_WANTED, {"train": train, "dest": [dest]})


def aligns(assembly: Assembly) -> list[dict[str, Any]]:
    return events(assembly.trace, "align")


def granted(assembly: Assembly, train: str) -> list[object]:
    """The resources of each `lock_granted` for `train`, its standing lock
    first."""
    return [
        line["resources"]
        for line in leaves(assembly, "lock_granted")
        if line["train"] == train
    ]


@each_strategy
def test_a_drag_locks_the_whole_route_and_sets_its_points(strategy: Strategy) -> None:
    """Every sensor unknown and one reading occupied in CE2, on the route:
    the launch takes the whole route in one `lock_granted` and every point in
    one `align` naming no transit, and grants no move."""
    assembly = railroad(strategy)
    every_sensor_unknown(assembly)
    press(assembly, *settled("CE2.A"))

    wants(assembly, "mover", "A2.A")

    chosen = leaves(assembly, "route_chosen")
    assert [line["route"] for line in chosen] == [ROUTE]
    assert granted(assembly, "mover") == [["C4"], ROUTE[1:]]
    assert [
        (line["connection"], line["transit"], line["points"])
        for line in aligns(assembly)
    ] == [(None, None, POINTS)]
    assert leaves(assembly, "move_granted") == []
    assert events(assembly.trace, "move") == []


def last(assembly: Assembly, topic: str) -> Payload:
    return assembly.bus.last_values[topic]


def underway(strategy: Strategy = Incremental, *trains: str) -> Assembly:
    """`railroad`, with every sensor unknown and `mover` launched to A2."""
    assembly = railroad(strategy, *trains)
    every_sensor_unknown(assembly)
    wants(assembly, "mover", "A2.A")
    return assembly


@each_strategy
def test_the_train_stands_in_its_origin_and_occupies_its_whole_route(
    strategy: Strategy,
) -> None:
    assembly = underway(strategy)

    picture = last(assembly, ALLOCATION)
    assert [(req["train"], req["route"]) for req in picture["requests"]] == [
        ("mover", ROUTE)
    ]
    assert picture["trains"] == {"mover": "C4"}
    assert picture["crossing"] == {}
    assert picture["occupied"] == {"mover": ROUTE}
    assert picture["locks"] == dict.fromkeys(sorted(ROUTE), "mover")


def under_way_still(assembly: Assembly, train: str = "mover") -> bool:
    picture = last(assembly, ALLOCATION)
    return any(req["train"] == train and "route" in req for req in picture["requests"])


@each_strategy
def test_nothing_is_disputed_or_moving_and_a_drain_ends_at_once(
    strategy: Strategy,
) -> None:
    """A reading occupied where no train is, C1, disputes nothing, and a
    drain switches the power off with the run still under way."""
    assembly = underway(strategy)
    press(assembly, *settled("C1.A"))

    assert last(assembly, DISPUTED)["blocks"] == []
    assert not any(line["blocks"] for line in leaves(assembly, "disputed"))
    assert movings(assembly) == [False]

    press(assembly, POWER_WANTED, {"power": "draining"})

    assert last(assembly, POWER)["power"] == "off"
    assert under_way_still(assembly)
    assert movings(assembly) == [False]


def test_a_restored_crossing_is_not_moving() -> None:
    """A crossing hint off the last picture is a train between two blocks,
    which counts as moving on a railroad run by its sensors. Without them
    nothing does, from the opening rows on: the setting already held is
    adopted at construction."""
    layout = drawing()
    bus = retaining(
        {
            SETTINGS: {"without_sensors": True},
            ALLOCATION: {
                "trains": {"mover": "C4"},
                "crossing": {"mover": "j2.C4_A__CE2_A"},
                "occupied": {"mover": ["C4", "j2.C4_A__CE2_A"]},
            },
        }
    )
    Dispatcher(bus, layout, stock(mover=250), {}, Incremental(layout, 2))
    bus.drain()

    assert bus.last_values[MOVING]["moving"] is False


def proceed(assembly: Assembly) -> dict[str, str]:
    """Every signal showing anything but `stop`."""
    shown = last(assembly, ASPECTS)["aspects"]
    return {end: aspect for end, aspect in shown.items() if aspect != "stop"}


@each_strategy
def test_the_exit_signals_show_the_route_by_its_depth(strategy: Strategy) -> None:
    """`mover` holds two blocks beyond C4 and shows `clear`, then `caution`
    out of CE2; `loner` holds one beyond C7 and shows `caution`. They stay
    so through the sweeps a reading and another request run."""
    assembly = underway(strategy, "loner")
    wants(assembly, "loner", "C3b.B")

    shown = {"C4.A": "clear", "CE2.B": "caution", "C7.A": "caution"}
    assert proceed(assembly) == shown

    press(assembly, *settled("CE2.A"))
    press(assembly, *settled("CE2.A", False))

    assert proceed(assembly) == shown


def refusals(assembly: Assembly, train: str) -> list[tuple[object, list[object]]]:
    """Each `grant_refused` for `train`'s requests: the reason and the
    holders it names."""
    ids = {
        line["id"]
        for line in leaves(assembly, "request_submitted")
        if line["train"] == train
    }
    return [
        (line["reason"], [each["holder"] for each in line["obstacles"]])
        for line in leaves(assembly, "grant_refused")
        if line["id"] in ids
    ]


def launched(assembly: Assembly) -> list[str]:
    """The trains whose routes were chosen, in order."""
    ids = {line["id"]: line["train"] for line in leaves(assembly, "request_submitted")}
    return [ids[line["id"]] for line in leaves(assembly, "route_chosen")]


@each_strategy
def test_a_route_sharing_a_block_is_held_until_the_run_is_cancelled(
    strategy: Strategy,
) -> None:
    """C3b, which `loner` holds, is on every route of `sharer`'s."""
    assembly = underway(strategy, "loner", "sharer")
    wants(assembly, "loner", "C3b.B")
    wants(assembly, "sharer", "C3b.A")

    assert refusals(assembly, "sharer") == [("held", ["loner"])]
    assert launched(assembly) == ["mover", "loner"]

    press(assembly, CANCEL_WANTED, {"id": minted(assembly, "loner")})

    assert launched(assembly) == ["mover", "loner", "sharer"]


@each_strategy
def test_a_route_conflicting_at_a_connection_waits_for_the_same(
    strategy: Strategy,
) -> None:
    """A1 to CW shares no block with `mover`'s route, and its one transit
    conflicts at j1 with the one `mover` holds there."""
    assembly = underway(strategy, "crosser")
    wants(assembly, "crosser", "CW.A")

    assert refusals(assembly, "crosser") == [("transit_conflict", ["mover"])]

    press(assembly, CANCEL_WANTED, {"id": minted(assembly, "mover")})

    assert launched(assembly) == ["mover", "crosser"]


@each_strategy
def test_a_route_over_free_track_launches_beside_the_run(strategy: Strategy) -> None:
    assembly = underway(strategy, "loner")
    wants(assembly, "loner", "C3b.B")

    assert launched(assembly) == ["mover", "loner"]
    assert granted(assembly, "loner") == [["C7"], ["j3.C3b_B__C7_A", "C3b"]]
    assert aligns(assembly)[-1]["points"] == [
        {"addr": "112", "position": "thrown", "reported": False},
        {"addr": "113", "position": "thrown", "reported": False},
    ]


def released(assembly: Assembly, train: str) -> list[object]:
    return [
        line["resources"]
        for line in leaves(assembly, "lock_released")
        if line["train"] == train
    ]


@each_strategy
def test_a_cancel_releases_all_but_the_origin_at_once(strategy: Strategy) -> None:
    """The train has not left its block: nothing is asked of `layout`."""
    assembly = underway(strategy)
    rid = minted(assembly, "mover")

    press(assembly, CANCEL_WANTED, {"id": rid})

    assert released(assembly, "mover") == [sorted(ROUTE[1:])]
    assert [
        (line["id"], line["reason"]) for line in leaves(assembly, "request_cancelled")
    ] == [(rid, "revoked")]
    assert leaves(assembly, "withdraw_wanted") == []
    picture = last(assembly, ALLOCATION)
    assert picture["occupied"] == {"mover": ["C4"]}
    assert picture["locks"] == {"C4": "mover"}
    assert picture["requests"] == []
