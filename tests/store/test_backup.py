"""Backing an installation's store up with git (#321).

Two halves, and the split is deliberate. The **policy** — when a commit is
made, what its message says, what is logged and what is refused — is driven
through a fake git whose clock the test moves, so a burst of saves inside the
idle window is one assertion and not a wait. The **driving** is then exercised
against a real repository in `tmp_path`, because what this app knows about git
is exactly that its commands mean what git says they mean, and a fake could
agree with a mistake.

Nothing here reaches the network. The remote a push is tested against is a
bare repository beside the store, and the unreachable one is a path that is
not there — which is what a laptop off the wifi looks like to `git push`,
minus the wait.
"""

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from tc49.store.backup import (
    PUSH_TIMEOUT_S,
    Backup,
    Said,
    Watch,
    document,
    documents,
    git,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="the app drives git, and there is none here"
)


class FakeGit:
    """A git that answers what the test says and remembers what it was asked.

    `porcelain` is the working tree as far as `status` is concerned, so a test
    says what has moved rather than making files move.
    """

    def __init__(self, toplevel: str | None = None, porcelain: str = "") -> None:
        self.toplevel = toplevel
        self.porcelain = porcelain
        self.pushes = Said(True, "")
        self.calls: list[tuple[str, ...]] = []
        # The deadline the last push was given, so a test can say that the one
        # command here that waits on another machine is bounded.
        self.deadline: float | None = None
        # What `log @{u}..HEAD --format=%ct` answers: the backups the remote
        # has not been given, newest first, as unix seconds.
        self.uncopied: list[int] = []

    def __call__(self, root: Path, *args: str, timeout: float | None = None) -> Said:
        self.calls.append(args)
        if args[0] == "rev-parse":
            top = self.toplevel if self.toplevel is not None else str(root)
            return Said(self.toplevel != "", top)
        if args[0] == "status":
            # Stripped, because `git` strips what it ran before anybody sees
            # it: a first line whose status is ` M` arrives without its
            # leading space, and a double that kept it would not be git (#389).
            return Said(True, self.porcelain.strip())
        if args[0] == "remote":
            return Said(True, "origin")
        if args[0] == "commit":
            self.porcelain = ""
            return Said(True, "[main 0000000] " + args[2])
        if args[0] == "push":
            self.deadline = timeout
            return self.pushes
        if args[0] == "log" and "@{u}..HEAD" in args:
            return Said(True, "\n".join(str(made) for made in self.uncopied))
        return Said(True, "")

    @property
    def messages(self) -> list[str]:
        return [call[2] for call in self.calls if call[0] == "commit"]


class FakeClock:
    """Seconds, moved by the test. `Backup` reads it through the `now` it was
    handed, so a twenty-second idle window costs no time at all."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def backing(
    root: Path, run: FakeGit, clock: FakeClock, log: list[str] | None = None
) -> Backup:
    """A `Backup` over a store with automation on, which is what every policy
    test below is about. Off is its own test."""
    backup = Backup(
        root,
        run=run,
        log=(log if log is None else log.append),
        now=clock,
        idle_s=20.0,
        push_s=300.0,
    )
    backup.switch(True)
    return backup


# --- what a path is called ---------------------------------------------------


def test_a_changed_path_is_named_as_the_document_it_is() -> None:
    """The message is read by the person who drew the railroad, so it says
    what the store calls the document and not what git calls the file."""
    assert document("layouts/reversing-loops.drawing.yaml") == "reversing-loops"
    assert document("layouts/reversing-loops.roster.yaml") == "reversing-loops roster"
    assert document("catalogue/re460.yaml") == "re460 model"
    assert document("scenarios/reversing-loops/meet.scenario.yaml") == (
        "reversing-loops/meet"
    )


def test_a_path_the_store_does_not_know_is_passed_through() -> None:
    """Something a person put in the store themselves. Inventing a name for it
    would say less than the path does."""
    assert document("notes/wiring.txt") == "notes/wiring.txt"


def test_the_documents_of_a_status_are_sorted_and_counted_once() -> None:
    """A drawing that moved twice moved once, and a rename moved the document
    it arrived at."""
    porcelain = (
        " M layouts/reversing-loops.drawing.yaml\n"
        "?? layouts/reversing-loops.roster.yaml\n"
        " D layouts/crossover-yard.drawing.yaml\n"
        "R  layouts/old.drawing.yaml -> layouts/new.drawing.yaml\n"
    )
    assert documents(porcelain) == [
        "crossover-yard",
        "new",
        "reversing-loops",
        "reversing-loops roster",
    ]


@pytest.mark.parametrize(
    "first",
    [
        " M layouts/reversing-loops.drawing.yaml",
        "?? layouts/reversing-loops.drawing.yaml",
        "A  layouts/reversing-loops.drawing.yaml",
        "MM layouts/reversing-loops.drawing.yaml",
        "R  layouts/old.drawing.yaml -> layouts/reversing-loops.drawing.yaml",
    ],
)
def test_the_first_document_is_named_in_full_whatever_its_status(first: str) -> None:
    """`git` strips what it ran, so a first line whose status column starts
    with a space — ` M`, the commonest of them — reaches the parser one
    character shorter than git wrote it. Read both ways round, because the
    status column is what is being dropped and not a fixed three characters
    (#389)."""
    porcelain = f"{first}\n?? catalogue/re460.yaml\n"
    named = ["re460 model", "reversing-loops"]
    assert documents(porcelain) == named
    assert documents(porcelain.strip()) == named


# --- the idle timer ----------------------------------------------------------


def test_a_burst_of_saves_inside_the_window_is_one_commit(
    tmp_path: Path, clock: FakeClock
) -> None:
    """Each save pushes the deadline out, so an editing session is one commit
    covering it rather than one per keystroke's worth of work."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    backup = backing(tmp_path, run, clock)

    for _ in range(5):
        backup.saved()
        clock.now += 5.0
        backup.due()
    assert run.messages == []

    clock.now += 20.0
    backup.due()
    assert run.messages == ["backup: reversing-loops"]


def test_the_message_names_the_documents_that_moved(
    tmp_path: Path, clock: FakeClock
) -> None:
    """A timer commit with a generic message is the noise the timer exists to
    avoid, and this costs one line."""
    run = FakeGit(
        porcelain=(" M layouts/reversing-loops.drawing.yaml\n?? catalogue/re460.yaml\n")
    )
    backup = backing(tmp_path, run, clock)
    backup.saved()
    clock.now += 20.0
    backup.due()
    assert run.messages == ["backup: re460 model, reversing-loops"]


def test_a_quiet_store_produces_no_commits(tmp_path: Path, clock: FakeClock) -> None:
    """Nothing was saved, so nothing is waiting on the deadline and an hour of
    ticks says nothing."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    backup = backing(tmp_path, run, clock)
    for _ in range(60):
        clock.now += 60.0
        backup.due()
    assert run.messages == []


def test_a_save_that_moved_nothing_is_not_committed(
    tmp_path: Path, clock: FakeClock
) -> None:
    """A drawing saved as it already stood. git says nothing moved, and an
    empty commit is history nobody can read."""
    run = FakeGit(porcelain="")
    backup = backing(tmp_path, run, clock)
    backup.saved()
    clock.now += 20.0
    backup.due()
    assert run.messages == []


def test_the_timers_are_silent_until_somebody_turns_backup_on(
    tmp_path: Path, clock: FakeClock
) -> None:
    """Automated backup is optional and off until it is asked for: a store
    nobody has switched on commits nothing, whatever is saved into it."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    backup = Backup(tmp_path, run=run, log=lambda _: None, now=clock, idle_s=20.0)
    assert not backup.automatic
    backup.saved()
    clock.now += 100.0
    backup.due()
    backup.quit()
    assert run.messages == []


def test_the_switch_outlives_the_process(tmp_path: Path) -> None:
    """Turned on has to stay on: the switch is a document of the installation
    and is kept in the store, not in the server that happened to be up."""
    Backup(tmp_path, run=FakeGit()).switch(True)
    assert Backup(tmp_path, run=FakeGit()).automatic
    Backup(tmp_path, run=FakeGit()).switch(False)
    assert not Backup(tmp_path, run=FakeGit()).automatic


# --- quitting and pushing ----------------------------------------------------


def test_quitting_commits_what_is_outstanding_and_pushes(
    tmp_path: Path, clock: FakeClock
) -> None:
    """A person closing the lid has said everything they are going to say, so
    there is nothing left to coalesce with and no timer to wait out."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    backup = backing(tmp_path, run, clock)
    backup.saved()
    backup.quit()
    assert run.messages == ["backup: reversing-loops"]
    assert ("push",) in run.calls


def test_an_unreachable_remote_is_logged_and_nothing_else(
    tmp_path: Path, clock: FakeClock
) -> None:
    """The commit is the backup and the push is the copy off this machine, so
    a lost network leaves the backup made, the reason on the log and no
    exception for a save to trip over."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    run.pushes = Said(False, "fatal: unable to access 'origin': could not resolve host")
    log: list[str] = []
    backup = backing(tmp_path, run, clock, log)

    backup.saved()
    backup.quit()

    assert run.messages == ["backup: reversing-loops"]
    assert any("could not resolve host" in line for line in log)


def test_a_push_that_failed_is_tried_again_on_the_next_timer(
    tmp_path: Path, clock: FakeClock
) -> None:
    """The commit is still only on this disk, so the copy off it is still
    owed. Nothing waits on that, and nothing asks about it again."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    run.pushes = Said(False, "fatal: could not read from remote repository")
    backup = backing(tmp_path, run, clock, [])

    backup.saved()
    clock.now += 20.0
    backup.due()
    pushes = run.calls.count(("push",))

    run.pushes = Said(True, "")
    clock.now += 300.0
    backup.due()
    assert run.calls.count(("push",)) == pushes + 1

    clock.now += 300.0
    backup.due()
    assert run.calls.count(("push",)) == pushes + 1  # nothing left to push


def test_a_quiet_store_stays_off_the_network(tmp_path: Path, clock: FakeClock) -> None:
    """The push timer runs on its own, but there is nothing to hand over until
    something has been committed."""
    run = FakeGit(porcelain="")
    backup = backing(tmp_path, run, clock)
    for _ in range(10):
        clock.now += 300.0
        backup.due()
    assert ("push",) not in run.calls


# --- a copy off this machine never waits in front of a save -------------------


class SlowGit(FakeGit):
    """A git whose push does not come back until the test lets it.

    What every other fake here cannot be: instant. The requirement #321 states
    — "a lost network must never block a save" — is about how long something
    takes, so a fake that answers at once tests the outcome and never the
    waiting, which is how the defect shipped.
    """

    def __init__(self, porcelain: str = "") -> None:
        super().__init__(porcelain=porcelain)
        self.pushing = threading.Event()
        self.release = threading.Event()

    def __call__(self, root: Path, *args: str, timeout: float | None = None) -> Said:
        if args[0] == "push":
            self.pushing.set()
            self.release.wait(timeout=5.0)
        return super().__call__(root, *args, timeout=timeout)


def test_a_save_does_not_wait_for_a_copy_that_is_going_nowhere(
    tmp_path: Path, clock: FakeClock
) -> None:
    """The store's server answers one request at a time, so a save that waits
    on `git push` is every route waiting on it: the drawing does not come back
    and the panel cannot read a roster. Against a host that is unreachable
    rather than refusing, that is the operating system's connect timeout."""
    run = SlowGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    backup = backing(tmp_path, run, clock, [])

    backup.saved()
    clock.now += 20.0
    backup.due()  # commits, and the copy is not owed until the push timer
    clock.now += 300.0
    copying = threading.Thread(target=backup.due, daemon=True)
    copying.start()
    assert run.pushing.wait(timeout=5.0), "the copy never started"

    began = time.monotonic()
    backup.saved()  # the save the editor is waiting on
    waited = time.monotonic() - began

    run.release.set()
    copying.join(timeout=5.0)
    assert waited < 0.5, f"a save waited {waited:.2f}s on a copy off the machine"


def test_the_button_answers_with_the_commit_and_leaves_the_copy_to_the_timer(
    tmp_path: Path, clock: FakeClock
) -> None:
    """`Back up now` runs on the thread serving the request, so a push made
    there blocks the store's whole face for as long as the network takes. The
    commit is what was asked for and is made; the copy is the next tick's."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    backup = backing(tmp_path, run, clock)

    said = backup.back_up()

    assert said.ok
    assert run.messages == ["backup: reversing-loops"]
    assert ("push",) not in run.calls

    backup.due()  # the tick the press asked for, with no timer left to wait
    assert ("push",) in run.calls


def test_a_copy_is_given_a_deadline(tmp_path: Path, clock: FakeClock) -> None:
    """A remote that refuses answers at once; one that is simply unreachable
    does not answer at all, and git waits on the connect timeout. A session
    being stopped has to be able to stop."""
    run = FakeGit(porcelain=" M layouts/reversing-loops.drawing.yaml\n")
    backup = backing(tmp_path, run, clock)
    backup.saved()
    backup.quit()
    assert run.deadline == PUSH_TIMEOUT_S


def test_a_command_that_gives_no_answer_reads_as_a_refusal(tmp_path: Path) -> None:
    """The real driver, and the only branch of it a fake cannot stand in for:
    what a killed command says. It is a refusal like any other, in words
    saying what was waited on."""
    said = git(tmp_path, "status", timeout=0)
    assert not said.ok
    assert "no answer" in said.words


def test_a_copy_that_has_been_failing_for_a_day_says_so(
    tmp_path: Path, clock: FakeClock
) -> None:
    """Each failed copy on its own is not worth interrupting anybody for. A
    remote unreachable for a day is a remote that moved, and the person who
    turned backup on believes they have a copy off this machine and does not.

    Asked of git rather than remembered, so a restart does not forget it.
    """
    day = 24 * 60 * 60
    run = FakeGit(porcelain="")
    backup = Backup(
        tmp_path, run=run, log=lambda _: None, now=clock, wall=lambda: 10 * day
    )

    run.uncopied = []
    assert backup.copy() == {
        "waiting": 0,
        "since": None,
        "stale": False,
        "ok": None,
        "said": "",
    }

    run.uncopied = [10 * day - 3600, 10 * day - 60]
    an_hour = backup.copy()
    assert an_hour["waiting"] == 2
    assert an_hour["since"] == 3600
    assert not an_hour["stale"]

    run.uncopied = [10 * day - 2 * day]
    assert backup.copy()["stale"]


# --- a store that is not a repository ----------------------------------------


def test_a_store_that_is_not_a_repository_says_what_backup_needs(
    tmp_path: Path,
) -> None:
    """A normal state and not a fault: the store works, backup is offered, and
    what it says is what to make and where to enter it, with git's own words
    after it — a machine with no git at all is the other thing this covers,
    and those words are the only way to tell. Nothing here runs `git init`
    either way (ADR-0053)."""
    backup = Backup(tmp_path, run=FakeGit(toplevel=""))
    assert not backup.repository()
    assert "create an empty private repository" in backup.needs()[0]
    assert "key" not in backup.needs()[0]  # it was given nowhere to keep one
    assert not backup.commit().ok
    assert not backup.restore().ok
    assert not backup.push().ok


def test_a_store_inside_a_larger_repository_is_not_one(tmp_path: Path) -> None:
    """A checkout's `bench/` is what a developer runs a session on, and
    committing there would land the store's backups in the control repository
    beside code, under whatever branch was out."""
    backup = Backup(tmp_path / "bench", run=FakeGit(toplevel=str(tmp_path)))
    assert not backup.repository()
    # Not `git init` here, which is the answer to the other way of having no
    # repository: this one is in one, and it is the checkout.
    assert "is inside the git repository at" in backup.needs()[0]
    assert str(tmp_path) in backup.needs()[0]


def test_a_repository_with_no_remote_says_the_backup_stays_here(
    tmp_path: Path,
) -> None:
    """It backs up, and what it has not got is the copy off this machine."""

    class NoRemote(FakeGit):
        def __call__(
            self, root: Path, *args: str, timeout: float | None = None
        ) -> Said:
            if args[0] == "remote":
                return Said(True, "")
            return super().__call__(root, *args)

    backup = Backup(tmp_path, run=NoRemote())
    assert backup.repository()
    assert "no remote" in backup.needs()[0]


# --- against a real repository -----------------------------------------------


def run_git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A store that is a git repository, with an identity of its own so that
    nothing about the machine running the suite decides whether a commit can
    be made."""
    root = tmp_path / "tc49"
    (root / "layouts").mkdir(parents=True)
    run_git(tmp_path, "init", "-q", "-b", "main", str(root))
    run_git(root, "config", "user.email", "suite@example.invalid")
    run_git(root, "config", "user.name", "The Suite")
    run_git(root, "config", "commit.gpgsign", "false")
    return root


def drawn(root: Path, name: str, text: str) -> None:
    (root / "layouts" / f"{name}.drawing.yaml").write_text(text)


def test_it_commits_what_a_person_drew(repository: Path) -> None:
    """The whole of the app's dealings with git: everything under the store,
    named as documents, in one commit."""
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup = Backup(repository, log=lambda _: None)
    backup.switch(True)

    assert backup.outstanding() == ["backup.yaml", "reversing-loops"]
    assert backup.commit().ok
    assert backup.outstanding() == []
    assert "backup: backup.yaml, reversing-loops" in run_git(
        repository, "log", "--format=%s"
    )


def test_a_modified_document_is_named_in_full(repository: Path) -> None:
    """The whole path from git to the list a person reads before pressing the
    button: a tracked document that has been edited is ` M` in git's words,
    and the leading space of that status does not survive `git` (#389)."""
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup = Backup(repository, log=lambda _: None)
    assert backup.commit().ok
    drawn(repository, "reversing-loops", "drawing: reversing-loops\nsymbols: {}\n")

    assert backup.outstanding() == ["reversing-loops"]


def test_the_backups_are_offered_newest_first(repository: Path) -> None:
    """What a person picks from to restore: the message names what moved, so
    the list reads as the editing sessions it records."""
    backup = Backup(repository, log=lambda _: None)
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup.commit()
    drawn(repository, "crossover-yard", "drawing: crossover-yard\n")
    backup.commit()

    made = backup.backups()
    assert [one["said"] for one in made] == [
        "backup: crossover-yard",
        "backup: reversing-loops",
    ]
    assert all(one["commit"] and one["when"] for one in made)


def test_a_restore_over_a_dirty_tree_is_refused_in_words(repository: Path) -> None:
    """The documents that have not been backed up are exactly the ones git
    could not give back, so the refusal names them and stops."""
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup = Backup(repository, log=lambda _: None)
    backup.commit()
    drawn(repository, "reversing-loops", "drawing: reversing-loops\nsymbols: {}\n")

    said = backup.restore()
    assert not said.ok
    assert "reversing-loops" in said.words
    assert "back the store up first" in said.words


def test_a_restore_over_a_clean_tree_brings_the_documents_back(
    repository: Path,
) -> None:
    """The editing session a person wants undone was itself backed up, which
    is why restoring names an earlier backup rather than the last one."""
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup = Backup(repository, log=lambda _: None)
    backup.commit()
    yesterday = backup.backups()[0]["commit"]

    drawn(repository, "reversing-loops", "drawing: reversing-loops\nsymbols: {}\n")
    backup.commit()

    said = backup.restore(yesterday)
    assert said.ok, said.words
    assert "reversing-loops" in said.words
    path = repository / "layouts" / "reversing-loops.drawing.yaml"
    assert path.read_text() == "drawing: reversing-loops\n"


def test_a_restore_puts_the_store_back_as_that_backup_held_it(
    repository: Path,
) -> None:
    """A railroad drawn after that backup goes with the rest, and nothing is
    lost by it: the later backup is still in the history and restoring it is
    the same one press."""
    backup = Backup(repository, log=lambda _: None)
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup.commit()
    yesterday = backup.backups()[0]["commit"]
    drawn(repository, "crossover-yard", "drawing: crossover-yard\n")
    backup.commit()
    today = backup.backups()[0]["commit"]
    yard = repository / "layouts" / "crossover-yard.drawing.yaml"

    assert backup.restore(yesterday).ok
    assert not yard.exists()

    assert backup.commit().ok  # the restore, backed up like any other change
    assert backup.restore(today).ok
    assert yard.exists()


def test_a_restore_to_a_backup_that_is_not_there_reads_gits_own_words(
    repository: Path,
) -> None:
    """The app surfaces what git said and adds nothing: it is git that knows
    what a commit-ish is."""
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup = Backup(repository, log=lambda _: None)
    backup.commit()

    said = backup.restore("nosuchcommit")
    assert not said.ok
    assert "nosuchcommit" in said.words


def test_it_pushes_to_a_remote_and_says_when_it_cannot(
    repository: Path, tmp_path: Path
) -> None:
    """A bare repository beside the store is a remote in every way that
    matters here, and no network is touched. The unreachable one is a path
    that is not there, which is what a laptop off the wifi looks like to
    `git push`, minus the wait."""
    remote = tmp_path / "remote.git"
    run_git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    run_git(repository, "remote", "add", "origin", str(remote))

    log: list[str] = []
    backup = Backup(repository, log=log.append)
    backup.switch(True)
    drawn(repository, "reversing-loops", "drawing: reversing-loops\n")
    backup.commit()
    # By hand, because the app never makes a branch or a remote of its own
    # (ADR-0053): what it does from here is `git push` and whatever git makes
    # of the branch that is out.
    run_git(repository, "push", "-q", "--set-upstream", "origin", "main")

    drawn(repository, "crossover-yard", "drawing: crossover-yard\n")
    backup.saved()
    backup.quit()
    assert "backup: crossover-yard" in run_git(remote, "log", "--format=%s")

    run_git(repository, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    drawn(repository, "facing-pair", "drawing: facing-pair\n")
    backup.saved()
    backup.quit()

    assert "backup: facing-pair" in run_git(repository, "log", "--format=%s")
    assert any("gone.git" in line for line in log)


def test_the_watch_lets_the_timers_fire(repository: Path) -> None:
    """The thread decides nothing; what is asserted is that it ticks at all,
    and that stopping it stops the ticking."""
    ticked = threading.Event()

    class Counted(Backup):
        def due(self) -> None:
            self.ticks += 1
            ticked.set()

        ticks = 0

    backup = Counted(repository, log=lambda _: None)
    watch = Watch(backup, period=0.01)
    watch.start()
    assert ticked.wait(5.0)
    watch.stop()
    stopped = backup.ticks
    time.sleep(0.05)
    assert backup.ticks == stopped


def test_a_machine_with_no_git_says_that_rather_than_run_git_init(
    tmp_path: Path,
) -> None:
    """A container built without git is the case this is really about: the
    words are git's own, so what a person is sent to is installing it rather
    than a command they have not got."""

    class NoGit:
        def __call__(
            self, root: Path, *args: str, timeout: float | None = None
        ) -> Said:
            return Said(False, "[Errno 2] No such file or directory: 'git'")

    backup = Backup(tmp_path, run=NoGit())
    assert not backup.repository()
    assert "No such file or directory: 'git'" in backup.needs()[0]


# --- adopting a repository the person made (#355) -----------------------------

keygen = pytest.mark.skipif(
    shutil.which("ssh-keygen") is None, reason="the store's key is ssh-keygen's"
)


@keygen
def test_a_store_makes_a_key_of_its_own_on_first_ask(tmp_path: Path) -> None:
    """The public half is what the dialog shows and the person pastes into the
    repository's deploy keys; it is made the first time it is asked for and is
    the same key every time after. The private half stays beside it, outside
    the store, where no commit can reach it."""
    keys = tmp_path / "keys"
    backup = Backup(tmp_path / "tc49", run=FakeGit(toplevel=""), keys=keys)
    shown = backup.key()
    assert shown is not None and shown.startswith("ssh-ed25519 ")
    assert backup.key() == shown
    assert (keys / "id_ed25519").exists()
    assert "add the key below" in backup.needs()[0]
    assert backup.status()["key"] == shown


def test_a_store_given_nowhere_to_keep_a_key_has_none(tmp_path: Path) -> None:
    """A workstation: git pushes with whatever the person's ssh already has."""
    assert Backup(tmp_path, run=FakeGit(toplevel="")).key() is None


@keygen
def test_a_key_the_store_cannot_use_does_not_read_as_a_working_one(
    tmp_path: Path,
) -> None:
    """A `keys` volume made before the image seeded it belongs to root, and
    the store runs as the person who deployed the box: it reads the public
    half, which is world-readable, and not the private one (#443). That showed
    a key that looked right in the dialog while every push was refused, so a
    private half that is not there is said in words a person can act on, no
    key is quietly made over the top of it, and the push is not attempted.
    """
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "id_ed25519.pub").write_text("ssh-ed25519 AAAAC3Nz tc49 backup\n")
    root = tmp_path / "tc49"
    root.mkdir()
    run = FakeGit(toplevel=str(root))
    backup = Backup(root, run=run, keys=keys, log=lambda _: None)

    assert backup.key() is None
    assert backup.status()["key"] is None
    assert not (keys / "id_ed25519").exists()

    said = backup.push()

    assert not said.ok and str(keys / "id_ed25519") in said.words
    assert ("push",) not in run.calls
    assert [word for word in backup.needs() if "can push with" in word]
    assert backup.status()["copy"]["ok"] is False


@keygen
@pytest.mark.skipif(os.geteuid() == 0, reason="root opens a file whatever its mode")
def test_a_private_half_the_store_cannot_open_reads_as_unusable(
    tmp_path: Path,
) -> None:
    """The state found on the box: both halves are there and the private one
    belongs to somebody else, so it is asked by opening it rather than of the
    mode bits — the answer depends on who this process is."""
    keys = tmp_path / "keys"
    backup = Backup(tmp_path / "tc49", run=FakeGit(toplevel=""), keys=keys)
    assert backup.key() is not None

    (keys / "id_ed25519").chmod(0o000)

    assert backup.key() is None
    assert [word for word in backup.needs() if "can push with" in word]


@keygen
def test_a_key_the_store_can_read_both_halves_of_is_shown_and_pushed_with(
    tmp_path: Path,
) -> None:
    """The ordinary case, unchanged: a key is still made unasked the first
    time it is asked for, the public half is what the dialog shows, and
    nothing about the check on the private half stands in the way of a
    push."""
    keys = tmp_path / "keys"
    root = tmp_path / "tc49"
    root.mkdir()
    run = FakeGit(toplevel=str(root))
    backup = Backup(root, run=run, keys=keys, log=lambda _: None)

    shown = backup.key()

    assert shown is not None and shown.startswith("ssh-ed25519 ")
    assert backup.status()["key"] == shown
    assert not [word for word in backup.needs() if "can push with" in word]
    assert backup.push().ok
    assert ("push",) in run.calls


@keygen
def test_no_key_is_made_for_a_store_inside_another_repository(
    tmp_path: Path,
) -> None:
    """`bench/` is nobody's to adopt into, so there is nothing for a key to
    push."""
    backup = Backup(
        tmp_path / "bench", run=FakeGit(toplevel=str(tmp_path)), keys=tmp_path / "k"
    )
    assert backup.key() is None
    assert not (tmp_path / "k").exists()


def empty_remote(tmp_path: Path) -> str:
    """What github.com hands over once the form is submitted: a bare, empty
    repository, here on disk so nothing reaches the network."""
    bare = tmp_path / "somebody-railroad.git"
    run_git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    return str(bare)


def test_a_store_adopts_an_empty_repository_and_keeps_its_documents(
    tmp_path: Path,
) -> None:
    """The ordinary case: the store has been drawn in for weeks before anybody
    thinks about backup. `git clone` refuses a directory with anything in it,
    so the clone's `.git` is moved in under the documents, which then read as
    outstanding and become the first backup — and the first push lands
    without a branch ever being named here."""
    root = tmp_path / "tc49"
    (root / "layouts").mkdir(parents=True)
    drawn(root, "reversing-loops", "drawing: reversing-loops\n")
    remote = empty_remote(tmp_path)
    backup = Backup(root, log=lambda _: None)
    assert not backup.repository()

    said = backup.adopt(remote)

    assert said.ok, said.words
    assert backup.repository()
    assert backup.remote() == remote
    assert backup.needs() == []
    assert backup.outstanding() == ["reversing-loops"]
    assert (root / "layouts" / "reversing-loops.drawing.yaml").exists()
    assert [p.name for p in root.iterdir() if p.name.startswith(".adopting")] == []

    run_git(root, "config", "user.email", "suite@example.invalid")
    run_git(root, "config", "user.name", "The Suite")
    run_git(root, "config", "commit.gpgsign", "false")
    assert backup.commit().ok
    assert backup.push().ok, backup.push().words
    assert "backup: reversing-loops" in run_git(Path(remote), "log", "--format=%s")


def test_a_repository_that_already_holds_backups_is_not_adopted(
    tmp_path: Path,
) -> None:
    """That is a restore onto a new box — which of two stores wins is a
    question this does not answer — so it is refused in words, and the store
    is left exactly as it was: no `.git`, no clone lying about."""
    root = tmp_path / "tc49"
    (root / "layouts").mkdir(parents=True)
    other = tmp_path / "other"
    run_git(tmp_path, "init", "-q", "-b", "main", str(other))
    run_git(other, "config", "user.email", "suite@example.invalid")
    run_git(other, "config", "user.name", "The Suite")
    run_git(other, "config", "commit.gpgsign", "false")
    (other / "a").write_text("a")
    run_git(other, "add", "a")
    run_git(other, "commit", "-q", "-m", "held")
    backup = Backup(root, log=lambda _: None)

    said = backup.adopt(str(other))

    assert not said.ok
    assert "already holds backups" in said.words
    assert not (root / ".git").exists()
    assert sorted(p.name for p in root.iterdir()) == ["layouts"]


def test_an_address_that_cannot_be_reached_is_refused_in_gits_words(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tc49"
    backup = Backup(root, log=lambda _: None)

    said = backup.adopt(str(tmp_path / "nowhere.git"))

    assert not said.ok
    assert "nowhere.git" in said.words
    assert not (root / ".git").exists()
    assert list(root.iterdir()) == []


def test_a_store_that_is_a_repository_is_not_adopted_again(repository: Path) -> None:
    backup = Backup(repository, log=lambda _: None)
    said = backup.adopt("git@github.com:somebody/railroad.git")
    assert not said.ok
    assert "is a repository already" in said.words


def test_adopting_nowhere_is_refused(tmp_path: Path) -> None:
    said = Backup(tmp_path, run=FakeGit(toplevel="")).adopt("  ")
    assert not said.ok
    assert not (tmp_path / ".git").exists()
