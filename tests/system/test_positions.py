"""The scenario that puts point positions on the panel (#130, ui/PANEL.md).

The panel draws a point in the position `align` commanded it into, the road
that position does not offer faint (#98). Nothing in the repo drove that until
`gotthard/positions`: it is the only drawing whose points carry addresses,
and a run over a drawing with none commands nothing and fades nothing.

So the scenario is checked the way the panel reads it — through the trace,
against the drawing — rather than by running the browser. What the panel holds
is a ledger of the last `align` naming each address, and what it can draw is an
address some symbol in the drawing wears; both are asserted here, because a
scenario rerouted onto unaddressed track, or a drawing whose addresses were
edited away, would leave the panel painting nothing and no other test would
notice.

The UI suite walks the same path in miniature, over a hand-copied drawing and a
hand-written `align` (#150). It cannot read either asset, so the last test here
holds a mirror of what that copy encodes and fails when the run or the drawing
stops agreeing with it.

The strategy is `Incremental`, because that is what a live session runs
(`tc49 live`, #165) and this scenario exists to be watched. It is named here
rather than defaulted: `run` is the batch loop, whose own default is the
`FullRoute` baseline.
"""

from dataclasses import dataclass
from typing import Any

from tc49.dispatcher import Incremental
from tc49.store import AssetStore
from tc49.store.drawing import POSITIONS
from tests.harness import ROOT, events, load, run

SCENARIO = "gotthard/positions"
UI_SUITE = "ui/test/points.test.ts"  # the suite that copies part of this one


def trace() -> str:
    layout, _roster, scenario = load(SCENARIO)
    return run(layout, _roster, scenario, Incremental)


def commanded(trace: str) -> dict[str, str]:
    """Address -> the position it was last commanded into, which is the ledger
    the panel keeps: a point stays where the last `align` naming it left it."""
    lying: dict[str, str] = {}
    for line in events(trace, "align"):
        for point in line["points"]:
            lying[point["addr"]] = point["position"]
    return lying


def symbols() -> dict[str, dict[str, Any]]:
    """The drawing the scenario runs on, symbol by symbol."""
    drawing, _, _ = SCENARIO.partition("/")  # a scenario is layout-qualified
    document: dict[str, Any] = AssetStore(ROOT).drawing(drawing)
    return document["symbols"]


def drawn() -> dict[str, set[str]]:
    """Address -> the points in the drawing wearing it. Two may share one, and
    then they answer to one accessory output and lie the same way."""
    wearers: dict[str, set[str]] = {}
    for name, spec in symbols().items():
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
    # closed, the four sharing `dccex/1` thrown along with sw3, sw14 and sw15.
    assert set(commanded(trace()).values()) == {"closed", "thrown"}


@dataclass(frozen=True)
class Miniature:
    """What the UI suite transcribes from this scenario and its drawing.

    That suite walks the panel's whole alignment path — the pairs `align`
    carries, the ledger they populate, the drawing that turns an address
    back into a symbol, the class the artwork paints — over four hand-copied
    symbols and one hand-written `align`. Its own assertions hold that copy
    together, but nothing there can read the originals: no YAML reaches the
    `ui` package, and none should. So the copy is checked against them here.
    """

    # Connection -> what each of its `align` commands carries, address to
    # position, in the order the run publishes them. Only the connections the
    # miniature draws: it draws j1, so j2 is nobody's business here.
    aligned: dict[str, list[dict[str, str]]]
    # Symbol -> the kind and the address it is drawn with. The miniature draws
    # turnouts, and reads a position off the address (ADR-0022), so a symbol
    # that changed kind or address would make it fiction either way.
    points: dict[str, tuple[str, str]]
    # Which of those symbols wear an address the run commands nowhere, and so
    # are drawn with both of their roads still on offer.
    uncommanded: list[str]


MINIATURE = Miniature(
    aligned={"j1": [{"dccex/1": "thrown", "dccex/5": "closed", "dccex/6": "thrown"}]},
    points={
        "sw1": ("turnout", "dccex/5"),
        "sw2": ("turnout", "dccex/5"),
        "sw3": ("turnout", "dccex/6"),
        "sw4": ("turnout", "dccex/7"),
    },
    uncommanded=["sw4"],
)


def transcribed(trace: str) -> Miniature:
    """The same facts, read off the real run and the real drawing."""
    aligned: dict[str, list[dict[str, str]]] = {name: [] for name in MINIATURE.aligned}
    for line in events(trace, "align"):
        if line["connection"] in aligned:
            aligned[line["connection"]].append(
                {point["addr"]: point["position"] for point in line["points"]}
            )
    points = {
        name: (str(spec["kind"]), str(spec.get("addr", "unaddressed")))
        for name, spec in symbols().items()
        if name in MINIATURE.points
    }
    lying = commanded(trace)
    return Miniature(
        aligned=aligned,
        points=points,
        uncommanded=sorted(
            name for name, (_, addr) in points.items() if addr not in lying
        ),
    )


def test_the_ui_miniature_still_transcribes_the_real_thing() -> None:
    assert transcribed(trace()) == MINIATURE, (
        f"the run or the drawing has moved under {UI_SUITE}, which hand-copies"
        " j1's alignment and four of the drawing's points and cannot read"
        " either original. Bring that copy and this constant back into line"
        " together."
    )
