"""Incremental locking gated by safe(): issue #27's acceptance criteria."""

from tc49.dispatcher import Incremental
from tc49.lib.layout import Layout
from tc49.lib.scenario import RequestSpec, Scenario, TrainSpec
from tc49.store import AssetStore
from tests.harness import ROOT, events, load, run


def final_tick(trace: str) -> int:
    return events(trace)[-1]["tick"]


def held_spans(trace: str, resource: str) -> list[tuple[int, int]]:
    """[start, end) tick spans during which `resource` was locked."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for line in events(trace):
        if line["event"] == "lock_granted" and resource in line["resources"]:
            start = line["tick"]
        if line["event"] == "lock_released" and resource in line["resources"]:
            assert start is not None
            spans.append((start, line["tick"]))
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
        {"t_west": TrainSpec(500, "west"), "t_east": TrainSpec(500, "east")},
        (
            RequestSpec("t_west", "west.B", ("east.A",), 0),
            RequestSpec("t_east", "east.A", ("west.B",), 0),
        ),
    )
    trace = run(layout, scenario, Incremental)  # run() returning is quiescence
    assert len(events(trace, "request_admitted")) == 2
    assert events(trace, "request_completed") == []
    assert events(trace, "cross") == []  # never a collision, never movement
    refusals = events(trace, "grant_refused")
    assert refusals, "both launches must be refused, not deadlocked"
    assert {"resource": "east", "holder": "t_east"} in refusals[0]["obstacles"]


def test_meet_completes_under_incremental_in_no_more_ticks() -> None:
    layout, scenario = load("crossover-yard/meet")
    full = run(layout, scenario)
    incremental = run(layout, scenario, Incremental)
    completed = {line["id"] for line in events(incremental, "request_completed")}
    assert completed == {"freight_1-1", "express_2-1", "freight_1-2"}
    assert final_tick(incremental) <= final_tick(full)


def test_concurrent_pair_held_simultaneously_and_undeclared_pairs_never() -> None:
    layout, _ = load("crossover-yard/meet")
    straights = Scenario(
        "parallel",
        "crossover-yard",
        {"t_up": TrainSpec(600, "up_w"), "t_dn": TrainSpec(600, "dn_w")},
        (
            RequestSpec("t_up", "up_w.B", ("up_e.A",), 0),
            RequestSpec("t_dn", "dn_w.B", ("dn_e.A",), 0),
        ),
    )
    trace = run(layout, straights, Incremental)
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
        {"t_up": TrainSpec(600, "up_w"), "t_dn": TrainSpec(600, "dn_w")},
        (
            RequestSpec("t_up", "up_w.B", ("dn_e.A",), 0),
            RequestSpec("t_dn", "dn_w.B", ("up_e.A",), 0),
        ),
    )
    trace = run(layout, crossing, Incremental)
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
    # committed to it, though nothing there is locked yet. On gotthard the
    # two trains approach airolo_1 over different connections (blue 2 and
    # the yellow), so nothing else refuses first.
    layout = AssetStore(ROOT).get("gotthard")
    assert isinstance(layout, Layout)
    scenario = Scenario(
        "collide",
        "gotthard",
        {"t_blue": TrainSpec(900, "claro_1"), "t_yellow": TrainSpec(900, "claro_3")},
        (
            RequestSpec("t_blue", "claro_1.B", ("airolo_1.A",), 0),
            RequestSpec("t_yellow", "claro_3.A", ("airolo_1.A",), 0),
        ),
    )
    trace = run(layout, scenario, Incremental)
    assert events(trace, "request_completed", rid="t_blue-1")
    refused = events(trace, "grant_refused", rid="t_yellow-1")
    assert refused[0]["reason"] == "unsafe"
    assert refused[0]["obstacles"][0] == {"resource": "airolo_1", "holder": "t_blue"}


def test_route_blindness_is_fixed_by_congestion_aware_costing() -> None:
    # The differential's committed counterexample (#28, property 3), shrunk by
    # Hypothesis: before congestion-aware costing (#33), `Incremental` was a
    # tick SLOWER here, because only `FullRoute`'s up-front locks let t2's
    # launch see t1 across its first candidate. Costing restores that signal
    # from committed routes, so both strategies now steer t2 to the up line
    # at the first candidate and finish together. See the scenario file.
    layout, scenario = load("crossover-yard/route-blindness")
    full = run(layout, scenario)
    incremental = run(layout, scenario, Incremental)
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
    assert final_tick(full) == 3
    assert final_tick(incremental) == 3


def test_transits_are_never_held_across_a_wait() -> None:
    # Lemma 1 made observable: under Incremental every lock grant beyond the
    # startup standing locks is one transit with its far block, atomically,
    # and every release is the origin block with its transit, atomically.
    layout, scenario = load("crossover-yard/meet")
    trace = run(layout, scenario, Incremental)
    for line in events(trace, "lock_granted"):
        resources = line["resources"]
        if line["tick"] == 0 and len(resources) == 1:
            continue  # a standing lock seeded from the scenario
        assert len(resources) == 2
        assert "." in resources[0] and "." not in resources[1]
    for line in events(trace, "lock_released"):
        resources = line["resources"]
        assert len(resources) == 2
        assert "." not in resources[0] and "." in resources[1]
