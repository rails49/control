"""Which railroad the app answers for (#371).

One broker runs one railroad and a view needs to know which
([ADR-0059](../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 2, as amended by ADR-0060), so the binding of the layout interface
that is running states it: it is the one app bound to a railroad. Retained and
published from the constructor, like everything else this app says about the
railroad before anybody has asked.
"""

from tc49.layout import LayoutInterface
from tc49.layout.interface import RAILROAD
from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout
from tests.layout.railroad import build, document, heard, railroad, stock


def test_the_railroad_is_named_from_the_constructor() -> None:
    """With the stamp the bus put on it as it published: a state payload
    carries the run clock's reading, zero at the constructor (#240)."""
    clock = Clock()
    bus = InProcessBus(clock)
    LayoutInterface(bus, railroad(), stock(), clock)

    assert bus.last_values[RAILROAD] == {"at": 0.0, "name": "bench"}


def test_a_view_arriving_afterwards_is_served_the_name() -> None:
    """Which is the case that matters: a page joins a railroad that has been
    up for hours and reads which one it is looking at (ADR-0032)."""
    bus, _app = build()

    seen = heard(bus, RAILROAD)
    bus.drain()

    assert seen == [(RAILROAD, {"at": 0.0, "name": "bench"})]


def test_the_name_is_the_layouts_own() -> None:
    """The name the store lists the railroad under, and not one told to this
    app a second way: a drawing is filed under the name it declares and
    derives to a layout wearing it, so the two cannot disagree."""
    clock = Clock()
    bus = InProcessBus(clock)
    LayoutInterface(
        bus, Layout.from_document(document() | {"layout": "yard"}), stock(), clock
    )

    assert bus.last_values[RAILROAD]["name"] == "yard"
