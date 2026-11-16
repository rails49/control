"""The stack's own settings are `/etc/rails49/control.env` (#1218).

rails49/installation#65 decision 14 named each stack's settings after the
stack, beside the box's `box.env`.

The lines that name the two files are run here against a directory made
under `tmp_path` in place of `/etc/rails49`, the way the tree check's are in
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
    """The two files' names."""
    start = DEPLOY.index("BOX_ENV=")
    end = DEPLOY.index("\n", DEPLOY.index("CONTROL_ENV=", start)) + 1
    return DEPLOY[start:end]


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


def test_a_box_with_the_new_name_passes_the_check(tmp_path: Path) -> None:
    ran = run_block(a_box(tmp_path, "control.env"))
    assert (ran.returncode, ran.stderr) == (0, "")


def test_compose_is_started_against_both_files() -> None:
    assert f"CONTROL_ENV={ETC}/control.env" in DEPLOY
    assert f"BOX_ENV={ETC}/box.env" in DEPLOY
    assert '--env-file "$BOX_ENV" --env-file "$CONTROL_ENV"' in DEPLOY


def test_nothing_else_names_the_old_file() -> None:
    assert "deploy.env" not in COMPOSE
    assert "deploy.env" not in STORE_ROOT
    assert "deploy.env" not in DEPLOY
    assert f"--env-file {ETC}/deploy.env" not in PAGE
