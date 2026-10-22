"""`scripts/land.sh` waits for `ci` to report, pass, and the PR to merge (#931).

Landing #930, the script stopped twice on a PR it had just opened. First with
status 8 and no message: while no check is reported `gh pr checks` exits 1,
which under `pipefail` ended the wait for the first check at once, and the
`gh pr checks` printed after `--watch` failed exited 8 (pending) under
`set -e`. Then, rerun, it gave up after 30 reads of `OPEN` on a PR whose
auto-merge GitHub started a minute later.

Nothing here reaches the network or GitHub. The script runs on a branch of a
repository made under `tmp_path`, whose `origin` is a bare repository beside
it, with `gh` a stub first on `PATH`. The stub plays GitHub by counting calls:
the first `NONE` reads of the checks find none reported, the next finds `ci`
pending, then it has passed (or failed, for `--watch`, when `WATCH` is 1); the
first `OPEN` reads of the PR's state find it open, then it is `FINALLY`.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAND = ROOT / "scripts/land.sh"

GH = r"""#!/usr/bin/env bash
count() { n=$(( $(cat "$STUB/$1" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$STUB/$1"; echo "$n"; }
none() { echo "no checks reported on the '$3' branch" >&2; exit 1; }
case "$1 $2" in
  "pr checks")
    n=$(count checks)
    [ "$n" -le "$NONE" ] && none "$@"
    case " $* " in *" --watch "*) [ "$WATCH" = 0 ] || { echo "ci  fail"; exit 1; }; exit 0 ;; esac
    [ "$n" -eq $(( NONE + 1 )) ] && { echo "ci  pending"; exit 8; }
    [ "$WATCH" = 0 ] || { echo "ci  fail"; exit 1; }
    echo "ci  pass" ;;
  "pr view")
    case " $* " in
      *" state "*) [ "$(count state)" -le "$OPEN" ] && echo OPEN || echo "$FINALLY" ;;
      *" url "*) echo "merged: https://github.invalid/pr/1" ;;
    esac ;;
  "pr merge") ;;
  *) echo "gh stub: unexpected $*" >&2; exit 2 ;;
esac
"""


IDENTITY = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@invalid",
}


def git(where: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=where,
        env={**os.environ, **IDENTITY},
        check=True,
        capture_output=True,
    )


def a_branch_to_land(tmp_path: Path) -> Path:
    """A checkout on a branch with one commit past `main`, whose `origin` is a
    bare repository holding `main`."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--quiet", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "--quiet", "-b", "main", str(work))
    git(work, "remote", "add", "origin", str(origin))
    git(work, "commit", "--quiet", "--allow-empty", "-m", "start")
    git(work, "push", "--quiet", "origin", "main")
    git(work, "switch", "--quiet", "-c", "work")
    git(work, "commit", "--quiet", "--allow-empty", "-m", "the work")
    return work


def land(
    tmp_path: Path,
    none: int = 0,
    watch: int = 0,
    open_reads: int = 0,
    finally_: str = "MERGED",
) -> subprocess.CompletedProcess[str]:
    work = a_branch_to_land(tmp_path)
    stub = tmp_path / "stub"
    (stub / "bin").mkdir(parents=True)
    gh = stub / "bin/gh"
    gh.write_text(GH)
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{stub / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "STUB": str(stub),
        "NONE": str(none),
        "WATCH": str(watch),
        "OPEN": str(open_reads),
        "FINALLY": finally_,
        "LAND_INTERVAL": "0",
        **IDENTITY,
    }
    return subprocess.run(
        ["bash", str(LAND)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_it_waits_while_no_check_is_reported(tmp_path: Path) -> None:
    """The case #930 hit: `ci` not yet reported on the first read nor at once
    after, then pending, then passed."""
    done = land(tmp_path, none=2)
    assert done.returncode == 0, done.stderr
    assert "merged: " in done.stdout


def test_a_failing_ci_is_named_and_leaves_the_pr_open(tmp_path: Path) -> None:
    done = land(tmp_path, watch=1)
    assert done.returncode == 1, done.stderr
    assert "ci failed" in done.stderr


def test_it_waits_past_thirty_reads_for_the_merge(tmp_path: Path) -> None:
    """GitHub starts an auto-merge when it gets round to it, which on #930 was
    over two and a half minutes after `ci` passed."""
    done = land(tmp_path, open_reads=35)
    assert done.returncode == 0, done.stderr
    assert "merged: " in done.stdout


def test_a_closed_pr_ends_the_wait_at_once(tmp_path: Path) -> None:
    done = land(tmp_path, open_reads=1, finally_="CLOSED")
    assert done.returncode == 1
    assert "the PR is CLOSED" in done.stderr
    assert (tmp_path / "stub/state").read_text().strip() == "2"


def test_an_open_pr_is_given_up_on_after_five_minutes(tmp_path: Path) -> None:
    """Sixty reads five seconds apart; the test shortens the five seconds."""
    done = land(tmp_path, open_reads=1000)
    assert done.returncode == 1
    assert "the PR is OPEN" in done.stderr
    assert (tmp_path / "stub/state").read_text().strip() == "60"
