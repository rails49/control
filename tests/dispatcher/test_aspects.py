"""What the dispatcher says every signal is showing (ADR-0025)."""

import json
from itertools import pairwise

from tc49.bench.runner import assemble
from tc49.dispatcher import Incremental
from tc49.dispatcher.dispatch import (
    Active,
    Request,
    State,
    aspects,
)
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.inventory import HELD, RUNNING
from tc49.lib.layout import Layout, block_of, end_on, opposite_end
from tests.harness import RUN_WANTED, events, load, press, run, ticks


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
    """`t` standing at the head of `route` with `ahead` blocks locked past it."""
    locks = {route.blocks[i]: "t" for i in range(ahead + 1)}
    request = Request("t-1", "t", f"{route.blocks[0]}.B", (), 0, 0)
    return State(
        layout,
        {"t": 500},
        locks,
        {"t": route.blocks[0]},
        {"t": Active(request, route, 0, None)},
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
    end = end_on(layout, route.blocks[0], route.transits[0])

    for ahead, expected in ((0, "stop"), (1, "caution"), (2, "clear"), (3, "clear")):
        shown = aspects(a_state(layout, route, ahead))
        assert shown[end] == expected, f"{ahead} ahead should show {expected}"


def test_an_end_no_train_is_leaving_by_shows_stop() -> None:
    """`stop` is not a rule of its own: it falls out of nothing being locked
    beyond the end. The one train's departure end is the only one that moves,
    including the other end of the very block it stands in."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = a_route(layout)
    end = end_on(layout, route.blocks[0], route.transits[0])
    shown = aspects(a_state(layout, route, 2))

    assert [e for e, a in shown.items() if a != "stop"] == [end]
    other = opposite_end(end)
    assert shown.get(other, "stop") == "stop"


def test_a_held_run_puts_every_signal_to_stop() -> None:
    """An aspect answers "may the train in this block leave via this end",
    and while held the answer is no at every end (ADR-0037). The real aspects
    return on release: the state is a gate over the reading, not a rewrite of
    it, so nothing about the locks has to be undone and put back."""
    layout, _roster, _ = load("crossover-yard/meet")
    state = a_state(layout, a_route(layout), 2)
    running = aspects(state)
    assert "clear" in running.values()

    state.run = HELD
    held = aspects(state)
    assert set(held.values()) == {"stop"}
    assert set(held) == set(running)  # the same ends, every time (ADR-0032)

    state.run = RUNNING
    assert aspects(state) == running


def test_holding_and_releasing_both_republish_the_aspects() -> None:
    """The topic is what a lineside signal and a panel read, so both
    transitions have to reach it — a `clear` left standing over a held
    railroad is a green light over dead track."""
    assembly = assemble(*load("crossover-yard/meet"))
    ticks(assembly, 2)
    before = [line["aspects"] for line in events(assembly.trace, "aspects")][-1]
    assert "clear" in before.values()

    press(assembly, RUN_WANTED, {"run": "held"})
    held = [line["aspects"] for line in events(assembly.trace, "aspects")][-1]
    assert set(held.values()) == {"stop"}

    press(assembly, RUN_WANTED, {"run": "running"})
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
