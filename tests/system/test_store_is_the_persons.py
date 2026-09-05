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

Making the *wrong* directory is the same fault (#442), so the answer the
deploy makes is checked here too, against the one compose reads: the shell's
value first, then the env file's, then `~/tc49`. That one is run rather than
read, `scripts/store-root.sh` being the only part of the deploy a test can
ask a question of without a box to ssh to and a daemon to start.
"""

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

COMPOSE: dict[str, Any] = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
DEPLOY = (ROOT / "scripts/deploy.sh").read_text()
DOCKERFILE = (ROOT / "deploy/app.Dockerfile").read_text()
STORE_ROOT = ROOT / "scripts/store-root.sh"

HOME = "/home/nobody"
"""A home the box does not have. The default is read off `HOME`, and a test
that let the runner's own through would pass on a machine that happens to
have `~/tc49` and say nothing about which of the two values was used."""

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
    made = DEPLOY.index('mkdir -p "$(scripts/store-root.sh "$DEPLOY_ENV")"')
    assert made < DEPLOY.index("docker compose")


def test_the_deploy_asks_the_env_file_compose_is_given() -> None:
    """One name for the file, so the directory made and the directory mounted
    cannot be resolved out of two different places (#442)."""
    assert "DEPLOY_ENV=/etc/tc49/deploy.env" in DEPLOY
    assert '--env-file "$DEPLOY_ENV"' in DEPLOY


def store_root(env_file: Path, store: str | None = None) -> str:
    """What the deploy would make, for a shell holding `store` and a box whose
    env file is `env_file`."""
    environment = {"HOME": HOME, "PATH": os.environ["PATH"]}
    if store is not None:
        environment["TC49_STORE"] = store
    done = subprocess.run(
        [str(STORE_ROOT), str(env_file)],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def env_file(tmp_path: Path, text: str) -> Path:
    written = tmp_path / "deploy.env"
    written.write_text(text)
    return written


def test_the_env_files_store_is_the_one_made(tmp_path: Path) -> None:
    """A box moves its store by putting `TC49_STORE` in the env file, which is
    where compose reads it and where the deploy shell does not."""
    moved = env_file(tmp_path, "CF_DNS_API_TOKEN=secret\nTC49_STORE=/srv/tc49\n")
    assert store_root(moved) == "/srv/tc49"


def test_the_shells_store_wins_over_the_env_files(tmp_path: Path) -> None:
    """Compose looks a variable up in its own environment before the file it
    is given, so an exported value is the one mounted and has to be the one
    made."""
    moved = env_file(tmp_path, "TC49_STORE=/srv/tc49\n")
    assert store_root(moved, store="/opt/mine") == "/opt/mine"


def test_neither_leaves_the_store_where_it_has_always_been(tmp_path: Path) -> None:
    """`~/tc49`, the default `deploy/compose.yaml` carries."""
    assert store_root(env_file(tmp_path, "CF_DNS_API_TOKEN=secret\n")) == f"{HOME}/tc49"


def test_no_env_file_does_not_stop_the_deploy(tmp_path: Path) -> None:
    """The file is root-owned and mode 640, and a box may have none at all.
    Either way the deploy goes on, at today's directory."""
    assert store_root(tmp_path / "absent.env") == f"{HOME}/tc49"
    assert store_root(tmp_path / "absent.env", store="/opt/mine") == "/opt/mine"


def test_the_env_file_is_read_and_not_sourced(tmp_path: Path) -> None:
    """It is the one place a secret sits on disk (docs/DEPLOY.md). Reading a
    line out of it cannot run what a later line says."""
    ran = tmp_path / "ran"
    hostile = env_file(tmp_path, f"TC49_STORE=/srv/tc49\nTOKEN=$(touch {ran})\n")
    assert store_root(hostile) == "/srv/tc49"
    assert not ran.exists()


def test_the_deploy_says_who_the_person_is() -> None:
    """`id` on the box, exported, because compose interpolates this file's
    `user:` out of the shell it is run from."""
    for line in ("TC49_UID=$(id -u)", "TC49_GID=$(id -g)"):
        assert line in DEPLOY
    assert "export TC49_UID TC49_GID" in DEPLOY
