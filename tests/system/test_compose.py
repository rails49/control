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
service per app, no app run twice, nothing ordered, and the hardware a box
owns in a profile of its own. The last is what makes one file both boxes':
`docker compose up` on a machine with no steel under it starts nothing that
claims a device, and a box wired to a command station asks for that profile
by name.
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

HARDWARE = frozenset({"dccex-usb", "dccex", "jmri"})
"""The services that exist because of what is wired to a box: the mirror that
owns the command station's device, the translator that speaks to it, and the
third-party appliance an operator clicks (ADR-0043). Named here because
hardware is a fact about a machine rather than something readable off a
command line — what they have in common is a cable, not a flag."""

PROFILE = "hardware"


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
    stock image, or a `tc49` subcommand that is not an app, `live` being the
    harness assembling several in one process (CLAUDE.md)."""
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


def test_the_hardware_services_are_in_a_profile_of_their_own() -> None:
    """The hardware a box owns is that box's choice: the services that answer
    for it are in the `hardware` profile, that profile holds nothing else,
    and none of them is in a second profile that would bring it up on a
    machine with no cable in it."""
    found = services()
    elsewhere = sorted(
        name
        for name in HARDWARE
        if list(found[name].get("profiles") or []) != [PROFILE]
    )
    assert not elsewhere, f"{elsewhere} are hardware and not that profile alone"
    software = sorted(
        name
        for name, service in found.items()
        if name not in HARDWARE and PROFILE in (service.get("profiles") or [])
    )
    assert not software, f"{software} are not hardware and are in '{PROFILE}'"


def test_nothing_owns_a_device_outside_that_profile() -> None:
    """The rule underneath the list above, read off the file rather than off
    a name: a service that claims a device claims one this machine may not
    have, so it can only be in the profile a person asks for by name."""
    loose = sorted(
        name
        for name, service in services().items()
        if service.get("devices") and PROFILE not in (service.get("profiles") or [])
    )
    assert not loose, f"{loose} own a device outside '{PROFILE}'"
