"""The six boundary conditions closing SAFETY.md, one scenario each (#29).

Each is scenario-shaped rather than a unit test, so each runs over the bus
with the real assembly and asserts through the **trace** — the same events a
future UI would consume — rather than through dispatcher internals. The
scenario files are ordinary committed fixtures, the format a shrunk
Hypothesis counterexample comes out in (ARCHITECTURE.md, tests).

Every one of these runs under `Incremental`: `FullRoute` never consults
`safe()`, so it is not the strategy any of these conditions is about.
"""

from typing import Any

from tc49.locking import Incremental
from tests.harness import events, load, run


def trace_of(scenario_id: str) -> str:
    layout, scenario = load(scenario_id)
    return run(layout, scenario, Incremental)


def latencies(trace: str) -> dict[str, int]:
    """Request id -> completion stamp minus the tick it was released on."""
    released = {line["id"]: line["tick"] for line in events(trace, "request_submitted")}
    return {
        line["id"]: line["tick"] - released[line["id"]]
        for line in events(trace, "request_completed")
    }


def arrival_block(chosen: dict[str, Any]) -> str:
    """The block a route_chosen event commits its train to parking on."""
    return chosen["route"][-1]


def coexisting_commitments(trace: str) -> list[tuple[str, str]]:
    """Any two requests whose committed routes aimed at one block at once.

    A commitment opens at `route_chosen` and closes at `request_completed`,
    so this walks the trace and reports overlaps — empty is the invariant.
    """
    open_now: dict[str, str] = {}
    clashes: list[tuple[str, str]] = []
    for line in events(trace):
        if line["event"] == "route_chosen":
            block = arrival_block(line)
            clashes += [
                (other, line["id"]) for other, b in open_now.items() if b == block
            ]
            open_now[line["id"]] = block
        elif line["event"] == "request_completed":
            open_now.pop(line["id"], None)
    return clashes


def test_pessimism_about_idle_trains_refuses_the_launch_outright() -> None:
    # Boundary condition 1. The first increment runner needs (w_main) is free,
    # so the lock table alone would let it go; safe() refuses on e_main, three
    # steps down the route, because an idle train's block is permanently
    # unavailable. The consequence is the point: runner never moves at all, so
    # it never reaches the position from which the two would wedge each other.
    trace = trace_of("single-track-meet/pessimism")
    assert events(trace, "request_completed") == []
    assert events(trace, "route_chosen") == []
    assert events(trace, "move_granted") == []
    assert events(trace, "cross") == []  # never entered w_main, never wedged
    refusals = events(trace, "grant_refused", rid="runner-1")
    assert refusals, "the launch must be refused, not deadlocked"
    assert refusals[-1]["reason"] == "unsafe"
    assert {"resource": "e_main", "holder": "blocker"} in refusals[-1]["obstacles"]


def test_an_obstructed_arrival_block_holds_back_only_the_request_that_needs_it() -> (
    None
):
    # Boundary condition 2. Same obstruction, same layout, same tick: what
    # separates the two requests is only how many arrival blocks each names.
    trace = trace_of("single-track-meet/arrival-obstruction")
    completed = {line["id"] for line in events(trace, "request_completed")}
    assert completed == {"flexible-1"}

    # The one-block request is unroutable-to for as long as squatter sits there.
    refusals = events(trace, "grant_refused", rid="fixed-1")
    assert refusals[-1]["reason"] == "unsafe"
    assert {"resource": "east_1", "holder": "squatter"} in refusals[-1]["obstacles"]

    # The set names the obstructed block first and still finishes, at the
    # other one — sorted first by congestion-aware costing (#33), so the
    # obstructed candidate is never tried at all.
    [chosen] = events(trace, "route_chosen", rid="flexible-1")
    assert arrival_block(chosen) == "east_2"
    assert chosen["k_tried"] == 1


def test_overlapping_arrival_sets_commit_to_different_blocks() -> None:
    # Boundary condition 3. Two requests naming the same two arrival ends are
    # not a shared destination: each commits to one end at launch.
    trace = trace_of("single-track-meet/shared-destination")
    assert {line["id"] for line in events(trace, "request_completed")} == {
        "first-1",
        "second-1",
    }
    committed = {
        line["id"]: arrival_block(line) for line in events(trace, "route_chosen")
    }
    assert committed == {"first-1": "east_1", "second-1": "east_2"}
    # And the refusal half: no block is ever the destination of two open
    # commitments at once, which is what safe() guarantees by refusing the
    # second launch while the first is active.
    assert coexisting_commitments(trace) == []


def test_a_completed_train_obstructs_exactly_as_a_parked_one_does() -> None:
    # Boundary condition 4. Completion changes the dispatcher's bookkeeping and
    # nothing in the lock table.
    trace = trace_of("crossover-yard/completion")
    [done] = events(trace, "request_completed")
    assert done["id"] == "arriver-1"

    # Completing released what was behind the train and nothing else: the
    # standing lock on the block it now occupies is never given up.
    assert all(
        "dn_e" not in line["resources"] for line in events(trace, "lock_released")
    )

    # The latecomer's request arrives after that completion and meets an
    # ordinary held block, named for the train standing in it.
    [admitted] = events(trace, "request_admitted", rid="latecomer-1")
    assert admitted["tick"] > done["tick"]
    refusals = events(trace, "grant_refused", rid="latecomer-1")
    assert refusals[-1]["reason"] == "held"
    assert refusals[-1]["obstacles"] == [{"resource": "dn_e", "holder": "arriver"}]


def test_a_train_may_re_enter_blocks_its_previous_working_released() -> None:
    # Boundary condition 5. A route is a simple path, so what self-intersects
    # is the train across two requests — and `feasible` checks blocks against
    # other trains only, so its own recent footprint is not an obstacle.
    trace = trace_of("crossover-yard/revisit")
    assert {line["id"] for line in events(trace, "request_completed")} == {
        "shuttle-1",
        "shuttle-2",
    }
    out, back = events(trace, "route_chosen")
    assert back["route"] == list(reversed(out["route"]))

    # Every step of the return route beyond its origin is ground the outward
    # working released — the self-intersection is total, not incidental.
    [done] = events(trace, "request_completed", rid="shuttle-1")
    released = {
        resource
        for line in events(trace, "lock_released")
        if line["tick"] <= done["tick"]
        for resource in line["resources"]
    }
    assert set(back["route"][1:]) <= released


def test_starvation_shows_up_in_max_latency_and_the_run_still_drains() -> None:
    # Boundary condition 6. Starvation is not deadlock: waiter is refused at
    # every grant phase until the train sitting in its arrival block receives a
    # request of its own — SAFETY.md's conditional-liveness proviso being
    # discharged — and then completes.
    trace = trace_of("single-track-meet/starvation")
    assert {line["id"] for line in events(trace, "request_completed")} == {
        "waiter-1",
        "squatter-1",
    }  # the run drains

    latency = latencies(trace)
    assert latency["waiter-1"] > latency["squatter-1"]

    # The wait, not the journey: waiter's route is four transits, so four ticks
    # of it are travel and the rest is refusals it accumulated while pending.
    [chosen] = events(trace, "route_chosen", rid="waiter-1")
    transits = len([step for step in chosen["route"] if "." in step])
    assert transits == 4
    assert latency["waiter-1"] >= 2 * transits

    # Refused at every phase from admission until squatter cleared the block.
    refused_at = [
        line["tick"] for line in events(trace, "grant_refused", rid="waiter-1")
    ]
    assert refused_at == list(range(1, chosen["tick"]))
