"""What `deploy/compose.yaml` may not say (ADR-0059, decision 5).

An app comes up alone: started by nothing, waiting for whatever it reads
rather than being ordered after it, and the process suite beside this one
holds each of them to that against a real broker. The file that starts them
can undo it in one line — a `depends_on` puts the order back into the
deployment, and an app then waits on a store's container being up rather than
on the store answering, which is not the same thing and is not what any of
them was written to survive.

So the file is read here, and the rules that keep the shape are asserted on
what it says: nothing is ordered, nothing runs an app that is not one, no app
is run twice, and nothing that owns a device on the layout box comes up in
the default set. What runs on a machine wired to steel is a profile a person
asks for by name.

**One service per app is not asserted**: no app has a compose service yet,
and the six of them arrive with the deployment issue rather than here. What
is asserted holds for whatever that adds.
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
    stock image, or the `tc49` command line, which is the harness and the
    store's face rather than an app of ADR-0059's six."""
    run = words(service)
    for before, word in pairwise(run):
        if before == "-m" and word.startswith(MODULE):
            return word[len(MODULE) :]
    return None


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


def test_a_service_that_runs_an_app_names_one() -> None:
    """A command line here and a package in `src/tc49/` are one thing said
    twice, and a rename that moves only one of them leaves a service that
    exits on its first start. The list is `test_app_boundaries`'s, which is
    already held against the tree, so the two checks cannot disagree about
    what the apps are."""
    unknown = sorted(
        f"{name} runs '{app}'"
        for name, service in services().items()
        if (app := app_of(service)) is not None and app not in APPS
    )
    assert not unknown, f"not an app: {unknown}"


def test_no_app_is_run_by_two_services() -> None:
    """One app, one process (ADR-0059): two services running the same app
    would be two of its client ids on one broker, and two clients sharing one
    id disconnect each other (decision 7)."""
    running: dict[str, list[str]] = {}
    for name, service in services().items():
        app = app_of(service)
        if app is not None:
            running.setdefault(app, []).append(name)
    twice = {app: names for app, names in running.items() if len(names) > 1}
    assert not twice, f"one app run by two services: {twice}"


def test_hardware_never_comes_up_in_the_default_set() -> None:
    """A service that claims a device claims one this machine may not have,
    so it is in a profile a person asks for by name. `docker compose up` on a
    box with no steel under it starts the software and nothing else — which
    is what makes one file the dev box's and the layout box's."""
    default = sorted(
        name
        for name, service in services().items()
        if service.get("devices") and not service.get("profiles")
    )
    assert not default, f"{default} own a device and are in the default set"
