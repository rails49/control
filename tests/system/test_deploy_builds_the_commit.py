"""The deploy builds on the box under the commit it pulled (#1216).

The images are named by the commit they were built from, and a release's
images and a box's own build of one commit carry the same name
(rails49/.github#71 decision 5). A tree with changes in it would build
something else under that name, so the deploy refuses one, as dccex's does
(dccex ADR-0005 d.4). The box needs no node or pnpm: the UI is built inside
the `control-web` image.

The lines that check the tree and name the commit are run here against a
repository made under `tmp_path`, the way the remote's are in
`test_deploy_pins_the_remote.py`.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEPLOY = (ROOT / "scripts/deploy.sh").read_text()


def block() -> str:
    """The tree check, then the commit's name."""
    start = DEPLOY.index("dirty=$(git status --porcelain)")
    check = DEPLOY[start : DEPLOY.index("\nfi\n", start) + 4]
    named = DEPLOY.index("CONTROL_COMMIT=$(git rev-parse HEAD)")
    return (
        check
        + DEPLOY[named : DEPLOY.index("\n", DEPLOY.index("export CONTROL_COMMIT"))]
    )


def a_repository(where: Path) -> str:
    """A clone with one commit, and that commit."""

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=where,
            check=True,
            capture_output=True,
            text=True,
        )
        return done.stdout.strip()

    where.mkdir()
    git("init", "--quiet")
    (where / "file").write_text("one\n")
    git("add", "file")
    git("commit", "--quiet", "-m", "one")
    return git("rev-parse", "HEAD")


def run_block(where: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{block()}\necho $CONTROL_COMMIT"],
        cwd=where,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_clean_tree_is_built_under_its_commit(tmp_path: Path) -> None:
    commit = a_repository(tmp_path / "box")
    ran = run_block(tmp_path / "box")
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == commit


def test_a_changed_tree_is_refused(tmp_path: Path) -> None:
    a_repository(tmp_path / "box")
    (tmp_path / "box/file").write_text("two\n")
    ran = run_block(tmp_path / "box")
    assert ran.returncode != 0
    assert "file" in ran.stderr, "the refusal does not say what changed"


def test_an_untracked_file_is_refused(tmp_path: Path) -> None:
    """It would be copied into the image as much as a changed one."""
    a_repository(tmp_path / "box")
    (tmp_path / "box/new").write_text("new\n")
    assert run_block(tmp_path / "box").returncode != 0


def test_the_tree_is_checked_before_the_pull() -> None:
    """A pull over changes merges around them or stops on git's own words."""
    assert DEPLOY.index("dirty=$(git status --porcelain)") < DEPLOY.index("git pull")


def test_the_commit_is_named_before_compose_builds() -> None:
    assert DEPLOY.index("export CONTROL_COMMIT") < DEPLOY.index("docker compose")
    assert "up -d --build" in DEPLOY


def test_the_box_needs_no_node() -> None:
    run = [line for line in DEPLOY.splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in run if re.search(r"\b(pnpm|npm|node)\b", line)]
