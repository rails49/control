"""The trains a rebuild under the same name took off the layout, and why
(#709).

A picture is kept through a rebuild of the railroad under the same name
(ADR-0071), and `restored` places a pictured train again only where its
block still exists and still holds it. A train it leaves off is listed on
`tc49/dispatch/state/unfit` with the block it stood in, so the run view can
say which trains a person has to come and place, and why.
"""

from dataclasses import replace
from typing import Any

from tc49.bench.runner import DEFAULT_K
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.dispatcher.dispatch import ALLOCATION, UNFIT
from tc49.lib.bus import InProcessBus
from tests.harness import load, retaining

MOVED: dict[str, Any] = {
    "trains": {"express_2": "up_w", "freight_1": "dn_e"},
    "crossing": {},
    "locks": {},
    "requests": [],
}
"""The picture the last build left: `freight_1`, 1100 long, in `dn_e`."""


def rebuilt(
    picture: dict[str, Any] | None, blocks: dict[str, int | None]
) -> tuple[InProcessBus, list[Any]]:
    """A dispatcher for a run an operator drives — no cold placement — built
    on `crossover-yard` with `blocks` changed (None drops one), over a bus
    that kept `picture`; and the `trains` of every `unfit` row it
    publishes."""
    layout, roster, _ = load("crossover-yard/meet")
    drawn = {**layout.blocks, **blocks}
    layout = replace(
        layout, blocks={block: at for block, at in drawn.items() if at is not None}
    )
    bus = retaining({} if picture is None else {ALLOCATION: picture})
    rows: list[Any] = []
    bus.subscribe(UNFIT, lambda _, payload: rows.append(payload["trains"]))
    Dispatcher(bus, layout, roster, {}, FullRoute(layout, DEFAULT_K))
    bus.drain()
    return bus, rows


def test_a_dispatcher_with_nothing_to_take_off_publishes_an_empty_list() -> None:
    _, rows = rebuilt(None, {})

    assert rows == [[]]


def test_a_rebuild_that_drops_a_placed_trains_block_lists_it_as_gone() -> None:
    _, rows = rebuilt(MOVED, {"dn_e": None})

    assert rows == [[{"train": "freight_1", "block": "dn_e", "why": "gone"}]]


def test_a_rebuild_that_shortens_the_block_below_the_train_lists_it_as_short() -> None:
    _, rows = rebuilt(MOVED, {"dn_e": 1000})

    assert rows == [[{"train": "freight_1", "block": "dn_e", "why": "short"}]]


def test_a_train_that_still_fits_is_not_listed() -> None:
    _, rows = rebuilt(MOVED, {})

    assert rows == [[]]


def test_placing_a_listed_train_republishes_the_row_without_it() -> None:
    bus, rows = rebuilt(MOVED, {"dn_e": 1000})

    bus.publish(
        "tc49/dispatch/placement_wanted", {"train": "freight_1", "block": "dn_w"}
    )
    bus.drain()

    assert rows[-1] == []
    assert bus.last_values[UNFIT]["trains"] == []


def test_placing_a_train_that_is_not_listed_publishes_nothing_more() -> None:
    bus, rows = rebuilt(MOVED, {"dn_e": 1000})

    bus.publish(
        "tc49/dispatch/placement_wanted", {"train": "express_2", "block": "up_e"}
    )
    bus.drain()

    assert len(rows) == 1
