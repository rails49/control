"""A railroad run without sensors (#1314, #1319).

While `tc49/layout/state/settings` says `without_sensors: true` the dispatcher
ignores sensor readings. A request that starts locks its whole route and sets
all its points in one `align`, and no move is granted: a person drives the
train with a throttle. The run ends by "arrived" (`arrival_wanted`, #1320), a
cancel, a placement or a removal.

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
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout
from tc49.lib.scenario import TrainSpec
from tests.dispatcher.test_power import Reordering
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
REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
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


def railroad(
    strategy: Strategy = Incremental, *trains: str, without_sensors: bool = True
) -> Assembly:
    """`reversing-loops` with `mover` and each of `trains` standing as
    `STOOD` has them, power on, the invariants checked, and the settings
    saying `without_sensors` unless told otherwise."""
    names = ("mover", *trains)
    assembly = assemble_live(
        drawing(),
        stock(**dict.fromkeys(names, 250)),
        {name: STOOD[name] for name in names},
        strategy,
    )
    check(assembly, strategy)
    if without_sensors:
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


ARRIVAL_WANTED = "tc49/dispatch/arrival_wanted"


def arrive(assembly: Assembly, payload: Payload) -> list[tuple[str, Payload]]:
    """`arrival_wanted` pressed: each leaf the dispatcher publishes on its
    drain, with its payload, in order."""
    heard: list[tuple[str, Payload]] = []
    assembly.bus.subscribe(
        "tc49/dispatch/#",
        lambda topic, said: heard.append((topic.removeprefix("tc49/dispatch/"), said)),
    )
    assembly.bus.drain()
    heard.clear()  # the retained rows a subscription is handed
    press(assembly, ARRIVAL_WANTED, payload)
    return [(leaf, said) for leaf, said in heard if leaf != "arrival_wanted"]


@each_strategy
@pytest.mark.parametrize("power", ["on", "off"])
def test_arrived_releases_the_route_completes_and_places_the_train(
    strategy: Strategy, power: str
) -> None:
    """At any power: everything on the route but A2, the origin among it, is
    released, the request completes, and `mover` stands in A2. The picture
    that follows has it there alone, and every signal along the route shows
    `stop`."""
    assembly = underway(strategy)
    rid = minted(assembly, "mover")
    press(assembly, POWER_WANTED, {"power": power})

    said = arrive(assembly, {"id": rid})

    assert said[:3] == [
        ("lock_released", {"train": "mover", "resources": sorted(ROUTE[:-1])}),
        ("request_completed", {"id": rid}),
        ("train_placed", {"train": "mover", "block": "A2"}),
    ]
    # The aspects row only where it changes: with the power off every signal
    # already shows `stop`.
    assert [leaf for leaf, _ in said[3:]] == (
        ["state/aspects", "state/allocation"] if power == "on" else ["state/allocation"]
    )
    picture = last(assembly, ALLOCATION)
    assert picture["trains"] == {"mover": "A2"}
    assert picture["locks"] == {"A2": "mover"}
    assert picture["occupied"] == {"mover": ["A2"]}
    assert picture["requests"] == []
    assert proceed(assembly) == {}


@each_strategy
@pytest.mark.parametrize("payload", [{}, {"id": 7}, {"id": "nobody"}])
def test_an_arrival_naming_no_request_held_is_dropped(
    strategy: Strategy, payload: Payload
) -> None:
    assembly = underway(strategy)

    assert arrive(assembly, payload) == []
    assert under_way_still(assembly)
    assert last(assembly, ALLOCATION)["occupied"] == {"mover": ROUTE}


@each_strategy
def test_an_arrival_for_a_waiting_request_is_dropped(strategy: Strategy) -> None:
    """`sharer` waits `held` on C3b, which `loner`'s route ends in."""
    assembly = underway(strategy, "loner", "sharer")
    wants(assembly, "loner", "C3b.B")
    wants(assembly, "sharer", "C3b.A")

    assert arrive(assembly, {"id": minted(assembly, "sharer")}) == []
    assert launched(assembly) == ["mover", "loner"]
    assert under_way_still(assembly, "loner")


@each_strategy
def test_a_second_arrival_for_the_same_request_is_dropped(strategy: Strategy) -> None:
    assembly = underway(strategy)
    rid = minted(assembly, "mover")
    arrive(assembly, {"id": rid})

    assert arrive(assembly, {"id": rid}) == []
    assert last(assembly, ALLOCATION)["trains"] == {"mover": "A2"}


@each_strategy
def test_an_arrival_on_a_railroad_run_by_its_sensors_is_dropped(
    strategy: Strategy,
) -> None:
    """The move granted into CE2 stands: its sensors end it. The simulator
    writes no `wanted/point`, so the route's points are put where it needs
    them first, as `layout` would."""
    assembly = railroad(strategy, without_sensors=False)
    for point in POINTS:
        press(
            assembly,
            f"{WANTED_POINT}/{point['addr']}",
            {"addr": point["addr"], "position": point["position"]},
        )
    wants(assembly, "mover", "A2.A")
    before = last(assembly, ALLOCATION)

    assert arrive(assembly, {"id": minted(assembly, "mover")}) == []
    assert [line["into"] for line in leaves(assembly, "move_granted")] == ["CE2"]
    assert last(assembly, ALLOCATION) == before
    assert under_way_still(assembly)


@each_strategy
def test_a_request_held_on_the_route_launches_at_the_arrivals_sweep(
    strategy: Strategy,
) -> None:
    """`crosser` runs from A1 to C1 by CW; `mover`'s route to A1 crosses j1
    on a transit that conflicts with none of `crosser`'s and waits `held` on
    A1, the route's origin, until the arrival releases it."""
    assembly = railroad(strategy, "crosser")
    every_sensor_unknown(assembly)
    wants(assembly, "crosser", "C1.B")
    wants(assembly, "mover", "A1.B")
    assert refusals(assembly, "mover") == [("held", ["crosser", "crosser"])]

    arrive(assembly, {"id": minted(assembly, "crosser")})

    assert launched(assembly) == ["crosser", "mover"]
    assert last(assembly, ALLOCATION)["trains"] == {"crosser": "C1", "mover": "C4"}


ONWARD = ["A2", "j1.A2_B__CE2_B", "CE2", "j2.C1_A__CE2_A", "C1"]
"""`mover`'s route on from A2 to C1, leaving by A2.B: the route to A2 came in
by A2.A."""


def chained(assembly: Assembly) -> str:
    """A request of `mover`'s to C1, submitted after its first; its id."""
    press(
        assembly,
        REQUEST_SUBMITTED,
        {
            "id": "m-on",
            "train": "mover",
            "dest": ["C1.A"],
            "after": minted(assembly, "mover"),
        },
    )
    return "m-on"


@each_strategy
def test_a_request_chained_after_the_arrival_departs_from_the_destination(
    strategy: Strategy,
) -> None:
    """It waits while the first is under way, and launches at the arrival's
    sweep as the first did: the whole route locked and occupied, its points
    set in one `align`, no move."""
    assembly = underway(strategy)
    rid = chained(assembly)
    assert events(assembly.trace, "route_chosen", rid=rid) == []

    arrive(assembly, {"id": minted(assembly, "mover")})

    [chosen] = events(assembly.trace, "route_chosen", rid=rid)
    assert chosen["route"] == ONWARD
    assert granted(assembly, "mover")[-1] == ONWARD[1:]
    assert aligns(assembly)[-1]["transit"] is None
    assert leaves(assembly, "move_granted") == []
    picture = last(assembly, ALLOCATION)
    assert picture["trains"] == {"mover": "A2"}
    assert picture["occupied"] == {"mover": ONWARD}
    assert [(req["id"], req["route"]) for req in picture["requests"]] == [(rid, ONWARD)]


@each_strategy
def test_with_the_power_off_the_chained_request_waits_for_it(
    strategy: Strategy,
) -> None:
    assembly = underway(strategy)
    rid = chained(assembly)
    press(assembly, POWER_WANTED, {"power": "off"})

    arrive(assembly, {"id": minted(assembly, "mover")})

    assert events(assembly.trace, "route_chosen", rid=rid) == []
    assert last(assembly, ALLOCATION)["occupied"] == {"mover": ["A2"]}

    press(assembly, POWER_WANTED, {"power": "on"})

    [chosen] = events(assembly.trace, "route_chosen", rid=rid)
    assert chosen["route"] == ONWARD


def place(assembly: Assembly, train: str, block: str | None) -> None:
    press(assembly, PLACEMENT_WANTED, {"train": train, "block": block})


@each_strategy
def test_a_placement_on_the_route_ends_the_run_there(strategy: Strategy) -> None:
    assembly = underway(strategy)
    rid = minted(assembly, "mover")

    place(assembly, "mover", "CE2")

    assert [
        (line["id"], line["reason"]) for line in leaves(assembly, "request_cancelled")
    ] == [(rid, "displaced")]
    assert [line["block"] for line in leaves(assembly, "train_placed")] == ["CE2"]
    picture = last(assembly, ALLOCATION)
    assert picture["trains"] == {"mover": "CE2"}
    assert picture["occupied"] == {"mover": ["CE2"]}
    assert picture["locks"] == {"CE2": "mover"}


@each_strategy
def test_a_placement_on_the_origin_is_refused_and_the_run_stands(
    strategy: Strategy,
) -> None:
    """Cancel is the gesture for a train that has not left."""
    assembly = underway(strategy)

    place(assembly, "mover", "C4")

    assert [line["reason"] for line in leaves(assembly, "placement_refused")] == [
        "not_free"
    ]
    assert under_way_still(assembly)
    assert last(assembly, ALLOCATION)["occupied"] == {"mover": ROUTE}


@each_strategy
def test_a_removal_keeps_nothing_where_a_sensor_reads_occupied(
    strategy: Strategy,
) -> None:
    assembly = underway(strategy)
    press(assembly, *settled("C4.A"))

    place(assembly, "mover", None)

    assert released(assembly, "mover") == [sorted(ROUTE)]
    assert len(leaves(assembly, "train_removed")) == 1
    picture = last(assembly, ALLOCATION)
    assert picture["locks"] == {}
    assert picture["trains"] == {}


def throw(assembly: Assembly, addr: str) -> None:
    press(assembly, POINT_WANTED, {"addr": addr, "position": "closed"})


@each_strategy
def test_a_hand_throw_on_the_route_is_dropped_and_one_off_it_goes_out(
    strategy: Strategy,
) -> None:
    """`110` is on j2's transit of the route; `112` lies in j3 alone."""
    assembly = underway(strategy)

    throw(assembly, "110")
    throw(assembly, "112")

    assert [line["points"] for line in aligns(assembly)[1:]] == [
        [{"addr": "112", "position": "closed", "reported": False}]
    ]


@each_strategy
def test_turning_the_setting_on_releases_residue(strategy: Strategy) -> None:
    """`mover` lifted off C4 with C4 reading occupied keeps C4 as residue,
    on a railroad run by its sensors. No reading will open it once they are
    ignored, so the row saying `without_sensors` releases it."""
    assembly = railroad(strategy, without_sensors=False)
    press(assembly, *settled("C4.A"))
    place(assembly, "mover", None)
    assert last(assembly, ALLOCATION)["locks"] == {"C4": "mover"}

    press(assembly, SETTINGS_WANTED, {"without_sensors": True})

    assert released(assembly, "mover") == [["C4"]]
    assert last(assembly, ALLOCATION)["locks"] == {}


def bare(bus: InProcessBus) -> None:
    """The dispatcher alone over `reversing-loops`, `mover` in C4, the power
    on."""
    layout = drawing()
    Dispatcher(bus, layout, stock(mover=250), {"mover": "C4"}, Incremental(layout, 2))
    bus.publish(POWER, {"power": "on"})
    bus.drain()


def submit(bus: InProcessBus) -> None:
    bus.publish(
        REQUEST_SUBMITTED,
        {"id": "m-1", "train": "mover", "depart": "C4.A", "dest": ["A2.A"]},
    )
    bus.drain()


def heard(bus: InProcessBus, leaf: str) -> list[Payload]:
    found: list[Payload] = []
    bus.subscribe(f"tc49/dispatch/{leaf}", lambda topic, payload: found.append(payload))
    return found


def test_a_row_older_than_the_one_held_changes_nothing() -> None:
    """`true` then `false`, delivered backwards: the stamp says `false` is
    the later, so the railroad runs by its sensors and the launch grants a
    move."""
    clock = Clock()
    bus = Reordering(clock, SETTINGS)
    bare(bus)
    moves = heard(bus, "move_granted")

    clock.advance(10.0)
    bus.publish(SETTINGS, {"without_sensors": True})
    clock.advance(20.0)
    bus.publish(SETTINGS, {"without_sensors": False})
    bus.drain()
    submit(bus)

    assert [move["into"] for move in moves] == ["CE2"]


def test_a_row_whose_field_does_not_read_changes_nothing() -> None:
    bus = InProcessBus(Clock())
    bare(bus)
    moves = heard(bus, "move_granted")

    bus.publish(SETTINGS, {"without_sensors": True})
    bus.drain()
    bus.publish(SETTINGS, {"without_sensors": "yes"})
    bus.drain()
    bus.publish(SETTINGS, {"short_blocks": True})
    bus.drain()
    submit(bus)

    assert moves == []
    assert bus.last_values[ALLOCATION]["occupied"] == {"mover": ROUTE}


@each_strategy
def test_a_drag_chained_before_the_cancel_is_cancelled_with_it(
    strategy: Strategy,
) -> None:
    assembly = underway(strategy)
    first = minted(assembly, "mover")
    wants(assembly, "mover", "CE2.B")
    second = minted(assembly, "mover", 2)

    press(assembly, CANCEL_WANTED, {"id": first})

    assert [
        (line["id"], line["reason"]) for line in leaves(assembly, "request_cancelled")
    ] == [(first, "revoked"), (second, "revoked")]


@each_strategy
def test_a_request_chained_after_the_cancel_departs_by_the_end_the_route_left_by(
    strategy: Strategy,
) -> None:
    assembly = underway(strategy)
    first = minted(assembly, "mover")
    press(assembly, CANCEL_WANTED, {"id": first})

    press(
        assembly,
        REQUEST_SUBMITTED,
        {"id": "m-late", "train": "mover", "dest": ["CE2.A"], "after": first},
    )

    [chosen] = events(assembly.trace, "route_chosen", rid="m-late")
    assert chosen["route"] == ROUTE[:3]


# -- changing the setting (#1321) ----------------------------------------------

WANTED_POINT = "tc49/layout/state/wanted/point"


def followed() -> Assembly:
    """Run by its sensors under `Incremental`: `mover` granted its move over
    j2 into CE2 with its head not yet in, holding CE2, j1's transit and A2
    ahead; `crosser`'s request to CW waiting on j1; and a second request of
    `mover`'s, to CE2, chained after its first. The simulator writes no
    `wanted/point`, so the points of `mover`'s route are put where it needs
    them first, as `layout` would."""
    assembly = railroad(Incremental, "crosser", without_sensors=False)
    for point in POINTS:
        press(
            assembly,
            f"{WANTED_POINT}/{point['addr']}",
            {"addr": point["addr"], "position": point["position"]},
        )
    wants(assembly, "mover", "A2.A")
    wants(assembly, "crosser", "CW.A")
    wants(assembly, "mover", "CE2.A")
    return assembly


def cancelled(assembly: Assembly) -> list[tuple[object, object]]:
    return [
        (line["id"], line["reason"]) for line in leaves(assembly, "request_cancelled")
    ]


def never_broken(assembly: Assembly) -> None:
    """`state/broken` read `[]` throughout."""
    assert all(line["rules"] == [] for line in leaves(assembly, "broken"))


def test_turning_it_on_ends_every_request_and_keeps_what_each_train_occupies() -> None:
    """In list order: `mover`'s started request, `crosser`'s waiting one,
    then `mover`'s chained one. `mover` keeps C4 and the transit it is
    crossing, and gives up what it held ahead; nothing is asked of
    `layout`."""
    assembly = followed()
    ids = [
        minted(assembly, "mover"),
        minted(assembly, "crosser"),
        minted(assembly, "mover", 2),
    ]
    moves = len(leaves(assembly, "move_granted"))
    crossed = "j2.C4_A__CE2_A"
    assert last(assembly, ALLOCATION)["occupied"]["mover"] == ["C4", crossed]

    press(assembly, SETTINGS_WANTED, {"without_sensors": True})

    assert cancelled(assembly) == [(rid, "revoked") for rid in ids]
    assert leaves(assembly, "withdraw_wanted") == []
    assert len(leaves(assembly, "move_granted")) == moves
    assert released(assembly, "mover") == [["A2", "CE2", "j1.A2_A__CE2_B"]]
    picture = last(assembly, ALLOCATION)
    assert picture["requests"] == []
    assert picture["crossing"] == {"mover": crossed}
    assert picture["occupied"]["mover"] == ["C4", crossed]
    assert picture["locks"] == {"A1": "crosser", "C4": "mover", crossed: "mover"}
    assert last(assembly, MOVING)["moving"] is False
    never_broken(assembly)


def picture_of(assembly: Assembly) -> Payload:
    """`state/allocation` without its stamp."""
    return {
        key: value for key, value in last(assembly, ALLOCATION).items() if key != "at"
    }


def test_after_that_the_readings_of_the_move_change_nothing() -> None:
    """The head into CE2, its far sensor, then the whole train in: no move is
    followed any more."""
    assembly = followed()
    press(assembly, SETTINGS_WANTED, {"without_sensors": True})
    before = picture_of(assembly)

    press(assembly, *settled("CE2.A"))
    press(assembly, *settled("CE2.B"))
    press(assembly, *settled("CE2.A", False))

    assert picture_of(assembly) == before
    never_broken(assembly)


def turned_off(strategy: Strategy, *trains: str) -> Assembly:
    """`underway`, then a row saying the railroad runs by its sensors."""
    assembly = underway(strategy, *trains)
    press(assembly, SETTINGS_WANTED, {"without_sensors": False})
    return assembly


@each_strategy
def test_turning_it_off_ends_the_run_and_keeps_the_whole_route(
    strategy: Strategy,
) -> None:
    """The train may be anywhere on its route, so nothing is released."""
    assembly = turned_off(strategy)

    assert cancelled(assembly) == [(minted(assembly, "mover"), "revoked")]
    assert released(assembly, "mover") == []
    picture = last(assembly, ALLOCATION)
    assert picture["requests"] == []
    assert picture["occupied"] == {"mover": ROUTE}
    assert picture["locks"] == dict.fromkeys(sorted(ROUTE), "mover")
    never_broken(assembly)


@each_strategy
def test_after_that_the_readings_and_sensors_not_reporting_are_back_in_use(
    strategy: Strategy,
) -> None:
    """C1 read occupied, and every sensor was listed not reporting, while the
    setting was on. Once it is off C1 is disputed, and `loner`'s request is
    held in C7, which is out of use."""
    assembly = underway(strategy, "loner")
    press(assembly, *settled("C1.A"))
    assert last(assembly, DISPUTED)["blocks"] == []

    press(assembly, SETTINGS_WANTED, {"without_sensors": False})
    wants(assembly, "loner", "C3b.B")

    assert last(assembly, DISPUTED)["blocks"] == ["C1"]
    assert refusals(assembly, "loner") == [("held", [""])]
    assert launched(assembly) == ["mover"]
    never_broken(assembly)


@each_strategy
def test_after_that_a_placement_releases_all_but_the_block_named(
    strategy: Strategy,
) -> None:
    assembly = turned_off(strategy)

    place(assembly, "mover", "CE2")

    picture = last(assembly, ALLOCATION)
    assert picture["trains"] == {"mover": "CE2"}
    assert picture["occupied"] == {"mover": ["CE2"]}
    assert picture["locks"] == {"CE2": "mover"}
    never_broken(assembly)


@each_strategy
def test_after_off_and_on_again_a_new_runs_cancel_keeps_only_its_origin(
    strategy: Strategy,
) -> None:
    """`mover` still holds its route to A2 from the run the change ended, and
    is sent to CE2 over part of it."""
    assembly = turned_off(strategy)
    press(assembly, SETTINGS_WANTED, {"without_sensors": True})
    wants(assembly, "mover", "CE2.A")
    rid = minted(assembly, "mover", 2)
    assert under_way_still(assembly)

    press(assembly, CANCEL_WANTED, {"id": rid})

    assert released(assembly, "mover")[-1] == sorted(ROUTE[1:])
    picture = last(assembly, ALLOCATION)
    assert picture["occupied"] == {"mover": ["C4"]}
    assert picture["locks"] == {"C4": "mover"}
    never_broken(assembly)


def test_a_train_left_crossing_is_moving_once_it_is_off_until_it_is_placed() -> None:
    """`mover` was crossing j2 when the setting went on. Once it is off the
    crossing has no move behind it, as after a restart."""
    assembly = followed()
    press(assembly, SETTINGS_WANTED, {"without_sensors": True})
    assert movings(assembly) == [False, True, False]

    press(assembly, SETTINGS_WANTED, {"without_sensors": False})
    assert movings(assembly) == [False, True, False, True]

    place(assembly, "mover", "CE2")
    assert movings(assembly) == [False, True, False, True, False]
    never_broken(assembly)


def test_a_request_after_one_the_change_ended_is_cancelled_revoked() -> None:
    assembly = followed()
    first = minted(assembly, "crosser")
    press(assembly, SETTINGS_WANTED, {"without_sensors": True})

    press(
        assembly,
        REQUEST_SUBMITTED,
        {"id": "c-late", "train": "crosser", "dest": ["A2.A"], "after": first},
    )

    assert cancelled(assembly)[-1] == ("c-late", "revoked")
    assert launched(assembly) == ["mover"]
    never_broken(assembly)


def test_a_row_with_the_value_already_held_ends_nothing() -> None:
    assembly = underway(Incremental)

    press(assembly, SETTINGS_WANTED, {"without_sensors": True, "short_blocks": True})

    assert cancelled(assembly) == []
    assert under_way_still(assembly)
    never_broken(assembly)


def test_a_row_whose_field_does_not_read_ends_nothing() -> None:
    bus = InProcessBus(Clock())
    bare(bus)
    ended = heard(bus, "request_cancelled")
    bus.publish(SETTINGS, {"without_sensors": True})
    bus.drain()
    submit(bus)

    bus.publish(SETTINGS, {"without_sensors": "yes"})
    bus.drain()

    assert ended == []
    assert bus.last_values[ALLOCATION]["requests"][0]["id"] == "m-1"
