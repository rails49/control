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


def test_a_roster_is_served_for_the_railroad_that_owns_it(
    store: AssetStore, backup: Backup
) -> None:
    """Every train the railroad owns, whether anything places it or not: the
    roster is the run view's source for what there is to place, and the one
    place a length is written down (ADR-0039, ui/PANEL.md)."""
    status, body = handle(store, backup, "GET", "/rosters/reversing-loops-v0", None)
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
    status, body = handle(AssetStore(tmp_path), backup, "GET", "/rosters/shed", None)
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
    a missing railroad: it is a railroad with no trains on it yet."""
    status, body = handle(store, backup, "GET", "/rosters/facing-pair-2", None)
    assert status == 200
    assert body == {"roster": "facing-pair-2", "trains": {}}


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

    def __call__(self, root: Path, *args: str) -> Said:
        self.calls.append(args)
        if args[0] == "rev-parse":
            return Said(True, str(root))
        if args[0] == "status":
            return Said(True, self.porcelain)
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
    and nothing else changes — nothing here runs `git init`."""
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
    assert "git init" in body["needs"][0]
