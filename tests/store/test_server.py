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

from tc49.store import AssetStore, Backup
from tc49.store.backup import Said
from tc49.store.server import handle, make_server
from tests.harness import ASSETS, catalogued


@pytest.fixture
def store(tmp_path: Path) -> AssetStore:
    catalogued(tmp_path)
    (tmp_path / "layouts").mkdir()
    for path in (ASSETS / "layouts").glob("*.yaml"):
        shutil.copy(path, tmp_path / "layouts" / path.name)
    return AssetStore(tmp_path)


@pytest.fixture
def backup(tmp_path: Path) -> Backup:
    """The backup over the same root. Every route below is a drawing's or a
    roster's, and what a save does to it is arm a timer nothing here lets
    fire: the store is no git repository and automation is off, which is the
    state a fresh installation is in."""
    return Backup(tmp_path, log=lambda _: None)


def test_the_drawings_are_listed(store: AssetStore, backup: Backup) -> None:
    status, body = handle(store, backup, "GET", "/drawings", None)
    assert status == 200
    assert "reversing-loops-v0" in body["drawings"]


def test_a_drawing_is_served_as_the_document_it_is(
    store: AssetStore, backup: Backup
) -> None:
    status, body = handle(store, backup, "GET", "/drawings/facing-pair", None)
    assert status == 200
    assert body["drawing"] == "facing-pair"
    assert {"pins": ["west.B", "east.A"], "connection": "gap"} in body["wires"]


def test_an_unknown_drawing_is_not_found(store: AssetStore, backup: Backup) -> None:
    status, body = handle(store, backup, "GET", "/drawings/atlantis", None)
    assert status == 404
    assert "atlantis" in body["error"]


def test_a_put_saves_the_drawing_and_keeps_its_prose(
    store: AssetStore, tmp_path: Path, backup: Backup
) -> None:
    doc = store.drawing("reversing-loops-v0")
    doc["symbols"]["sw16"]["at"] = [4, 7]
    status, _ = handle(store, backup, "PUT", "/drawings/reversing-loops-v0", doc)

    assert status == 200
    text = (tmp_path / "layouts" / "reversing-loops-v0.drawing.yaml").read_text()
    assert "# The WX310, west of the station" in text
    assert store.drawing("reversing-loops-v0")["symbols"]["sw16"]["at"] == [4, 7]


def test_a_put_naming_a_different_drawing_is_refused(
    store: AssetStore, backup: Backup
) -> None:
    doc = store.drawing("facing-pair")
    status, body = handle(store, backup, "PUT", "/drawings/reversing-loops-v0", doc)
    assert status == 400
    assert "facing-pair" in body["error"]


def test_a_roster_is_served_as_the_document_it_is(
    store: AssetStore, backup: Backup
) -> None:
    """The route is the document, so what comes back is the file: the cars
    the railroad owns and the entries each train is made of, which is what an
    editing surface needs and what the derived answer withholds (#388)."""
    status, body = handle(store, backup, "GET", "/rosters/reversing-loops-v0", None)
    assert status == 200
    assert body["roster"] == "reversing-loops-v0"
    assert body["cars"]["south_car"] == {"model": "bench-900"}
    assert body["trains"]["south"] == {"cars": [{"car": "south_car"}]}


def test_a_roster_is_written_and_read_back(tmp_path: Path, backup: Backup) -> None:
    """The round trip the stock screen is, on a box with nothing on it: a
    drawing saved this morning has no roster beside it, and this is what puts
    the first train on the railroad (#388, #392)."""
    catalogued(tmp_path)
    store = AssetStore(tmp_path)
    doc = {
        "roster": "oval",
        "cars": {"krokodil_a": {"model": "arnold-ce68", "addr": "3"}},
        "trains": {"ore": {"cars": [{"car": "krokodil_a"}, {"model": "bench-600"}]}},
    }
    assert handle(store, backup, "PUT", "/rosters/oval", doc) == (
        200,
        {"saved": "oval"},
    )
    assert handle(store, backup, "GET", "/rosters/oval", None) == (200, doc)
    # And the same document read as the run views read it: one car of 122 and
    # one of 600, summed by the train that names them (ADR-0061).
    assert handle(store, backup, "GET", "/rosters/oval/trains", None)[1] == {
        "roster": "oval",
        "trains": {
            "ore": {
                "length": 722,
                "functions": [{"name": "lights", "values": ["off", "on"]}],
            }
        },
    }


def test_a_roster_naming_a_model_the_installation_has_not_is_refused(
    tmp_path: Path, backup: Backup
) -> None:
    """400 carrying what the validator said, and nothing written: a roster is
    strict — there is no picture to look at, so there is no half-made shape
    to save."""
    catalogued(tmp_path)
    store = AssetStore(tmp_path)
    status, body = handle(
        store,
        backup,
        "PUT",
        "/rosters/oval",
        {
            "roster": "oval",
            "cars": {},
            "trains": {"ore": {"cars": [{"model": "hopper"}]}},
        },
    )
    assert status == 400
    assert "hopper" in body["error"]
    assert not (tmp_path / "layouts" / "oval.roster.yaml").exists()


def test_a_roster_with_a_train_that_has_nothing_in_it_is_refused(
    tmp_path: Path, backup: Backup
) -> None:
    """400 and nothing written, so a roster the store takes is always one
    `GET /rosters/<name>/trains` can answer: an empty `cars` list names no
    cars, and the train it names is the one to go and fill (#412)."""
    catalogued(tmp_path)
    status, body = handle(
        AssetStore(tmp_path),
        backup,
        "PUT",
        "/rosters/oval",
        {"roster": "oval", "cars": {}, "trains": {"ore": {"cars": []}}},
    )
    assert status == 400
    assert "train 'ore': names no cars" in body["error"]
    assert not (tmp_path / "layouts" / "oval.roster.yaml").exists()


def test_two_cars_sharing_a_decoder_address_are_refused(
    tmp_path: Path, backup: Backup
) -> None:
    """Both answer the same packet and no run can tell them apart, so the
    roster that says so is refused rather than written."""
    catalogued(tmp_path)
    store = AssetStore(tmp_path)
    status, body = handle(
        store,
        backup,
        "PUT",
        "/rosters/oval",
        {
            "roster": "oval",
            "cars": {
                "krokodil_a": {"model": "arnold-ce68", "addr": "3"},
                "krokodil_b": {"model": "arnold-ce68", "addr": "3"},
            },
            "trains": {},
        },
    )
    assert status == 400
    assert "share address '3'" in body["error"]
    assert not (tmp_path / "layouts" / "oval.roster.yaml").exists()


def test_a_roster_cannot_be_saved_under_another_railroads_name(
    tmp_path: Path, backup: Backup
) -> None:
    """The name in the path is the railroad the roster belongs to, so a
    document naming another one is refused rather than filed under this."""
    catalogued(tmp_path)
    status, body = handle(
        AssetStore(tmp_path),
        backup,
        "PUT",
        "/rosters/oval",
        {"roster": "loop", "cars": {}, "trains": {}},
    )
    assert status == 400
    assert "loop" in body["error"]


def test_the_run_views_answer_is_the_trains_below_the_document(
    store: AssetStore, backup: Backup
) -> None:
    """Every train the railroad owns, whether anything places it or not: the
    roster is the run view's source for what there is to place, and the one
    place a length is written down (ADR-0039, ui/PANEL.md)."""
    status, body = handle(
        store, backup, "GET", "/rosters/reversing-loops-v0/trains", None
    )
    assert status == 200
    assert body["roster"] == "reversing-loops-v0"
    assert body["trains"]["south"] == {"length": 900, "functions": []}
    assert body["trains"] == dict(sorted(body["trains"].items()))


def test_a_trains_functions_are_served_with_it(tmp_path: Path, backup: Backup) -> None:
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
    status, body = handle(
        AssetStore(tmp_path), backup, "GET", "/rosters/shed/trains", None
    )
    assert status == 200
    assert body["trains"]["light_1"] == {
        "length": 220,
        "functions": [
            {"name": "headlights", "values": ["off", "on"]},
            {"name": "vacuum", "values": ["off", "low", "high"]},
        ],
    }


def test_a_railroad_with_no_roster_owns_nothing_yet(
    store: AssetStore, backup: Backup
) -> None:
    """A drawing made this morning has no roster file beside it, which is not
    a missing railroad: it is a railroad with no trains on it yet. Both routes
    say so — the document is the empty one the stock screen draws itself
    from, and the derived answer has no trains in it."""
    status, body = handle(store, backup, "GET", "/rosters/facing-pair-2", None)
    assert status == 200
    assert body == {"roster": "facing-pair-2", "cars": {}, "trains": {}}
    status, body = handle(store, backup, "GET", "/rosters/facing-pair-2/trains", None)
    assert status == 200
    assert body == {"roster": "facing-pair-2", "trains": {}}


def test_the_catalogue_is_served_as_the_documents_it_holds(
    store: AssetStore, backup: Backup
) -> None:
    """Every model the installation knows, keyed by name and each as written:
    what the screen that edits them reads, rather than the merged models a
    roster is read against (#392)."""
    status, body = handle(store, backup, "GET", "/catalogue", None)
    assert status == 200
    assert body["models"]["arnold-ce68"] == {
        "model": "arnold-ce68",
        "kind": "locomotive",
        "length": 122,
        "manufacturer": "Arnold",
        "scale": "N",
        "description": 'SBB Ce 6/8 II "Krokodil"',
        "functions": {"0": {"name": "lights"}},
    }
    assert "bench-900" in body["models"]


def test_a_model_is_served_as_the_document_it_is(
    store: AssetStore, backup: Backup
) -> None:
    status, body = handle(store, backup, "GET", "/catalogue/conrad-e10", None)
    assert status == 200
    assert body["model"] == "conrad-e10"


def test_an_unknown_model_is_not_found(store: AssetStore, backup: Backup) -> None:
    status, body = handle(store, backup, "GET", "/catalogue/atlantis", None)
    assert status == 404
    assert "atlantis" in body["error"]


def test_an_installation_with_no_catalogue_answers_an_empty_map(
    tmp_path: Path, backup: Backup
) -> None:
    """Which is every fresh box: no `catalogue/` directory is no models yet,
    and the screen that would write the first one has to be able to read the
    empty map to draw itself."""
    status, body = handle(
        AssetStore(tmp_path / "fresh"), backup, "GET", "/catalogue", None
    )
    assert status == 200
    assert body == {"models": {}}


def test_a_model_is_written_and_read_back(tmp_path: Path, backup: Backup) -> None:
    """The round trip a fresh box needs: with no catalogue every car names a
    model the installation has not got, so no roster can be written at all
    until one can be (#392)."""
    doc = {"model": "re460", "kind": "locomotive", "length": 220}
    store = AssetStore(tmp_path)
    assert handle(store, backup, "PUT", "/catalogue/re460", doc) == (
        200,
        {"saved": "re460"},
    )
    assert handle(store, backup, "GET", "/catalogue/re460", None) == (200, doc)


def test_a_model_that_does_not_validate_leaves_no_file_behind(
    tmp_path: Path, backup: Backup
) -> None:
    """400 carrying what the validator said, and nothing written: a
    half-written entry is a roster that stops loading."""
    store = AssetStore(tmp_path)
    status, body = handle(
        store,
        backup,
        "PUT",
        "/catalogue/re460",
        {"model": "re460", "kind": "wagon", "length": 220},
    )
    assert status == 400
    assert "kind" in body["error"]
    assert handle(store, backup, "GET", "/catalogue", None)[1] == {"models": {}}


def test_a_model_cannot_be_saved_under_another_name(
    tmp_path: Path, backup: Backup
) -> None:
    """The name in the path is the key every car refers to the model by, so a
    document naming another one is refused rather than filed under this."""
    store = AssetStore(tmp_path)
    status, body = handle(
        store,
        backup,
        "PUT",
        "/catalogue/re465",
        {"model": "re460", "kind": "locomotive", "length": 220},
    )
    assert status == 400
    assert "re460" in body["error"]
    assert handle(store, backup, "GET", "/catalogue", None)[1] == {"models": {}}


def test_a_review_returns_the_layout_and_why_it_is_that(
    store: AssetStore, backup: Backup
) -> None:
    status, body = handle(
        store, backup, "POST", "/review", store.drawing("crossover-yard")
    )
    assert status == 200
    assert body["red_pins"] == [] and body["refused"] is None
    excluded = body["explain"]["connections"]["crossover"]["exclusive"]
    assert {"transits": ["dn_to_up", "up_to_dn"], "shared": ["diamond"]} in excluded
    assert sorted(body["layout"]["connections"]) == [
        "crossover",
        "east_ladder",
        "west_ladder",
    ]


def test_a_review_names_the_wires_the_editor_has_to_name(
    store: AssetStore, backup: Backup
) -> None:
    """A bare wire between two blocks is a connection and needs a name the
    editor mints. Which wires those are is a walk of the drawing, so it comes
    from here rather than a second walk in TypeScript."""
    status, body = handle(
        store, backup, "POST", "/review", store.drawing("facing-pair")
    )
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
    store: AssetStore, backup: Backup
) -> None:
    """A drawing with a dangling pin is the normal state mid-edit, so it is
    reviewed with a 200 and a refusal inside, not an error."""
    doc = store.drawing("crossover-yard")
    doc["wires"] = doc["wires"][:-1]
    status, body = handle(store, backup, "POST", "/review", doc)
    assert status == 200
    assert body["red_pins"] and body["refused"] is not None
    assert body["layout"] is None


def test_a_document_that_will_not_load_is_a_bad_request(
    store: AssetStore, backup: Backup
) -> None:
    """A schema error is the client's, and it is reported as one."""
    status, body = handle(
        store, backup, "POST", "/review", {"drawing": "d", "symbols": 3}
    )
    assert status == 400
    assert "symbols" in body["error"]


def test_a_drawing_that_will_not_load_is_reported_rather_than_thrown(
    store: AssetStore, tmp_path: Path, backup: Backup
) -> None:
    """A file can be broken by hand between two editor sessions. Serving it
    must answer, not drop the connection and leave the editor guessing."""
    (tmp_path / "layouts" / "broken.drawing.yaml").write_text(
        "drawing: broken\nsymbols: 3\n"
    )
    status, body = handle(store, backup, "GET", "/drawings/broken", None)
    assert status == 400
    assert "symbols" in body["error"]


def test_a_query_string_does_not_make_a_new_route(
    store: AssetStore, backup: Backup
) -> None:
    """A cache-buster from `fetch` is not a different resource."""
    assert handle(store, backup, "GET", "/drawings?t=1", None)[0] == 200
    assert handle(store, backup, "GET", "/drawings/facing-pair?t=1", None)[0] == 200


def test_an_unknown_route_is_not_found(store: AssetStore, backup: Backup) -> None:
    for method, path in (
        ("GET", "/nowhere"),
        ("DELETE", "/drawings/reversing-loops-v0"),
        # No DELETE on this face for any document, and nothing below a roster
        # but the run views' derived answer, which is read and never written.
        ("DELETE", "/rosters/reversing-loops-v0"),
        ("PUT", "/rosters/reversing-loops-v0/trains"),
        ("GET", "/rosters/reversing-loops-v0/cars"),
    ):
        status, _ = handle(store, backup, method, path, None)
        assert status == 404


def test_review_is_the_only_route_that_takes_a_document(
    store: AssetStore, backup: Backup
) -> None:
    """Everything else is addressed by name, so a body on them is a mistake
    worth catching rather than ignoring."""
    doc: dict[str, Any] = store.drawing("facing-pair")
    assert handle(store, backup, "PUT", "/drawings/facing-pair", None)[0] == 400
    assert handle(store, backup, "PUT", "/catalogue/conrad-e10", None)[0] == 400
    assert handle(store, backup, "PUT", "/rosters/facing-pair", None)[0] == 400
    assert handle(store, backup, "POST", "/review", None)[0] == 400
    assert handle(store, backup, "POST", "/review", doc)[0] == 200


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


def served(tmp_path: Path) -> tuple[Any, str, Thread]:
    """A server on a port, listening, with the caller owning the shutdown."""
    (tmp_path / "layouts").mkdir()
    shutil.copy(
        ASSETS / "layouts" / "facing-pair.drawing.yaml",
        tmp_path / "layouts" / "facing-pair.drawing.yaml",
    )
    server = make_server(tmp_path, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}", thread


def test_a_page_on_another_origin_is_refused_every_route(tmp_path: Path) -> None:
    """A page somebody's browser visits while the store is running must not be
    able to drive the railroad it is on the network with (#329, ADR-0055).

    `Origin` is written by the browser and a page cannot forge it, so a
    request carrying one that is not this server's own `Host` is answered 403
    and nothing runs — the read that would list the backups and the write that
    would roll the store back alike. No `Access-Control-*` header is sent
    either way, which is the other half: even the reply to the refusal is one
    the page cannot read."""
    server, url, thread = served(tmp_path)
    try:
        for method, route, body in (
            ("GET", "/drawings", None),
            ("GET", "/backup", None),
            ("POST", "/backup/restore", b'{"commit": "abc123"}'),
        ):
            foreign = Request(
                f"{url}{route}",
                data=body,
                headers={"Origin": "http://evil.example"},
                method=method,
            )
            with pytest.raises(HTTPError) as refused:
                urlopen(foreign)
            assert refused.value.code == 403
            assert refused.value.headers.get("Access-Control-Allow-Origin") is None

        # And the preflight that would ask permission for the JSON body.
        with pytest.raises(HTTPError) as preflight:
            urlopen(Request(f"{url}/review", method="OPTIONS"))
        assert preflight.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_app_reaches_every_route_on_its_own_origin(tmp_path: Path) -> None:
    """Which is how the app reaches them on a layout server: the proxy that
    serves the page routes them and passes the host header through, so the
    browser's `Origin` and the `Host` that arrives here are one host. Named
    rather than loopback, so this is the host comparison and not the loopback
    clause below."""
    server, url, thread = served(tmp_path)
    try:
        same = Request(
            f"{url}/drawings",
            headers={
                "Origin": "https://layout.rails49.org",
                "Host": "layout.rails49.org",
            },
            method="GET",
        )
        with urlopen(same) as listed:
            assert json.load(listed) == {"drawings": ["facing-pair"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_client_with_no_origin_at_all_goes_through(tmp_path: Path) -> None:
    """A native client, a `curl`, a same-origin `GET`: no page wrote the
    header because no page is involved. The LAN stays the trust boundary and
    this narrows nothing about it (ADR-0042)."""
    server, url, thread = served(tmp_path)
    try:
        with urlopen(f"{url}/drawings") as listed:
            assert json.load(listed) == {"drawings": ["facing-pair"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_store_that_is_not_there_yet_comes_up_and_answers(tmp_path: Path) -> None:
    """A fresh installation has drawn no railroad and nothing seeds one, so
    the server is rooted at a directory that does not exist yet and serves an
    empty list rather than refusing to come up (#320). The first `PUT` is what
    makes the directory."""
    root = tmp_path / "never-made"
    server = make_server(root, port=0)
    url = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"{url}/drawings") as listed:
            assert json.load(listed) == {"drawings": []}

        with pytest.raises(HTTPError) as missing:
            urlopen(f"{url}/drawings/reversing-loops")
        assert missing.value.code == 404

        doc = AssetStore(ASSETS).drawing("facing-pair")
        saved = Request(
            f"{url}/drawings/facing-pair",
            data=json.dumps(doc).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urlopen(saved) as stored:
            assert stored.status == 200
        with urlopen(f"{url}/drawings") as listed:
            assert json.load(listed) == {"drawings": ["facing-pair"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- backup ------------------------------------------------------------------
#
# The routes, not the driving: what git makes of a commit is `test_backup.py`'s,
# and what is here is the mapping onto requests — which is why these run against
# a fake driver rather than a repository.


class FakeGit:
    """A git that says the store is a repository with one document waiting,
    and remembers what it was asked to do about it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.porcelain = " M layouts/reversing-loops.drawing.yaml\n"
        self.pushes = Said(True, "")

    def __call__(self, root: Path, *args: str, timeout: float | None = None) -> Said:
        self.calls.append(args)
        if args[0] == "rev-parse":
            return Said(True, str(root))
        if args[0] == "status":
            # Stripped as `git` strips it, so a first line whose status is
            # ` M` reaches the parser as it really does (#389).
            return Said(True, self.porcelain.strip())
        if args[0] == "remote":
            return Said(True, "origin")
        if args[0] == "commit":
            self.porcelain = ""
            return Said(True, "[main 0000000] " + args[2])
        if args[0] == "push":
            return self.pushes
        if args[0] == "log":
            return Said(True, "a1b2c3d\tbackup: reversing-loops\t2026-09-02 19:04")
        return Said(True, "")


@pytest.fixture
def driving() -> FakeGit:
    return FakeGit()


@pytest.fixture
def clock() -> list[float]:
    """The seconds the backup reads, moved by the test: the idle window is
    waited out by assignment rather than by sleeping."""
    return [0.0]


@pytest.fixture
def driven(tmp_path: Path, driving: FakeGit, clock: list[float]) -> Backup:
    return Backup(
        tmp_path, run=driving, log=lambda _: None, now=lambda: clock[0], idle_s=20.0
    )


def test_the_backup_route_says_what_the_store_can_do(
    store: AssetStore, driven: Backup
) -> None:
    """Everything the UI draws from: where the store is, whether it can be
    backed up at all, whether it is being, what is waiting and what there is
    to come back to."""
    status, body = handle(store, driven, "GET", "/backup", None)
    assert status == 200
    assert body["repository"] is True
    assert body["automatic"] is False
    assert body["needs"] == []
    assert body["outstanding"] == ["reversing-loops"]
    assert body["backups"][0]["said"] == "backup: reversing-loops"


def test_the_switch_is_turned_over_the_route(store: AssetStore, driven: Backup) -> None:
    """Automated backup is off until somebody turns it on, and the answer is
    the standing it left behind rather than an acknowledgement."""
    status, body = handle(store, driven, "PUT", "/backup", {"automatic": True})
    assert status == 200
    assert body["automatic"] is True
    assert (
        handle(store, driven, "PUT", "/backup", {"automatic": False})[1]["automatic"]
        is False
    )


def test_the_switch_takes_a_word_it_understands(
    store: AssetStore, driven: Backup
) -> None:
    """The one bad request among these: a body that says nothing about the
    switch is the caller's mistake, where everything git refuses is not."""
    assert handle(store, driven, "PUT", "/backup", {"automatic": "yes"})[0] == 400
    assert handle(store, driven, "PUT", "/backup", None)[0] == 400


def test_backing_up_answers_what_git_said(store: AssetStore, driven: Backup) -> None:
    """The button. It commits what is outstanding under a message naming it,
    and the reply carries git's own words."""
    status, body = handle(store, driven, "POST", "/backup/commit", None)
    assert status == 200
    assert body["ok"] is True
    assert "backup: reversing-loops" in body["said"]
    assert body["outstanding"] == []


def test_a_restore_over_a_dirty_tree_is_refused_inside_a_200(
    store: AssetStore, driven: Backup
) -> None:
    """A refusal the UI has to read and say. A status code would leave it
    guessing which of the states of somebody's machine this was."""
    status, body = handle(store, driven, "POST", "/backup/restore", None)
    assert status == 200
    assert body["ok"] is False
    assert "reversing-loops" in body["said"]


def test_adopting_a_repository_takes_its_address(
    store: AssetStore, driven: Backup, driving: FakeGit
) -> None:
    """The route hands the address to the backup and answers what it said,
    inside a 200 like every other refusal — here, that the fake's store is a
    repository already."""
    assert handle(store, driven, "POST", "/backup/repository", None)[0] == 400
    assert handle(store, driven, "POST", "/backup/repository", {"url": 3})[0] == 400
    status, body = handle(
        store, driven, "POST", "/backup/repository", {"url": "git@example:a/b.git"}
    )
    assert status == 200
    assert body["ok"] is False
    assert "is a repository already" in body["said"]
    assert body["repository"] is True


def test_a_restore_names_the_backup_to_come_back_to(
    store: AssetStore, driven: Backup, driving: FakeGit
) -> None:
    """A person restoring usually names an earlier backup: the session they
    want undone was backed up itself."""
    handle(store, driven, "POST", "/backup/commit", None)
    status, body = handle(
        store, driven, "POST", "/backup/restore", {"commit": "a1b2c3d"}
    )

    assert status == 200
    assert body["ok"] is True
    assert (
        "restore",
        "--source",
        "a1b2c3d",
        "--worktree",
        "--staged",
        "--",
        ".",
    ) in driving.calls


def test_an_unknown_backup_route_is_not_found(
    store: AssetStore, driven: Backup
) -> None:
    assert handle(store, driven, "POST", "/backup", None)[0] == 404
    assert handle(store, driven, "GET", "/backup/commit", None)[0] == 404


def test_a_save_arms_the_idle_timer(
    store: AssetStore, driven: Backup, driving: FakeGit, clock: list[float]
) -> None:
    """The one place the two meet: a drawing written over the route is what
    the idle timer then waits out. The save itself commits nothing — it is the
    tick after the store has gone quiet that does."""
    driven.switch(True)
    handle(store, driven, "PUT", "/drawings/facing-pair", store.drawing("facing-pair"))
    committed = [call for call in driving.calls if call[0] == "commit"]
    assert committed == []

    clock[0] += 20.0
    driven.due()
    assert [call[2] for call in driving.calls if call[0] == "commit"] == [
        "backup: reversing-loops"
    ]


def test_saving_a_model_arms_the_idle_timer(
    store: AssetStore, driven: Backup, driving: FakeGit, clock: list[float]
) -> None:
    """A model written over the route is a document of the store that moved,
    so it arms the timer the way a drawing does — the catalogue is backed up
    with everything else and not by itself (#392)."""
    driven.switch(True)
    doc = {"model": "re460", "kind": "locomotive", "length": 220}
    assert handle(store, driven, "PUT", "/catalogue/re460", doc)[0] == 200
    assert [call for call in driving.calls if call[0] == "commit"] == []

    clock[0] += 20.0
    driven.due()
    assert [call[0] for call in driving.calls if call[0] == "commit"] == ["commit"]


def test_saving_a_roster_arms_the_idle_timer(
    store: AssetStore, driven: Backup, driving: FakeGit, clock: list[float]
) -> None:
    """A roster written over the route is a document of the store that moved,
    so it arms the timer the way a drawing and a model do — the one place
    saving and backup meet (#388)."""
    driven.switch(True)
    doc = {
        "roster": "facing-pair-2",
        "cars": {"t1_car": {"model": "bench-1000"}},
        "trains": {"t1": {"cars": [{"car": "t1_car"}]}},
    }
    assert handle(store, driven, "PUT", "/rosters/facing-pair-2", doc)[0] == 200
    assert [call for call in driving.calls if call[0] == "commit"] == []

    clock[0] += 20.0
    driven.due()
    assert [call[0] for call in driving.calls if call[0] == "commit"] == ["commit"]


def test_a_save_lands_over_a_remote_that_cannot_be_reached(
    store: AssetStore, driving: FakeGit, clock: list[float], tmp_path: Path
) -> None:
    """A lost network never reaches the person drawing: the drawing is written,
    the commit is made, and what could not be pushed is on the log and nowhere
    else (ADR-0053). No dialog, because there is nothing they can answer about
    the wifi."""
    said: list[str] = []
    # Its own, rather than the fixture's: the push timer is up from the start,
    # so the tick that commits is the one that finds the remote gone.
    driven = Backup(
        tmp_path,
        run=driving,
        log=said.append,
        now=lambda: clock[0],
        idle_s=20.0,
        push_s=0.0,
    )
    driven.switch(True)
    driving.pushes = Said(False, "fatal: could not read from remote repository")

    status, _ = handle(
        store, driven, "PUT", "/drawings/facing-pair", store.drawing("facing-pair")
    )
    assert status == 200
    assert (tmp_path / "layouts" / "facing-pair.drawing.yaml").exists()

    clock[0] += 20.0
    driven.due()
    assert [call[2] for call in driving.calls if call[0] == "commit"] == [
        "backup: reversing-loops"
    ]
    assert any("could not read from remote" in line for line in said)


def test_a_store_that_is_no_repository_serves_and_saves_as_it_always_did(
    store: AssetStore, tmp_path: Path
) -> None:
    """The ordinary state of a fresh installation. Backup says what it needs
    and nothing else changes — nothing here runs `git init`; the way in is a
    repository the person made (#355)."""
    backup = Backup(tmp_path / "not-a-repo", log=lambda _: None)
    assert handle(store, backup, "GET", "/drawings", None)[0] == 200
    assert (
        handle(
            store, backup, "PUT", "/drawings/facing-pair", store.drawing("facing-pair")
        )[0]
        == 200
    )

    status, body = handle(store, backup, "GET", "/backup", None)
    assert status == 200
    assert body["repository"] is False
    assert "create an empty private repository" in body["needs"][0]


def test_a_page_on_this_machine_reaches_a_store_whose_host_was_rewritten(
    tmp_path: Path,
) -> None:
    """The app in development: vite rewrites `Host` to the proxy's target, so
    the page's own origin and the host arriving here disagree by an accident
    of the proxy and every write was refused (#351).

    A loopback origin is admitted whatever the `Host` (ADR-0057). It gives an
    attacker nothing — a page it controls is served from somewhere else and
    its origin is that somewhere — and anyone who can serve a page from this
    machine can reach the store with no browser at all.
    """
    server, url, thread = served(tmp_path)
    try:
        proxied = Request(
            f"{url}/drawings",
            headers={"Origin": "http://localhost:5173"},  # Host: 127.0.0.1:port
            method="GET",
        )
        with urlopen(proxied) as listed:
            assert json.load(listed) == {"drawings": ["facing-pair"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
