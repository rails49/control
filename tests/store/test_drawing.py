"""Tests at the drawing seam: the schema, the three derivation passes, and
the refusals (docs/store/DRAWING.md).

The end-to-end proof is the committed railroads: each derives a layout the
validator accepts, with the shape its drawing describes. The rest are
hand-built documents, kept small enough to read as a statement about one pass
each.
"""

from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from tc49.lib.layout import Layout
from tc49.store import AssetStore
from tc49.store.drawing import Drawing
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


def test_gotthard_derives_one_junction_at_airolo_and_two_at_claro() -> None:
    layout = committed("gotthard")
    assert len(layout.blocks) == 14
    assert sorted(layout.connections) == ["airolo", "claro_east", "claro_west"]
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
    airolo = committed("gotthard").connections["airolo"]
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


def test_claro_west_keeps_its_names_and_gains_the_pairs_its_ladder_allows() -> None:
    """Every transit there is identified by one symbol transit, so the names
    the hand-written layout picked survive being drawn. What is new is the
    concurrency: shunting track 3's sidings shares no switch with the yellow
    reaching track 1 or track 2."""
    claro_west = committed("gotthard").connections["claro_west"]
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
    with pytest.raises(ValueError, match="name it"):
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
    airolo = committed_drawing("gotthard").explain()["connections"]["airolo"]
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
    # Only the kinds drawn several ways take an angle.
    (
        lambda d: d["symbols"].update(points={"kind": "turnout", "angle": "shallow"}),
        "unknown key",
    ),
]


def test_hardware_ids_load_and_are_dropped_by_derivation() -> None:
    doc = spanned()
    doc["symbols"]["west"]["sensors"] = {"A": "s1", "B": "s2"}
    assert derive(doc)["blocks"]["west"] == {"length": 1000}


def test_placement_loads_and_derives_to_the_same_layout() -> None:
    """Geometry is the drawing's alone (ADR-0018): placing every symbol, and
    placing them somewhere else, derives the same layout as placing none."""
    bare = spanned()
    placed = spanned()
    for i, symbol in enumerate(placed["symbols"].values()):
        symbol.update(at=[i * 2, 3], rot=90, flip=True)
    assert derive(placed) == derive(bare)


def test_an_angle_loads_on_the_kinds_drawn_several_ways() -> None:
    """Wires meet a symbol at whatever angle their pins give them, so a
    crossing has an appearance per pair of leg angles. All share one pin set,
    so the choice reaches nothing but the picture."""
    doc = two_blocks(points={"kind": "crossing", "angle": "shallow"})
    assert Drawing.from_document(doc).symbols["points"].pins == ("a1", "a2", "b1", "b2")


def test_a_block_label_loads_and_is_dropped_by_derivation() -> None:
    """The key is the id that prefixes every transit id; the label is the
    platform's real name and reaches nothing downstream."""
    doc = spanned()
    doc["symbols"]["west"]["label"] = "Zürich HB Gleis 1"
    assert derive(doc)["blocks"]["west"] == {"length": 1000}
    assert "west" in derive(doc)["blocks"]


@pytest.mark.parametrize("mutate, message", _SCHEMA_ERRORS)
def test_schema_errors(mutate: Mutate, message: str) -> None:
    doc = two_blocks(gap={**gap_symbol(), "concurrent": []})
    mutate(doc)
    with pytest.raises((ValueError, TypeError), match=message):
        Drawing.from_document(doc)
