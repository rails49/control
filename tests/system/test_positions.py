"""The scenario that puts point positions on the panel (#130, ui/PANEL.md).

The panel draws a point in the position `align` commanded it into, the road
that position does not offer faint (#98). Nothing in the repo drove that until
`beb-gotthard/positions`: it is the only drawing whose points carry addresses,
and a run over a drawing with none commands nothing and fades nothing.

So the scenario is checked the way the panel reads it — through the trace,
against the drawing — rather than by running the browser. What the panel holds
is a ledger of the last `align` naming each address, and what it can draw is an
address some symbol in the drawing wears; both are asserted here, because a
scenario rerouted onto unaddressed track, or a drawing whose addresses were
edited away, would leave the panel painting nothing and no other test would
notice.

The strategy is the default one, `FullRoute`, because that is what a live
session runs (`tc49 live`) and this scenario exists to be watched.
"""

from typing import Any

from tc49.store import AssetStore
from tc49.store.drawing import POSITIONS
from tests.harness import ROOT, events, load, run

SCENARIO = "beb-gotthard/positions"


def trace() -> str:
    layout, scenario = load(SCENARIO)
    return run(layout, scenario)


def commanded(trace: str) -> dict[str, str]:
    """Address -> the position it was last commanded into, which is the ledger
    the panel keeps: a point stays where the last `align` naming it left it."""
    lying: dict[str, str] = {}
    for line in events(trace, "align"):
        for point in line["points"]:
            lying[point["addr"]] = point["position"]
    return lying


def drawn() -> dict[str, set[str]]:
    """Address -> the points in the drawing wearing it. Two may share one, and
    then they answer to one accessory output and lie the same way."""
    drawing, _, _ = SCENARIO.partition("/")  # a scenario is layout-qualified
    document: dict[str, Any] = AssetStore(ROOT).drawing(drawing)
    wearers: dict[str, set[str]] = {}
    for name, spec in document["symbols"].items():
        addr = spec.get("addr")
        if addr is not None and spec["kind"] in POSITIONS:
            wearers.setdefault(addr, set()).add(name)
    return wearers


def test_the_run_leaves_points_lying_where_the_panel_can_draw_them() -> None:
    lying = commanded(trace())
    wearers = drawn()
    assert lying, f"{SCENARIO} commanded no point: nothing to draw a position on"
    assert all(addr in wearers for addr in lying), (
        f"{SCENARIO} commanded addresses no drawn point wears:"
        f" {sorted(set(lying) - set(wearers))}"
    )


def test_it_shows_both_positions_at_once() -> None:
    # A road set against is only legible beside one that is not, so the picture
    # worth watching has points lying each way when the run ends: sw1 and sw2
    # closed, the four sharing address 1 thrown along with sw3, sw14 and sw15.
    assert set(commanded(trace()).values()) == {"closed", "thrown"}
