"""A block with an unknown sensor is out of use (#1152, GLOSSARY.md).

A block whose sensor has stopped reporting is treated as if it did not exist:
no train is sent into it or out of it and the rest of the railroad runs. A train
already on a route through it waits at its signal, and when the sensor returns
the block is back in use with no press.

Driven at the bus where a request's fate is the question, on a live railroad
under each locking discipline, `state/unknown_sensors` published as `layout`
publishes it. Both railroads have the shape a case needs: `single-track-meet` has
one way through `w_main` and `e_main` and two round its loops, and
`crossover-yard` has parallel tracks for a train on free track.
"""

from collections.abc import Iterable
from typing import cast

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.dispatcher import Dispatcher, FullRoute, Incremental
from tc49.dispatcher.dispatch import Active, Request, State, aspects
from tc49.dispatcher.locking import Move, Refused, safety_view
from tc49.dispatcher.routing import Route, candidates
from tc49.dispatcher.safety import finishable
from tc49.lib.bus import Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import DRAINING, ON, Aspect, Refusal
from tc49.lib.layout import Layout, transit_ends
from tc49.lib.scenario import TrainSpec
from tc49.store import AssetStore
from tests.dispatcher.test_power import Reordering
from tests.harness import ASSETS, leaves, movings, power, press, retaining, stock, ticks

UNKNOWN_SENSORS = "tc49/layout/state/unknown_sensors"
REQUEST_WANTED = "tc49/schedule/request_wanted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
MEET = "single-track-meet"
YARD = "crossover-yard"

Strategy = type[Incremental | FullRoute]
STRATEGIES: list[Strategy] = [Incremental, FullRoute]


def drawing(name: str) -> Layout:
    layout = AssetStore(ASSETS).get(name)
    assert isinstance(layout, Layout)
    return layout


def railroad(
    name: str, strategy: Strategy = Incremental, **at: tuple[str, str]
) -> Assembly:
    """`name` with each train of 600 stood at a `(block, facing)`, power on."""
    return assemble_live(
        drawing(name),
        stock(**{train: 600 for train in at}),
        {train: TrainSpec(*spec) for train, spec in at.items()},
        strategy,
    )


def runner_in_the_west(strategy: Strategy = Incremental) -> Assembly:
    return railroad(MEET, strategy, runner=("west_1", "A-to-B"))


def row(*sensors: str) -> Payload:
    return {
        "sensors": [
            {"sensor": sensor, "reason": "no report for 10 s", "reported": True}
            for sensor in sensors
        ]
    }


def lists(assembly: Assembly, *sensors: str) -> None:
    press(assembly, UNKNOWN_SENSORS, row(*sensors))


def wants(assembly: Assembly, train: str, *dest: str) -> None:
    press(assembly, REQUEST_WANTED, {"train": train, "dest": list(dest)})


def routes(assembly: Assembly) -> list[list[str]]:
    return [
        cast(list[str], chosen["route"]) for chosen in leaves(assembly, "route_chosen")
    ]


def last_refusal(assembly: Assembly) -> tuple[object, object]:
    refused = leaves(assembly, "grant_refused")[-1]
    return refused["reason"], refused["obstacles"]


def held(block: str, holder: str = "") -> tuple[object, object]:
    return Refusal.HELD, [{"resource": block, "holder": holder}]


# -- no grant in, and no route through ---------------------------------------


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_route_around_the_block_is_the_one_launched(strategy: Strategy) -> None:
    assembly = runner_in_the_west(strategy)
    lists(assembly, "loop_dn.A")
    wants(assembly, "runner", "east_1.A")

    assert "loop_up" in routes(assembly)[0]
    assert "loop_dn" not in routes(assembly)[0]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_request_whose_only_route_crosses_the_block_waits_for_it(
    strategy: Strategy,
) -> None:
    """It is not rejected: `None` from a launch means unreachable, and this
    request is waiting on a failed sensor. The sensor returning is the whole
    of what launches it."""
    assembly = runner_in_the_west(strategy)
    lists(assembly, "e_main.B")
    wants(assembly, "runner", "east_1.A")

    assert routes(assembly) == []
    assert leaves(assembly, "request_rejected") == []
    assert [req.train for req in assembly.dispatcher.pending] == ["runner"]
    assert last_refusal(assembly) == held("e_main")

    lists(assembly)

    assert len(routes(assembly)) == 1
    assert "e_main" in routes(assembly)[0]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_request_whose_destination_is_the_block_waits_the_same_way(
    strategy: Strategy,
) -> None:
    assembly = runner_in_the_west(strategy)
    lists(assembly, "east_1.B")
    wants(assembly, "runner", "east_1.A")

    assert routes(assembly) == []
    assert leaves(assembly, "request_rejected") == []
    assert last_refusal(assembly) == held("east_1")

    lists(assembly)

    assert routes(assembly)[0][-1] == "east_1"


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_with_every_route_barred_the_first_route_names_the_block(
    strategy: Strategy,
) -> None:
    """Both loops listed: the refusal names the first such block on the route
    the unfiltered search puts first, and there is one obstacle."""
    assembly = runner_in_the_west(strategy)
    lists(assembly, "loop_dn.A", "loop_up.B")
    wants(assembly, "runner", "east_1.A")

    assert last_refusal(assembly) == held("loop_dn")


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_request_no_route_serves_is_still_unreachable(strategy: Strategy) -> None:
    """The refusal is for a route the sensor is in the way of. A request no
    route serves whatever the sensors say goes on being rejected, from a block
    out of use too."""
    layout = drawing(MEET)
    state = State(
        layout,
        {"runner": 600},
        {"west_1": "runner"},
        {"runner": "west_1"},
        {},
        unknown_sensors=frozenset({"west_1.A"}),
    )
    request = Request("r-1", "runner", "west_1.A", ("east_1.A",), 0)
    assert strategy(layout, 2).launch(request, "west_1", "west_1.A", state) is None


def test_the_budget_is_spent_on_routes_that_can_run() -> None:
    """Filtered before `k`, or the two routes a budget of one or two tries
    could be the ones that cross the block, and another route is never found."""
    layout = drawing(YARD)
    barred = frozenset({"dn_w"})
    found = candidates(
        layout, "yard_w", "yard_w.B", ("yard_e.A",), 600, 1, frozenset(), barred
    )
    assert [route.blocks for route in found] == [("yard_w", "up_w", "dn_e", "yard_e")]


def test_the_origin_is_not_one_of_the_blocks_a_route_is_left_out_for() -> None:
    """Leaving the origin is the strategy's refusal, so `candidates` answers
    the same with the origin in the set as without it."""
    layout = drawing(YARD)
    found = candidates(
        layout, "yard_w", "yard_w.B", ("yard_e.A",), 600, 4, frozenset(), {"yard_w"}
    )
    assert len(found) == 4


# -- no grant out ------------------------------------------------------------


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_an_idle_train_standing_in_the_block_launches_nothing(
    strategy: Strategy,
) -> None:
    """And a person may still place it elsewhere."""
    assembly = railroad(MEET, strategy, runner=("w_main", "A-to-B"))
    lists(assembly, "w_main.A")
    wants(assembly, "runner", "east_1.A")

    assert routes(assembly) == []
    assert leaves(assembly, "request_rejected") == []
    assert last_refusal(assembly) == held("w_main")

    press(assembly, PLACEMENT_WANTED, {"train": "runner", "block": "loop_up"})

    assert leaves(assembly, "placement_refused") == []
    assert assembly.dispatcher.state.block_of["runner"] == "loop_up"


def standing(layout: Layout, *blocks: str) -> Route:
    """The route running through `blocks`."""
    origin, arrival = blocks[0], blocks[-1]
    for depart in (f"{origin}.A", f"{origin}.B"):
        for end in (f"{arrival}.A", f"{arrival}.B"):
            for route in candidates(layout, origin, depart, (end,), 600, 8):
                if route.blocks == blocks:
                    return route
    raise AssertionError(f"no route through {blocks}")


def under_way(
    layout: Layout,
    routes_of: dict[str, Route],
    listed: Iterable[str],
    locked_ahead: dict[str, list[str]] | None = None,
) -> State:
    locks = {route.blocks[0]: train for train, route in routes_of.items()}
    for train, resources in (locked_ahead or {}).items():
        locks.update({resource: train for resource in resources})
    return State(
        layout,
        {train: 600 for train in routes_of},
        locks,
        {train: route.blocks[0] for train, route in routes_of.items()},
        {
            train: Active(
                Request(f"{train}-1", train, "", (f"{route.arrival_block}.A",), 0),
                route,
                0,
                None,
            )
            for train, route in routes_of.items()
        },
        power=ON,
        unknown_sensors=frozenset(listed),
    )


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_an_active_train_standing_in_the_block_is_granted_nothing(
    strategy: Strategy,
) -> None:
    layout = drawing(MEET)
    route = standing(layout, "w_main", "loop_up", "e_main")
    state = under_way(layout, {"runner": route}, ["w_main.B"])

    assert strategy(layout, 2).grant("runner", state) == Refused(
        Refusal.HELD, [{"resource": "w_main", "holder": ""}]
    )


def test_a_block_out_of_use_names_no_holder_whoever_stands_in_it() -> None:
    """What stops a train there is the sensor, and the train standing in the
    block cannot move either (#1254)."""
    state = State(
        drawing(MEET),
        {"parked": 600, "runner": 600},
        {"w_main": "parked", "e_main": "runner"},
        {"parked": "w_main", "runner": "e_main"},
        {},
        power=ON,
        unknown_sensors=frozenset({"w_main.B"}),
    )

    assert state.obstacle("w_main", "runner") == (Refusal.HELD, "w_main", "")


def test_an_unsafe_verdict_names_no_holder_for_a_block_out_of_use() -> None:
    """`runner`'s route ends through `e_main`, where `parked` stands with a
    sensor that has not reported."""
    layout = drawing(MEET)
    route = standing(layout, "west_1", "w_main", "loop_up", "e_main", "east_1")
    state = under_way(layout, {"runner": route}, ["e_main.A"])
    state.roster["parked"] = 600
    state.locks["e_main"] = "parked"
    state.block_of["parked"] = "e_main"

    assert Incremental(layout, 2).grant("runner", state) == Refused(
        Refusal.UNSAFE, [{"resource": "e_main", "holder": ""}]
    )


def test_a_train_is_not_named_for_its_own_residue() -> None:
    """It waits for the block's sensor to read clear, and not for itself (#1254)."""
    state = State(
        drawing(MEET),
        {"runner": 600},
        {"w_main": "runner", "e_main": "runner"},
        {"runner": "e_main"},
        {},
        power=ON,
        readings={"w_main.A": True},
        residue={"w_main"},
    )

    assert state.obstacle("w_main", "runner") == (Refusal.HELD, "w_main", "")


def test_a_train_standing_in_the_block_is_frozen_for_every_other_train() -> None:
    """It could finish, on the track ahead of it, and is not going to: what it
    stands in and what it holds are idle obstacles. So one needing what it holds
    waits and one on free track runs."""
    layout = drawing(YARD)
    route = standing(layout, "dn_w", "dn_e", "yard_e")
    state = under_way(
        layout,
        {
            "stuck": route,
            "behind": standing(layout, "up_w", "dn_e", "yard_e"),
            "free": standing(layout, "up_e", "yard_e"),
        },
        ["dn_w.A"],
        {"stuck": ["dn_e"]},
    )

    cur, _rem, idle, _held = safety_view(state)
    assert "stuck" not in cur
    assert {"dn_w", "dn_e"} <= set(idle)
    assert finishable(*safety_view(state)) == frozenset(cur)
    answer = Incremental(layout, 2).grant("behind", state)
    assert isinstance(answer, Refused)
    assert answer.obstacles[0]["resource"] == "dn_e"
    assert isinstance(Incremental(layout, 2).grant("free", state), Move)


# -- a committed route stays -------------------------------------------------


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_committed_train_waits_with_its_route_and_others_run(
    strategy: Strategy,
) -> None:
    """No reroute, and the train elsewhere is granted. The sensor returning
    carries the waiting train on with no press."""
    assembly = railroad(
        YARD, strategy, runner=("yard_w", "A-to-B"), other=("up_e", "B-to-A")
    )
    wants(assembly, "runner", "yard_e.A")
    state = assembly.dispatcher.state
    route = state.active["runner"].route
    assert route.blocks == ("yard_w", "dn_w", "dn_e", "yard_e")

    lists(assembly, "dn_e.B")
    ticks(assembly, 8)

    assert state.active["runner"].route == route
    assert state.block_of["runner"] == "dn_w"
    assert state.locks["dn_w"] == "runner"
    assert not state.crossing
    assert assembly.dispatcher.requests[0].refused is not None

    wants(assembly, "other", "up_w.B")
    ticks(assembly, 8)

    assert any(chosen[-1] == "up_w" for chosen in routes(assembly))
    assert state.block_of["other"] == "up_w"
    assert state.active["runner"].route == route

    lists(assembly)
    ticks(assembly, 12)

    assert state.block_of["runner"] == "yard_e"
    assert "runner" not in state.active


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_person_can_cancel_the_request_of_a_train_waiting_for_the_block(
    strategy: Strategy,
) -> None:
    assembly = railroad(YARD, strategy, runner=("yard_w", "A-to-B"))
    wants(assembly, "runner", "yard_e.A")
    lists(assembly, "dn_e.B")
    ticks(assembly, 8)
    request = assembly.dispatcher.requests[0]
    assert "runner" in assembly.dispatcher.state.active

    press(assembly, CANCEL_WANTED, {"id": request.id})

    assert [end["id"] for end in leaves(assembly, "request_cancelled")] == [request.id]
    assert "runner" not in assembly.dispatcher.state.active


# -- signals -----------------------------------------------------------------


def shown_along(route: Route, state: State) -> list[str]:
    """The aspect at the exit of each block of `route` but its last."""
    shown = aspects(state)
    ends = [
        transit_ends(state.layout, block, transit)
        for block, transit in zip(route.blocks, route.transits)
    ]
    return [shown[end[0]] for end in ends if end is not None]


def held_all_along(layout: Layout, route: Route, listed: Iterable[str]) -> State:
    return under_way(
        layout, {"runner": route}, listed, {"runner": route.crossing_order()}
    )


def test_a_signal_at_the_entry_to_the_block_shows_stop() -> None:
    layout = drawing(MEET)
    route = standing(layout, "west_1", "w_main", "loop_up", "e_main", "east_1")

    assert (
        shown_along(route, held_all_along(layout, route, ["w_main.A"]))
        == [Aspect.STOP] * 4
    )


def test_depth_counts_only_up_to_the_first_block_out_of_use() -> None:
    layout = drawing(MEET)
    route = standing(layout, "west_1", "w_main", "loop_up", "e_main", "east_1")

    assert shown_along(route, held_all_along(layout, route, [])) == [
        Aspect.CLEAR,
        Aspect.CLEAR,
        Aspect.CLEAR,
        Aspect.CAUTION,
    ]
    assert shown_along(route, held_all_along(layout, route, ["e_main.A"])) == [
        Aspect.CLEAR,
        Aspect.CAUTION,
        Aspect.STOP,
        Aspect.STOP,
    ]
    assert shown_along(route, held_all_along(layout, route, ["loop_up.B"])) == [
        Aspect.CAUTION,
        Aspect.STOP,
        Aspect.STOP,
        Aspect.STOP,
    ]


def test_a_signal_over_a_train_that_will_not_be_let_out_shows_stop() -> None:
    """The aspect answers whether a train may leave by that end (ADR-0093), and
    out of a block out of use none may."""
    layout = drawing(MEET)
    route = standing(layout, "w_main", "loop_up", "e_main", "east_1")

    assert (
        shown_along(route, held_all_along(layout, route, ["w_main.B"]))
        == [Aspect.STOP] * 3
    )


# -- state/moving ------------------------------------------------------------


def crossing_into_dn_w() -> Assembly:
    """freight granted its move into `dn_w`, which it enters by `dn_w.A`."""
    assembly = railroad(YARD, freight=("yard_w", "A-to-B"))
    wants(assembly, "freight", "yard_e.A")
    assert movings(assembly) == [False, True]
    assert assembly.dispatcher.state.crossing
    return assembly


def test_a_crossing_with_both_sensors_listed_is_not_moving() -> None:
    """`layout` has stopped that train, so a person's off press can finish its
    drain, and the crossing goes on being one."""
    assembly = crossing_into_dn_w()
    press(assembly, *power(DRAINING))
    lists(assembly, "dn_w.A", "dn_w.B")

    assert movings(assembly) == [False, True, False]
    assert assembly.dispatcher.state.crossing == {"freight": "west_ladder.to_dn"}


def test_a_crossing_with_only_its_far_sensor_listed_still_moves() -> None:
    assembly = crossing_into_dn_w()
    lists(assembly, "dn_w.B")

    assert movings(assembly) == [False, True]


def test_a_sensor_returning_moves_it_again() -> None:
    assembly = crossing_into_dn_w()
    lists(assembly, "dn_w.A", "dn_w.B")
    lists(assembly, "dn_w.B")

    assert movings(assembly) == [False, True, False, True]


# -- the row ----------------------------------------------------------------


def test_a_list_that_has_not_changed_sweeps_nothing() -> None:
    """A `sensors: []` is no row at all: the bench's fixed scenarios go on
    running the same, and a sweep there would stamp admissions differently. A
    sweep is seen by what a waiting request says each time one runs."""
    assembly = runner_in_the_west()
    lists(assembly)
    lists(assembly, "e_main.B")
    wants(assembly, "runner", "east_1.A")
    refusals = len(leaves(assembly, "grant_refused"))

    lists(assembly, "e_main.B")
    assert len(leaves(assembly, "grant_refused")) == refusals

    lists(assembly, "e_main.A", "e_main.B")
    assert len(leaves(assembly, "grant_refused")) == refusals + 1


@pytest.mark.parametrize("unreadable", [{}, {"sensors": None}, {"sensors": 7}])
def test_an_unreadable_row_is_dropped_and_the_last_value_stands(
    unreadable: Payload,
) -> None:
    assembly = runner_in_the_west()
    lists(assembly, "e_main.A")
    press(assembly, UNKNOWN_SENSORS, unreadable)

    assert assembly.dispatcher.state.out_of_use == {"e_main"}


def test_either_sensor_takes_its_block_out_of_use() -> None:
    assembly = runner_in_the_west()
    lists(assembly, "e_main.A", "w_main.B", "w_main.A")

    assert assembly.dispatcher.state.out_of_use == {"e_main", "w_main"}


def test_a_row_the_bus_already_holds_counts_from_the_first_event() -> None:
    """Read where the power is, in the constructor: a request arriving before
    the drain that delivers the subscription is not sent into the block."""
    layout = drawing(MEET)
    bus = retaining({UNKNOWN_SENSORS: row("w_main.A")})
    dispatcher = Dispatcher(bus, layout, stock(), {}, FullRoute(layout, 2))

    assert dispatcher.state.out_of_use == {"w_main"}


def test_a_stale_row_loses_to_the_later_one() -> None:
    """A state topic like the power, and a pair delivered backwards (#240)
    would otherwise leave a block out of use that has come back, or the other
    way about."""
    clock = Clock()
    layout = drawing(MEET)
    bus = Reordering(clock, UNKNOWN_SENSORS)
    dispatcher = Dispatcher(bus, layout, stock(), {}, FullRoute(layout, 2))

    clock.advance(10.0)
    bus.publish(UNKNOWN_SENSORS, row("e_main.A"))
    clock.advance(20.0)
    bus.publish(UNKNOWN_SENSORS, row("w_main.A"))
    bus.drain()

    assert dispatcher.state.out_of_use == {"w_main"}


# -- placing is untouched ----------------------------------------------------


def test_a_placement_on_the_block_is_accepted() -> None:
    assembly = railroad(MEET, runner=("west_1", "A-to-B"))
    lists(assembly, "loop_up.A")
    press(assembly, PLACEMENT_WANTED, {"train": "runner", "block": "loop_up"})

    assert leaves(assembly, "placement_refused") == []
    assert assembly.dispatcher.state.block_of["runner"] == "loop_up"
