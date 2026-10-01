"""What `deploy/compose.yaml` has to say, and what it may not (ADR-0059,
decision 5).

An app comes up alone: started by nothing, waiting for whatever it reads
rather than being ordered after it, and the two process suites beside this
one hold each of them to that against a real broker. The file that starts
them can undo it in one line — a `depends_on` puts the order back into the
deployment, and an app then waits on a store's container being up rather than
on the store answering, which is not the same thing and is not what any of
them was written to survive.

So the file is read here and six rules are asserted on what it says: one
service per app, no app run twice, nothing ordered, no service claiming a
device, the two bindings of the layout interface sharing no profile, and the
deploy asking only for profiles the file declares. The device rule is what
makes one file both boxes': `docker compose up` on a machine with no steel
under it starts nothing that reaches for a cable, because nothing here reaches
for one at all. The services that did were translators, and no translator is
this repository's — each lives in a repository of its own, as the one that
spoke to the command station does in
[`rails49/dccex`](https://github.com/rails49/dccex) (#587, #595).
"""

import re
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import yaml

from tests.system.test_app_boundaries import APPS

ROOT = Path(__file__).resolve().parents[2]

COMPOSE = ROOT / "deploy/compose.yaml"

ASKS = ("scripts/deploy.sh", "docs/DEPLOY.md")
"""The files that ask compose for profiles by name: the deploy and the page
that gives the same sequence to anyone running it by hand."""

DEPLOY = ASKS[0]
"""The ask a box actually runs, and so the one held to starting a binding."""

PROFILE = re.compile(r"--profile\s+(\S+)")
"""How either file asks for one. A flag and a name, never `--profile=<name>`:
the sequence is written the way it is typed."""

MODULE = "tc49."
"""What a service's command says to run one of ours: `python -m tc49.<app>`,
the command line each app's `__main__` parses."""

FACE = ("tc49", "serve")
"""The one app started by name rather than by module: the store's face is a
subcommand of the `tc49` script, which is what a wheel installs (ADR-0014)."""

SOFTWARE = "layout"
"""The profile every box asks for: the software of a running railroad, which
is the same on a box wired to a command station and on one standing in for
it. A binding of the layout interface in this profile is a binding on both
boxes, which is what the rule below refuses."""


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


def asked_by(name: str) -> set[str]:
    """Every profile a file asks compose for, by name."""
    return set(PROFILE.findall((ROOT / name).read_text()))


def declared() -> set[str]:
    """Every profile some service in the file declares."""
    return {
        str(profile)
        for service in services().values()
        for profile in service.get("profiles", [])
    }


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


def test_the_two_bindings_share_no_profile() -> None:
    """`layout` and `simulator` are two bindings of one interface and one role
    writes it (ADR-0035), so each is asked for by a profile of its own and a
    box asks for exactly one of them: `steel` where a command station is
    wired, `sim` where nothing is. Neither may be the profile every box asks
    for either — the layout interface among the software is the layout
    interface on the box standing in for steel, which is the same two writers
    by another route (#604)."""
    found = services()
    bindings = {
        name: list(found[name].get("profiles", [])) for name in ("layout", "simulator")
    }
    loose = {name: said for name, said in bindings.items() if len(said) != 1}
    assert not loose, f"{loose}: a binding is asked for by one profile and no other"
    asked = {name: said[0] for name, said in bindings.items()}
    shared = sorted(name for name, profile in asked.items() if profile == SOFTWARE)
    assert not shared, (
        f"{shared} in the `{SOFTWARE}` profile, which every box asks for; a box"
        " with no steel under it would start both bindings"
    )
    assert asked["layout"] != asked["simulator"], (
        f"layout and simulator share the profile `{asked['layout']}`; the box"
        " that asks for it would start both bindings"
    )


def test_the_deploy_asks_for_declared_profiles() -> None:
    """A profile no service declares is not an error: compose starts every
    other service and exits 0 (#616). So a renamed or misspelled `steel`
    deploys a railroad with no layout interface under it and reports success,
    which is what the names being read off both files refuses. The profiles
    asked for here and the `profiles:` lists there are one thing said twice,
    and the page is held to it beside the script because somebody running the
    sequence by hand asks with whatever it says."""
    known = declared()
    for name in ASKS:
        unknown = sorted(asked_by(name) - known)
        assert not unknown, (
            f"{name} asks for {unknown}, which no service in deploy/compose.yaml"
            " declares; compose starts the rest and exits 0"
        )
    found = services()
    wanted = asked_by(DEPLOY)
    started = sorted(
        name
        for name in ("layout", "simulator")
        if wanted.intersection(found[name].get("profiles", []))
    )
    assert len(started) == 1, (
        f"{DEPLOY} asks for {sorted(wanted)}, which starts {started}; a box"
        " runs exactly one binding of the layout interface"
    )
