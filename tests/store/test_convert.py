"""The mechanical conversion of a layout into a drawing (#43).

It converted the four hand-written railroads when drawings took over (#45),
and the round trip it has to satisfy outlives them: converting a derived
layout and deriving the result gives the same layout back, for every committed
railroad. That covers Gotthard's 19-transit junction and crossover-yard's
composed concurrency, neither of which is a layout anyone typed.
"""

from typing import Any

import pytest

from tc49.store.convert import to_drawing
from tests.store.railroads import RAILROADS, derive, read


@pytest.mark.parametrize("name", RAILROADS)
def test_converting_a_derived_layout_round_trips(name: str) -> None:
    layout = derive(read(f"{name}.drawing.yaml"))
    assert derive(to_drawing(layout)) == layout


def test_the_conversion_of_a_layout_is_symbols_and_wires() -> None:
    """One connection becomes one generic symbol whose pins are the block ends
    it holds; an end no connection holds becomes a terminal."""
    layout: dict[str, Any] = {
        "layout": "d",
        "units": "mm",
        "blocks": {"west": {"length": 1000}, "east": {"length": 1000}},
        "connections": {"gap": {"transits": {"span": ["west.B", "east.A"]}}},
    }
    assert to_drawing(layout) == {
        "drawing": "d",
        "units": "mm",
        "symbols": {
            "west": {"kind": "block", "length": 1000},
            "east": {"kind": "block", "length": 1000},
            "gap": {
                "kind": "connection",
                "pins": ["east_A", "west_B"],
                "transits": {"span": ["west_B", "east_A"]},
            },
            "west_A_stop": {"kind": "terminal"},
            "east_B_stop": {"kind": "terminal"},
        },
        "wires": [
            ["east.A", "gap.east_A"],
            ["west.B", "gap.west_B"],
            ["west.A", "west_A_stop.P"],
            ["east.B", "east_B_stop.P"],
        ],
    }


def test_concurrency_is_carried_verbatim() -> None:
    """What the drawn crossover composes, the converted one declares — the
    generic symbol is where composed concurrency ends up when geometry is
    dropped."""
    layout = derive(read("crossover-yard.drawing.yaml"))
    assert to_drawing(layout)["symbols"]["crossover"]["concurrent"] == [
        ["dn_straight", "up_straight"]
    ]
