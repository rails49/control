"""Tests at the AssetStore seam: CRUD contract and scenario validation."""

import shutil
from pathlib import Path
from typing import Any

import pytest

from tc49.store import AssetStore, Scenario

ROOT = Path(__file__).parent.parent


@pytest.fixture
def store() -> AssetStore:
    return AssetStore(ROOT)


@pytest.fixture
def scratch_store(tmp_path: Path) -> AssetStore:
    (tmp_path / "layouts").mkdir()
    shutil.copy(
        ROOT / "layouts" / "crossover-yard.layout.yaml",
        tmp_path / "layouts" / "crossover-yard.layout.yaml",
    )
    return AssetStore(tmp_path)


def meet_document() -> dict[str, Any]:
    return {
        "scenario": "meet",
        "layout": "crossover-yard",
        "trains": {"freight_1": {"length": 1100, "at": "yard_w"}},
        "requests": [
            {"train": "freight_1", "from": "yard_w.B", "to": ["yard_e"], "at": 0},
        ],
    }


def test_list_layouts_and_scenarios(store: AssetStore) -> None:
    assert {"crossover-yard", "gotthard"} <= set(store.list())
    assert "crossover-yard/meet" in store.list("crossover-yard")
    assert all(s.startswith("crossover-yard/") for s in store.list("crossover-yard"))


def test_meet_scenario_loads_clean(store: AssetStore) -> None:
    scenario = store.get("crossover-yard/meet")
    assert isinstance(scenario, Scenario)
    assert scenario.layout == "crossover-yard"
    assert scenario.trains["freight_1"].length == 1100
    assert scenario.trains["express_2"].at == "up_e"
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


def test_request_train_must_be_declared(scratch_store: AssetStore) -> None:
    doc = meet_document()
    doc["requests"][0]["train"] = "ghost"
    with pytest.raises(ValueError, match="ghost"):
        scratch_store.put(doc)


def test_arrival_blocks_must_exist(scratch_store: AssetStore) -> None:
    doc = meet_document()
    doc["requests"][0]["to"] = ["yard_x.A"]
    with pytest.raises(ValueError, match="yard_x"):
        scratch_store.put(doc)


def test_departure_end_must_be_an_end_or_bare_letter(
    scratch_store: AssetStore,
) -> None:
    doc = meet_document()
    doc["requests"][0]["from"] = "yard_q.B"
    with pytest.raises(ValueError, match="yard_q"):
        scratch_store.put(doc)


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


def test_delete_removes_the_document(scratch_store: AssetStore) -> None:
    scratch_store.put(meet_document())
    scratch_store.delete("crossover-yard/meet")
    assert scratch_store.list("crossover-yard") == []
    with pytest.raises(FileNotFoundError):
        scratch_store.get("crossover-yard/meet")
