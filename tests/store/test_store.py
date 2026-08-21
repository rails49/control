"""Tests at the AssetStore seam: CRUD contract and scenario validation."""

import shutil
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml.representer import RepresenterError

from tc49.lib.layout import Layout
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore, yamlfile
from tests.harness import ROOT
from tests.store.railroads import RAILROADS


@pytest.fixture
def store() -> AssetStore:
    return AssetStore(ROOT)


@pytest.fixture
def scratch_store(tmp_path: Path) -> AssetStore:
    (tmp_path / "layouts").mkdir()
    shutil.copy(
        ROOT / "layouts" / "crossover-yard.drawing.yaml",
        tmp_path / "layouts" / "crossover-yard.drawing.yaml",
    )
    return AssetStore(tmp_path)


@pytest.fixture
def drawings(tmp_path: Path) -> AssetStore:
    """Every committed railroad, somewhere writable."""
    (tmp_path / "layouts").mkdir()
    for path in (ROOT / "layouts").glob("*.drawing.yaml"):
        shutil.copy(path, tmp_path / "layouts" / path.name)
    return AssetStore(tmp_path)


def written(root: Path, name: str) -> str:
    return (root / "layouts" / f"{name}.drawing.yaml").read_text()


def prose(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("#")]


# The railroads that explain themselves in comments, which is what there is to
# keep. Not every drawing has them — one made in the editor starts with none —
# so the ones with prose are read off rather than assumed to be all of them.
COMMENTED = [name for name in RAILROADS if prose(written(ROOT, name))]


def meet_document() -> dict[str, Any]:
    return {
        "scenario": "meet",
        "layout": "crossover-yard",
        "trains": {"freight_1": {"length": 1100, "at": "yard_w", "facing": "B"}},
        "requests": [
            {"train": "freight_1", "from": "yard_w.B", "to": ["yard_e"], "at": 0},
        ],
    }


def test_list_layouts_and_scenarios(store: AssetStore) -> None:
    assert {"crossover-yard", "gotthard-v0", "facing-pair"} <= set(store.list())
    assert "crossover-yard/meet" in store.list("crossover-yard")
    assert all(s.startswith("crossover-yard/") for s in store.list("crossover-yard"))


def test_a_layout_is_derived_from_its_drawing_at_get(store: AssetStore) -> None:
    layout = store.get("facing-pair")
    assert isinstance(layout, Layout)
    assert layout.connections["gap"].transits["east_A__west_B"] == ("east.A", "west.B")


def test_a_drawing_is_read_back_as_the_document_it_is(store: AssetStore) -> None:
    """`get` derives and throws the document away; the editor edits the
    document, so the store hands it back unchanged."""
    doc = store.drawing("facing-pair")
    assert doc["drawing"] == "facing-pair"
    assert set(doc["symbols"]) == {"west", "east", "west_stop", "east_stop"}
    assert {"pins": ["west.B", "east.A"], "connection": "gap"} in doc["wires"]


@pytest.mark.parametrize("name", RAILROADS)
def test_saving_an_unchanged_drawing_changes_no_byte(
    drawings: AssetStore, tmp_path: Path, name: str
) -> None:
    """Read and write with nothing in between, and the file is the file."""
    before = written(tmp_path, name)
    drawings.put(drawings.drawing(name))
    assert written(tmp_path, name) == before


def test_a_railroad_explains_itself_in_comments() -> None:
    """Else the test below is parametrised over nothing and says nothing, which
    is what its own `assert before` refuses to do one railroad at a time."""
    assert COMMENTED


@pytest.mark.parametrize("name", COMMENTED)
def test_placing_every_symbol_keeps_the_prose(
    drawings: AssetStore, tmp_path: Path, name: str
) -> None:
    """The first editor save writes `at:` onto every symbol line, which is
    where a hand-written drawing does its explaining: 107 of Gotthard's 237
    lines are comments. A fresh dump would delete every one."""
    before = prose(written(tmp_path, name))
    assert before  # else this would pass by saying nothing

    doc = drawings.drawing(name)
    for i, symbol in enumerate(doc["symbols"].values()):
        symbol["at"] = [i * 2, 0]
    drawings.put(doc)

    assert prose(written(tmp_path, name)) == before
    placed = drawings.drawing(name)
    assert all("at" in symbol for symbol in placed["symbols"].values())


@pytest.mark.parametrize("name", RAILROADS)
def test_a_saved_drawing_derives_what_it_did(drawings: AssetStore, name: str) -> None:
    drawings.put(drawings.drawing(name))
    assert drawings.get(name) == AssetStore(ROOT).get(name)


def test_a_placement_lands_above_the_next_symbol_s_comment(
    drawings: AssetStore, tmp_path: Path
) -> None:
    """Where a paragraph introduces the *next* symbol, the new key has to go
    above it. ruamel holds that paragraph against the last key of the symbol
    before, so an unguarded append writes the placement underneath it: sw39's
    `at:` below the eight lines introducing Claro west, which parses and reads
    as nonsense."""
    doc = drawings.drawing("gotthard-v0")
    doc["symbols"]["sw39"]["at"] = [4, 7]
    drawings.put(doc)

    lines = written(tmp_path, "gotthard-v0").splitlines()
    assert lines.index("    at: [4, 7]") < lines.index(
        "  # Claro west, drawn from real symbols (#46): the yellow line fans out to all"
    )
    assert drawings.drawing("gotthard-v0")["symbols"]["sw39"]["at"] == [4, 7]


def test_deleting_a_symbol_takes_the_comment_above_it(
    drawings: AssetStore, tmp_path: Path
) -> None:
    """A comment describes the thing under it, so it goes when that goes."""
    doc = drawings.drawing("gotthard-v0")
    del doc["symbols"]["return_loop"]
    doc["wires"] = [w for w in doc["wires"] if "return_loop" not in str(w)]
    drawings.put(doc)

    text = written(tmp_path, "gotthard-v0")
    assert "return_loop" not in text
    assert "# The return loop off the east end" not in text
    assert "# The east ladder." in text  # the next symbol's keeps its own


def test_a_new_drawing_is_written_in_the_style_a_committed_one_is(
    drawings: AssetStore, tmp_path: Path
) -> None:
    """There is nothing to merge into, and a plain dump would write `at:` over
    three lines and every wire as `- - pin`. Style is per node once written, so
    a file created sprawling stays sprawling."""
    doc = drawings.drawing("facing-pair")
    doc["drawing"] = "facing-pair-copy"
    doc["symbols"]["west"]["at"] = [2, 4]
    drawings.put(doc)

    text = written(tmp_path, "facing-pair-copy")
    assert "at: [2, 4]" in text
    assert "- [west.A, west_stop.P]" in text
    copied, original = drawings.get("facing-pair-copy"), drawings.get("facing-pair")
    assert isinstance(copied, Layout) and isinstance(original, Layout)
    assert copied.connections == original.connections


def test_a_placement_lands_above_a_paragraph_held_by_a_block_list(
    tmp_path: Path,
) -> None:
    """A symbol whose last value is a block list holds the next symbol's
    paragraph one level down, against the list's last item rather than against
    any key. Missing it puts the placement below the paragraph."""
    path = tmp_path / "d.yaml"
    path.write_text(
        "symbols:\n"
        "  gap:\n"
        "    kind: connection\n"
        "    pins:\n"
        "      - A\n"
        "      - B\n"
        "\n"
        "  # the paragraph introducing east\n"
        "  east: {kind: terminal}\n"
    )
    doc: dict[str, Any] = {
        "symbols": {
            "gap": {"kind": "connection", "pins": ["A", "B"], "at": [1, 2]},
            "east": {"kind": "terminal"},
        }
    }
    yamlfile.save(path, doc)

    lines = path.read_text().splitlines()
    assert lines.index("    at: [1, 2]") < lines.index(
        "  # the paragraph introducing east"
    )


def test_a_document_that_will_not_serialise_leaves_the_file_alone(
    tmp_path: Path,
) -> None:
    """The file is the only copy of its own reasoning, so it is not truncated
    until there is something to put in it."""
    path = tmp_path / "d.yaml"
    path.write_text("# reasoning\nsymbols:\n  west: {kind: terminal}\n")
    before = path.read_text()

    with pytest.raises(RepresenterError):
        yamlfile.save(path, {"symbols": {"west": {"kind": object()}}})
    assert path.read_text() == before


def test_a_save_after_one_that_failed_writes_the_file_it_was_given(
    tmp_path: Path,
) -> None:
    """The failed save must leave nothing of itself behind either. One shared
    ruamel instance kept the context manager the failed dump set up, so the
    next save wrote into that dump's stream and truncated its own file to
    nothing while reporting success."""
    path = tmp_path / "d.yaml"
    path.write_text("# reasoning\nsymbols:\n  west: {kind: terminal}\n")

    with pytest.raises(RepresenterError):
        yamlfile.save(path, {"symbols": {"west": {"kind": object()}}})
    yamlfile.save(path, {"symbols": {"west": {"kind": "block", "length": 1000}}})

    assert "length: 1000" in path.read_text()
    assert "# reasoning" in path.read_text()


def test_meet_scenario_loads_clean(store: AssetStore) -> None:
    scenario = store.get("crossover-yard/meet")
    assert isinstance(scenario, Scenario)
    assert scenario.layout == "crossover-yard"
    assert scenario.trains["freight_1"].length == 1100
    assert scenario.trains["express_2"].at == "up_e"
    assert scenario.trains["freight_1"].facing == "B"
    first = scenario.requests[0]
    assert (first.train, first.depart, first.arrivals, first.at) == (
        "freight_1",
        "yard_w.B",
        ("yard_e",),
        0,
    )


def test_scenario_layout_must_exist(scratch_store: AssetStore) -> None:
    doc = meet_document()
    doc["layout"] = "atlantis"
    with pytest.raises(ValueError, match="atlantis"):
        scratch_store.put(doc)


def test_train_starting_block_must_exist(scratch_store: AssetStore) -> None:
    doc = meet_document()
    doc["trains"]["freight_1"]["at"] = "yard_q"
    with pytest.raises(ValueError, match="yard_q"):
        scratch_store.put(doc)


def test_train_must_declare_its_facing(scratch_store: AssetStore) -> None:
    doc = meet_document()
    del doc["trains"]["freight_1"]["facing"]
    with pytest.raises(ValueError, match="freight_1.*facing"):
        scratch_store.put(doc)


def test_facing_must_be_an_end_letter(scratch_store: AssetStore) -> None:
    doc = meet_document()
    doc["trains"]["freight_1"]["facing"] = "yard_w.B"
    with pytest.raises(ValueError, match="freight_1"):
        scratch_store.put(doc)


def test_facing_must_name_an_end_a_connection_holds(
    scratch_store: AssetStore,
) -> None:
    """`yard_w` is a terminal block and `yard_w.A` its wall, so a train
    placed facing it could never leave: every drag would compose a request
    rejected `unreachable` (#145). A file request keeps the
    freedom to state that end — facing is a discipline, not an invariant
    (ADR-0019) — but a placement is what every later request is composed
    from, so it is checked at load."""
    doc = meet_document()
    doc["trains"]["freight_1"]["facing"] = "A"
    with pytest.raises(ValueError, match="meet.*freight_1.*yard_w.A"):
        scratch_store.put(doc)


def test_request_train_must_be_declared(scratch_store: AssetStore) -> None:
    doc = meet_document()
    doc["requests"][0]["train"] = "ghost"
    with pytest.raises(ValueError, match="ghost"):
        scratch_store.put(doc)


def test_arrival_blocks_must_exist(scratch_store: AssetStore) -> None:
    doc = meet_document()
    doc["requests"][0]["to"] = ["yard_x.A"]
    with pytest.raises(ValueError, match="arrival 'yard_x.A' names unknown block"):
        scratch_store.put(doc)


def test_a_bare_arrival_block_must_exist_too(scratch_store: AssetStore) -> None:
    """An arrival entry may name a whole block rather than an end — the meet
    scenario's first request does — and the block is read off the entry the
    same way either way, so an unknown one is refused in the same words."""
    doc = meet_document()
    doc["requests"][0]["to"] = ["yard_x"]
    with pytest.raises(ValueError, match="arrival 'yard_x' names unknown block"):
        scratch_store.put(doc)


def test_departure_end_must_be_an_end_or_bare_letter(
    scratch_store: AssetStore,
) -> None:
    doc = meet_document()
    doc["requests"][0]["from"] = "yard_q.B"
    with pytest.raises(ValueError, match="yard_q"):
        scratch_store.put(doc)


def test_an_address_typed_onto_a_turnout_is_read_back_unchanged(
    scratch_store: AssetStore,
) -> None:
    """What the editor does with a typed address: save the document, reopen it,
    and read back what was typed (ADR-0022). Nothing checks an address, so a
    string that is not a number has to survive the trip too."""
    doc = scratch_store.drawing("crossover-yard")
    doc["symbols"]["west_ladder"]["addr"] = "LH-3/2"
    scratch_store.put(doc)
    reopened = scratch_store.drawing("crossover-yard")
    assert reopened["symbols"]["west_ladder"]["addr"] == "LH-3/2"


def test_put_is_whole_document_create_or_replace(scratch_store: AssetStore) -> None:
    scratch_store.put(meet_document())
    assert scratch_store.list("crossover-yard") == ["crossover-yard/meet"]

    replaced = meet_document()
    replaced["trains"]["freight_1"]["length"] = 900
    scratch_store.put(replaced)

    scenario = scratch_store.get("crossover-yard/meet")
    assert isinstance(scenario, Scenario)
    assert scenario.trains["freight_1"].length == 900


def test_put_rejects_invalid_documents_and_writes_nothing(
    scratch_store: AssetStore,
) -> None:
    doc = meet_document()
    doc["trains"]["freight_1"]["at"] = "yard_q"
    with pytest.raises(ValueError):
        scratch_store.put(doc)
    assert scratch_store.list("crossover-yard") == []


def test_put_refuses_a_layout_document(scratch_store: AssetStore) -> None:
    """A layout is derived, never stored, so there is nothing to put it into
    (ADR-0015)."""
    doc: dict[str, Any] = {"layout": "crossover-yard", "blocks": {}, "connections": {}}
    with pytest.raises(ValueError, match="neither a drawing nor a scenario"):
        scratch_store.put(doc)


def test_delete_removes_the_document(scratch_store: AssetStore) -> None:
    scratch_store.put(meet_document())
    scratch_store.delete("crossover-yard/meet")
    assert scratch_store.list("crossover-yard") == []
    with pytest.raises(FileNotFoundError):
        scratch_store.get("crossover-yard/meet")
