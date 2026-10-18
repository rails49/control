"""The lock table's rules, checked at every sweep (#761, ADR-0076).

`broken` is a pure function of `State` and is tested on its own: a valid
state breaks nothing, and each rule broken alone gives one line naming what
broke it. Then the dispatcher at the bus, on two paths the physical railroad
produces and the simulator does not — a detector stuck occupied with GO
pressed over it, and a vacate delivered before the occupy ahead of it — where
the newly broken rule holds the run once and a person's GO is honoured.
"""

import pytest

from tc49.bench.runner import DEFAULT_K, Assembly, placement
from tc49.dispatcher import Dispatcher, FullRoute, Incremental
from tc49.dispatcher.dispatch import Active, Request, State, broken
from tc49.dispatcher.locking import Move, Refused
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout
from tests.harness import RUN_WANTED, events, live, load, press, runs, ticks

REQUEST_WANTED = "tc49/schedule/request_wanted"
REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"


def a_route(layout: Layout) -> Route:
    """`yard_w` to `yard_e` by the down line: four blocks, three transits."""
    route = candidates(
        layout, "yard_w", "yard_w.B", ("yard_e.A",), 500, 4, frozenset()
    )[0]
    assert route.blocks == ("yard_w", "dn_w", "dn_e", "yard_e")
    return route


def a_state() -> State:
    """`t` moving out of `yard_w` into `dn_w`, the move outstanding, and
    `idle` standing in `up_e`: every rule kept."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    request = Request("t-1", "t", "yard_w.B", ("yard_e.A",), 0, 0)
    move = Move("yard_w", route.transits[0], "dn_w", [], [])
    return State(
        layout,
        {"t": 500, "idle": 500, "gone": 500},
        {
            "yard_w": "t",
            route.transits[0]: "t",
            "dn_w": "t",
            "up_e": "idle",
        },
        {"t": "yard_w", "idle": "up_e"},
        {"t": Active(request, route, 1, move)},
        crossing={"t": route.transits[0]},
    )


def with_residue(state: State) -> State:
    """`gone`, taken off the layout while crossing `up_straight` with `up_w`
    reading occupied: the block and the transit kept as residue."""
    state.locks["up_w"] = "gone"
    state.locks["crossover.up_straight"] = "gone"
    state.residue |= {"up_w", "crossover.up_straight"}
    state.reported["up_w"] = True
    return state


def test_a_valid_state_breaks_no_rule() -> None:
    assert broken(a_state()) == []
    assert broken(with_residue(a_state())) == []


def test_a_placed_train_holds_the_lock_on_its_block() -> None:
    state = a_state()
    del state.locks["up_e"]
    assert broken(state) == ["idle stands in up_e, which is locked to nobody"]


def test_every_lock_is_a_placed_trains_or_residue() -> None:
    state = a_state()
    state.locks["up_w"] = "gone"
    assert broken(state) == ["up_w is locked to gone, which is not placed"]


def test_an_idle_train_holds_its_block_and_its_residue() -> None:
    state = a_state()
    state.locks["up_w"] = "idle"
    assert broken(state) == ["idle is idle and holds up_w"]


def test_residue_is_locked() -> None:
    state = with_residue(a_state())
    del state.locks["crossover.up_straight"]
    assert broken(state) == ["crossover.up_straight is residue and not locked"]


def test_a_residue_block_reads_occupied() -> None:
    state = with_residue(a_state())
    state.reported["up_w"] = False
    assert broken(state) == ["up_w is gone's residue and not read occupied"]


def test_a_residue_transit_keeps_one_of_its_blocks() -> None:
    state = with_residue(a_state())
    state.residue.discard("up_w")
    del state.locks["up_w"]
    assert broken(state) == [
        "crossover.up_straight is gone's residue with neither block kept"
    ]


def test_a_residue_block_is_not_where_its_holder_stands() -> None:
    state = a_state()
    state.residue.add("up_e")
    state.reported["up_e"] = True
    assert broken(state) == ["up_e is idle's residue and it stands there"]


def test_an_active_train_holds_its_move() -> None:
    state = a_state()
    del state.locks["dn_w"]
    assert broken(state) == ["t is moving through dn_w and not holding it"]


def test_an_active_train_is_crossing_its_move() -> None:
    state = a_state()
    del state.crossing["t"]
    assert broken(state) == [
        "t is moving through west_ladder.to_dn and not crossing it"
    ]


def test_an_active_train_with_no_move_is_not_crossing() -> None:
    state = a_state()
    state.active["t"].outstanding = None
    assert broken(state) == ["t has no move and is crossing"]


def test_an_active_train_is_placed() -> None:
    state = a_state()
    del state.block_of["t"]
    state.locks = {r: h for r, h in state.locks.items() if h != "t"}
    del state.crossing["t"]
    state.active["t"].outstanding = None
    assert broken(state) == ["t is active and not placed"]


def test_a_crossing_train_is_placed() -> None:
    state = a_state()
    state.crossing["gone"] = "crossover.up_straight"
    assert broken(state) == ["gone is crossing and not placed"]


def test_no_two_trains_lock_conflicting_transits() -> None:
    state = a_state()
    # `up_to_dn` crosses `dn_straight` at the crossover.
    state.locks["crossover.up_to_dn"] = "idle"
    state.locks["crossover.dn_straight"] = "idle2"
    state.locks["dn_e"] = "idle2"
    state.block_of["idle2"] = "dn_e"
    # Both active, so neither is an idle train holding a transit.
    for seq, train in enumerate(("idle", "idle2"), start=1):
        request = Request(f"{train}-1", train, "yard_w.B", (), seq, 0)
        state.active[train] = Active(request, a_route(state.layout), 0, None)
    assert state.layout.conflicts("crossover.up_to_dn", "crossover.dn_straight")
    line = "crossover.dn_straight locked to idle2 conflicts with crossover.up_to_dn"
    assert broken(state) == [f"{line} of idle"]


def test_equal_states_give_equal_lists() -> None:
    one, other = a_state(), a_state()
    for state in (one, other):
        del state.locks["up_e"]
        del state.locks["dn_w"]
    assert broken(one) == broken(other) == sorted(broken(one))
    assert len(broken(one)) == 2


@pytest.mark.parametrize("strategy", [Incremental, FullRoute])
def test_a_strategy_writes_nothing(strategy: type[Incremental | FullRoute]) -> None:
    """The dispatcher locks what a strategy returns; the strategy locks
    nothing itself (#761)."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    request = Request("t-1", "t", "yard_w.B", ("yard_e.A",), 0, 0)
    state = State(layout, {"t": 500}, {"yard_w": "t"}, {"t": "yard_w"}, {})
    before = dict(state.locks)

    launched = strategy(layout, 2).launch(request, "yard_w", "yard_w.B", state)
    assert launched is not None and not isinstance(launched, Refused)
    assert state.locks == before

    state.active["t"] = Active(request, route, 0, None)
    strategy(layout, 2).grant("t", state)
    assert state.locks == before


# -- at the bus --------------------------------------------------------------


def test_a_request_completed_over_a_stuck_detector_holds_the_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`yard_e` reads occupied before GO, a person releases over it, and
    `freight_1` is sent there. Its arrival repeats a level already held and
    is dropped, so the vacate behind it completes the move with the train
    still placed where it left: a placed train not holding its block."""
    assembly = live("crossover-yard/meet")
    press(assembly, OCCUPIED, {"block": "yard_e"})
    press(assembly, RUN_WANTED, {"run": "running"})
    assert runs(assembly) == ["running", "held", "running"]
    capsys.readouterr()

    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 8)

    assert events(assembly.trace, "request_completed")
    assert runs(assembly)[-1] == "held"
    said = capsys.readouterr().err
    assert any(
        line.startswith("dispatcher: lock table:") and "freight_1" in line
        for line in said.splitlines()
    ), said

    go_is_honoured(assembly)


def go_is_honoured(assembly: Assembly) -> None:
    """GO over the same broken rule leaves the run running through the next
    sweep: a rule still broken from the last check does not hold again."""
    press(assembly, RUN_WANTED, {"run": "running"})
    assert assembly.dispatcher.state.run == "running"
    assert broken(assembly.dispatcher.state)  # still broken, and not held for it
    press(assembly, REQUEST_WANTED, {"train": "express_2", "dest": ["up_w.B"]})
    ticks(assembly, 2)
    assert runs(assembly)[-1] == "running"


def a_bus_dispatcher() -> tuple[InProcessBus, Dispatcher, list[tuple[str, Payload]]]:
    """A dispatcher on a bus of its own over `crossover-yard/meet`, running,
    and everything it publishes."""
    layout, roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    said: list[tuple[str, Payload]] = []
    dispatcher = Dispatcher(
        bus,
        layout,
        roster,
        placement(scenario.trains),
        Incremental(layout, DEFAULT_K),
    )
    bus.subscribe(
        "tc49/dispatch/#", lambda topic, payload: said.append((topic, payload))
    )
    bus.drain()
    return bus, dispatcher, said


def deliver(bus: InProcessBus, topic: str, payload: Payload) -> None:
    bus.publish(topic, payload)
    bus.drain()


def test_a_vacate_before_the_occupy_ahead_holds_the_run() -> None:
    """A dead detector at `dn_w`'s entry: `yard_w` reads clear before `dn_w`
    reads occupied. The vacate releases `yard_w` while `freight_1` is still
    placed there, and the sweep it runs grants nothing."""
    bus, dispatcher, said = a_bus_dispatcher()
    assert dispatcher.state.run == "running"
    deliver(
        bus,
        REQUEST_SUBMITTED,
        {"id": "r-1", "train": "freight_1", "depart": "yard_w.B", "dest": ["yard_e.A"]},
    )
    granted = [p for t, p in said if t.endswith("/move_granted")]
    assert [p["into"] for p in granted] == ["dn_w"]

    mark = len(said)
    deliver(bus, VACATED, {"block": "yard_w"})

    assert dispatcher.state.run == "held"
    assert not [t for t, _ in said[mark:] if t.endswith("/move_granted")]

    # GO, and the next sweep — a request admitted runs one — leaves it
    # running over the rule still broken.
    deliver(bus, RUN_WANTED, {"run": "running"})
    assert dispatcher.state.run == "running"
    deliver(
        bus,
        REQUEST_SUBMITTED,
        {"id": "r-2", "train": "express_2", "depart": "up_e.A", "dest": ["up_w.B"]},
    )
    assert any(p.get("id") == "r-2" for t, p in said if t.endswith("/request_admitted"))
    assert broken(dispatcher.state)
    assert dispatcher.state.run == "running"
