"""The stack's own settings are `/etc/rails49/control.env` (#1218).

The file was `deploy.env` until rails49/installation#65 decision 14 named
each stack's settings after the stack, beside the box's `box.env`. A box
that still has only `deploy.env` is told to rename it before the deploy
pulls.

The lines that check are run here against a directory made under `tmp_path`
in place of `/etc/rails49`, the way the tree check's are in
`test_deploy_builds_the_commit.py`.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEPLOY = (ROOT / "scripts/deploy.sh").read_text()
COMPOSE = (ROOT / "deploy/compose.yaml").read_text()
STORE_ROOT = (ROOT / "scripts/store-root.sh").read_text()
PAGE = (ROOT / "docs/DEPLOY.md").read_text()

ETC = "/etc/rails49"


def block() -> str:
    """The two files' names, then the check for the old one."""
    start = DEPLOY.index("BOX_ENV=")
    return DEPLOY[start : DEPLOY.index("\nfi\n", start) + 4]


def run_block(etc: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" + block().replace(ETC, str(etc))],
        capture_output=True,
        text=True,
        check=False,
    )


def a_box(tmp_path: Path, *files: str) -> Path:
    etc = tmp_path / "rails49"
    etc.mkdir()
    for name in ("box.env", *files):
        (etc / name).write_text("")
    return etc


def test_a_box_with_only_the_old_name_is_told_to_rename_it(tmp_path: Path) -> None:
    etc = a_box(tmp_path, "deploy.env")
    ran = run_block(etc)
    assert ran.returncode != 0
    assert f"mv {etc}/deploy.env {etc}/control.env" in ran.stderr


def test_a_box_with_the_new_name_passes_the_check(tmp_path: Path) -> None:
    ran = run_block(a_box(tmp_path, "control.env"))
    assert (ran.returncode, ran.stderr) == (0, "")


def test_an_old_file_left_beside_the_new_one_is_not_read(tmp_path: Path) -> None:
    ran = run_block(a_box(tmp_path, "control.env", "deploy.env"))
    assert (ran.returncode, ran.stderr) == (0, "")


def test_the_check_comes_before_the_pull() -> None:
    """A box told to rename its file has not pulled."""
    assert DEPLOY.index("[ -e /etc/rails49/deploy.env ]") < DEPLOY.index("git pull")


def test_compose_is_started_against_both_files() -> None:
    assert f"CONTROL_ENV={ETC}/control.env" in DEPLOY
    assert f"BOX_ENV={ETC}/box.env" in DEPLOY
    assert '--env-file "$BOX_ENV" --env-file "$CONTROL_ENV"' in DEPLOY


def test_nothing_else_names_the_old_file() -> None:
    """The deploy names it only to say it is renamed."""
    assert "deploy.env" not in COMPOSE
    assert "deploy.env" not in STORE_ROOT
    assert "deploy.env" not in DEPLOY.replace(block(), "")
    assert f"--env-file {ETC}/deploy.env" not in PAGE
