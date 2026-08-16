"""Convert a layout document into the drawing that derives it.

This is how the four hand-written railroads were migrated (#43) before the
drawing became the only committed topology (#45), with no topology re-typed:
each block becomes a block symbol, each connection a generic connection symbol
carrying its transits and `concurrent` verbatim, and every block end a wire. A
block end that no connection holds gets a terminal symbol, which is how the
derived layout keeps the same terminal blocks.

The conversion is lossless by construction — deriving the drawing reproduces
the layout it came from, which `tests/store/test_convert.py` asserts by
round-tripping every committed railroad's derived layout. What the drawing
does not gain is the real geometry: a junction arrives as one opaque symbol
until someone redraws it from turnouts and crossings (#44).
"""

from typing import Any

from tc49.lib.layout import Layout


def to_drawing(doc: Any) -> dict[str, Any]:
    """The drawing document for a layout document, in canonical order."""
    layout = Layout.from_document(doc)

    symbols: dict[str, Any] = {
        block: {"kind": "block", "length": length}
        for block, length in layout.blocks.items()
    }
    wires: list[list[str]] = []

    for name, connection in layout.connections.items():
        ends = sorted({end for pair in connection.transits.values() for end in pair})
        symbols[name] = {
            "kind": "connection",
            "pins": [_pin(end) for end in ends],
            "transits": {
                transit: [_pin(a), _pin(b)]
                for transit, (a, b) in connection.transits.items()
            },
            **(
                {"concurrent": sorted(sorted(pair) for pair in connection.concurrent)}
                if connection.concurrent
                else {}
            ),
        }
        wires += [[end, f"{name}.{_pin(end)}"] for end in ends]

    for block in layout.blocks:
        for end in (f"{block}.A", f"{block}.B"):
            if end not in layout.end_connection:
                stop = f"{_pin(end)}_stop"
                symbols[stop] = {"kind": "terminal"}
                wires.append([end, f"{stop}.P"])

    return {
        "drawing": layout.name,
        **({"units": doc["units"]} if "units" in doc else {}),
        "symbols": symbols,
        "wires": wires,
    }


def _pin(end: str) -> str:
    """A block end as a pin name: `up_w.B` wires to the connection's `up_w_B`."""
    return end.replace(".", "_")
