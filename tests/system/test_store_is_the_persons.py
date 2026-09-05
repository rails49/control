"""The store's directory, and everything written into it, is the person's
(#387).

A bind mount whose source is missing is made by the Docker daemon, as root.
`~/tc49` on a fresh layout box was made that way and the services writing it
ran as root too, so the fault was invisible from the app and total from a
terminal: the person could not edit their own drawings, `git init` the store
or drop a catalogue in. A `chown -R` cures it until the next save.

What cures it for good is three lines in three files that have nothing to do
with each other — the directory made ahead of compose, the uid the services
run as, and what an image has to carry for a uid it does not know — so they
are checked together here rather than each being remembered on its own.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

COMPOSE: dict[str, Any] = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
DEPLOY = (ROOT / "scripts/deploy.sh").read_text()
DOCKERFILE = (ROOT / "deploy/app.Dockerfile").read_text()

PERSONS = ["store"]
"""The services that write the store, and so run as the person. One, since
the session that also wrote it went with `tc49 live` (ADR-0059, decision 5):
a list rather than a name, because the next thing to write the store is a
service and not a special case."""


def service(name: str) -> dict[str, Any]:
    found: dict[str, Any] = COMPOSE["services"][name]
    return found


@pytest.mark.parametrize("name", PERSONS)
def test_the_service_runs_as_the_person(name: str) -> None:
    """The uid and gid come from the deploy shell, with the first ordinary
    account as the default; root is what the absence of this means."""
    assert service(name).get("user") == "${TC49_UID:-1000}:${TC49_GID:-1000}"


@pytest.mark.parametrize("name", PERSONS)
def test_the_service_is_not_told_the_store_is_safe(name: str) -> None:
    """`safe.directory` said *this process is root and the documents are not
    its own*. It is not, any more, and saying so again would hide the day it
    stops being true."""
    environment: dict[str, str] = service(name).get("environment", {})
    assert "/store" not in [
        value
        for key, value in environment.items()
        if key.startswith("GIT_CONFIG_VALUE")
    ]
    assert "safe.directory" not in environment.values()


@pytest.mark.parametrize("name", PERSONS)
def test_the_git_settings_are_counted_as_they_are_given(name: str) -> None:
    """`GIT_CONFIG_COUNT` is how many of the numbered pairs git reads, so a
    setting removed without it is one still applied — or one silently lost."""
    environment: dict[str, str] = service(name).get("environment", {})
    count = environment.get("GIT_CONFIG_COUNT")
    if count is None:
        assert not [k for k in environment if k.startswith("GIT_CONFIG_KEY")]
        return
    keys = sorted(k for k in environment if k.startswith("GIT_CONFIG_KEY_"))
    assert keys == [f"GIT_CONFIG_KEY_{i}" for i in range(int(count))]


def test_the_store_can_name_the_uid_it_pushes_as() -> None:
    """OpenSSH refuses to run for a uid with no passwd entry — "No user
    exists for uid" — and the backup pushes over ssh."""
    volumes: list[str] = service("store")["volumes"]
    assert "/etc/passwd:/etc/passwd:ro" in volumes
    assert "/etc/group:/etc/group:ro" in volumes


def test_the_image_carries_the_directory_the_keys_volume_lands_on() -> None:
    """Docker fills a fresh named volume from the image and makes it root's
    where the image has nothing there, which the store could not then write."""
    assert "/keys" in DOCKERFILE
    made = [line for line in DOCKERFILE.splitlines() if "/keys" in line]
    assert any("mkdir" in line and "chmod" in line for line in made), made


def test_the_deploy_makes_the_store_directory_before_compose() -> None:
    """Made by something that knows whose it is, rather than by the daemon."""
    made = DEPLOY.index('mkdir -p "${TC49_STORE:-$HOME/tc49}"')
    assert made < DEPLOY.index("docker compose")


def test_the_deploy_says_who_the_person_is() -> None:
    """`id` on the box, exported, because compose interpolates this file's
    `user:` out of the shell it is run from."""
    for line in ("TC49_UID=$(id -u)", "TC49_GID=$(id -g)"):
        assert line in DEPLOY
    assert "export TC49_UID TC49_GID" in DEPLOY
