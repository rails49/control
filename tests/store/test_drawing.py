"""Tests at the drawing seam: the schema, the three derivation passes, and
the refusals (docs/store/DRAWING.md).

The end-to-end proof is the committed railroads: each derives a layout the
validator accepts, with the shape its drawing describes. The rest are
hand-built documents, kept small enough to read as a statement about one pass
each.
"""

from collections import defaultdict
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from random import Random
from typing import Any, cast

import pytest
import yaml

from tc49.lib.layout import Layout, Point
from tc49.store import AssetStore
from tc49.store.drawing import BEND, LIBRARY, POSITIONS, Drawing, Use
from tests.store.railroads import RAILROADS, derive, read


def block(length: int = 1000) -> dict[str, Any]:
    return {"kind": "block", "length": length}


def two_blocks(**symbols: Any) -> dict[str, Any]:
    """`west` and `east` capped at their outer ends, plus whatever the test
    wires between them."""
    return {
        "drawing": "d",
        "symbols": {
            "west": block(),
            "east": block(),
            "west_stop": {"kind": "terminal"},
            "east_stop": {"kind": "terminal"},
            **symbols,
        },
        "wires": [["west.A", "west_stop.P"], ["east.B", "east_stop.P"]],
    }


def gap_symbol(*, named: bool = True) -> dict[str, Any]:
    return {
        "kind": "connection",
        "pins": ["A", "B"],
        "transits": {"span": ["A", "B"]} if named else [["A", "B"]],
    }


def flipped(wire: Any) -> Any:
    """A wire with its two pins the other way round, in either written form."""
    if isinstance(wire, dict):
        spec = cast(dict[str, Any], wire)
        return {**spec, "pins": list(reversed(cast(list[Any], spec["pins"])))}
    return list(reversed(cast(list[Any], wire)))


def spanned(**symbols: Any) -> dict[str, Any]:
    doc = two_blocks(gap=gap_symbol(), **symbols)
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "east.A"]]
    return doc


# --- the committed drawings ------------------------------------------------


def committed_drawing(name: str) -> Drawing:
    return Drawing.from_document(read(f"{name}.drawing.yaml"))


def committed(name: str) -> Layout:
    """A committed drawing, as the apps read it: derived and validated."""
    return Layout.from_document(derive(read(f"{name}.drawing.yaml")))


@pytest.mark.parametrize("name", RAILROADS)
def test_a_committed_drawing_derives_a_validator_clean_layout(name: str) -> None:
    assert committed(name).name == name


def test_facing_pair_derives_two_blocks_and_the_gap_between_them() -> None:
    layout = committed("facing-pair")
    assert layout.blocks == {"east": 1000, "west": 1000}
    assert layout.connections["gap"].transits == {
        "east_A__west_B": ("east.A", "west.B")
    }
    assert layout.terminal_blocks == frozenset({"west", "east"})


def test_single_track_meet_derives_a_throat_and_a_switch_at_each_end() -> None:
    layout = committed("single-track-meet")
    assert sorted(layout.connections) == [
        "east_switch",
        "east_throat",
        "west_switch",
        "west_throat",
    ]
    assert layout.terminal_blocks == frozenset({"west_1", "west_2", "east_1", "east_2"})
    # Every throat funnels into one block, so nothing here is concurrent.
    assert all(not c.concurrent for c in layout.connections.values())


def test_gotthard_v0_derives_one_junction_at_airolo_and_three_at_claro() -> None:
    layout = committed("gotthard-v0")
    assert len(layout.blocks) == 14
    # Claro's east end is two throats, not one: blue 1's lead and blue 2's
    # share no track, which is what drawing it from turnouts showed (#58).
    assert sorted(layout.connections) == [
        "airolo",
        "claro_east_b1",
        "claro_east_b2",
        "claro_west",
    ]
    assert sum(len(c.transits) for c in layout.connections.values()) == 29
    assert layout.terminal_blocks == frozenset(
        {"airolo_4", "claro_4", "claro_5", "claro_6", "claro_7"}
    )
    # A reversing loop's signature: out through one end of a block and back in
    # through the same one (LAYOUT.md).
    at_yellow = layout.transits_at("line_yellow.A")
    assert ("airolo.airolo_2_A__line_yellow_A", "airolo_2.A") in at_yellow
    assert ("airolo.airolo_2_B__line_yellow_A", "airolo_2.B") in at_yellow


def test_airolo_composes_the_concurrency_the_wx310_allows() -> None:
    """#46, from the owner's account on #35. Set straight the WX310 passes two
    trains, one per leg: blue 2 to the A ends while the yellow or blue 1 works
    the B ends. Set crossed it passes one. Nothing in the drawing declares
    that — it is composed from four turnouts and a crossing."""
    airolo = committed("gotthard-v0").connections["airolo"]
    # Say it in block ends, the thing the geometry is about, so the assertion
    # holds whatever the transits end up called.
    ends = {name: frozenset(pair) for name, pair in airolo.transits.items()}
    composed = {frozenset((ends[one], ends[two])) for one, two in airolo.concurrent}

    straight = {
        frozenset(
            (
                frozenset((f"airolo_{track}.A", "line_blue_2.B")),
                frozenset((f"airolo_{other}.B", line)),
            )
        )
        for track in (1, 2, 3)
        for other in (1, 2, 3)
        for line in ("line_yellow.A", "line_blue_1.B")
    }
    # The siding is sw39's straight leg alone, so it clears everything that
    # does not reach track 3's B end — including every crossed transit.
    siding = {pair for pair in composed if ends["siding_4"] in pair}
    assert len(siding) == 15
    assert composed - siding == straight


def test_claro_east_is_two_throats_serving_one_line_each() -> None:
    """#58, settling #35. The netlist's track tiles run blue 1 into sw50 and
    blue 2 into sw49, and the two leads share no track, so the station's east
    end is two connections rather than the one the hand-written layout
    declared. The sidings hang off blue 2's lead, past sw49, not off track 1.

    Said in block ends, which is what the tiles settle; the names are the
    layout's and are asserted separately."""
    layout = committed("gotthard-v0")
    b1, b2 = layout.connections["claro_east_b1"], layout.connections["claro_east_b2"]
    assert {name: frozenset(pair) for name, pair in b1.transits.items()} == {
        "blue_1_2": frozenset(("line_blue_1.A", "claro_2.B")),
        "blue_1_3": frozenset(("line_blue_1.A", "claro_3.B")),
    }
    assert {name: frozenset(pair) for name, pair in b2.transits.items()} == {
        "blue_2_1": frozenset(("line_blue_2.A", "claro_1.B")),
        "siding_5": frozenset(("line_blue_2.A", "claro_5.A")),
        "siding_4": frozenset(("line_blue_2.A", "claro_4.A")),
    }
    # Each throat is one turnout's toe, or two in a row, so nothing within
    # either runs together. Across them nothing conflicts at all, which is the
    # point of their being two connections rather than one.
    assert b1.concurrent == frozenset()
    assert b2.concurrent == frozenset()


def test_claro_west_keeps_its_names_and_gains_the_pairs_its_ladder_allows() -> None:
    """Every transit there is identified by one symbol transit, so the names
    the hand-written layout picked survive being drawn. What is new is the
    concurrency: shunting track 3's sidings shares no switch with the yellow
    reaching track 1 or track 2."""
    claro_west = committed("gotthard-v0").connections["claro_west"]
    assert sorted(claro_west.transits) == [
        "siding_6",
        "siding_7",
        "yellow_1",
        "yellow_2",
        "yellow_3",
    ]
    assert claro_west.concurrent == frozenset(
        frozenset((siding, yellow))
        for siding in ("siding_6", "siding_7")
        for yellow in ("yellow_1", "yellow_2")
    )


# --- pass 1: components give the connections -------------------------------


def test_a_connection_with_no_transits_derives_nothing() -> None:
    doc = two_blocks(gap={"kind": "connection", "pins": ["A", "B"], "transits": {}})
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "east.A"]]
    assert derive(doc)["connections"] == {}


def test_a_bend_belongs_to_the_connection_it_joins() -> None:
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        gap={
            "kind": "connection",
            "pins": ["A", "B", "C"],
            "transits": [["A", "B"], ["A", "C"]],
        },
        bend={"kind": "pin"},
    )
    doc["wires"] += [
        ["west.B", "gap.A"],
        ["gap.B", "bend.P"],
        ["bend.P", "east.A"],
        ["gap.C", "north.A"],
        ["north.B", "north_stop.P"],
    ]
    derived = derive(doc)
    assert list(derived["connections"]) == ["gap"]
    assert set(derived["connections"]["gap"]["transits"]) == {
        "east_A__west_B",
        "north_A__west_B",
    }


def test_a_junction_of_four_symbols_in_a_chain_stays_one_connection() -> None:
    """Airolo's throats are long chains of turnouts, and the union-find that
    groups them has to hold a chain of any length together: a four-turnout
    ladder is the shortest one deep enough to catch a path-compression slip."""
    symbols: dict[str, Any] = {"trunk": block(), "trunk_stop": {"kind": "terminal"}}
    wires = [["trunk.A", "trunk_stop.P"]]
    lead = "trunk.B"
    for track in range(1, 5):
        symbols[f"sw{track}"] = {"kind": "turnout", "connection": "ladder"}
        symbols[f"track{track}"] = block()
        symbols[f"track{track}_stop"] = {"kind": "terminal"}
        wires += [
            [lead, f"sw{track}.toe"],
            [f"sw{track}.straight", f"track{track}.A"],
            [f"track{track}.B", f"track{track}_stop.P"],
        ]
        lead = f"sw{track}.diverging"
    symbols |= {"track5": block(), "track5_stop": {"kind": "terminal"}}
    wires += [[lead, "track5.A"], ["track5.B", "track5_stop.P"]]

    derived = derive({"drawing": "d", "symbols": symbols, "wires": wires})
    assert list(derived["connections"]) == ["ladder"]
    assert len(derived["connections"]["ladder"]["transits"]) == 5


def test_blocks_wired_directly_by_a_nameless_wire_are_refused() -> None:
    """Every movement between blocks is a named transit in a named connection,
    and a bare wire declares neither."""
    doc = two_blocks()
    doc["wires"].append(["west.B", "east.A"])
    with pytest.raises(ValueError, match="connection symbol"):
        derive(doc)


# --- a wire between two blocks is itself the connection --------------------


def joint(*bends: str, named: int = 0, connection: str = "gap") -> dict[str, Any]:
    """`west` and `east` joined through `bends` bend pins, with the wire at
    index `named` carrying the connection's name."""
    doc = two_blocks(**{bend: {"kind": "pin"} for bend in bends})
    pins = ["west.B", *(f"{bend}.P" for bend in bends), "east.A"]
    chain: list[Any] = [list(pair) for pair in pairwise(pins)]
    chain[named] = {"pins": chain[named], "connection": connection}
    doc["wires"] += chain
    return doc


def test_a_named_wire_between_two_blocks_derives_the_connection_it_is() -> None:
    derived = derive(joint())["connections"]
    assert derived == {"gap": {"transits": {"east_A__west_B": ["east.A", "west.B"]}}}


@pytest.mark.parametrize("named", (0, 1, 2))
def test_a_joint_routed_through_bends_takes_its_name_from_any_segment(
    named: int,
) -> None:
    """Routed around a corner the joint is several wires, and which one holds
    the name is a drawing accident, so the whole chain is searched."""
    assert list(derive(joint("b1", "b2", named=named))["connections"]) == ["gap"]


def test_two_names_on_one_joint_are_refused() -> None:
    doc = joint("bend", named=0)
    doc["wires"][-1] = {"pins": doc["wires"][-1], "connection": "other"}
    with pytest.raises(ValueError, match="is named .* one joint takes one name"):
        derive(doc)


def test_a_named_wire_that_joins_no_blocks_is_refused() -> None:
    """The key says this wire is the connection. Inside a junction it is not,
    and the junction's symbols name that."""
    doc = spanned()
    doc["wires"][-1] = {"pins": doc["wires"][-1], "connection": "nope"}
    with pytest.raises(ValueError, match="does not join two blocks"):
        derive(doc)


def test_a_way_leading_back_into_its_own_end_is_refused() -> None:
    """Leaving a block end and arriving back through it is a reversal, not a
    transit, so the drawing refuses it rather than deriving `west.B` twice."""
    doc = two_blocks(
        loop={
            "kind": "connection",
            "pins": ["A", "B", "C"],
            "transits": [["A", "B"], ["C", "A"]],
        },
        bend={"kind": "pin"},
        east_head={"kind": "terminal"},
    )
    doc["wires"] += [
        ["west.B", "loop.A"],
        ["loop.B", "bend.P"],
        ["bend.P", "loop.C"],
        ["east.A", "east_head.P"],
    ]
    with pytest.raises(ValueError, match="leads back into it"):
        derive(doc)


def test_a_component_with_no_connection_symbol_is_refused() -> None:
    doc = two_blocks(bend={"kind": "pin"})
    doc["wires"] += [["west.B", "bend.P"], ["bend.P", "east.A"]]
    with pytest.raises(ValueError, match="connection symbol"):
        derive(doc)


# --- pass 2: walking symbol transits gives the connection transits ---------


def test_a_three_pin_junction_derives_one_transit_per_symbol_transit() -> None:
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        junction={
            "kind": "connection",
            "pins": ["toe", "straight", "diverging"],
            "transits": {
                "through": ["toe", "straight"],
                "branch": ["toe", "diverging"],
            },
        },
    )
    doc["wires"] += [
        ["west.B", "junction.toe"],
        ["junction.straight", "east.A"],
        ["junction.diverging", "north.A"],
        ["north.B", "north_stop.P"],
    ]
    assert derive(doc)["connections"]["junction"]["transits"] == {
        "branch": ["north.A", "west.B"],
        "through": ["east.A", "west.B"],
    }


def test_a_transit_into_a_terminal_symbol_is_not_derived() -> None:
    doc = two_blocks(
        junction={
            "kind": "connection",
            "pins": ["toe", "straight", "diverging"],
            "transits": {
                "through": ["toe", "straight"],
                "branch": ["toe", "diverging"],
            },
        },
        siding_stop={"kind": "terminal"},
    )
    doc["wires"] += [
        ["west.B", "junction.toe"],
        ["junction.straight", "east.A"],
        ["junction.diverging", "siding_stop.P"],
    ]
    assert list(derive(doc)["connections"]["junction"]["transits"]) == ["through"]


def test_a_portal_pair_joins_its_wires_and_derives_to_nothing() -> None:
    doc = two_blocks(
        gap=gap_symbol(),
        here={"kind": "portal", "label": "staging"},
        there={"kind": "portal", "label": "staging"},
    )
    doc["wires"] += [
        ["west.B", "gap.A"],
        ["gap.B", "here.P"],
        ["there.P", "east.A"],
    ]
    assert derive(doc)["connections"] == {
        "gap": {"transits": {"span": ["east.A", "west.B"]}}
    }


# --- pass 3: composing symbol concurrency ---------------------------------


def crossover() -> dict[str, Any]:
    """Four blocks meeting at one generic connection that declares two of its
    four transits concurrent — crossover-yard's shape, in miniature."""
    doc: dict[str, Any] = {
        "drawing": "d",
        "symbols": {
            "crossover": {
                "kind": "connection",
                "pins": ["uw", "ue", "dw", "de"],
                "transits": {
                    "up_straight": ["uw", "ue"],
                    "dn_straight": ["dw", "de"],
                    "up_to_dn": ["uw", "de"],
                    "dn_to_up": ["dw", "ue"],
                },
                "concurrent": [["up_straight", "dn_straight"]],
            }
        },
        "wires": [],
    }
    for name, pin in (("up_w", "uw"), ("up_e", "ue"), ("dn_w", "dw"), ("dn_e", "de")):
        doc["symbols"][name] = block()
        doc["symbols"][f"{name}_stop"] = {"kind": "terminal"}
        near, far = ("B", "A") if name.endswith("_w") else ("A", "B")
        doc["wires"] += [
            [f"{name}.{near}", f"crossover.{pin}"],
            [f"{name}.{far}", f"{name}_stop.P"],
        ]
    return doc


def test_declared_symbol_concurrency_passes_through() -> None:
    assert derive(crossover())["connections"]["crossover"]["concurrent"] == [
        ["dn_straight", "up_straight"]
    ]


def test_transits_sharing_a_bend_conflict() -> None:
    """A bend declares no concurrency, so two transits through the same one
    exclude each other exactly as two transits through a shared frog do."""
    doc = crossover()
    doc["symbols"]["crossover"]["concurrent"] = [
        ["up_straight", "dn_straight"],
        ["up_straight", "dn_to_up"],
    ]
    doc["symbols"]["bend"] = {"kind": "pin"}
    doc["wires"] = [w for w in doc["wires"] if w != ["up_e.A", "crossover.ue"]]
    doc["wires"] += [["up_e.A", "bend.P"], ["bend.P", "crossover.ue"]]
    # up_straight and dn_to_up both run through the bend, so the pair the
    # symbol declares is composed away; dn_straight does not touch it.
    assert derive(doc)["connections"]["crossover"]["concurrent"] == [
        ["dn_straight", "up_straight"]
    ]


# --- the symbol library ---------------------------------------------------


def four_ways(kind: str) -> dict[str, Any]:
    """A crossing or a slip with a terminated block on each of its four
    pins — the smallest drawing that shows what routes the symbol has."""
    doc: dict[str, Any] = {
        "drawing": "d",
        "symbols": {"x": {"kind": kind}},
        "wires": [],
    }
    for name in ("a1", "a2", "b1", "b2"):
        doc["symbols"][name] = block()
        doc["symbols"][f"{name}_stop"] = {"kind": "terminal"}
        doc["wires"] += [[f"{name}.A", f"x.{name}"], [f"{name}.B", f"{name}_stop.P"]]
    return doc


def test_a_turnout_has_two_routes_and_declares_nothing_concurrent() -> None:
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        points={"kind": "turnout"},
    )
    doc["wires"] += [
        ["west.B", "points.toe"],
        ["points.straight", "east.A"],
        ["points.diverging", "north.A"],
        ["north.B", "north_stop.P"],
    ]
    # Both routes take the toe, so composition leaves them exclusive.
    assert derive(doc)["connections"]["points"] == {
        "transits": {
            "east_A__west_B": ["east.A", "west.B"],
            "north_A__west_B": ["north.A", "west.B"],
        }
    }


@pytest.mark.parametrize(
    "kind, transits",
    [
        ("crossing", [["a1.A", "a2.A"], ["b1.A", "b2.A"]]),
        ("crossing_90", [["a1.A", "a2.A"], ["b1.A", "b2.A"]]),
        ("crossing_90d", [["a1.A", "a2.A"], ["b1.A", "b2.A"]]),
        ("single_slip", [["a1.A", "a2.A"], ["a1.A", "b2.A"], ["b1.A", "b2.A"]]),
        (
            "double_slip",
            [
                ["a1.A", "a2.A"],
                ["a1.A", "b2.A"],
                ["a2.A", "b1.A"],
                ["b1.A", "b2.A"],
            ],
        ),
    ],
)
def test_a_crossing_and_the_slips_are_exclusive(
    kind: str, transits: list[list[str]]
) -> None:
    """Every route through one of these takes the shared frog, so none of the
    pairs composes to concurrent — the derived connection has no `concurrent`
    at all."""
    derived = derive(four_ways(kind))["connections"]["x"]
    assert sorted(derived["transits"].values()) == transits
    assert "concurrent" not in derived


def test_the_scissors_crossover_composes_the_hand_declared_concurrency() -> None:
    """The proof of composition: crossover-yard drawn from four turnouts and
    one crossing derives the four transits the layout declared, and exactly
    the one concurrent pair — the only two ways that share no symbol."""
    crossover = derive(read("crossover-yard.drawing.yaml"))["connections"]["crossover"]
    assert crossover == {
        "transits": {
            "dn_straight": ["dn_e.A", "dn_w.B"],
            "dn_to_up": ["dn_w.B", "up_e.A"],
            "up_straight": ["up_e.A", "up_w.B"],
            "up_to_dn": ["dn_e.A", "up_w.B"],
        },
        "concurrent": [["dn_straight", "up_straight"]],
    }


def test_a_junction_of_several_symbols_takes_the_name_they_declare() -> None:
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        points={"kind": "turnout", "connection": "throat"},
        bend={"kind": "turnout", "connection": "throat"},
        bend_stop={"kind": "terminal"},
    )
    doc["wires"] += [
        ["west.B", "points.toe"],
        ["points.straight", "east.A"],
        ["points.diverging", "bend.toe"],
        ["bend.straight", "north.A"],
        ["bend.diverging", "bend_stop.P"],
        ["north.B", "north_stop.P"],
    ]
    assert list(derive(doc)["connections"]) == ["throat"]


def test_an_unnamed_junction_of_several_symbols_is_refused() -> None:
    doc = two_blocks(one={"kind": "turnout"}, two={"kind": "turnout"})
    doc["symbols"]["one_stop"] = {"kind": "terminal"}
    doc["symbols"]["two_stop"] = {"kind": "terminal"}
    doc["wires"] += [
        ["west.B", "one.toe"],
        ["one.straight", "two.toe"],
        ["one.diverging", "one_stop.P"],
        ["two.straight", "east.A"],
        ["two.diverging", "two_stop.P"],
    ]
    with pytest.raises(ValueError, match="is unnamed"):
        derive(doc)


def test_symbols_of_one_junction_disagreeing_on_its_name_are_refused() -> None:
    doc = spanned(bend={"kind": "pin"})
    doc["symbols"]["gap"]["connection"] = "west_end"
    doc["symbols"]["other"] = {**gap_symbol(), "connection": "east_end"}
    doc["wires"] = [w for w in doc["wires"] if w != ["gap.B", "east.A"]]
    doc["wires"] += [
        ["gap.B", "bend.P"],
        ["bend.P", "other.A"],
        ["other.B", "east.A"],
    ]
    with pytest.raises(ValueError, match="are one connection"):
        derive(doc)


def test_two_junctions_taking_the_same_name_are_refused() -> None:
    doc = two_blocks(
        middle=block(),
        west_gap={**gap_symbol(named=False), "connection": "join"},
        east_gap={**gap_symbol(named=False), "connection": "join"},
    )
    doc["wires"] += [
        ["west.B", "west_gap.A"],
        ["west_gap.B", "middle.A"],
        ["middle.B", "east_gap.A"],
        ["east_gap.B", "east.A"],
    ]
    with pytest.raises(ValueError, match="two junctions are named 'join'"):
        derive(doc)


# --- explain: the way a transit takes, and what excludes it ---------------


def explain(doc: dict[str, Any]) -> dict[str, Any]:
    return Drawing.from_document(doc).explain()


def test_a_transit_reports_the_way_it_takes() -> None:
    """Symbol by symbol and leg by leg, which is what lights a route on the
    canvas."""
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        points={"kind": "turnout"},
    )
    doc["wires"] += [
        ["west.B", "points.toe"],
        ["points.straight", "east.A"],
        ["points.diverging", "north.A"],
        ["north.B", "north_stop.P"],
    ]
    transits = explain(doc)["connections"]["points"]["transits"]
    assert transits["east_A__west_B"] == {
        "ends": ["east.A", "west.B"],
        "way": [["points", "straight"]],
    }
    assert transits["north_A__west_B"]["way"] == [["points", "diverging"]]


def test_an_exclusion_names_the_symbol_that_causes_it() -> None:
    """The claim DRAWING.md makes about composition, said out loud: a
    turnout's two ways share its toe."""
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        points={"kind": "turnout"},
    )
    doc["wires"] += [
        ["west.B", "points.toe"],
        ["points.straight", "east.A"],
        ["points.diverging", "north.A"],
        ["north.B", "north_stop.P"],
    ]
    assert explain(doc)["connections"]["points"]["exclusive"] == [
        {"transits": ["east_A__west_B", "north_A__west_B"], "shared": ["points"]}
    ]


def test_transits_that_run_together_are_not_listed_as_exclusive() -> None:
    """Concurrency is the layout's to report; explain says only what stops a
    pair, so a declared-concurrent pair says nothing."""
    excluded = explain(crossover())["connections"]["crossover"]["exclusive"]
    assert ["dn_straight", "up_straight"] not in [pair["transits"] for pair in excluded]
    assert {
        "transits": ["dn_straight", "dn_to_up"],
        "shared": ["crossover"],
    } in excluded


def test_the_scissors_crossover_says_which_frog_excludes_a_pair() -> None:
    """`crossover-yard` drawn from real symbols: the two crossing moves are
    exclusive because both take the diamond, which is the composition
    argument DRAWING.md rests on."""
    crossing = committed_drawing("crossover-yard").explain()["connections"]["crossover"]
    excluded = {
        tuple(pair["transits"]): pair["shared"] for pair in crossing["exclusive"]
    }
    assert "diamond" in excluded[("dn_to_up", "up_to_dn")]
    assert ("dn_straight", "up_straight") not in excluded


def test_airolo_says_the_wx310_is_what_a_crossed_pair_shares() -> None:
    airolo = committed_drawing("gotthard-v0").explain()["connections"]["airolo"]
    shared = {
        symbol
        for pair in airolo["exclusive"]
        for symbol in pair["shared"]
        if "line_blue_2" in str(pair["transits"])
    }
    assert "sw16" in shared


def test_explain_refuses_what_derivation_refuses() -> None:
    doc = two_blocks()
    doc["wires"].append(["west.B", "east.A"])
    with pytest.raises(ValueError, match="connection symbol"):
        explain(doc)


# --- review: everything the editor draws that is not in the document ------


def test_a_complete_drawing_reviews_clean() -> None:
    review = Drawing.from_document(spanned()).review()
    assert review["red_pins"] == []
    assert review["refused"] is None
    assert review["layout"]["connections"]["gap"]["transits"]
    assert review["explain"]["connections"]["gap"]["transits"]


def test_a_dangling_pin_is_red_and_the_layout_is_refused() -> None:
    """Work in progress: the editor still draws it, derivation still says no,
    and the front end works neither out for itself."""
    doc = two_blocks(points={"kind": "turnout"})
    doc["wires"] += [["west.B", "points.toe"], ["points.straight", "east.A"]]
    review = Drawing.from_document(doc).review()
    assert review["red_pins"] == ["points.diverging"]
    assert review["layout"] is None and review["explain"] is None
    assert "points.diverging" in review["refused"]


# --- review: points that share an address move together ---------------------


def ganged_in_series() -> dict[str, Any]:
    """One way crossing two points on the same address, one lying straight and
    the other diverging. No accessory output can do that."""
    doc = two_blocks(
        swa={"kind": "turnout", "addr": "1", "connection": "throat"},
        swb={"kind": "turnout", "addr": "1", "connection": "throat"},
        swa_stop={"kind": "terminal"},
        swb_stop={"kind": "terminal"},
    )
    doc["wires"] += [
        ["west.B", "swa.toe"],
        ["swa.straight", "swb.toe"],
        ["swa.diverging", "swa_stop.P"],
        ["swb.diverging", "east.A"],
        ["swb.straight", "swb_stop.P"],
    ]
    return doc


def ganged_across_concurrent() -> dict[str, Any]:
    """Two ways that may run at once, each crossing a point on address `1`,
    one straight and one diverging."""
    doc = crossover()
    for name, pin, leg, spare in (
        ("up", "uw", "straight", "diverging"),
        ("dn", "dw", "diverging", "straight"),
    ):
        points = f"sw{name}"
        doc["symbols"][points] = {
            "kind": "turnout",
            "addr": "1",
            "connection": "crossover",
        }
        doc["symbols"][f"{points}_stop"] = {"kind": "terminal"}
        doc["wires"].remove([f"{name}_w.B", f"crossover.{pin}"])
        doc["wires"] += [
            [f"{name}_w.B", f"{points}.toe"],
            [f"{points}.{leg}", f"crossover.{pin}"],
            [f"{points}.{spare}", f"{points}_stop.P"],
        ]
    return doc


def test_points_on_one_address_at_odds_in_one_way_are_a_fault() -> None:
    faults = Drawing.from_document(ganged_in_series()).review()["motor_faults"]
    assert [(f["addr"], f["positions"]) for f in faults] == [
        ("1", {"closed": ["swa"], "thrown": ["swb"]})
    ]
    assert len(faults[0]["transits"]) == 1


def test_points_on_one_address_at_odds_across_concurrent_ways_are_a_fault() -> None:
    """Each way is throwable alone; the pair is not, and only the pair is the
    fault. Declared concurrent is a promise two trains may hold it at once."""
    faults = Drawing.from_document(ganged_across_concurrent()).review()["motor_faults"]
    assert [(f["addr"], f["transits"]) for f in faults] == [
        ("1", ["dn_straight", "up_straight"])
    ]


def test_points_on_one_address_agreeing_are_no_fault() -> None:
    doc = ganged_in_series()
    doc["wires"].remove(["swb.diverging", "east.A"])
    doc["wires"].remove(["swb.straight", "swb_stop.P"])
    doc["wires"] += [["swb.straight", "east.A"], ["swb.diverging", "swb_stop.P"]]
    assert Drawing.from_document(doc).review()["motor_faults"] == []


@pytest.mark.parametrize("name", RAILROADS)
def test_a_committed_drawing_can_be_thrown(name: str) -> None:
    """gotthard is the one that gangs points: `5` moves sw1 and sw2, `1`
    moves sw6 through sw9, which is what the hardware needs and why that throat
    has fewer usable ways than its geometry suggests."""
    assert committed_drawing(name).review()["motor_faults"] == []


def test_a_bend_short_of_its_second_wire_is_red() -> None:
    doc = two_blocks(bend={"kind": "pin"})
    doc["wires"].append(["west.B", "bend.P"])
    assert Drawing.from_document(doc).review()["red_pins"] == ["bend.P", "east.A"]


def test_junctions_are_the_symbols_that_form_them_and_the_name_they_take() -> None:
    """What the editor tints as one region, computed the way derivation
    computes it rather than a second time in TypeScript, and named so the
    region can be matched to its connection without deriving anything."""
    junctions = committed_drawing("crossover-yard").review()["junctions"]
    assert {
        "name": "crossover",
        "names": ["crossover"],
        "symbols": [
            "diamond",
            "dn_e_points",
            "dn_w_points",
            "up_e_points",
            "up_w_points",
        ],
    } in junctions
    assert sorted(j["name"] for j in junctions) == [
        "crossover",
        "east_ladder",
        "west_ladder",
    ]


def test_a_terminal_is_not_a_junction() -> None:
    """Every non-block symbol is a component of its own, but a terminal
    declares no transit and derives no connection, so tinting it as a region
    would say something untrue."""
    junctions = committed_drawing("gotthard-v0").review()["junctions"]
    tinted = {symbol for junction in junctions for symbol in junction["symbols"]}
    assert not [symbol for symbol in tinted if symbol.endswith("_stop")]
    assert sorted(j["name"] for j in junctions) == [
        "airolo",
        "claro_east_b1",
        "claro_east_b2",
        "claro_west",
    ]


def test_a_joint_is_reported_with_the_wires_that_may_carry_its_name() -> None:
    """The editor mints the name a bare wire between two blocks needs, so it
    has to be told which wires want one. Working that out means walking the
    drawing, which is what the front end does not do."""
    assert Drawing.from_document(joint("b1", "b2", named=1)).joints() == [
        {
            "ends": ["east.A", "west.B"],
            "wires": [["b1.P", "west.B"], ["b1.P", "b2.P"], ["b2.P", "east.A"]],
            "name": "gap",
            "names": ["gap"],
        }
    ]


def test_a_joint_nobody_has_named_is_reported_without_a_name() -> None:
    """The normal state a moment after the wire is drawn, and the case the
    editor answers by minting."""
    doc = joint()
    doc["wires"][-1] = doc["wires"][-1]["pins"]
    joints = Drawing.from_document(doc).joints()
    assert [(j["name"], j["names"]) for j in joints] == [(None, [])]
    assert joints[0]["wires"] == [["east.A", "west.B"]]


def test_a_joint_named_twice_is_told_apart_from_one_named_not_at_all() -> None:
    """Deriving either is refused; reviewing is not, because the editor draws
    the drawing that caused the refusal. The editor mints a name for the one
    and leaves the other alone, so the two cases have to be distinguishable."""
    doc = joint("bend", named=0)
    doc["wires"][-1] = {"pins": doc["wires"][-1], "connection": "other"}
    twice = Drawing.from_document(doc).joints()
    assert [(j["name"], j["names"]) for j in twice] == [(None, ["gap", "other"])]


def test_a_way_through_a_junction_is_not_a_joint() -> None:
    """A junction's symbols name their connection, so those wires must not be
    offered a name of their own."""
    assert Drawing.from_document(spanned()).joints() == []
    assert committed_drawing("crossover-yard").joints() == []


# --- the wire rule, proven exact -------------------------------------------


Wire = tuple[str, str]  # a wire, as the sorted pair of pins naming it
Edge = tuple[str, Wire | None, Use | None]


def hops(drawing: Drawing, ends: tuple[str, str], used: tuple[Use, ...]) -> set[Wire]:
    """The wires a way is actually drawn over, found by re-walking it pin by
    pin rather than by asking the rule.

    Derivation records a way as its two block ends and the symbol legs it
    took, and keeps no wires; the hops are recovered by walking the pin graph
    — wires, the leg of each symbol the way crosses, and the pairing a portal
    wears — for the one simple path between the ends that crosses exactly
    those legs. A pairing joins two pins and is not a wire, so it carries no
    key and contributes none.

    A second algorithm on purpose. Comparing the rule against a copy of
    itself would prove nothing about either.
    """
    joins: dict[str, list[Edge]] = defaultdict(list)
    for wire in drawing.wires:
        key = cast(Wire, tuple(sorted(wire)))
        joins[wire[0]].append((wire[1], key, None))
        joins[wire[1]].append((wire[0], key, None))
    for symbol, leg in used:
        if not leg:
            continue  # a joiner takes no leg of its own; it is passed through
        a, b = drawing.symbols[symbol].transits[leg]
        joins[f"{symbol}.{a}"].append((f"{symbol}.{b}", None, (symbol, leg)))
        joins[f"{symbol}.{b}"].append((f"{symbol}.{a}", None, (symbol, leg)))
    portals = [name for name, _ in used if drawing.symbols[name].kind == "portal"]
    for one in portals:
        for two in portals:
            if one != two and drawing.symbols[one].label == drawing.symbols[two].label:
                joins[f"{one}.P"].append((f"{two}.P", None, None))

    walked: list[frozenset[Wire]] = []

    def step(
        node: str,
        seen: frozenset[str],
        wires: frozenset[Wire],
        crossed: frozenset[Use],
    ) -> None:
        name = node.partition(".")[0]
        kind = drawing.symbols[name].kind
        if kind == "block" and node != ends[0]:
            if node == ends[1] and crossed == frozenset(used):
                walked.append(wires)
            return  # any other block end stops the way, as the walk does
        if kind in {BEND, "portal"}:
            crossed |= {(name, "")}
        for other, wire, use in joins[node]:
            if other in seen:
                continue
            step(
                other,
                seen | {other},
                wires if wire is None else wires | {wire},
                crossed if use is None else crossed | {use},
            )

    step(ends[0], frozenset({ends[0]}), frozenset(), frozenset())
    assert len(walked) == 1, f"{ends} through {used} walks {len(walked)} ways"
    return set(walked[0])


def ways(drawing: Drawing) -> list[tuple[tuple[str, str], tuple[Use, ...]]]:
    """Every way of a drawing, as the explanation states it."""
    return [
        (
            cast(tuple[str, str], tuple(transit["ends"])),
            tuple(cast(Use, tuple(use)) for use in transit["way"]),
        )
        for connection in drawing.explain()["connections"].values()
        for transit in connection["transits"].values()
    ]


@pytest.mark.parametrize("name", RAILROADS)
def test_the_wire_rule_is_exact_on_every_way_of_every_railroad(name: str) -> None:
    """The rule that decides which wires a way is drawn over holds no more and
    no less than the hops the walk takes.

    The rule is cheap — a subset test per wire — and the front end transcribes
    it to light a committed route and a chosen transit (#140, #142). It could
    in theory over-light: a wire between two pins of one crossed symbol is in
    the set whether the way runs over it or not. This says the case does not
    arise on any drawing that exists, in the store, where the rule lives,
    rather than in a browser painting a route over a wire no train will take.
    """
    drawing = committed_drawing(name)
    walked = ways(drawing)
    assert walked, f"{name} has no ways to check"
    for ends, used in walked:
        assert set(drawing.wires_on(ends, used)) == hops(drawing, ends, used)


def portal_joint() -> dict[str, Any]:
    """`west` and `east` joined by a wire each into a portal pair: one joint,
    crossing the canvas rather than a corner. The pairing joins the two
    portals and is not a wire, so the chain is two."""
    doc = two_blocks(
        here={"kind": "portal", "label": "hop"},
        there={"kind": "portal", "label": "hop"},
    )
    doc["wires"] += [
        {"pins": ["west.B", "here.P"], "connection": "gap"},
        ["there.P", "east.A"],
    ]
    return doc


def test_the_wire_rule_is_exact_on_the_shapes_no_railroad_is_drawn_with() -> None:
    """A joint chained through bend pins, and a joint whose chain crosses a
    portal pair. Neither is on a committed railroad — the parametrised test
    above covers what is — and both are exactly the shapes the front end's
    copy of the rule has to get right, a joint lighting nothing at all today.
    """
    for doc in (joint("b1", "b2"), portal_joint()):
        drawing = Drawing.from_document(doc)
        for ends, used in ways(drawing):
            assert set(drawing.wires_on(ends, used)) == hops(drawing, ends, used)


def test_a_joint_through_a_portal_pair_is_the_two_wires_and_not_the_pairing() -> None:
    """The pairing is how a joint's chain crosses the canvas, not a wire on
    it (CONTEXT.md), so nothing downstream has one to draw."""
    assert Drawing.from_document(portal_joint()).joints() == [
        {
            "ends": ["east.A", "west.B"],
            "wires": [["here.P", "west.B"], ["east.A", "there.P"]],
            "name": "gap",
            "names": ["gap"],
        }
    ]


def with_portals(*labels: str) -> dict[str, Any]:
    """A drawing that derives, plus a portal per label wired to a terminal of
    its own — so nothing here is a red pin and the only thing wrong is what
    the labels do or do not pair."""
    doc = spanned()
    for i, label in enumerate(labels):
        doc["symbols"][f"p{i}"] = {"kind": "portal", "label": label}
        doc["symbols"][f"p{i}_stop"] = {"kind": "terminal"}
        doc["wires"].append([f"p{i}.P", f"p{i}_stop.P"])
    return doc


def test_a_label_no_second_portal_wears_is_reported_with_the_portal() -> None:
    """The refusal names one label and stops, so two lone portals used to
    report one and reveal the next on the fix. The finding names them all."""
    review = Drawing.from_document(with_portals("staging", "hidden")).review()
    assert review["unpaired_portals"] == [
        {"label": "hidden", "portals": ["p1"]},
        {"label": "staging", "portals": ["p0"]},
    ]


def test_a_label_three_portals_wear_is_reported_the_same_way() -> None:
    """Both halves of "a label pairs exactly two" are one finding: a third
    mouth is no more a pair than a lone one, and derivation refuses both."""
    doc = with_portals("staging", "staging", "staging")
    assert Drawing.from_document(doc).review()["unpaired_portals"] == [
        {"label": "staging", "portals": ["p0", "p1", "p2"]}
    ]


def test_a_drawing_whose_labels_all_pair_reports_no_unpaired_portal() -> None:
    doc = two_blocks(
        gap=gap_symbol(),
        here={"kind": "portal", "label": "staging"},
        there={"kind": "portal", "label": "staging"},
    )
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "here.P"], ["there.P", "east.A"]]
    review = Drawing.from_document(doc).review()
    assert review["unpaired_portals"] == []
    assert review["refused"] is None


def test_an_unpaired_label_is_reported_beside_the_rest_of_the_review() -> None:
    """The finding is one of several: reviewing a drawing that will not derive
    still answers with its red pins, its junctions and its joints, and the
    refusal stays a refusal — this changes what is reported, not what
    derives."""
    doc = with_portals("staging")
    doc["symbols"]["north"] = block()
    doc["symbols"]["points"] = {"kind": "turnout", "connection": "throat"}
    doc["wires"][1] = {"pins": ["east.B", "north.A"], "connection": "hop"}
    doc["wires"].append(["north.B", "east_stop.P"])
    review = Drawing.from_document(doc).review()
    assert [f["label"] for f in review["unpaired_portals"]] == ["staging"]
    assert review["red_pins"] == ["points.diverging", "points.straight", "points.toe"]
    assert [j["name"] for j in review["junctions"]] == ["gap", "throat"]
    assert [j["name"] for j in review["joints"]] == ["hop"]
    assert review["layout"] is None and review["refused"] is not None


@pytest.mark.parametrize("name", RAILROADS)
def test_review_answers_however_damaged_the_drawing_is(name: str) -> None:
    """The editor reviews on every edit, so a half-finished drawing has to come
    back with an answer rather than an exception. Symbols and wires are removed
    at random: a schema error is the loader's to raise, but anything that loads
    must review."""
    rng = Random(49)
    base = read(f"{name}.drawing.yaml")
    for _ in range(200):
        doc = yaml.safe_load(yaml.safe_dump(base))
        for _ in range(rng.randint(1, 4)):
            if rng.random() < 0.5 and doc["symbols"]:
                del doc["symbols"][rng.choice(list(doc["symbols"]))]
            elif doc["wires"]:
                doc["wires"].pop(rng.randrange(len(doc["wires"])))
        try:
            drawing = Drawing.from_document(doc)
        except (ValueError, TypeError):
            continue  # a schema error, which the server answers as a 400
        review = drawing.review()
        assert isinstance(review["red_pins"], list)
        assert (review["layout"] is None) == (review["refused"] is not None)


def test_junctions_are_reported_even_when_the_drawing_will_not_derive() -> None:
    doc = two_blocks(points={"kind": "turnout"})
    doc["wires"] += [["west.B", "points.toe"], ["points.straight", "east.A"]]
    review = Drawing.from_document(doc).review()
    assert review["junctions"] == [
        {"name": "points", "names": [], "symbols": ["points"]}
    ]
    assert review["refused"] is not None


def test_a_junction_the_drawing_has_not_named_reports_no_name() -> None:
    """Two turnouts wired together and neither writing `connection` is a
    refusal at derivation. The region is still there to be tinted and named,
    so it comes back with a null name rather than an exception."""
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        south=block(),
        south_stop={"kind": "terminal"},
        one={"kind": "turnout"},
        two={"kind": "turnout"},
    )
    doc["wires"] += [
        ["west.B", "one.toe"],
        ["one.straight", "two.toe"],
        ["one.diverging", "north.A"],
        ["north.B", "north_stop.P"],
        ["two.straight", "east.A"],
        ["two.diverging", "south.A"],
        ["south.B", "south_stop.P"],
    ]
    review = Drawing.from_document(doc).review()
    assert review["junctions"] == [
        {"name": None, "names": [], "symbols": ["one", "two"]}
    ]
    assert "unnamed" in review["refused"]

    # Named twice instead of not at all: the same null name, and the names
    # someone typed, which is what stops the editor minting over them.
    doc["symbols"]["one"]["connection"] = "airolo"
    doc["symbols"]["two"]["connection"] = "claro"
    review = Drawing.from_document(doc).review()
    assert review["junctions"] == [
        {"name": None, "names": ["airolo", "claro"], "symbols": ["one", "two"]}
    ]


def test_a_way_looping_back_into_its_block_is_the_offending_way() -> None:
    """The refusal is a statement about a route, and a sentence beside the
    drawing cannot point at one (ADR-0024). The walk that failed is what the
    editor lights, in the shape `explain` gives a transit's way, so the canvas
    lights it with the machinery the netlist pane already uses."""
    doc = two_blocks(
        loop={
            "kind": "connection",
            "pins": ["A", "B", "C"],
            "transits": [["A", "B"], ["C", "A"]],
        },
        bend={"kind": "pin"},
        east_head={"kind": "terminal"},
    )
    doc["wires"] += [
        ["west.B", "loop.A"],
        ["loop.B", "bend.P"],
        ["bend.P", "loop.C"],
        ["east.A", "east_head.P"],
    ]
    review = Drawing.from_document(doc).review()
    assert review["refused"] is not None
    assert review["offending"] == [
        {
            "ends": ["west.B", "west.B"],
            "way": [["loop", "0"], ["bend", ""], ["loop", "1"]],
        }
    ]


def test_two_transits_deriving_one_name_come_back_as_both_ways() -> None:
    """Two paths joining one pair of block ends: neither is the offender, so
    both light."""
    doc = two_blocks(
        gap={
            "kind": "connection",
            "pins": ["A", "B"],
            "transits": [["A", "B"], ["A", "B"]],
        }
    )
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "east.A"]]
    review = Drawing.from_document(doc).review()
    assert "two transits named" in review["refused"]
    assert review["offending"] == [
        {"ends": ["east.A", "west.B"], "way": [["gap", "0"]]},
        {"ends": ["east.A", "west.B"], "way": [["gap", "1"]]},
    ]


def test_a_refusal_that_is_not_about_a_way_offends_no_way() -> None:
    """A dangling pin is a mark on the pin, not a route, so there is nothing
    here to light and nothing raised in working that out."""
    doc = two_blocks(points={"kind": "turnout"})
    doc["wires"] += [["west.B", "points.toe"], ["points.straight", "east.A"]]
    review = Drawing.from_document(doc).review()
    assert review["refused"] is not None
    assert review["offending"] == []


def test_a_drawing_that_derives_offends_no_way() -> None:
    assert Drawing.from_document(spanned()).review()["offending"] == []


# --- names and determinism ------------------------------------------------


def test_unnamed_transits_take_a_name_derived_from_their_block_ends() -> None:
    doc = two_blocks(gap=gap_symbol(named=False))
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "east.A"]]
    assert list(derive(doc)["connections"]["gap"]["transits"]) == ["east_A__west_B"]


def test_a_named_symbol_transit_overrides_the_derived_name() -> None:
    assert list(derive(spanned())["connections"]["gap"]["transits"]) == ["span"]


def test_derived_names_do_not_depend_on_drawing_order_or_pin_ids() -> None:
    doc = two_blocks(gap=gap_symbol(named=False))
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "east.A"]]

    shuffled = two_blocks(
        gap={"kind": "connection", "pins": ["y", "x"], "transits": [["y", "x"]]}
    )
    shuffled["symbols"] = dict(reversed(list(shuffled["symbols"].items())))
    shuffled["wires"] = [["gap.y", "east.A"], ["west.B", "gap.x"]] + list(
        reversed(shuffled["wires"])
    )

    assert yaml.safe_dump(derive(doc), sort_keys=False) == yaml.safe_dump(
        derive(shuffled), sort_keys=False
    )


@pytest.mark.parametrize("name", RAILROADS)
def test_the_derived_layout_survives_a_drawing_file_reorder(name: str) -> None:
    """Symbol and wire order is drawing-file bookkeeping, and a symbol carries
    no position at all, so neither can move a byte of the derived layout. Every
    railroad, since order-sensitivity shows up first in the biggest component:
    Gotthard's Airolo is a chain a dozen symbols long."""
    doc = read(f"{name}.drawing.yaml")
    shuffled = {
        **doc,
        "symbols": dict(reversed(list(doc["symbols"].items()))),
        "wires": [flipped(wire) for wire in reversed(doc["wires"])],
    }
    assert yaml.safe_dump(derive(shuffled), sort_keys=False) == yaml.safe_dump(
        derive(doc), sort_keys=False
    )


def test_the_derived_layout_has_canonical_key_order() -> None:
    doc = crossover()
    doc["symbols"]["crossover"]["concurrent"] = [
        ["up_to_dn", "dn_to_up"],
        ["up_straight", "dn_straight"],
    ]
    doc["symbols"] = dict(reversed(list(doc["symbols"].items())))
    derived = derive(doc)
    assert list(derived["blocks"]) == ["dn_e", "dn_w", "up_e", "up_w"]
    assert list(derived["connections"]["crossover"]["transits"]) == [
        "dn_straight",
        "dn_to_up",
        "up_straight",
        "up_to_dn",
    ]
    # Pairs sorted within, and the list of them sorted.
    assert derived["connections"]["crossover"]["concurrent"] == [
        ["dn_straight", "up_straight"],
        ["dn_to_up", "up_to_dn"],
    ]


def test_connections_are_in_canonical_order() -> None:
    doc = two_blocks(
        middle=block(),
        west_gap={**gap_symbol(named=False)},
        east_gap={**gap_symbol(named=False)},
    )
    doc["wires"] += [
        ["west.B", "west_gap.A"],
        ["west_gap.B", "middle.A"],
        ["middle.B", "east_gap.A"],
        ["east_gap.B", "east.A"],
    ]
    assert list(derive(doc)["connections"]) == ["east_gap", "west_gap"]


def test_colliding_derived_names_are_refused() -> None:
    doc = two_blocks(
        gap={
            "kind": "connection",
            "pins": ["A", "B"],
            "transits": [["A", "B"], ["A", "B"]],
        }
    )
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "east.A"]]
    with pytest.raises(ValueError, match="two transits named 'east_A__west_B'"):
        derive(doc)


# --- refusals: an incomplete drawing saves but never derives --------------


def dangling() -> dict[str, Any]:
    doc = two_blocks(gap=gap_symbol())
    doc["wires"].append(["west.B", "gap.A"])  # east.A and gap.B left unwired
    return doc


def unpaired_portal() -> dict[str, Any]:
    doc = two_blocks(gap=gap_symbol(), here={"kind": "portal", "label": "staging"})
    doc["wires"] += [["west.B", "gap.A"], ["gap.B", "here.P"], ["east.A", "here.P"]]
    return doc


def test_a_dangling_pin_refuses_to_derive() -> None:
    with pytest.raises(ValueError, match="pin 'east.A' takes one wire, got 0"):
        derive(dangling())


def test_an_over_wired_pin_refuses_to_derive() -> None:
    doc = spanned()
    doc["wires"].append(["gap.B", "west.B"])
    with pytest.raises(ValueError, match="takes one wire, got 2"):
        derive(doc)


def test_a_bend_joining_one_wire_refuses_to_derive() -> None:
    doc = spanned(bend={"kind": "pin"}, stray={"kind": "terminal"})
    doc["wires"].append(["bend.P", "stray.P"])
    with pytest.raises(ValueError, match="free-standing pin 'bend.P' joins two wires"):
        derive(doc)


@pytest.mark.parametrize("portals", [1, 3])
def test_a_label_worn_by_other_than_two_portals_refuses_to_derive(portals: int) -> None:
    doc = spanned()
    for i in range(portals):
        doc["symbols"][f"p{i}"] = {"kind": "portal", "label": "staging"}
    with pytest.raises(ValueError, match="label 'staging' is worn by"):
        derive(doc)


@pytest.mark.parametrize("broken", [dangling, unpaired_portal])
def test_an_incomplete_drawing_loads_and_saves(broken: Any, tmp_path: Path) -> None:
    doc = broken()
    assert Drawing.from_document(doc).name == "d"
    store = AssetStore(tmp_path)
    store.put(doc)
    assert store.list() == ["d"]
    with pytest.raises(ValueError):
        store.get("d")
    store.delete("d")
    assert store.list() == []


# --- schema errors: caught at load, before anything is saved --------------


Mutate = Callable[[dict[str, Any]], object]

_SCHEMA_ERRORS: list[tuple[Mutate, str]] = [
    (lambda d: d["symbols"].update(gap={"kind": "signal"}), "unknown kind"),
    (lambda d: d["wires"].append(["west.B", "gap.Z"]), "unknown pin"),
    (lambda d: d["wires"].append(["west.B", "west.B"]), "distinct pins"),
    (
        lambda d: d["symbols"]["gap"]["transits"].update(span=["A", "Z"]),
        "unknown pin",
    ),
    (
        lambda d: d["symbols"]["gap"].update(concurrent=[["span", "other"]]),
        "unknown transit",
    ),
    (
        lambda d: d["symbols"]["gap"].update(transits=[["A", "B"]]),
        "concurrent needs named transits",
    ),
    (
        lambda d: d["symbols"].update(points={"kind": "turnout", "concurrent": []}),
        "unknown key",
    ),
    (
        lambda d: d["symbols"].update(
            points={"kind": "turnout", "names": {"through": "to_up"}}
        ),
        "names unknown transit",
    ),
    (lambda d: d["symbols"]["west"].update(length=0), "positive integer"),
    (lambda d: d["symbols"].update(here={"kind": "portal"}), "missing key"),
    (
        lambda d: d["symbols"]["west"].update(sensors={"C": "s1"}),
        "sensors names unknown end",
    ),
    (lambda d: d["symbols"]["west"].update(at=[1, 2, 3]), "at must be two integers"),
    (lambda d: d["symbols"]["west"].update(at=["a", "b"]), "at must be two integers"),
    (lambda d: d["symbols"]["west"].update(rot=45), "rot must be one of"),
    (lambda d: d["symbols"]["west"].update(flip="yes"), "flip must be true or false"),
    # A fixed crossing has no motor, so there is nothing for an address to
    # answer to (ADR-0022).
    (
        lambda d: d["symbols"].update(points={"kind": "crossing", "addr": "31"}),
        "unknown key",
    ),
    # Each kind is drawn one way, so nothing picks between appearances.
    (
        lambda d: d["symbols"].update(points={"kind": "crossing", "angle": "shallow"}),
        "unknown key",
    ),
]


def test_sensor_ids_load_and_are_dropped_by_derivation() -> None:
    doc = spanned()
    doc["symbols"]["west"]["sensors"] = {"A": "s1", "B": "s2"}
    assert derive(doc)["blocks"]["west"] == {"length": 1000}


def test_the_motorised_kinds_are_the_ones_with_a_motor() -> None:
    """ADR-0022's table, which a fixed crossing is not in: it has no motor, so
    it has no position to be commanded into and takes no address."""
    assert set(POSITIONS) == {"turnout", "single_slip", "double_slip"}


@pytest.mark.parametrize("kind", sorted(POSITIONS))
def test_every_leg_of_a_motorised_kind_wants_one_of_the_two_positions(
    kind: str,
) -> None:
    """One motor, two positions: a way through the symbol takes some leg, and
    the leg has to say which way the points must lie, whichever leg it is."""
    assert set(POSITIONS[kind]) == set(LIBRARY[kind])
    assert set(POSITIONS[kind].values()) == {"closed", "thrown"}


@pytest.mark.parametrize("kind", sorted(POSITIONS))
def test_a_motorised_symbol_takes_the_address_hardware_answers_to(kind: str) -> None:
    """`addr` is a plain string and nothing checks it: a DCC accessory number
    is a string that happens to be digits, and what a physical point answers to
    is knowledge the drawing cannot hold (ADR-0022)."""
    doc = two_blocks(points={"kind": kind, "addr": "31"})
    assert Drawing.from_document(doc).symbols["points"].addr == "31"


def test_an_address_written_as_digits_is_read_as_the_string_it_names() -> None:
    """`addr: 31` in the yaml is the accessory number 31, not an integer the
    schema has to refuse."""
    doc = two_blocks(points={"kind": "turnout", "addr": 31})
    assert Drawing.from_document(doc).symbols["points"].addr == "31"


def throat(**spec: Any) -> dict[str, Any]:
    """`west` reaching `east` straight or `north` diverging, over one point."""
    doc = two_blocks(
        north=block(),
        north_stop={"kind": "terminal"},
        points={"kind": "turnout", **spec},
    )
    doc["wires"] += [
        ["west.B", "points.toe"],
        ["points.straight", "east.A"],
        ["points.diverging", "north.A"],
        ["north.B", "north_stop.P"],
    ]
    return doc


def test_an_address_changes_nothing_in_the_layout_but_the_points() -> None:
    """The derived layout's shape does not depend on an address being there
    (#94) — everything except the `points` key itself (ADR-0031)."""
    addressed = derive(throat(addr="31"))
    bare = derive(throat())
    assert "points" in addressed["connections"]["points"]
    del addressed["connections"]["points"]["points"]
    assert addressed == bare


def test_a_way_names_every_point_it_crosses_and_the_position_it_wants() -> None:
    """The layout's whole knowledge of hardware: an address and a position,
    per way, in the position the leg that way takes wants (ADR-0031)."""
    assert derive(throat(addr="31"))["connections"]["points"]["points"] == {
        "east_A__west_B": [{"addr": "31", "position": "closed"}],
        "north_A__west_B": [{"addr": "31", "position": "thrown"}],
    }


def test_a_point_wearing_no_address_is_left_out() -> None:
    """A drawing may be finished as topology and unfinished as wiring: it
    derives, and the layout carries only what can be thrown. The connection
    then has nothing to say and says nothing, as `concurrent` does."""
    assert "points" not in derive(throat())["connections"]["points"]


def test_one_address_wanted_in_both_positions_is_emitted_verbatim() -> None:
    """The way cannot be thrown at all, and the layout says so rather than
    dropping the transit: derivation's topology never depends on an address
    (#94), and `motor_faults` is where the fault is reported."""
    assert derive(ganged_in_series())["connections"]["throat"]["points"] == {
        "east_A__west_B": [
            {"addr": "1", "position": "closed"},
            {"addr": "1", "position": "thrown"},
        ]
    }


def test_gotthards_ganged_points_come_out_one_entry_each() -> None:
    """The railroad that gangs points, worked through by hand from its wires.

    `A1.A` reaches `A4.B` over `sw2` alone, lying straight, and `sw2` shares
    address `5` with `sw1`, so one entry is the whole of it. `A2.A` reaches
    `CE1.B` over five points: `sw1` straight (`5`), `sw3` diverging (`6`),
    then `sw8` and `sw7` both straight — which are two of the four on address
    `1`, wanting the same position, so they collapse to one — and `sw10`
    diverging (`2`). Sorted by address, four entries for five points.
    """
    points = committed("gotthard").connections["j1"].points
    assert points["A1_A__A4_B"] == (Point("5", "closed"),)
    assert points["A2_A__CE1_B"] == (
        Point("1", "closed"),
        Point("2", "thrown"),
        Point("5", "closed"),
        Point("6", "thrown"),
    )


def test_placement_loads_and_derives_to_the_same_layout() -> None:
    """Geometry is the drawing's alone (ADR-0018): placing every symbol, and
    placing them somewhere else, derives the same layout as placing none."""
    bare = spanned()
    placed = spanned()
    for i, symbol in enumerate(placed["symbols"].values()):
        symbol.update(at=[i * 2, 3], rot=90, flip=True)
    assert derive(placed) == derive(bare)


def test_the_90_degree_crossings_are_two_kinds_sharing_one_pin_set() -> None:
    """Their footprints and pin positions differ, which is why they are two
    kinds rather than two appearances of one (ui/EDITOR.md); what they declare
    is the same two exclusive routes over the same four pins."""
    for kind in ("crossing_90", "crossing_90d"):
        doc = two_blocks(points={"kind": kind})
        symbol = Drawing.from_document(doc).symbols["points"]
        assert symbol.pins == ("a1", "a2", "b1", "b2")
        assert symbol.transits == {"a": ("a1", "a2"), "b": ("b1", "b2")}
        assert symbol.concurrent == frozenset()


def test_a_block_takes_no_label() -> None:
    """A block's key is its only name (#82). The display label it once took is
    refused outright rather than ignored, so a file still carrying one is a
    finding at load rather than a name that quietly stops being drawn."""
    doc = spanned()
    doc["symbols"]["west"]["label"] = "Zürich HB Gleis 1"
    with pytest.raises(ValueError, match=r"unknown key\(s\) \['label'\]"):
        Drawing.from_document(doc)


@pytest.mark.parametrize("mutate, message", _SCHEMA_ERRORS)
def test_schema_errors(mutate: Mutate, message: str) -> None:
    doc = two_blocks(gap={**gap_symbol(), "concurrent": []})
    mutate(doc)
    with pytest.raises((ValueError, TypeError), match=message):
        Drawing.from_document(doc)
