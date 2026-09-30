"""What `deploy/compose.yaml` has to say, and what it may not (ADR-0059,
decision 5).

An app comes up alone: started by nothing, waiting for whatever it reads
rather than being ordered after it, and the two process suites beside this
one hold each of them to that against a real broker. The file that starts
them can undo it in one line — a `depends_on` puts the order back into the
deployment, and an app then waits on a store's container being up rather than
on the store answering, which is not the same thing and is not what any of
them was written to survive.

So the file is read here and four rules are asserted on what it says: one
service per app, no app run twice, nothing ordered, and no service claiming a
device. The last is what makes one file both boxes': `docker compose up` on a
machine with no steel under it starts nothing that reaches for a cable,
because nothing here reaches for one at all. The services that did were
translators, and no translator is this repository's — each lives in a
repository of its own, as the one that spoke to the command station does in
[`rails49/dccex`](https://github.com/rails49/dccex) (#587, #595).
"""

from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import yaml

from tests.system.test_app_boundaries import APPS

COMPOSE = Path(__file__).resolve().parents[2] / "deploy/compose.yaml"

MODULE = "tc49."
"""What a service's command says to run one of ours: `python -m tc49.<app>`,
the command line each app's `__main__` parses."""

FACE = ("tc49", "serve")
"""The one app started by name rather than by module: the store's face is a
subcommand of the `tc49` script, which is what a wheel installs (ADR-0014)."""


def services() -> dict[str, dict[str, Any]]:
    """The file's services, by name."""
    document = cast(dict[str, Any], yaml.safe_load(COMPOSE.read_text()))
    found = cast(dict[str, dict[str, Any]], document["services"])
    assert found, "no services in deploy/compose.yaml"
    return found


def words(service: dict[str, Any]) -> list[str]:
    """What a service runs, whichever of the two keys says it. A list rather
    than a string throughout: a shell form would put an app's flags at the
    mercy of a shell that is not there."""
    run: list[str] = []
    for key in ("entrypoint", "command"):
        said = service.get(key)
        if isinstance(said, list):
            run += [str(word) for word in cast(list[Any], said)]
    return run


def app_of(service: dict[str, Any]) -> str | None:
    """The app a service runs, or `None` where it runs something else — a
    stock image, or a `tc49` subcommand that is not an app."""
    run = words(service)
    for before, word in pairwise(run):
        if before == "-m" and word.startswith(MODULE):
            return word[len(MODULE) :]
        if (before, word) == FACE:
            return "store"
    return None


def running() -> dict[str, list[str]]:
    """Which services run which app, by app."""
    found: dict[str, list[str]] = {}
    for name, service in services().items():
        app = app_of(service)
        if app is not None:
            found.setdefault(app, []).append(name)
    return found


def test_one_service_per_app() -> None:
    """Every app is a container of its own (ADR-0059, decision 5), so every
    app has a service here. The list is `test_app_boundaries`'s, which is
    already held against the tree, so a package that arrives without a way to
    deploy it fails one check and not two."""
    missing = sorted(app for app in APPS if app not in running())
    assert not missing, f"no compose service runs {missing}"


def test_a_service_that_runs_an_app_names_one() -> None:
    """A command line here and a package in `src/tc49/` are one thing said
    twice, and a rename that moves only one of them leaves a service that
    exits on its first start."""
    unknown = sorted(app for app in running() if app not in APPS)
    assert not unknown, f"not an app: {unknown}"


def test_no_app_is_run_by_two_services() -> None:
    """One app, one process (ADR-0059): two services running the same app
    would be two of its client ids on one broker, and two clients sharing one
    id disconnect each other (decision 7)."""
    twice = {app: names for app, names in running().items() if len(names) > 1}
    assert not twice, f"one app run by two services: {twice}"


def test_nothing_depends_on_anything() -> None:
    """The rule the apps are written to: an app is started against nothing
    and waits (ADR-0059, decision 5), so the order compose would impose is
    both unnecessary and untrue — a container that is up is not a store that
    answers."""
    ordered = sorted(
        name for name, service in services().items() if "depends_on" in service
    )
    assert not ordered, (
        f"{ordered} depend on another service; every app waits for what it"
        " reads instead"
    )


def test_nothing_claims_a_device() -> None:
    """A service that claims a device claims one the box it comes up on may
    not have, and nothing here answers for what is wired to a box: the
    services that did were translators and a device mirror, and each of those
    is a repository of its own (#595). Read off the file rather than off a
    name, so a `devices:` written back fails here whatever it is called."""
    loose = sorted(
        name for name, service in services().items() if service.get("devices")
    )
    assert not loose, f"{loose} claim a device; no service here owns hardware"
