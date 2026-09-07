"""The scenario document: what it places, what it asks for, and what it
refuses.

At the validator and not through the store, for the reason `tests/lib/
test_stock.py` gives about the roster's: what is under test is the schema and
its refusals, and a document written inline says what it is testing where the
assertion is.

That this file needs no `tmp_path` is the point of #494. The same three
refusals were reachable only through a temp directory holding a copy of the
whole catalogue, a drawing and a roster, with the drawing derived on the way
past — to assert one sentence about a train not being on a roster. A scenario
is only complete against a railroad and that railroad's stock, so both are
passed in and a test hands over the two it wants.
"""

from typing import Any

import pytest

from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.lib.scenario import validate_scenario
from tc49.lib.stock import validate_model, validate_roster

LAYOUT = Layout.from_document(
    {
        "layout": "mini",
        "blocks": {"a": {"length": 1000}, "b": {"length": 1000}},
        "connections": {"j": {"transits": {"ab": ["a.B", "b.A"]}}},
    }
)
"""Two blocks and the one connection between them, so `a.B` and `b.A` are the
ends a connection holds and `a.A` and `b.B` are the ends nothing does."""

CATALOGUE = {
    "wagon": validate_model(
        {"model": "wagon", "kind": "freight", "length": 400}, "wagon"
    )
}


def roster(*trains: str) -> Roster:
    """A railroad owning one car per train named, which is what makes each
    train **known** (ADR-0039). Their lengths are nothing this file's
    assertions turn on."""
    return validate_roster(
        {
            "roster": "mini",
            "cars": {f"{train}_car": {"model": "wagon"} for train in trains},
            "trains": {train: {"cars": [{"car": f"{train}_car"}]} for train in trains},
        },
        CATALOGUE,
    )


def document(**over: Any) -> dict[str, Any]:
    """A scenario standing one train in `a`, facing the end the connection
    holds, with one working across to `b`."""
    return {
        "scenario": "meet",
        "layout": "mini",
        "trains": {"pickup": {"at": "a", "facing": "A-to-B"}},
        "requests": [{"train": "pickup", "from": "a.B", "to": ["b.A"]}],
    } | over


def test_a_scenario_is_its_placement_and_its_workings() -> None:
    scenario = validate_scenario(document(), LAYOUT, roster("pickup"))

    assert (scenario.name, scenario.layout) == ("meet", "mini")
    assert scenario.trains["pickup"].at == "a"
    assert [request.arrivals for request in scenario.requests] == [("b.A",)]


def test_a_scenario_may_only_place_trains_the_roster_has() -> None:
    """A train's length is the roster's, so a scenario naming a train the
    railroad does not own has nothing to read (ADR-0039)."""
    doc = document()
    doc["trains"]["phantom"] = {"at": "b", "facing": "B-to-A"}

    with pytest.raises(ValueError, match="phantom.*roster"):
        validate_scenario(doc, LAYOUT, roster("pickup"))


def test_a_departure_end_the_layout_does_not_have_is_refused() -> None:
    """A 'from' entry naming a full end is checked against the railroad, so a
    working written over a block that is not there is caught where it was
    written rather than at run time."""
    doc = document(requests=[{"train": "pickup", "from": "z.B", "to": ["b.A"]}])

    with pytest.raises(ValueError, match="unknown block 'z'"):
        validate_scenario(doc, LAYOUT, roster("pickup"))


def test_a_departure_block_the_train_is_not_standing_in_is_refused() -> None:
    """A stated departure block must be the block the file leaves the train
    in. Nothing downstream catches this: at run time a stated block is a hint
    the dispatcher corrects from the route it chose, and in a file the same
    disagreement is a silently different experiment."""
    doc = document(requests=[{"train": "pickup", "from": "b.A", "to": ["b.A"]}])

    with pytest.raises(ValueError, match="departs 'b'.*stands in 'a'"):
        validate_scenario(doc, LAYOUT, roster("pickup"))


def test_a_train_facing_an_end_no_connection_holds_can_never_leave() -> None:
    """A placement is what every later working is composed from, so the nose
    is checked once here rather than as a rejection per request (#145)."""
    doc = document(trains={"pickup": {"at": "a", "facing": "B-to-A"}})

    with pytest.raises(ValueError, match="faces end 'a.A'"):
        validate_scenario(doc, LAYOUT, roster("pickup"))
