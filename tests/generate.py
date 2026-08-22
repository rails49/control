"""The Hypothesis generator: scenario documents over the fixed layout library.

Deadlock is a property of request interleaving, not of exotic topology
(ARCHITECTURE.md, tests), so the layouts are hand-written and fixed and the
search pressure goes on placements and chained request sequences. Arrival-end
*sets* are drawn too, and shrink toward singletons, so a counterexample
reduces to the tightest request that still breaks.

What is drawn is a scenario **document** — the very mapping a
``*.scenario.yaml`` file holds — and it is validated by the asset store on
the way out. A shrunk failure is therefore a committable fixture, printed by
``fixture_yaml`` in the same format as the scenarios in ``scenarios/``.
"""

from typing import Any

import yaml
from hypothesis import strategies as st

from tc49.lib.layout import Layout, connected_end, end_letter
from tc49.lib.roster import Roster
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore
from tests.harness import ROOT

LIBRARY = ("facing-pair", "single-track-meet", "crossover-yard")

_STORE = AssetStore(ROOT)


def _load(layout_id: str) -> Layout:
    layout = _STORE.get(layout_id)
    assert isinstance(layout, Layout)
    return layout


LAYOUTS = {layout_id: _load(layout_id) for layout_id in LIBRARY}

# The stock each library railroad owns (ADR-0039). A drawn scenario places
# `t1`..`t3` from it and states no length of its own: the roster gives those
# three one length that fits every block of their railroad, so the fit check
# prunes nothing and the pressure stays on interleaving.
ROSTERS = {layout_id: _STORE.roster(layout_id) for layout_id in LIBRARY}

# Every end of every block, including the outer end of a terminal block —
# which is pruned `no_entry` at admission, and is drawn so that pruning and
# the surviving-set logic take pressure too.
ENDS = {
    layout_id: sorted(f"{block}.{end}" for block in layout.blocks for end in "AB")
    for layout_id, layout in LAYOUTS.items()
}

Document = dict[str, Any]


@st.composite
def scenario_documents(
    draw: st.DrawFn, max_trains: int = 3, max_workings: int = 2
) -> Document:
    """One scenario document: placements, then chained workings per train.

    Draw order mirrors the sweep generator of BENCHMARKS.md — placements
    first, then per train in id order a chain in which only the first
    working states a departure block. Every request arrives at boundary 0, so
    contention is maximal and makespan is drain time.
    """
    layout_id = draw(st.sampled_from(LIBRARY))
    layout = LAYOUTS[layout_id]
    blocks = sorted(layout.blocks)

    count = draw(st.integers(1, min(max_trains, len(blocks))))
    placements = draw(
        st.lists(st.sampled_from(blocks), min_size=count, max_size=count, unique=True)
    )
    # Facing is scheduler state nothing in a batch run reads (ADR-0019), so a
    # constant keeps the search pressure on interleaving — except on a
    # terminal block, where A may be the end no connection holds and the
    # store refuses the placement (#145). `connected_end` picks the letter.
    trains = {
        f"t{i + 1}": {
            "at": block,
            "facing": end_letter(connected_end(layout, f"{block}.A")),
        }
        for i, block in enumerate(placements)
    }

    requests: list[Document] = []
    for train, placement in zip(trains, placements):
        for working in range(draw(st.integers(1, max_workings))):
            end = draw(st.sampled_from(["A", "B"]))
            arrivals = draw(
                st.lists(
                    st.sampled_from(ENDS[layout_id]),
                    min_size=1,
                    max_size=3,
                    unique=True,
                )
            )
            requests.append(
                {
                    "train": train,
                    # A chained working cannot state its block: where the
                    # previous one parked the train is a dispatcher choice.
                    "from": f"{placement}.{end}" if working == 0 else end,
                    "to": sorted(arrivals),  # the list is unordered (LAYOUT.md)
                    "at": 0,
                }
            )

    return {
        "scenario": "generated",
        "layout": layout_id,
        "trains": trains,
        "requests": requests,
    }


@st.composite
def scenarios(draw: st.DrawFn) -> tuple[Document, Layout, Roster, Scenario]:
    """A drawn document with the layout, the roster and the validated scenario
    it names."""
    doc = draw(scenario_documents())
    layout_id = doc["layout"]
    return doc, LAYOUTS[layout_id], ROSTERS[layout_id], _STORE.validate_scenario(doc)


def fixture_yaml(doc: Document) -> str:
    """The document as a committable scenario file."""
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=None)
