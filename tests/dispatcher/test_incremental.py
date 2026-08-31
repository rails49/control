"""Incremental locking gated by safe(): issue #27's acceptance criteria."""

from tc49.dispatcher import Incremental
from tc49.dispatcher.dispatch import Active, Request, State
from tc49.dispatcher.locking import Move
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.layout import Layout
from tc49.lib.scenario import RequestSpec, Scenario, TrainSpec
from tc49.store import AssetStore
from tests.harness import ROOT, events, load, run, stock


def final_boundary(trace: str) -> int:
    return events(trace)[-1]["boundary"]


def held_spans(trace: str, resource: str) -> list[tuple[int, int]]:
    """[start, end) boundary spans during which `resource` was locked."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for line in events(trace):
        if line["event"] == "lock_granted" and resource in line["resources"]:
            start = line["boundary"]
        if line["event"] == "lock_released" and resource in line["resources"]:
            assert start is not None
            spans.append((start, line["boundary"]))
            start = None
    return spans


def overlap(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> bool:
    return any(s1 < e2 and s2 < e1 for s1, e1 in a for s2, e2 in b)


def assert_no_conflicting_transits_overlap(trace: str, layout: Layout) -> None:
    """Trace-wide invariant: two same-connection transits are ever held at
    once only if the connection declares them concurrent."""
    transits = sorted(
        {
            resource
            for line in events(trace, "lock_granted")
            for resource in line["resources"]
            if "." in resource
        }
    )
    for i, a in enumerate(transits):
        for b in transits[i + 1 :]:
            if overlap(held_spans(trace, a), held_spans(trace, b)):
                assert not layout.conflicts(a, b), f"{a} and {b} held at once"


def test_facing_pair_refuses_a_launch_and_quiesces() -> None:
    layout = AssetStore(ROOT).get("facing-pair")
    assert isinstance(layout, Layout)
    scenario = Scenario(
        "swap",
        "facing-pair",
        {"t_west": TrainSpec("west", "B"), "t_east": TrainSpec("east", "A")},
        (
            RequestSpec("t_west", "west.B", ("east.A",), 0),
            RequestSpec("t_east", "east.A", ("west.B",), 0),
        ),
    )
    # `run()` returning is quiescence.
    trace = run(layout, stock(t_west=500, t_east=500), scenario, Incremental)
    assert len(events(trace, "request_admitted")) == 2
    assert events(trace, "request_completed") == []
    assert events(trace, "move") == []  # never a collision, never movement
    refusals = events(trace, "grant_refused")
    assert refusals, "both launches must be refused, not deadlocked"
    assert {"resource": "east", "holder": "t_east"} in refusals[0]["obstacles"]


def test_meet_completes_under_incremental_in_no_more_boundaries() -> None:
    layout, _roster, scenario = load("crossover-yard/meet")
    full = run(layout, _roster, scenario)
    incremental = run(layout, _roster, scenario, Incremental)
    completed = {line["id"] for line in events(incremental, "request_completed")}
    assert completed == {"freight_1-1", "express_2-1", "freight_1-2"}
    assert final_boundary(incremental) <= final_boundary(full)


def test_concurrent_pair_held_simultaneously_and_undeclared_pairs_never() -> None:
    layout, _roster, _ = load("crossover-yard/meet")
    straights = Scenario(
        "parallel",
        "crossover-yard",
        {"t_up": TrainSpec("up_w", "B"), "t_dn": TrainSpec("dn_w", "B")},
        (
            RequestSpec("t_up", "up_w.B", ("up_e.A",), 0),
            RequestSpec("t_dn", "dn_w.B", ("dn_e.A",), 0),
        ),
    )
    trace = run(layout, stock(t_up=600, t_dn=600), straights, Incremental)
    assert {line["id"] for line in events(trace, "request_completed")} == {
        "t_up-1",
        "t_dn-1",
    }
    # The declared concurrent pair is held at the same time.
    assert overlap(
        held_spans(trace, "crossover.up_straight"),
        held_spans(trace, "crossover.dn_straight"),
    )
    assert_no_conflicting_transits_overlap(trace, layout)

    crossing = Scenario(
        "crossing",
        "crossover-yard",
        {"t_up": TrainSpec("up_w", "B"), "t_dn": TrainSpec("dn_w", "B")},
        (
            RequestSpec("t_up", "up_w.B", ("dn_e.A",), 0),
            RequestSpec("t_dn", "dn_w.B", ("up_e.A",), 0),
        ),
    )
    trace = run(layout, stock(t_up=600, t_dn=600), crossing, Incremental)
    assert {line["id"] for line in events(trace, "request_completed")} == {
        "t_up-1",
        "t_dn-1",
    }
    # The undeclared (conflicting) pair is never held at the same time.
    assert not overlap(
        held_spans(trace, "crossover.up_to_dn"),
        held_spans(trace, "crossover.dn_to_up"),
    )
    assert_no_conflicting_transits_overlap(trace, layout)
    [refused] = events(trace, "grant_refused")
    assert refused["reason"] == "transit_conflict"


def test_shared_destination_refusal_names_the_committed_train() -> None:
    # SAFETY.md boundary condition: two active trains committed to the same
    # block can never both appear in a witness ordering, so the second
    # launch is refused unsafe — naming the block and the train already
    # committed to it, though nothing there is locked yet. On gotthard-v0 the
    # two trains approach airolo_1 over different connections (blue 2 and
    # the yellow), so nothing else refuses first.
    layout = AssetStore(ROOT).get("gotthard-v0")
    assert isinstance(layout, Layout)
    scenario = Scenario(
        "collide",
        "gotthard-v0",
        {
            "t_blue": TrainSpec("claro_1", "B"),
            "t_yellow": TrainSpec("claro_3", "A"),
        },
        (
            RequestSpec("t_blue", "claro_1.B", ("airolo_1.A",), 0),
            RequestSpec("t_yellow", "claro_3.A", ("airolo_1.A",), 0),
        ),
    )
    trace = run(layout, stock(t_blue=900, t_yellow=900), scenario, Incremental)
    assert events(trace, "request_completed", rid="t_blue-1")
    refused = events(trace, "grant_refused", rid="t_yellow-1")
    assert refused[0]["reason"] == "unsafe"
    assert refused[0]["obstacles"][0] == {"resource": "airolo_1", "holder": "t_blue"}


def test_route_blindness_is_fixed_by_congestion_aware_costing() -> None:
    # The differential's committed counterexample (#28, property 3), shrunk by
    # Hypothesis: before congestion-aware costing (#33), `Incremental` was a
    # boundary SLOWER here, because only `FullRoute`'s up-front locks let t2's
    # launch see t1 across its first candidate. Costing restores that signal
    # from committed routes, so both strategies now steer t2 to the up line
    # at the first candidate and finish together. See the scenario file.
    layout, _roster, scenario = load("crossover-yard/route-blindness")
    full = run(layout, _roster, scenario)
    incremental = run(layout, _roster, scenario, Incremental)
    assert {line["id"] for line in events(full, "request_completed")} == {
        "t1-1",
        "t2-1",
    }
    assert {line["id"] for line in events(incremental, "request_completed")} == {
        "t1-1",
        "t2-1",
    }
    # t1's route congests dn_e — locked under FullRoute, committed under
    # Incremental — so t2's candidate over the up line sorts first for both.
    assert [line["k_tried"] for line in events(full, "route_chosen")] == [1, 1]
    assert [line["k_tried"] for line in events(incremental, "route_chosen")] == [1, 1]
    assert final_boundary(full) == 3
    assert final_boundary(incremental) == 3


def test_transits_are_never_held_across_a_wait() -> None:
    # Lemma 1 made observable: under Incremental every lock grant beyond the
    # startup standing locks is one transit with its far block, atomically,
    # and every release is the origin block with its transit, atomically.
    layout, _roster, scenario = load("crossover-yard/meet")
    trace = run(layout, _roster, scenario, Incremental)
    for line in events(trace, "lock_granted"):
        resources = line["resources"]
        if line["boundary"] == 0 and len(resources) == 1:
            continue  # a standing lock seeded from the scenario
        assert len(resources) == 2
        assert "." in resources[0] and "." not in resources[1]
    for line in events(trace, "lock_released"):
        resources = line["resources"]
        assert len(resources) == 2
        assert "." not in resources[0] and "." in resources[1]


def a_state(layout: Layout, route: Route, locks: dict[str, str]) -> State:
    """One active train, `t`, standing at the head of `route`."""
    request = Request("t-1", "t", f"{route.blocks[0]}.B", (), 0, 0)
    return State(
        layout,
        {"t": 500, "other": 500},
        dict(locks),
        {"t": route.blocks[0]},
        {"t": Active(request, route, 0, None)},
    )


def a_route(layout: Layout, train: str) -> Route:
    """The first candidate route of at least three blocks that `layout`
    offers from `train`'s standing block, so there is a second increment to
    reach for at all."""
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
                    if len(route.blocks) >= 3:
                        return route
    raise AssertionError("no route of three blocks in this layout")


def test_a_grant_reaches_one_increment_past_what_it_needs() -> None:
    """Depth two: the grant locks the increment it needs and then the one
    after it, so the train stands with two blocks locked ahead rather than
    one — which is the difference between `caution` and `clear`."""
    layout, _roster, _ = load("gotthard-v0/saturation")
    route = a_route(layout, "t")
    state = a_state(layout, route, {route.blocks[0]: "t"})

    move = Incremental(layout, 2).grant("t", state)
    assert isinstance(move, Move)
    assert move.locked == [route.transits[0], route.blocks[1]]
    assert move.ahead == [route.transits[1], route.blocks[2]]
    assert state.locks[route.blocks[2]] == "t"


def test_an_unavailable_second_increment_refuses_nothing() -> None:
    """The second increment is asked for, not required. With it held by
    another train the move is granted exactly as before, reporting nothing
    ahead — and reporting nothing ahead is what `caution` means, not an
    error the train has to wait on."""
    layout, _roster, _ = load("gotthard-v0/saturation")
    route = a_route(layout, "t")
    state = a_state(layout, route, {route.blocks[0]: "t", route.blocks[2]: "other"})

    move = Incremental(layout, 2).grant("t", state)
    assert isinstance(move, Move)
    assert move.locked == [route.transits[0], route.blocks[1]]
    assert move.ahead == []
    assert state.locks[route.blocks[2]] == "other"


def test_a_route_with_nothing_two_blocks_ahead_reaches_for_nothing() -> None:
    """The last grant of a route has no second increment to ask for, and
    that is not a failure either."""
    layout, _roster, _ = load("gotthard-v0/saturation")
    route = a_route(layout, "t")
    short = Route(route.blocks[:2], route.transits[:1])
    state = a_state(layout, short, {short.blocks[0]: "t"})

    move = Incremental(layout, 2).grant("t", state)
    assert isinstance(move, Move)
    assert move.ahead == []
