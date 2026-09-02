"""The two stock documents: what a catalogue's model says, and what a
railroad's roster makes of it.

Mostly at the validator rather than through the store, because what is under
test is the schema — the merge, the derivations and the refusals — and a
document written inline says what it is testing where the assertion is. The
store's own reads (the committed catalogue, a roster loaded beside a drawing)
are at the bottom.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from tc49.lib.roster import Model, Train
from tc49.store import AssetStore
from tc49.store.stock import validate_model, validate_roster
from tests.harness import ROOT


def models(*docs: dict[str, Any]) -> dict[str, Model]:
    """A catalogue of this test's own, validated as a file's would be."""
    return {doc["model"]: validate_model(doc, doc["model"]) for doc in docs}


RE460 = {
    "model": "sbb-re460",
    "kind": "locomotive",
    "length": 220,
    "functions": {
        "0": {"name": "headlights"},
        "5": {"name": "vacuum", "values": ["off", "low", "high"]},
    },
}
IC2000 = {"model": "sbb-ic2000", "kind": "passenger", "length": 270}
HBIS = {"model": "hbis", "kind": "freight", "length": 180}
CATALOGUE = models(RE460, IC2000, HBIS)


def roster(cars: dict[str, Any], trains: dict[str, Any] | None = None) -> Any:
    return validate_roster(
        {"roster": "gotthard", "cars": cars, "trains": trains or {}}, CATALOGUE
    )


def test_a_model_is_a_length_a_kind_and_what_each_function_does() -> None:
    model = CATALOGUE["sbb-re460"]
    assert (model.kind, model.length) == ("locomotive", 220)
    assert model.functions["0"].name == "headlights"
    # Absent `values` is the plain switch, off to begin with.
    assert model.functions["0"].values == ("off", "on")
    assert model.functions["5"].values == ("off", "low", "high")


def test_a_model_may_say_who_made_it_what_scale_and_what_it_is() -> None:
    """The three a real product needs beyond a synthetic one (#317). Plain
    data: read back and carried, and nothing branches on them."""
    model = models({**RE460, "manufacturer": "Roco", "scale": "N", "description": "a"})
    assert model["sbb-re460"].manufacturer == "Roco"
    assert model["sbb-re460"].scale == "N"
    assert model["sbb-re460"].description == "a"


def test_a_model_saying_none_of_the_three_is_still_a_model() -> None:
    """Every `bench-<length>` stand-in is written this way, so all three are
    optional and absent reads as absent rather than as a blank."""
    assert CATALOGUE["hbis"].manufacturer is None
    assert CATALOGUE["hbis"].scale is None
    assert CATALOGUE["hbis"].description is None


def test_the_three_are_words_and_not_coerced() -> None:
    """`scale: 160` would read as a number where every other catalogue writes
    a word, and the two would not compare as the same thing — `_addr`'s reason
    one field along."""
    with pytest.raises(ValueError, match="scale: must be a non-empty string"):
        models({**IC2000, "scale": 160})


def test_a_car_inherits_the_three_and_may_not_override_them() -> None:
    """Who made a product and what scale it is are facts about the product, so
    a car saying otherwise would be describing a different one. The car's own
    document is not read for them, and what it says is ignored as any unknown
    key is."""
    catalogue = models({**RE460, "manufacturer": "Roco", "scale": "N"})
    owned = validate_roster(
        {
            "roster": "gotthard",
            "cars": {"re460_1": {"model": "sbb-re460", "manufacturer": "Arnold"}},
            "trains": {},
        },
        catalogue,
    )
    assert owned.cars["re460_1"].manufacturer == "Roco"
    assert owned.cars["re460_1"].scale == "N"


def test_the_two_real_locomotives_are_addressed_and_drive_alone() -> None:
    """#317: the first stock on a committed roster that somebody owns. Each is
    one car with the bare address its decoder answers to, and one train of that
    car — so each derives `light engine` and each drives on its own.

    The addresses are what the whole entry is for: without one,
    `LayoutInterface._addressed` yields nothing and a `move` writes no traction
    row at all.
    """
    roster = AssetStore(ROOT).roster("gotthard")
    addressed = {
        name: train.cars[0].car.addr
        for name, train in roster.trains.items()
        if train.cars and train.cars[0].car.addr is not None
    }
    assert addressed == {"e10": "10", "ce68": "11"}
    for name, length in (("e10", 103), ("ce68", 122)):
        train = roster.trains[name]
        assert train.length == length
        assert train.kind == "light engine"
        assert train.cars[0].car.scale == "N"
        assert [function.name for function in train.functions] == ["lights"]


def test_a_model_file_names_itself() -> None:
    """Filed under one name and referred to by another is a car pointing at
    nothing, so the disagreement is refused where it is written."""
    with pytest.raises(ValueError, match="names itself"):
        validate_model(IC2000, "sbb-ic2001")


def test_a_models_kind_is_one_of_the_four() -> None:
    with pytest.raises(ValueError, match="kind must be"):
        validate_model({**IC2000, "kind": "coach"}, "sbb-ic2000")


def test_a_function_number_is_written_as_a_string() -> None:
    """YAML integer keys and JSON object keys do not agree, so the number is
    quoted and an unquoted one is refused rather than silently renamed."""
    with pytest.raises(TypeError, match="written as a string"):
        validate_model({**IC2000, "functions": {0: {"name": "lights"}}}, "sbb-ic2000")


def test_a_car_with_no_overrides_is_its_model() -> None:
    """Zero overrides is the ordinary case, and the merged result is what is
    validated: the car is complete however little it was written with."""
    car = roster({"re460_1": {"model": "sbb-re460", "addr": "460"}}).cars["re460_1"]
    assert car.model == "sbb-re460"
    assert (car.kind, car.length) == ("locomotive", 220)
    assert car.functions == CATALOGUE["sbb-re460"].functions
    assert car.addr == "460"


def test_a_car_overriding_a_field_keeps_the_others() -> None:
    """One coach shortened is one field; what the product is otherwise still
    comes from the model, which is what having a model is for."""
    car = roster({"ic_2": {"model": "sbb-ic2000", "length": 285}}).cars["ic_2"]
    assert car.length == 285
    assert car.kind == CATALOGUE["sbb-ic2000"].kind
    assert car.functions == CATALOGUE["sbb-ic2000"].functions
    assert car.addr is None  # no decoder, so no address


def test_a_car_names_a_model_and_that_model_exists() -> None:
    with pytest.raises(ValueError, match="missing key"):
        roster({"ic_1": {"length": 270}})
    with pytest.raises(ValueError, match="unknown model"):
        roster({"ic_1": {"model": "sbb-ic3000"}})


def test_two_cars_may_not_share_one_address() -> None:
    """Both answer the same packet, and no run can tell them apart."""
    with pytest.raises(ValueError, match="share address"):
        roster(
            {
                "re460_1": {"model": "sbb-re460", "addr": "460"},
                "re460_2": {"model": "sbb-re460", "addr": "460"},
            }
        )


def test_an_address_is_written_as_a_string() -> None:
    """`460` and `"460"` would be one address written two ways, and two cars
    wearing them would not read as the collision they are."""
    with pytest.raises(ValueError, match="address must be"):
        roster({"re460_1": {"model": "sbb-re460", "addr": 460}})


def test_an_unknown_key_loads_and_is_not_carried() -> None:
    """The shelf a locomotive lives on, or what it cost, is worth writing down
    and no version of this software will ever read it — so it loads, at every
    level of both documents, and nothing carries it.

    `manufacturer` used to be the example here and is now a field of its own
    (#317). That is the intended path for one of these: lenient today, read
    the day something needs it, and no file rewritten either way.
    """
    catalogue = models({**IC2000, "shelf": "3b", "kind": "passenger"})
    plain = validate_roster(
        {
            "roster": "gotthard",
            "cars": {"ic_1": {"model": "sbb-ic2000"}},
            "trains": {"ic_721": {"cars": [{"car": "ic_1"}]}},
        },
        catalogue,
    )
    embellished = validate_roster(
        {
            "roster": "gotthard",
            "shed": "erstfeld",
            "cars": {"ic_1": {"model": "sbb-ic2000", "bought": 2019}},
            "trains": {"ic_721": {"cars": [{"car": "ic_1"}], "notes": "evenings"}},
        },
        catalogue,
    )
    assert embellished == plain


def test_a_trains_length_is_the_sum_of_its_cars() -> None:
    stock = roster(
        {
            "re460_1": {"model": "sbb-re460"},
            "ic_1": {"model": "sbb-ic2000"},
            "ic_2": {"model": "sbb-ic2000", "length": 285},
        },
        {
            "ic_721": {
                "cars": [
                    {"car": "re460_1"},
                    {"car": "ic_1", "orientation": "reverse"},
                    {"car": "ic_2"},
                ]
            }
        },
    )
    train = stock.trains["ic_721"]
    assert train.length == 220 + 270 + 285
    assert stock.lengths() == {"ic_721": 775}
    # Ordered, head first, and each car remembers which way round it is.
    assert [coupled.orientation for coupled in train.cars] == [
        "forward",
        "reverse",
        "forward",
    ]


def test_a_trains_kind_ignores_the_locomotives() -> None:
    """Every hauled train has one, so counting them would make every train
    mixed and the classification would say nothing (CONTEXT.md, **Kind**)."""
    stock = roster(
        {
            "re460_1": {"model": "sbb-re460"},
            "ic_1": {"model": "sbb-ic2000"},
            "hbis_1": {"model": "hbis"},
        },
        {
            "ic_721": {"cars": [{"car": "re460_1"}, {"car": "ic_1"}]},
            "mixed_9": {
                "cars": [{"car": "re460_1"}, {"car": "ic_1"}, {"car": "hbis_1"}]
            },
            "light_1": {"cars": [{"car": "re460_1"}]},
        },
    )
    assert stock.trains["ic_721"].kind == "passenger"
    assert stock.trains["mixed_9"].kind == "mixed"
    assert stock.trains["light_1"].kind == "light engine"


def test_a_trains_functions_are_its_cars_by_name_and_each_name_once() -> None:
    """What a person driving the train can switch, in the train's frame: a set
    with a locomotive at each end has one headlight to press, and which car it
    reaches is `layout`'s (ui/THROTTLE.md)."""
    stock = roster(
        {
            "re460_1": {"model": "sbb-re460"},
            "re460_2": {"model": "sbb-re460"},
            "ic_1": {"model": "sbb-ic2000"},
        },
        {
            "top_and_tail": {
                "cars": [
                    {"car": "re460_1"},
                    {"car": "ic_1"},
                    {"car": "re460_2", "orientation": "reverse"},
                ]
            },
            "ic_721": {"cars": [{"car": "ic_1"}]},
        },
    )
    functions = stock.trains["top_and_tail"].functions
    assert [function.name for function in functions] == ["headlights", "vacuum"]
    assert functions[1].values == ("off", "low", "high")
    # A train whose cars declare none has none, and so has one made of no cars.
    assert stock.trains["ic_721"].functions == ()
    assert Train(stated_length=400).functions == ()


def test_a_train_with_no_priority_sorts_after_every_train_that_has_one() -> None:
    """Absent means lowest, and no default number is written into a
    document: lowest number highest among the numbers that are present."""
    stock = roster(
        {"ic_1": {"model": "sbb-ic2000"}},
        {
            "whenever": {"cars": [{"car": "ic_1"}]},
            "ic_721": {"cars": [{"car": "ic_1"}], "priority": 2},
            "ice_1": {"cars": [{"car": "ic_1"}], "priority": 1},
        },
    )
    assert stock.trains["whenever"].priority is None
    assert sorted(stock.trains, key=lambda name: stock.trains[name].priority_key) == [
        "ice_1",
        "ic_721",
        "whenever",
    ]


def test_orientation_is_forward_or_reverse() -> None:
    """The word rather than a boolean, and only the two words."""
    with pytest.raises(ValueError, match="orientation must be"):
        roster(
            {"ic_1": {"model": "sbb-ic2000"}},
            {"ic_721": {"cars": [{"car": "ic_1", "orientation": "backwards"}]}},
        )


def test_a_train_is_made_of_cars_the_railroad_owns() -> None:
    with pytest.raises(ValueError, match="which the railroad has not"):
        roster({}, {"ic_721": {"cars": [{"car": "ic_1"}]}})


def test_a_train_states_a_length_only_where_it_names_no_cars() -> None:
    """The shape the committed rosters had before #223 rewrote them, kept so
    an older file on disk still loads. Saying both would be two ways to know
    one length, and that is the field that rots."""
    assert (
        roster({}, {"freight_1": {"length": 1100}}).trains["freight_1"].length == 1100
    )
    with pytest.raises(ValueError, match="never authored"):
        roster(
            {"ic_1": {"model": "sbb-ic2000"}},
            {"ic_721": {"cars": [{"car": "ic_1"}], "length": 270}},
        )


def test_the_committed_catalogue_is_what_the_library_railroads_need() -> None:
    """Every length the five rosters use, which is what lets each synthetic
    train be one car and no product be invented (#223)."""
    catalogue = AssetStore(ROOT).catalogue()
    lengths = {model.length for model in catalogue.values()}
    owned = {
        train.length
        for name in sorted(AssetStore(ROOT).list())
        for train in AssetStore(ROOT).roster(name).trains.values()
    }
    assert owned <= lengths
    # The synthetic stock is hauled, so a train of it derives `freight` rather
    # than `light engine`. The real locomotives beside it are the exception
    # and are `locomotive` (#317).
    bench = [model for model in catalogue.values() if model.name.startswith("bench-")]
    assert all(model.kind == "freight" for model in bench)


def test_every_library_train_is_one_bench_car_of_its_length() -> None:
    """The migration (#223): each of the five committed rosters is a handful
    of models by length with one car per train pointing at one.

    Nothing under `layouts/` authors a length any more — a train's is the sum
    of its cars — and the sum is the length that train had before, which is
    why no benchmark result moved.

    The two real locomotives (#317) are one car each as well, but of a product
    rather than a stand-in, so what holds of every train is the car count and
    that the length is derived; only the synthetic ones name a `bench-` model.
    """
    store = AssetStore(ROOT)
    for railroad in sorted(store.list()):
        for name, train in store.roster(railroad).trains.items():
            where = f"roster '{railroad}': train '{name}'"
            assert train.stated_length is None, where
            assert len(train.cars) == 1, where
            model = train.cars[0].car.model
            if model.startswith("bench-"):
                assert model == f"bench-{train.length}", where


def test_an_installation_with_no_catalogue_knows_no_models(tmp_path: Path) -> None:
    """Which is every railroad whose stock is still written the old way, and
    not a fault."""
    assert AssetStore(tmp_path).catalogue() == {}


def test_a_roster_is_read_against_the_catalogue_beside_it(tmp_path: Path) -> None:
    """The store's own path: a roster file naming a model the installation
    has, loaded as a committed one is."""
    (tmp_path / "catalogue").mkdir()
    (tmp_path / "catalogue" / "sbb-ic2000.yaml").write_text(yaml.safe_dump(IC2000))
    (tmp_path / "layouts").mkdir()
    (tmp_path / "layouts" / "gotthard.roster.yaml").write_text(
        yaml.safe_dump(
            {
                "roster": "gotthard",
                "cars": {"ic_1": {"model": "sbb-ic2000"}},
                "trains": {"ic_721": {"cars": [{"car": "ic_1"}]}},
            }
        )
    )
    stock = AssetStore(tmp_path).roster("gotthard")
    assert stock.cars["ic_1"].length == 270
    assert stock.trains["ic_721"].length == 270
