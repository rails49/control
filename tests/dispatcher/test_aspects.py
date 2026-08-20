"""What the dispatcher says every signal is showing (ADR-0025)."""

import json
from itertools import pairwise

from tc49.dispatcher import Incremental
from tc49.dispatcher.dispatch import (
    Active,
    Request,
    State,
    aspects,
)
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.layout import Layout, end_on, opposite_end
from tests.harness import events, load, run


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
    layout, _ = load("crossover-yard/meet")
    shown = aspects(a_state(layout, a_route(layout), 0))

    assert "yard_e.A" in shown  # the end trains enter and leave by
    assert "yard_e.B" not in shown  # the buffer stop
    assert all(end in layout.end_connection for end in shown)


def test_the_aspect_is_how_far_ahead_the_dispatcher_has_locked() -> None:
    layout, _ = load("crossover-yard/meet")
    route = a_route(layout)
    end = end_on(layout, route.blocks[0], route.transits[0])

    for ahead, expected in ((0, "stop"), (1, "approach"), (2, "clear"), (3, "clear")):
        shown = aspects(a_state(layout, route, ahead))
        assert shown[end] == expected, f"{ahead} ahead should show {expected}"


def test_an_end_no_train_is_leaving_by_shows_stop() -> None:
    """`stop` is not a rule of its own: it falls out of nothing being locked
    beyond the end. The one train's departure end is the only one that moves,
    including the other end of the very block it stands in."""
    layout, _ = load("crossover-yard/meet")
    route = a_route(layout)
    end = end_on(layout, route.blocks[0], route.transits[0])
    shown = aspects(a_state(layout, route, 2))

    assert [e for e, a in shown.items() if a != "stop"] == [end]
    other = opposite_end(end)
    assert shown.get(other, "stop") == "stop"


def test_the_grant_and_the_state_topic_tell_the_same_story() -> None:
    """Two projections of one truth (ADR-0025): the aspect on `move_granted`
    is the same aspect the state topic shows at that train's departure end, so
    a run's counts of each agree exactly."""
    layout, scenario = load("gotthard/saturation")
    trace = run(layout, scenario, Incremental)

    on_grants: dict[str, int] = {}
    for line in events(trace, "move_granted"):
        on_grants[line["aspect"]] = on_grants.get(line["aspect"], 0) + 1

    on_topic: dict[str, int] = {}
    for line in events(trace, "aspects"):
        for shown in line["aspects"].values():
            if shown != "stop":
                on_topic[shown] = on_topic.get(shown, 0) + 1

    assert on_grants == on_topic
    assert set(on_grants) == {"approach", "clear"}, "the run must show both"


def test_the_state_topic_carries_the_whole_picture_and_only_on_a_change() -> None:
    """One topic rather than one per end, so a late subscriber gets every end
    at once. Republishing an unchanged map would say nothing, so it does not
    happen: consecutive values always differ."""
    layout, scenario = load("gotthard/saturation")
    trace = run(layout, scenario, Incremental)
    published = [line["aspects"] for line in events(trace, "aspects")]

    assert published, "the run published no aspects at all"
    signalled = set(published[0])
    assert all(set(shown) == signalled for shown in published)
    assert all(a != b for a, b in pairwise(published))


def test_a_trace_line_keeps_the_inventory_field_order() -> None:
    layout, scenario = load("crossover-yard/meet")
    trace = run(layout, scenario, Incremental)
    granted = next(line for line in trace.splitlines() if '"move_granted"' in line)
    assert list(json.loads(granted)) == [
        "boundary",
        "event",
        "id",
        "train",
        "transit",
        "into",
        "aspect",
    ]
