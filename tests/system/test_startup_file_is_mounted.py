"""The startup file reaches the translator (#523).

`--startup` names this installation's per-district trip currents (#217), and
for as long as nothing passed it the values reached the command station by not
existing at all: no flag in the `dccex` service, no mount, and no file on the
layout box. The mechanism was whole and connected to nothing, which is a fault
no test of the app could see — every one of them passes with the flag unset.

So the three lines that connect it are checked together, the way the store's
three are (`test_store_is_the_persons.py`): the flag, the mount that puts the
file behind it, and the deploy making the file before compose can.

The mount is the **file** and not `/etc/tc49`. That directory holds
`deploy.env`, this box's one on-disk secret (docs/DEPLOY.md), and a directory
mount would put it inside the translator's container — so this is the one
place where the lesson of the route mount (#353, `test_route_mount.py`) is
deliberately not followed, and the inode a single-file mount binds is the
price.
"""

import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

COMPOSE: dict[str, Any] = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
DEPLOY = (ROOT / "scripts/deploy.sh").read_text()
PAGE = (ROOT / "docs/DEPLOY.md").read_text()

FILE = "/etc/tc49/dccex-startup.txt"
"""Where this box keeps it, on the host and in the container alike. One path
in both halves of the mount, because a person reading a container's command
line is then reading the path they would edit."""

SECRETS = "/etc/tc49"
"""The directory it sits in, which is not mountable: `deploy.env` is in it."""


def translator() -> dict[str, Any]:
    service: dict[str, Any] = COMPOSE["services"]["dccex"]
    return service


def startup_flag() -> str:
    """What the service passes as `--startup`."""
    command: list[str] = translator()["command"]
    assert "--startup" in command, (
        "the dccex service passes no startup file, so this railroad's trip"
        " currents reach the command station by not existing (#523)"
    )
    return command[command.index("--startup") + 1]


def mounts() -> list[str]:
    volumes: list[str] = translator().get("volumes") or []
    return volumes


def test_the_translator_is_given_the_startup_file() -> None:
    assert startup_flag() == FILE


def test_the_file_the_flag_names_is_mounted() -> None:
    """The flag alone names a path inside a container that has nothing at it,
    which is the state the app treats as *no file* and logs (ADR-0050): the
    deploy would look right and the districts would still be at whatever the
    firmware was built with."""
    behind = [m for m in mounts() if m.split(":")[1] == startup_flag()]
    assert len(behind) == 1, f"nothing mounts {startup_flag()}; {mounts()}"


def test_the_mount_is_the_file_and_not_the_directory_holding_the_secret() -> None:
    """`/etc/tc49/deploy.env` is root:docker 640 and the one secret on this
    box's disk. Mounting the directory to reach one file in it would hand the
    translator the other."""
    sources = [m.split(":")[0] for m in mounts()]
    assert (
        SECRETS not in sources
    ), f"{SECRETS} holds deploy.env; mount the startup file itself"
    assert FILE in sources


def test_the_mount_is_read_only() -> None:
    """The translator reads it and nothing writes it from a container; a
    person edits it on the box."""
    for mount in mounts():
        if mount.startswith(FILE):
            assert mount.endswith(":ro"), mount


def test_the_deploy_makes_the_file_before_compose() -> None:
    """For the reason the store's directory is made there (#387): a bind
    mount whose source is missing is created by the daemon as a root-owned
    *directory*, and the translator would open a directory as its file of
    trip currents."""
    assert f"DCCEX_STARTUP={FILE}" in DEPLOY
    made = DEPLOY.index('touch "$DCCEX_STARTUP"')
    assert made < DEPLOY.index("docker compose")


def test_the_deploy_does_not_write_over_a_file_that_is_there() -> None:
    """The values in it are this installation's and are edited on the box.
    A deploy that truncated them would be a deploy that silently moved every
    district to the firmware's default."""
    assert 'if [ ! -f "$DCCEX_STARTUP" ]; then' in DEPLOY


def test_a_file_the_deploy_could_not_make_does_not_stop_it() -> None:
    """`/etc/tc49` is root's, and this account may not be able to make a file
    in it. An empty startup file is an ordinary state and the railroad powers
    on without one (ADR-0050), so stopping here would take the whole box down
    over a file that is allowed to be missing — it says what to run by hand
    instead."""
    assert 'touch "$DCCEX_STARTUP" 2>/dev/null || true' in DEPLOY
    assert "'$remedy' is run on the box" in DEPLOY


# -- the remedy it prints (#529) ---------------------------------------------


def remedy() -> str:
    """The command `deploy.sh` advises, read as an operator reads it: the one
    line the script builds, with the path it holds put back in."""
    built = re.search(r'^remedy="(.+)"$', DEPLOY, re.MULTILINE)
    assert built, "scripts/deploy.sh builds no advised command to print"
    return built.group(1).replace("$DCCEX_STARTUP", FILE)


def collapsed(text: str) -> str:
    """One run of whitespace is another: the page wraps the command over
    three lines and the script keeps it on one, and that is not drift."""
    return " ".join(text.split())


def run_remedy(tmp_path: Path) -> Path:
    """The advised command as this account can run it — the path it names
    moved under `tmp_path` and `sudo` dropped, because what is under test is
    what the command does and not who is allowed to do it."""
    where = tmp_path / "dccex-startup.txt"
    line = remedy().replace(FILE, str(where)).replace("sudo ", "")
    subprocess.run(["sh", "-c", line], check=True)
    return where


def a_made_startup_file(where: Path) -> None:
    made = where.lstat()
    assert stat.S_ISREG(made.st_mode), f"{where} is not a regular file"
    assert made.st_size == 0
    assert stat.S_IMODE(made.st_mode) == 0o644


linux_only = pytest.mark.skipif(
    sys.platform != "linux",
    reason="the layout box is Linux, and macOS's install refuses /dev/null",
)


@linux_only
def test_the_remedy_resolves_the_directory_it_is_printed_for(tmp_path: Path) -> None:
    """The case the second test exists to catch: a directory the daemon made
    at that path. `install` takes a directory as a destination, writes `null`
    inside it and reports success, so the operator saw no error, the
    translator went on opening a directory as its startup file, and the next
    deploy printed the same line again (#529). `rm -rf` and not `rmdir`,
    because an earlier run of the old advice left that `null` behind."""
    made_by_the_daemon = tmp_path / "dccex-startup.txt"
    made_by_the_daemon.mkdir()
    (made_by_the_daemon / "null").write_text("")
    a_made_startup_file(run_remedy(tmp_path))


@linux_only
def test_the_remedy_makes_the_file_where_there_is_nothing(tmp_path: Path) -> None:
    """The other state the message is printed in: `/etc/tc49` is root's, the
    `touch` before it was refused, and nothing is at the path at all."""
    a_made_startup_file(run_remedy(tmp_path))


def test_the_page_gives_the_command_the_deploy_prints() -> None:
    """Two places tell an operator what to run, and the one they read is
    whichever they reached first. They drift the moment only one is fixed."""
    assert collapsed(remedy()) in collapsed(PAGE), remedy()


def test_the_page_guards_the_remedy_against_a_file_that_is_there() -> None:
    """The block on that page is the by-hand sequence of `deploy.sh`, which
    prints the remedy only where no regular file is at the path. Run
    unguarded on a box that has one, `rm -rf` would take this installation's
    trip currents with it."""
    assert f"[ -f {FILE} ] || {{ {remedy()}; }}" in collapsed(PAGE)
