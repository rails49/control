"""The uid a container runs as has a name inside it (#566).

The store runs as the person who deployed the box — an arbitrary host uid, so
that the documents stay theirs (#320, #387) — and OpenSSH refuses to run for a
uid with no passwd entry. `ssh-keygen` makes the store's deploy key and `ssh`
pushes with it, so on a box whose tables do not name that uid the whole backup
feature is unreachable: every `GET /backup` answered "no key could be made: No
user exists for uid 501".

The box's own tables came in read-only before this, which answers the question
only where the box keeps its people in a file. A mac keeps them in Open
Directory and hands the store uid 501 with a passwd file that has never heard
of it; a Linux box works only where the uid happens to be one the base image
ships. So the image answers it, for whatever uid it is handed, and the script
that does it is run here rather than read: `TC49_ETC` is how it is pointed at
tables a test owns, and is set nowhere in the deployment.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "deploy/entrypoint.sh"

OTHER = 65534
"""A uid and gid the tables below name, and the test runner does not have.
Somebody has to be in them — a passwd file with no lines at all would pass a
script that appended nothing — and `nobody` is the one id no account is."""


def tables(where: Path, uid: int = OTHER, gid: int = OTHER) -> Path:
    """Passwd and group tables naming `uid` and nobody else."""
    where.mkdir(parents=True, exist_ok=True)
    (where / "passwd").write_text(
        f"nobody:x:{uid}:{gid}::/nonexistent:/usr/sbin/nologin\n"
    )
    (where / "group").write_text(f"nogroup:x:{gid}:\n")
    return where


def run(etc: Path, *command: str) -> subprocess.CompletedProcess[str]:
    """The entrypoint, against tables in `etc`, asked to run `command`."""
    return subprocess.run(
        [str(ENTRYPOINT), *command],
        env={**os.environ, "TC49_ETC": str(etc)},
        capture_output=True,
        text=True,
        check=False,
    )


def entry(etc: Path, uid: int) -> str | None:
    """The passwd line for `uid`, or `None` where the tables have none."""
    for line in (etc / "passwd").read_text().splitlines():
        if line.split(":")[2] == str(uid):
            return line
    return None


def test_a_uid_the_tables_do_not_name_is_given_one(tmp_path: Path) -> None:
    """The entry ssh looks for, with this uid's own gid and a home it can
    write — ssh reads the home out of the passwd entry rather than out of the
    environment, and makes `~/.ssh` there."""
    etc = tables(tmp_path / "etc")
    assert run(etc, "true").returncode == 0
    line = entry(etc, os.getuid())
    assert line is not None
    name, _, _, gid, _, home, shell = line.split(":")
    assert name == "tc49"
    assert gid == str(os.getgid())
    assert home == "/tmp"
    assert shell == "/usr/sbin/nologin"


def test_the_gid_is_given_one_too(tmp_path: Path) -> None:
    """A group the tables do not name is the same fault one table over."""
    etc = tables(tmp_path / "etc")
    run(etc, "true")
    ids = [line.split(":")[2] for line in (etc / "group").read_text().splitlines()]
    assert str(os.getgid()) in ids


def test_the_command_is_what_runs(tmp_path: Path) -> None:
    """Naming the uid is what the entrypoint does *before* the service's own
    command line, which is the one written in `deploy/compose.yaml` and
    reaches the program word for word."""
    done = run(
        tables(tmp_path / "etc"), "sh", "-c", 'printf "%s|" "$@"', "sh", "a b", "c"
    )
    assert done.stdout == "a b|c|"


def test_a_uid_that_is_named_already_is_left_alone(tmp_path: Path) -> None:
    """Every service but the store is root, which every image names."""
    etc = tables(tmp_path / "etc", uid=os.getuid(), gid=os.getgid())
    was = (etc / "passwd").read_text()
    assert run(etc, "true").returncode == 0
    assert (etc / "passwd").read_text() == was


def test_a_container_started_twice_is_named_once(tmp_path: Path) -> None:
    """The tables are the image's own copy and a restarted container gets a
    fresh one, but a rewritten command or a second run must not stack entries
    up: what the entry says is a question the passwd file answers with its
    first match, and a second line would be a name nothing could correct."""
    etc = tables(tmp_path / "etc")
    run(etc, "true")
    run(etc, "true")
    lines = [line for line in (etc / "passwd").read_text().splitlines() if line]
    assert len(lines) == 2, lines


@pytest.mark.skipif(os.getuid() == 0, reason="root writes a file it may not")
def test_tables_it_cannot_write_are_said_and_the_command_still_runs(
    tmp_path: Path,
) -> None:
    """The fault this exists to cure is a backup that cannot be made, and a
    store that refused to come up over it would take the editor and every
    document with it. So it says what is wrong where the deploy log will show
    it, and serves."""
    etc = tables(tmp_path / "etc")
    (etc / "passwd").chmod(0o444)
    done = run(etc, "echo", "served")
    assert done.returncode == 0
    assert done.stdout.strip() == "served"
    assert "#566" in done.stderr
    assert entry(etc, os.getuid()) is None


def test_the_image_can_run_it(tmp_path: Path) -> None:
    """`COPY` carries the mode it has here, and an entrypoint that is not
    executable is a container that starts nothing at all."""
    assert os.access(ENTRYPOINT, os.X_OK)
