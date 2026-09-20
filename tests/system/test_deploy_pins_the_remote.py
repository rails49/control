"""The deploy pulls from the repository this checkout names (#541).

Which remote a box pulls from is state outside the checkout: a line in
`.git/config` on that one machine, put there by whatever `git clone` somebody
typed once. `scripts/deploy.sh` depends on it and cannot see it, which is the
fault #496 removed for the ssh alias by naming the host in full. On 2026-09-20
the layout box's remote was an ssh URL whose key GitHub no longer accepted and
the deploy stopped before it did anything.

The lines that remove the dependency are in `scripts/deploy.sh` itself and not
in a script beside `store-root.sh`. They run before the pull, and everything
under `scripts/` on the box is whatever that box last pulled — so on the box
this exists to rescue, a script would never arrive (#543). The heredoc is read
from the dev box's checkout, which makes it the one thing that is current
whatever state the box is in.

So the two that are left are checked together, the way the startup file's are
(`test_startup_file_is_mounted.py`): the deploy pinning the remote before it
pulls, and the page giving the same line to anyone running the sequence by
hand.

Nothing here reaches the network. The block is run against a repository made
under `tmp_path`, and `git remote set-url` is local.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEPLOY = (ROOT / "scripts/deploy.sh").read_text()
PAGE = (ROOT / "docs/DEPLOY.md").read_text()

BEFORE = "git@github.com:rails49/control.git"
"""What the box had instead, and what a colleague cloning out of habit gets."""


def collapsed(text: str) -> str:
    """One run of whitespace is another, as in the startup file's test: the
    page wraps a sequence the script keeps on one line, and that is not
    drift."""
    return " ".join(text.split())


def pinned() -> str:
    """The URL the deploy holds, read the way the deploy uses it."""
    held = re.search(r"^ORIGIN=(\S+)$", DEPLOY, re.MULTILINE)
    assert held, "scripts/deploy.sh names no repository to pull from"
    return held.group(1)


def block() -> str:
    """The lines that pin it, as an operator reads them: from the URL to the
    pull they come before."""
    return DEPLOY[DEPLOY.index("ORIGIN=") : DEPLOY.index("git pull")]


def test_the_url_is_the_https_one() -> None:
    """The ssh URL needs a key registered on GitHub, which is the same state
    outside the checkout that this removes, with a rotation to remember on top.
    The repository is public and the box only ever pulls."""
    assert pinned() == "https://github.com/rails49/control.git"
    assert BEFORE not in DEPLOY


def test_the_deploy_pins_the_remote_before_it_pulls() -> None:
    """After the pull it would be a deploy that already failed."""
    assert "git remote set-url origin" in block()


def test_the_deploy_carries_the_lines_rather_than_calling_a_script() -> None:
    """A script under `scripts/` is read on the box, out of whatever it last
    pulled. This runs before the pull, and on a box that cannot pull the file
    is not there at all — which is how the first deploy after #541 failed."""
    assert "pin-origin" not in DEPLOY
    assert not (ROOT / "scripts/pin-origin.sh").exists()
    assert "pin-origin" not in PAGE


def test_the_page_gives_the_line_the_deploy_runs() -> None:
    """Two places tell an operator what to run, and the one they read is
    whichever they reached first."""
    assert collapsed(f"git remote set-url origin {pinned()}") in collapsed(PAGE)


def a_repository_whose_origin_is(where: Path, url: str) -> Path:
    where.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=where, check=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=where, check=True)
    return where


def run_pin(where: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", block()], cwd=where, check=True, capture_output=True, text=True
    )


def origin_of(where: Path) -> str:
    got = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=where,
        check=True,
        capture_output=True,
        text=True,
    )
    return got.stdout.strip()


def test_it_moves_a_box_that_was_cloned_over_ssh(tmp_path: Path) -> None:
    """The state the layout box was found in, and the state a colleague's
    clone starts in."""
    box = a_repository_whose_origin_is(tmp_path / "box", BEFORE)
    ran = run_pin(box)
    assert origin_of(box) == pinned()
    assert BEFORE in ran.stderr, "the deploy log does not say what it replaced"


def test_it_leaves_a_box_that_is_already_right_alone(tmp_path: Path) -> None:
    """Every deploy runs this, and a line printed on every one of them is a
    line nobody reads on the one that mattered."""
    box = a_repository_whose_origin_is(tmp_path / "box", pinned())
    ran = run_pin(box)
    assert origin_of(box) == pinned()
    assert ran.stderr == ""
    assert ran.stdout == ""
