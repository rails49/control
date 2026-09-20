"""The deploy pulls from the repository this checkout names (#541).

Which remote a box pulls from is state outside the checkout: a line in
`.git/config` on that one machine, put there by whatever `git clone` somebody
typed once. `scripts/deploy.sh` depends on it and cannot see it, which is the
fault #496 removed for the ssh alias by naming the host in full. On 2026-09-20
the layout box's remote was an ssh URL whose key GitHub no longer accepted and
the deploy stopped before it did anything.

So the three lines that remove the dependency are checked together, the way the
startup file's are (`test_startup_file_is_mounted.py`): the script that holds
the URL, the deploy calling it before the pull, and the page giving the same
line to anyone running the sequence by hand.

Nothing here reaches the network. What `scripts/pin-origin.sh` does is run
against a repository made under `tmp_path`, and `git remote set-url` is local.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = ROOT / "scripts/pin-origin.sh"
PIN = SCRIPT.read_text()
DEPLOY = (ROOT / "scripts/deploy.sh").read_text()
PAGE = (ROOT / "docs/DEPLOY.md").read_text()

ORIGIN = "https://github.com/rails49/control.git"
"""Where the box pulls from. HTTPS because the repository is public: nothing
registered on GitHub, no key to rotate, no credential on the box."""

BEFORE = "git@github.com:rails49/control.git"
"""What the box had instead, and what a colleague cloning out of habit gets."""


def collapsed(text: str) -> str:
    """One run of whitespace is another, as in the startup file's test: the
    page wraps a sequence the script keeps on one line, and that is not
    drift."""
    return " ".join(text.split())


def pinned() -> str:
    """The URL the script holds, read the way the script uses it."""
    assignment = f"ORIGIN={ORIGIN}\n"
    assert assignment in PIN, f"scripts/pin-origin.sh does not set {ORIGIN}"
    return ORIGIN


def test_the_url_is_the_https_one() -> None:
    """The ssh URL needs a key registered on GitHub, which is the same state
    outside the checkout that this removes, with a rotation to remember on top.
    The repository is public and the box only ever pulls."""
    assert pinned().startswith("https://")
    assert BEFORE not in PIN


def test_the_script_is_the_only_place_that_holds_the_url() -> None:
    """Two places naming a repository drift the moment one is changed."""
    assert ORIGIN not in DEPLOY


def test_the_deploy_pins_the_remote_before_it_pulls() -> None:
    """After the pull it would be a deploy that already failed."""
    pins = DEPLOY.index("scripts/pin-origin.sh")
    assert pins < DEPLOY.index("git pull")


def test_the_page_gives_the_line_the_deploy_runs() -> None:
    """Two places tell an operator what to run, and the one they read is
    whichever they reached first."""
    assert ORIGIN in PAGE
    assert collapsed("cd ~/control && scripts/pin-origin.sh && git pull") in collapsed(
        PAGE
    )


def a_repository_whose_origin_is(where: Path, url: str) -> Path:
    where.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=where, check=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=where, check=True)
    return where


def run_pin(where: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT)], cwd=where, check=True, capture_output=True, text=True
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
    assert origin_of(box) == ORIGIN
    assert BEFORE in ran.stderr, "the deploy log does not say what it replaced"


def test_it_leaves_a_box_that_is_already_right_alone(tmp_path: Path) -> None:
    """Every deploy runs this, and a line printed on every one of them is a
    line nobody reads on the one that mattered."""
    box = a_repository_whose_origin_is(tmp_path / "box", ORIGIN)
    ran = run_pin(box)
    assert origin_of(box) == ORIGIN
    assert ran.stderr == ""
    assert ran.stdout == ""
