"""What the dispatcher says every signal is showing (ADR-0025)."""

import json
from collections.abc import Callable
from itertools import pairwise

import pytest

from tc49.bench.runner import Assembly, assemble, assemble_live
from tc49.dispatcher import FullRoute, Incremental
from tc49.dispatcher.dispatch import (
    Active,
    Request,
    State,
    aspects,
)
from tc49.dispatcher.locking import Move
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.inventory import DRAINING, OFF, ON
from tc49.lib.layout import Layout, block_of, opposite_end, transit_ends
from tc49.lib.scenario import TrainSpec
from tests.harness import events, load, power, press, run, ticks
from tests.invariants import check

ASPECTS = "tc49/dispatch/state/aspects"
DISPUTED = "tc49/dispatch/state/disputed"
OCCUPIED = "tc49/layout/block_occupied"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"
UNKNOWN_SENSORS = "tc49/layout/state/unknown_sensors"
VACATED = "tc49/layout/block_vacated"


def a_route(layout: Layout) -> Route:
    """The first route of at least four blocks the layout offers, so there is
    room to hold two ahead and still have route left."""
    for block in sorted(layout.blocks):
        for end in ("A", "B"):
            for arrival in sorted(layout.blocks):
                if arrival == block:
                    continue
                for route in candidates(
                    layout,
                    block,
                    f"{block}.{end}",
                    (f"{arrival}.A",),
                    500,
                    4,
                    frozenset(),
                ):
                    if len(route.blocks) >= 4:
                        return route
    raise AssertionError("no route of four blocks in this layout")


def a_state(layout: Layout, route: Route, ahead: int) -> State:
    """`t` standing at the head of `route` with `ahead` blocks locked past it,
    the power on."""
    locks = {route.blocks[i]: "t" for i in range(ahead + 1)}
    request = Request("t-1", "t", f"{route.blocks[0]}.B", (), 0)
    return State(
        layout,
        {"t": 500},
        locks,
        {"t": route.blocks[0]},
        {"t": Active(request, route, 0, None)},
        power=ON,
    )


def test_only_ends_something_can_leave_by_carry_a_signal() -> None:
    """A siding's blind end could only ever show `stop`, and a signal that can
    never clear is furniture. Such an end is in no connection, so it simply
    does not appear."""
    layout, _roster, _ = load("crossover-yard/meet")
    shown = aspects(a_state(layout, a_route(layout), 0))

    assert "yard_e.A" in shown  # the end trains enter and leave by
    assert "yard_e.B" not in shown  # the buffer stop
    assert all(end in layout.end_connection for end in shown)


def test_the_aspect_is_how_far_ahead_the_dispatcher_has_locked() -> None:
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    ends = transit_ends(layout, route.blocks[0], route.transits[0])
    assert ends is not None
    end = ends[0]

    for ahead, expected in ((0, "stop"), (1, "caution"), (2, "clear"), (3, "clear")):
        shown = aspects(a_state(layout, route, ahead))
        assert shown[end] == expected, f"{ahead} ahead should show {expected}"


def exit_of(layout: Layout, route: Route, i: int) -> str:
    """The end the route's `i`th transit leaves `route.blocks[i]` by."""
    ends = transit_ends(layout, route.blocks[i], route.transits[i])
    assert ends is not None
    return ends[0]


def test_an_end_no_train_is_leaving_by_shows_stop() -> None:
    """`stop` is not a rule of its own: it falls out of nothing being locked
    beyond the end. Only the exits along the train's locked blocks move
    (ADR-0093), and not the other end of the very block it stands in."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    shown = aspects(a_state(layout, route, 2))

    assert {e for e, a in shown.items() if a != "stop"} == {
        exit_of(layout, route, 0),
        exit_of(layout, route, 1),
    }
    other = opposite_end(exit_of(layout, route, 0))
    assert shown.get(other, "stop") == "stop"


def test_every_signal_along_the_locked_blocks_shows_its_aspect() -> None:
    """Two blocks held ahead: `clear` leaving the block the train stands in,
    `caution` leaving the next, and `stop` leaving the last it holds — each
    counted from its own block (ADR-0093)."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    shown = aspects(a_state(layout, route, 2))

    assert shown[exit_of(layout, route, 0)] == "clear"
    assert shown[exit_of(layout, route, 1)] == "caution"
    assert shown[exit_of(layout, route, 2)] == "stop"


def test_a_committed_block_that_is_not_locked_shows_stop() -> None:
    """The route goes on past the locks, and its signals there stay at stop
    until the blocks beyond them are locked: an unlocked block can still go
    to another train."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    shown = aspects(a_state(layout, route, 1))

    assert shown[exit_of(layout, route, 0)] == "caution"
    for i in range(1, len(route.transits)):
        assert shown[exit_of(layout, route, i)] == "stop", route.blocks[i]


def test_a_passed_signal_shows_stop_once_the_next_block_reads_occupied() -> None:
    """With the move into the second block outstanding, the entered block
    read occupied and the origin not yet clear, the dispatcher records the
    train in the entered block: the signal it passed shows `stop`, and the
    entered block's exit its own aspect (ADR-0093)."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    state = a_state(layout, route, 3)
    move = Move(route.blocks[0], route.transits[0], route.blocks[1], [], [])
    state.active["t"] = Active(state.active["t"].request, route, 1, move)

    state.block_of["t"] = route.blocks[0]  # the entered block not yet occupied
    before = aspects(state)
    assert before[exit_of(layout, route, 0)] == "clear"

    state.block_of["t"] = route.blocks[1]  # it now reads occupied
    after = aspects(state)
    assert after[exit_of(layout, route, 0)] == "stop"
    assert after[exit_of(layout, route, 1)] == "clear"
    assert after[exit_of(layout, route, 2)] == "caution"


def test_power_not_on_puts_every_signal_to_stop() -> None:
    """An aspect answers "may a train that reaches this end leave by it"
    (ADR-0093), and while `draining` or `off` the answer is no at every end:
    nothing is granted (ADR-0078). The real aspects return with the power: the power is
    a gate over the reading, not a rewrite of it, so nothing about the locks
    has to be undone and put back."""
    layout, _roster, _ = load("crossover-yard/meet")
    state = a_state(layout, a_route(layout), 2)
    routing = aspects(state)
    assert "clear" in routing.values()

    for value in (DRAINING, OFF):
        state.power = value
        stopped = aspects(state)
        assert set(stopped.values()) == {"stop"}, value
        assert set(stopped) == set(routing)  # the same ends (ADR-0032)

    state.power = ON
    assert aspects(state) == routing


def test_power_going_off_and_on_both_republish_the_aspects() -> None:
    """The topic is what a lineside signal and a panel read, so both
    transitions have to reach it — a `clear` left standing over a railroad
    that grants nothing is a green light over a train that will not be let
    past it."""
    assembly = assemble(*load("crossover-yard/meet"))
    ticks(assembly, 2)
    before = [line["aspects"] for line in events(assembly.trace, "aspects")][-1]
    assert "clear" in before.values()

    press(assembly, *power(OFF))
    stopped = [line["aspects"] for line in events(assembly.trace, "aspects")][-1]
    assert set(stopped.values()) == {"stop"}

    press(assembly, *power(ON))
    after = [line["aspects"] for line in events(assembly.trace, "aspects")][-1]
    assert after == before


def test_the_grant_and_the_state_topic_tell_the_same_story() -> None:
    """Two projections of one truth (ADR-0025): the aspect a grant carries is
    the aspect the state topic shows, in the same sweep, at the end the train
    departs by — the near end of the granted transit."""
    layout, _roster, scenario = load("crossover-yard/meet")
    trace = run(layout, _roster, scenario)

    lines = events(trace)
    first = next(i for i, line in enumerate(lines) if line["event"] == "move_granted")
    granted = lines[first]
    connection, _, transit = str(granted["transit"]).partition(".")
    a, b = layout.connections[connection].transits[transit]
    departed_by = b if block_of(a) == granted["into"] else a
    shown = next(line for line in lines[first:] if line["event"] == "aspects")
    assert granted["aspect"] == shown["aspects"][departed_by]

    grants = {
        str(line["aspect"])
        for line in events(
            run(*load("reversing-loops-v0/saturation"), Incremental), "move_granted"
        )
    }
    assert grants == {"caution", "clear"}, "the runs must show both"


def test_the_state_topic_carries_the_whole_picture_and_only_on_a_change() -> None:
    """One topic rather than one per end, so a late subscriber gets every end
    at once. Republishing an unchanged map would say nothing, so it does not
    happen: consecutive values always differ."""
    layout, _roster, scenario = load("reversing-loops-v0/saturation")
    trace = run(layout, _roster, scenario, Incremental)
    published = [line["aspects"] for line in events(trace, "aspects")]

    assert published, "the run published no aspects at all"
    signalled = set(published[0])
    assert all(set(shown) == signalled for shown in published)
    assert all(a != b for a, b in pairwise(published))


STOOD = {
    "freight_1": TrainSpec("yard_w", "A-to-B"),
    "express_2": TrainSpec("up_e", "B-to-A"),
}

each_strategy = pytest.mark.parametrize("strategy", [Incremental, FullRoute])


def under_way(strategy: type[Incremental | FullRoute]) -> Assembly:
    """`freight_1` granted its move out of `yard_w`, on its way to `yard_e` by
    `dn_w` and `dn_e`, with the power on and the invariants checked."""
    layout, roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, roster, STOOD, strategy)
    check(assembly, strategy)
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    return assembly


def reading(assembly: Assembly, topic: str, block: str) -> None:
    press(assembly, topic, {"block": block})


def proceed(assembly: Assembly) -> dict[str, str]:
    """Every signal showing anything but `stop`."""
    shown = assembly.bus.last_values[ASPECTS]["aspects"]
    return {end: aspect for end, aspect in shown.items() if aspect != "stop"}


def granted(assembly: Assembly) -> list[str]:
    return [line["into"] for line in events(assembly.trace, "move_granted")]


@each_strategy
def test_a_train_whose_block_read_clear_in_a_drain_goes_on_with_the_power(
    strategy: type[Incremental | FullRoute],
) -> None:
    """Drained and its detector dropped: the power coming back grants its next
    move, and the signals along its route show (#1164)."""
    assembly = under_way(strategy)
    reading(assembly, OCCUPIED, "dn_w")
    press(assembly, *power(DRAINING))
    reading(assembly, VACATED, "yard_w")
    reading(assembly, VACATED, "dn_w")
    press(assembly, *power(ON))

    assert granted(assembly) == ["dn_w", "dn_e"]
    assert proceed(assembly) == {"dn_w.B": "clear", "dn_e.B": "caution"}


@each_strategy
def test_a_train_whose_block_read_clear_with_the_power_on_is_granted(
    strategy: type[Incremental | FullRoute],
) -> None:
    """The arrival block drops before the origin clears. A clear reading
    disputes nothing, so the move ends and the next is granted (#1164)."""
    assembly = under_way(strategy)
    reading(assembly, OCCUPIED, "dn_w")
    reading(assembly, VACATED, "dn_w")
    reading(assembly, VACATED, "yard_w")

    assert granted(assembly) == ["dn_w", "dn_e"]
    assert assembly.bus.last_values[DISPUTED]["blocks"] == []


@each_strategy
def test_a_placement_leaves_nothing_showing_from_the_old_route(
    strategy: type[Incremental | FullRoute],
) -> None:
    """A person says where the train stands. Its request goes with the
    placement (ADR-0049), so nothing of the route is left lit (#1160)."""
    assembly = under_way(strategy)
    reading(assembly, OCCUPIED, "dn_w")
    reading(assembly, VACATED, "dn_w")
    reading(assembly, VACATED, "yard_w")

    press(assembly, PLACEMENT_WANTED, {"train": "freight_1", "block": "up_w"})

    assert assembly.bus.last_values[DISPUTED]["blocks"] == []
    assert proceed(assembly) == {}


@each_strategy
def test_depth_stops_at_a_locked_block_that_reads_occupied(
    strategy: type[Incremental | FullRoute],
) -> None:
    """A locomotive put on a block the train has locked: nothing is sent into
    it (ADR-0077), so the signal over that move shows `stop` and the one
    before it counts only that far. The aspects return when it reads clear
    (#1160)."""
    assembly = under_way(strategy)
    before = proceed(assembly)
    assert before["yard_w.B"] == "clear"
    assert assembly.dispatcher.state.locks["dn_e"] == "freight_1"

    reading(assembly, OCCUPIED, "dn_e")
    assert proceed(assembly) == {"yard_w.B": "caution"}

    reading(assembly, VACATED, "dn_e")
    assert proceed(assembly) == before


@each_strategy
def test_a_train_waits_under_stop_at_a_locked_block_that_reads_occupied(
    strategy: type[Incremental | FullRoute],
) -> None:
    """It reaches the block before the locomotive and stands there, under
    `stop` rather than `caution`, until the block reads clear (#1160)."""
    assembly = under_way(strategy)
    reading(assembly, OCCUPIED, "dn_e")
    reading(assembly, OCCUPIED, "dn_w")
    reading(assembly, VACATED, "yard_w")

    assert granted(assembly) == ["dn_w"]
    assert proceed(assembly) == {}

    reading(assembly, VACATED, "dn_e")

    assert granted(assembly) == ["dn_w", "dn_e"]


def reads_occupied(assembly: Assembly) -> None:
    reading(assembly, OCCUPIED, "yard_e")


def reads_clear(assembly: Assembly) -> None:
    reading(assembly, VACATED, "yard_e")


def goes_out_of_use(assembly: Assembly) -> None:
    row = {"sensor": "yard_e.A", "reason": "no report for 3 s", "reported": True}
    press(assembly, UNKNOWN_SENSORS, {"sensors": [row]})


def comes_back_into_use(assembly: Assembly) -> None:
    press(assembly, UNKNOWN_SENSORS, {"sensors": []})


each_failure_past_the_locks = pytest.mark.parametrize(
    ("fails", "recovers"),
    [(reads_occupied, reads_clear), (goes_out_of_use, comes_back_into_use)],
)


def arrives_in_dn_w(assembly: Assembly) -> None:
    reading(assembly, OCCUPIED, "dn_w")
    reading(assembly, VACATED, "yard_w")


@each_failure_past_the_locks
def test_a_signal_shows_stop_over_a_train_refused_its_next_move(
    fails: Callable[[Assembly], None], recovers: Callable[[Assembly], None]
) -> None:
    """`yard_e`, past what `freight_1` has locked, cannot be finished through,
    so `Incremental` refuses the move into `dn_e` though the train holds it. No
    signal along its route says it may go, and it keeps its locks. The signals
    return with the grant, in the sweep that follows the failure ending
    (#1160)."""
    assembly = under_way(Incremental)
    fails(assembly)
    arrives_in_dn_w(assembly)

    assert granted(assembly) == ["dn_w"]
    assert events(assembly.trace, "grant_refused")[-1]["reason"] == "unsafe"
    assert proceed(assembly) == {}
    assert assembly.dispatcher.state.locks["dn_e"] == "freight_1"

    recovers(assembly)

    assert granted(assembly) == ["dn_w", "dn_e"]
    assert proceed(assembly) == {"dn_w.B": "clear", "dn_e.B": "caution"}


@each_failure_past_the_locks
def test_a_train_on_its_way_keeps_its_signals_until_it_is_refused(
    fails: Callable[[Assembly], None], recovers: Callable[[Assembly], None]
) -> None:
    """A refusal is what puts them to `stop`, and nothing asks for the next move
    until the one under way has ended (#1160)."""
    assembly = under_way(Incremental)
    before = proceed(assembly)

    fails(assembly)

    assert proceed(assembly) == before


@each_failure_past_the_locks
def test_a_signal_stands_over_a_train_granted_past_the_same_failure(
    fails: Callable[[Assembly], None], recovers: Callable[[Assembly], None]
) -> None:
    """`FullRoute` holds the whole route, so it grants the move into `dn_e`
    where `Incremental` refuses it, and the signal says so (#1160)."""
    assembly = under_way(FullRoute)
    fails(assembly)
    arrives_in_dn_w(assembly)

    assert granted(assembly) == ["dn_w", "dn_e"]
    assert proceed(assembly) == {"dn_w.B": "caution"}


def test_a_grant_with_its_second_block_reading_occupied_is_at_caution() -> None:
    """The grant reads the depth the signal shows, so the train moves slowly
    enough to stop at the next signal (ADR-0093, decision 4; #1160). `FullRoute`
    alone: `Incremental` never locks a block that reads occupied ahead of the
    grant, and refuses this one as unsafe."""
    assembly = under_way(FullRoute)
    reading(assembly, OCCUPIED, "yard_e")
    reading(assembly, OCCUPIED, "dn_w")
    reading(assembly, VACATED, "yard_w")

    last = events(assembly.trace, "move_granted")[-1]
    assert (last["into"], last["aspect"]) == ("dn_e", "caution")


@each_strategy
def test_a_crossing_train_whose_origin_reads_clear_keeps_its_signals(
    strategy: type[Incremental | FullRoute],
) -> None:
    """The ordinary railroad: a train between two blocks is not disputed, so
    the signals ahead of it stand (#1160)."""
    assembly = under_way(strategy)
    before = proceed(assembly)

    reading(assembly, VACATED, "yard_w")

    assert assembly.bus.last_values[DISPUTED]["blocks"] == []
    assert proceed(assembly) == before


def test_a_trace_line_keeps_the_inventory_field_order() -> None:
    layout, _roster, scenario = load("crossover-yard/meet")
    trace = run(layout, _roster, scenario, Incremental)
    granted = next(line for line in trace.splitlines() if '"move_granted"' in line)
    assert list(json.loads(granted)) == [
        "time",
        "event",
        "id",
        "train",
        "transit",
        "into",
        "aspect",
    ]
