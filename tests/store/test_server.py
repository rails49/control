"""Tests at the store's HTTP face: the routes the editor talks to.

Routing is a function of (method, path, body), so these exercise the contract
without a socket. What is served is the store's own behaviour, tested in
`test_store.py` and `test_drawing.py`; what is tested here is the mapping onto
requests and the status codes an editor has to distinguish.
"""

import json
import shutil
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tc49.store import AssetStore
from tc49.store.server import handle, make_server
from tests.harness import ASSETS, catalogued


@pytest.fixture
def store(tmp_path: Path) -> AssetStore:
    catalogued(tmp_path)
    (tmp_path / "layouts").mkdir()
    for path in (ASSETS / "layouts").glob("*.yaml"):
        shutil.copy(path, tmp_path / "layouts" / path.name)
    return AssetStore(tmp_path)


def test_the_drawings_are_listed(store: AssetStore) -> None:
    status, body = handle(store, "GET", "/drawings", None)
    assert status == 200
    assert "gotthard-v0" in body["drawings"]


def test_a_drawing_is_served_as_the_document_it_is(store: AssetStore) -> None:
    status, body = handle(store, "GET", "/drawings/facing-pair", None)
    assert status == 200
    assert body["drawing"] == "facing-pair"
    assert {"pins": ["west.B", "east.A"], "connection": "gap"} in body["wires"]


def test_an_unknown_drawing_is_not_found(store: AssetStore) -> None:
    status, body = handle(store, "GET", "/drawings/atlantis", None)
    assert status == 404
    assert "atlantis" in body["error"]


def test_a_put_saves_the_drawing_and_keeps_its_prose(
    store: AssetStore, tmp_path: Path
) -> None:
    doc = store.drawing("gotthard-v0")
    doc["symbols"]["sw16"]["at"] = [4, 7]
    status, _ = handle(store, "PUT", "/drawings/gotthard-v0", doc)

    assert status == 200
    text = (tmp_path / "layouts" / "gotthard-v0.drawing.yaml").read_text()
    assert "# The WX310, west of the station" in text
    assert store.drawing("gotthard-v0")["symbols"]["sw16"]["at"] == [4, 7]


def test_a_put_naming_a_different_drawing_is_refused(store: AssetStore) -> None:
    doc = store.drawing("facing-pair")
    status, body = handle(store, "PUT", "/drawings/gotthard-v0", doc)
    assert status == 400
    assert "facing-pair" in body["error"]


def test_a_roster_is_served_for_the_railroad_that_owns_it(store: AssetStore) -> None:
    """Every train the railroad owns, whether anything places it or not: the
    roster is the run view's source for what there is to place, and the one
    place a length is written down (ADR-0039, ui/PANEL.md)."""
    status, body = handle(store, "GET", "/rosters/gotthard-v0", None)
    assert status == 200
    assert body["roster"] == "gotthard-v0"
    assert body["trains"]["south"] == {"length": 900, "functions": []}
    assert body["trains"] == dict(sorted(body["trains"].items()))


def test_a_trains_functions_are_served_with_it(tmp_path: Path) -> None:
    """What a person driving the train can switch, by the names the catalogue
    gives them and by no number: the throttle view's whole source for its
    buttons (ui/THROTTLE.md). The library railroads' bench cars declare none,
    so this railroad owns a model that does."""
    catalogued(tmp_path)
    (tmp_path / "catalogue" / "re460.yaml").write_text(
        "model: re460\nkind: locomotive\nlength: 220\n"
        "functions:\n"
        "  '0': {name: headlights}\n"
        "  '5': {name: vacuum, values: ['off', low, high]}\n"
    )
    (tmp_path / "layouts").mkdir()
    (tmp_path / "layouts" / "shed.roster.yaml").write_text(
        "roster: shed\n"
        "cars:\n  re460_1: {model: re460}\n"
        "trains:\n  light_1: {cars: [{car: re460_1}]}\n"
    )
    status, body = handle(AssetStore(tmp_path), "GET", "/rosters/shed", None)
    assert status == 200
    assert body["trains"]["light_1"] == {
        "length": 220,
        "functions": [
            {"name": "headlights", "values": ["off", "on"]},
            {"name": "vacuum", "values": ["off", "low", "high"]},
        ],
    }


def test_a_railroad_with_no_roster_owns_nothing_yet(store: AssetStore) -> None:
    """A drawing made this morning has no roster file beside it, which is not
    a missing railroad: it is a railroad with no trains on it yet."""
    status, body = handle(store, "GET", "/rosters/facing-pair-2", None)
    assert status == 200
    assert body == {"roster": "facing-pair-2", "trains": {}}


def test_a_review_returns_the_layout_and_why_it_is_that(store: AssetStore) -> None:
    status, body = handle(store, "POST", "/review", store.drawing("crossover-yard"))
    assert status == 200
    assert body["red_pins"] == [] and body["refused"] is None
    excluded = body["explain"]["connections"]["crossover"]["exclusive"]
    assert {"transits": ["dn_to_up", "up_to_dn"], "shared": ["diamond"]} in excluded
    assert sorted(body["layout"]["connections"]) == [
        "crossover",
        "east_ladder",
        "west_ladder",
    ]


def test_a_review_names_the_wires_the_editor_has_to_name(store: AssetStore) -> None:
    """A bare wire between two blocks is a connection and needs a name the
    editor mints. Which wires those are is a walk of the drawing, so it comes
    from here rather than a second walk in TypeScript."""
    status, body = handle(store, "POST", "/review", store.drawing("facing-pair"))
    assert status == 200
    assert body["joints"] == [
        {
            "ends": ["east.A", "west.B"],
            "wires": [["east.A", "west.B"]],
            "name": "gap",
            "names": ["gap"],
        }
    ]


def test_a_review_of_work_in_progress_reports_rather_than_fails(
    store: AssetStore,
) -> None:
    """A drawing with a dangling pin is the normal state mid-edit, so it is
    reviewed with a 200 and a refusal inside, not an error."""
    doc = store.drawing("crossover-yard")
    doc["wires"] = doc["wires"][:-1]
    status, body = handle(store, "POST", "/review", doc)
    assert status == 200
    assert body["red_pins"] and body["refused"] is not None
    assert body["layout"] is None


def test_a_document_that_will_not_load_is_a_bad_request(store: AssetStore) -> None:
    """A schema error is the client's, and it is reported as one."""
    status, body = handle(store, "POST", "/review", {"drawing": "d", "symbols": 3})
    assert status == 400
    assert "symbols" in body["error"]


def test_a_drawing_that_will_not_load_is_reported_rather_than_thrown(
    store: AssetStore, tmp_path: Path
) -> None:
    """A file can be broken by hand between two editor sessions. Serving it
    must answer, not drop the connection and leave the editor guessing."""
    (tmp_path / "layouts" / "broken.drawing.yaml").write_text(
        "drawing: broken\nsymbols: 3\n"
    )
    status, body = handle(store, "GET", "/drawings/broken", None)
    assert status == 400
    assert "symbols" in body["error"]


def test_a_query_string_does_not_make_a_new_route(store: AssetStore) -> None:
    """A cache-buster from `fetch` is not a different resource."""
    assert handle(store, "GET", "/drawings?t=1", None)[0] == 200
    assert handle(store, "GET", "/drawings/facing-pair?t=1", None)[0] == 200


def test_an_unknown_route_is_not_found(store: AssetStore) -> None:
    for method, path in (("GET", "/nowhere"), ("DELETE", "/drawings/gotthard-v0")):
        status, _ = handle(store, method, path, None)
        assert status == 404


def test_review_is_the_only_route_that_takes_a_document(store: AssetStore) -> None:
    """Everything else is addressed by name, so a body on them is a mistake
    worth catching rather than ignoring."""
    doc: dict[str, Any] = store.drawing("facing-pair")
    assert handle(store, "PUT", "/drawings/facing-pair", None)[0] == 400
    assert handle(store, "POST", "/review", None)[0] == 400
    assert handle(store, "POST", "/review", doc)[0] == 200


def test_the_routes_are_reachable_over_http(tmp_path: Path) -> None:
    """Once, end to end, so the JSON and the status codes are known to survive
    a socket — the rest of this file tests the contract, not the plumbing."""
    (tmp_path / "layouts").mkdir()
    shutil.copy(
        ASSETS / "layouts" / "facing-pair.drawing.yaml",
        tmp_path / "layouts" / "facing-pair.drawing.yaml",
    )
    server = make_server(tmp_path, port=0)
    url = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"{url}/drawings") as listed:
            assert json.load(listed) == {"drawings": ["facing-pair"]}

        with urlopen(f"{url}/drawings/facing-pair") as served:
            doc = json.load(served)
        assert doc["drawing"] == "facing-pair"

        reviewed = Request(
            f"{url}/review",
            data=json.dumps(doc).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(reviewed) as answer:
            assert json.load(answer)["refused"] is None

        with pytest.raises(HTTPError) as missing:
            urlopen(f"{url}/drawings/atlantis")
        assert missing.value.code == 404

        # The browser preflights a JSON POST from the editor's own origin.
        preflight = Request(f"{url}/review", method="OPTIONS")
        with urlopen(preflight) as allowed:
            assert allowed.status == 200
            assert allowed.headers["Access-Control-Allow-Origin"] == "*"
            assert "POST" in allowed.headers["Access-Control-Allow-Methods"]

        # A body the handler cannot measure is answered, not dropped.
        unmeasured = Request(
            f"{url}/review",
            data=b"{}",
            headers={"Content-Length": "banana"},
            method="POST",
        )
        with pytest.raises(HTTPError) as refused:
            urlopen(unmeasured)
        assert refused.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
