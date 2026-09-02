"""Where an installation's store is rooted, and what overrides it (#320).

The store the fixtures live in is the harness's and is found by
`tc49.bench.runner.find_assets`; this is the other one — the person's, which
`tc49 live` and the store server open and which starts out empty.
"""

from pathlib import Path

import pytest

from tc49.store import DEFAULT_STORE, STORE_ENV, AssetStore, store_root


def test_the_default_is_a_visible_directory_in_the_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`~/tc49/`, expanded here: it is a repository somebody clones, pushes
    and looks at rather than a cache, so it is not an XDG data directory and
    it is not left as a literal `~` for something else to expand."""
    monkeypatch.delenv(STORE_ENV, raising=False)
    assert DEFAULT_STORE == "~/tc49"
    assert store_root() == Path.home() / "tc49"


def test_the_environment_says_where_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """The UI opens the store with no arguments, so a flag alone could not be
    the answer."""
    monkeypatch.setenv(STORE_ENV, "/srv/railroad")
    assert store_root() == Path("/srv/railroad")


def test_the_environment_may_write_a_home_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing expands the environment's `~`, so this does."""
    monkeypatch.setenv(STORE_ENV, "~/elsewhere")
    assert store_root() == Path.home() / "elsewhere"


def test_the_flag_beats_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A person typing `--store` is answering the question for this one
    command, which is the last word by definition."""
    monkeypatch.setenv(STORE_ENV, "/srv/railroad")
    assert store_root(Path("/tmp/other")) == Path("/tmp/other")


def test_an_empty_variable_is_no_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shell script exporting it empty must mean the same as not exporting
    it, rather than rooting the store at the working directory."""
    monkeypatch.setenv(STORE_ENV, "   ")
    assert store_root() == Path.home() / "tc49"


def test_a_store_that_is_not_there_yet_holds_nothing_and_says_so(
    tmp_path: Path,
) -> None:
    """A fresh installation has drawn no railroad and nothing seeds one, so
    the empty store answers rather than refusing to come up. Only `get` of a
    name raises, which is how every caller already asks whether a railroad is
    there."""
    store = AssetStore(tmp_path / "never-made")
    assert store.list() == []
    assert store.list("reversing-loops") == []
    assert store.catalogue() == {}
    assert store.roster("reversing-loops").trains == {}
    with pytest.raises(FileNotFoundError):
        store.get("reversing-loops")


def test_an_empty_store_takes_the_first_drawing_somebody_makes(
    tmp_path: Path,
) -> None:
    """Not seeded is not read-only: the directories are made by the `put`
    that needs them, so the editor's first save is what fills the store."""
    store = AssetStore(tmp_path / "never-made")
    store.put({"drawing": "first", "symbols": {}, "wires": []})
    assert store.list() == ["first"]
