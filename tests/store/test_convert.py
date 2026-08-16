"""The mechanical migration (#43): a hand-written layout converts to a
drawing that derives it back, unchanged.

The round trip over every committed railroad is the whole claim — blocks,
transits, hand-picked names and `concurrent` all survive, and the derived
layout passes the validator. The committed drawings are that conversion with
the reasoning comments moved across, and `test_drawing.py` checks those files
themselves; a drawing refined by hand from real symbols (#44) is no longer
the converter's output, so the two are asserted separately.
"""

from typing import Any

import pytest

from tc49.lib.layout import Layout
from tc49.store.convert import to_drawing
from tests.store.railroads import RAILROADS, canonical, derive, read


@pytest.mark.parametrize("name", RAILROADS)
def test_converting_a_committed_layout_round_trips(name: str) -> None:
    layout = read(f"{name}.layout.yaml")
    assert derive(to_drawing(layout)) == canonical(layout)


@pytest.mark.parametrize("name", RAILROADS)
def test_the_converted_drawing_derives_a_validator_clean_layout(name: str) -> None:
    written = Layout.from_document(read(f"{name}.layout.yaml"))
    derived = Layout.from_document(derive(to_drawing(read(f"{name}.layout.yaml"))))

    assert derived.blocks == written.blocks
    assert derived.terminal_blocks == written.terminal_blocks
    assert derived.end_connection == written.end_connection


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
    symbol = to_drawing(read("crossover-yard.layout.yaml"))["symbols"]["crossover"]
    assert symbol["concurrent"] == [["dn_straight", "up_straight"]]
