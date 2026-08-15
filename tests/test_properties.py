"""The four properties of ARCHITECTURE.md, over the real assembly.

Every generated case wires scheduler, dispatcher, driver and simulator on
one in-process bus and interacts only by publishing and observing events, so
the bus contract gets thousands of adversarial runs for free. The layouts are
the fixed library of `tests/generate.py`; what varies is the workload.
"""

from typing import Any

import yaml
from hypothesis import given, note, settings

from tc49.bus import Payload
from tc49.dispatch import Request, State
from tc49.locking import FullRoute, Incremental, congested, resolve_depart, safety_view
from tc49.routing import candidates
from tc49.safety import safe
from tc49.store import AssetStore
from tests.generate import fixture_yaml, scenarios
from tests.harness import ROOT, Assembly, build, events, run

K = 2  # the default candidate budget; the k axis is swept by `tc49 sweep`
TICK_LIMIT = 100  # a backstop against live-lock, never the normal stop

EXAMPLES = settings(deadline=None, max_examples=200)


def first_workings(pending: tuple[Request, ...]) -> list[Request]:
    """The oldest still-pending request of each train — the only ones the
    dispatcher can act on, since a train's chained workings run in order."""
    seen: set[str] = set()
    oldest: list[Request] = []
    for req in pending:
        if req.train not in seen:
            seen.add(req.train)
            oldest.append(req)
    return oldest


def obstructed_blocks(
    route_blocks: tuple[str, ...], state: State, train: str
) -> list[str]:
    """The blocks of a route, beyond its origin, held by some other train."""
    return [
        block
        for block in route_blocks[1:]
        if state.locks.get(block) not in (None, train)
    ]


@given(scenarios())
@EXAMPLES
def test_safety_invariant_holds_after_every_grant(
    case: tuple[dict[str, Any], Any, Any],
) -> None:
    """Property 1. The bus drives, the assertion peeks: after each grant the
    library `safe()` is re-evaluated on the dispatcher's live state, so a
    violation fails at the grant that broke it rather than at the deadlock
    much later."""
    doc, layout, scenario = case
    note(fixture_yaml(doc))
    assembly = build(layout, scenario, Incremental, K)

    def check(topic: str, payload: Payload) -> None:
        assert safe(
            *safety_view(assembly.dispatcher.state)
        ), f"unsafe state after granting {payload}"

    assembly.bus.subscribe("tc49/dispatch/move_granted", check)
    assembly.simulator.run(TICK_LIMIT)
    assert safe(*safety_view(assembly.dispatcher.state))


def assert_quiescence_is_a_permanent_obstacle(assembly: Assembly) -> None:
    """The oracle of property 2, applied to a quiesced assembly.

    A circular wait is a cycle of trains stuck part-way through their routes,
    so the first half is that no train is active at all; the second is that
    every candidate route the dispatcher was allowed to try crosses a block
    held by another train — necessarily idle at quiescence, hence a permanent
    obstacle. Anything else is a policy bug.
    """
    state = assembly.dispatcher.state
    assert not state.active, "quiesced with a train part-way through its route"

    for req in first_workings(assembly.dispatcher.pending):
        note(f"pending: {req}")
        assert events(
            assembly.trace, "grant_refused", rid=req.id
        ), f"{req.id} is pending but was never refused"
        origin = state.block_of[req.train]
        routes = candidates(
            assembly.layout,
            origin,
            resolve_depart(req.depart, origin),
            req.arrivals,
            state.train_lengths[req.train],
            assembly.k,
            congested(state, req.train),
        )
        for route in routes:
            assert obstructed_blocks(
                route.blocks, state, req.train
            ), f"{req.id} is pending though {route.blocks} was clear"


@given(scenarios())
@EXAMPLES
def test_quiescence_is_always_a_permanent_obstacle(
    case: tuple[dict[str, Any], Any, Any],
) -> None:
    """Property 2, under the research core."""
    doc, layout, scenario = case
    note(fixture_yaml(doc))
    assembly = build(layout, scenario, Incremental, K)
    assembly.simulator.run(TICK_LIMIT)
    assert_quiescence_is_a_permanent_obstacle(assembly)


@given(scenarios())
@EXAMPLES
def test_differential_against_the_baseline(
    case: tuple[dict[str, Any], Any, Any],
) -> None:
    """Property 3. The same harness run twice with the locking strategy
    swapped, so the baseline gets the same oracle the research core does:
    both quiesce, and whatever either leaves behind is a permanent obstacle
    rather than a wedge.

    ARCHITECTURE.md states this property with a second, stronger half —
    "`Incremental` completes every request set `FullRoute` completes, in no
    more ticks" — and that half is **false**, which is what this suite exists
    to find out. Every form of it falls to adversarial search: the completed
    sets can be incomparable, the counts can favour either side, and even
    when both strategies complete exactly the same set `Incremental` can be
    slower. `scenarios/crossover-yard/route-blindness.scenario.yaml` is the
    shrunk counterexample, kept as the regression fixture for the
    congestion-aware costing (#33) that removed its mechanism; the write-up
    is in the scenario file. The dominance claim stays withdrawn: the
    throughput claim belongs to the measured benchmark workloads
    (BENCHMARKS.md), not to arbitrary ones.
    """
    doc, layout, scenario = case
    note(fixture_yaml(doc))
    for strategy in (FullRoute, Incremental):
        assembly = build(layout, scenario, strategy, K)
        assembly.simulator.run(TICK_LIMIT)
        assert_quiescence_is_a_permanent_obstacle(assembly)


@given(scenarios())
@EXAMPLES
def test_traces_are_byte_identical_across_runs(
    case: tuple[dict[str, Any], Any, Any],
) -> None:
    """Property 4. Each case run twice, the two trace byte streams identical
    in memory — the tie-break, grant-order and canonical-serialization
    promises. No trace files are committed; the goldens are metrics numbers
    and scenario YAML."""
    doc, layout, scenario = case
    note(fixture_yaml(doc))
    for strategy in (FullRoute, Incremental):
        first = run(layout, scenario, strategy, K, TICK_LIMIT)
        second = run(layout, scenario, strategy, K, TICK_LIMIT)
        assert first == second


@given(scenarios())
@settings(deadline=None, max_examples=25)
def test_generated_documents_are_committable_fixtures(
    case: tuple[dict[str, Any], Any, Any],
) -> None:
    """The shrink output is a scenario file: rendered as YAML text it passes
    the same asset-store validation a committed file gets, unchanged."""
    doc, _, scenario = case
    store = AssetStore(ROOT)
    assert store.validate_scenario(yaml.safe_load(fixture_yaml(doc))) == scenario
