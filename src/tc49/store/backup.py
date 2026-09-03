"""Backing an installation's store up with git, driven rather than owned.

The documents somebody's railroad is made of live in one directory — `~/tc49/`
unless they said otherwise (:mod:`tc49.store.root`, #320) — and nothing keeps
a copy of them. A railroad drawn over months, the stock entered item by item
and the addresses the decoders answer to are on one disk.

**The app drives git; it does not own it.** It commits and pushes when asked
and surfaces what git said. It never runs `git init`, never makes a remote,
never resolves a conflict and never moves a branch. Owning the repository
would put a model railroad program in the business of detached heads and
credentials for what is one button; knowing nothing about git would mean
reinventing versioning worse than git already does it (ADR-0053).

**A store that is not a git repository is a normal state.** Every operation
answers what is missing in words, saving is untouched, and nothing is created
behind anybody's back. The same goes for a store that is not the *top* of its
repository: a checkout's `bench/` is inside the control repo, and backing that
up would commit the research fixtures under somebody's railroad. It is
refused in the same words rather than by a special case.

**A store becomes a repository by adopting one the person made** (#355). On
a layout box there is no terminal to run `git init` in, and this never runs
it anyway. The person makes an empty repository on github.com and gives its
address; :meth:`Backup.adopt` clones it and moves the clone's `.git` under the
store, so the documents already there become the first backup. Neither `init`
nor `remote add` is run: the repository is the person's and the remote came
with the address.

**The push goes out under a key the store made for itself**, where it was
given somewhere to keep one (`keys`). The public half is shown by
:meth:`Backup.status` for the person to paste into that repository's deploy
keys — a key scoped to one repository, so a box on a wireless anybody can
join reaches nothing else of theirs. The private half never leaves the
machine and lives outside the store, so it cannot be committed.

**Commit on idle.** :meth:`Backup.saved` arms a deadline that each further
save pushes out, and :meth:`Backup.due` — the watch thread's tick — commits
once the store has been quiet for `idle_s`. Commit-per-save is history nobody
reads for somebody who saves often, and a fixed interval cuts commits at clock
ticks, so one edit straddles two and a quiet hour still ticks. A quiet store
produces no commits at all, because a commit is made only where git says
something moved.

**Push on its own timer**, and never in the way of a save. The local commit is
the backup that matters and the push is the off-machine copy, so an
unreachable remote is logged and retried on the next timer, and no caller
ever waits on the network to write a drawing.
"""

import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

IDLE_S = 20.0
"""Seconds of quiet after the last save before the store is committed. Long
enough that a burst of saves is one commit and short enough that a person who
walks away has their evening's drawing backed up before they are out the
door."""

PUSH_S = 300.0
"""Seconds between attempts to push, where there is a commit that has not been
pushed. It is the off-machine copy rather than the backup, so it is unhurried;
nothing waits on it and a failure only means the next timer tries again."""

PUSH_TIMEOUT_S = 30.0
"""How long one `git push` is given before it is killed.

A remote that is refusing answers at once; a remote that is simply unreachable
— a laptop off the wifi, a host that no longer resolves — does not answer at
all, and git waits on the operating system's connect timeout, which is minutes.
Nothing is lost by cutting that short: the commit is the backup, the copy is
retried on the next timer, and a session that is being stopped gets to stop.
"""

STALE_S = 24 * 60 * 60.0
"""How long a backup may sit here uncopied before the editor says so.

Each failed copy on its own is not worth interrupting anybody for — a network
comes and goes. A remote that has been unreachable for a day is not a network
blip; it is a remote that moved, or a credential that expired, and the person
who turned backup on believes they have an off-machine copy and does not.
"""

TICK_S = 1.0
"""How often :class:`Watch` lets the two timers above fire. It only bounds how
late a deadline is noticed, so it stays well under either of them."""

KEY = "id_ed25519"
"""The file the store's own deploy key is kept in, under `keys`, with the
public half beside it as `id_ed25519.pub`. Ed25519 because it is short enough
to read back and paste, and the one every host supports."""

SWITCH = "backup.yaml"
"""The file in the store that says whether automated backup is on.

It is kept in the store rather than in the process because *turned on* has to
survive the next restart, and there is nowhere else that belongs to one
installation. It is a document of the installation like the catalogue is, so
it is backed up with everything else — a restored store comes back with
backup still on."""


@dataclass(frozen=True)
class Said:
    """What one git command answered: whether it worked, and its own words.

    Both halves matter. The words are git's and are passed on as they came,
    which is the whole of what this app knows how to say about a conflict, a
    missing remote or a rejected push; `ok` is what the caller branches on so
    that it never has to read them.
    """

    ok: bool
    words: str


class Driver(Protocol):
    """How a git command is run. A seam so the policy above can be tested
    without a repository, and the one place a process is started."""

    def __call__(
        self, root: Path, *args: str, timeout: float | None = None
    ) -> Said: ...


def git(root: Path, *args: str, timeout: float | None = None) -> Said:
    """Run one git command in `root` and answer what it said.

    `-C` rather than a working directory, so nothing about this process's own
    directory reaches the command. Both streams are joined because git writes
    its refusals to one and its answers to the other, and the caller wants the
    words rather than the stream they came on.

    `timeout` bounds the wait and is given only to the push, the one command
    here that talks to another machine. A killed command reads as an ordinary
    refusal, in words saying what was waited on, because that is what it is:
    git was asked and did not answer in time.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Said(False, f"git {args[0]} gave no answer in {timeout:.0f}s")
    except OSError as missing:  # no git on this machine, or no such directory
        return Said(False, str(missing))
    return Said(done.returncode == 0, f"{done.stdout}{done.stderr}".strip())


def document(path: str) -> str:
    """One changed path, as the store names the document it is.

    A commit message is read by the person who drew the railroad, so it says
    `reversing-loops` where git says `layouts/reversing-loops.drawing.yaml`.
    A path this store does not recognise is passed through as it stands: it is
    something a person put there, and inventing a name for it would say less
    than the path does.
    """
    if path.startswith("layouts/"):
        name = path.removeprefix("layouts/")
        if name.endswith(".drawing.yaml"):
            return name.removesuffix(".drawing.yaml")
        if name.endswith(".roster.yaml"):
            return f"{name.removesuffix('.roster.yaml')} roster"
    if path.startswith("catalogue/") and path.endswith(".yaml"):
        return f"{path.removeprefix('catalogue/').removesuffix('.yaml')} model"
    if path.startswith("scenarios/") and path.endswith(".scenario.yaml"):
        return path.removeprefix("scenarios/").removesuffix(".scenario.yaml")
    return path


def documents(porcelain: str) -> list[str]:
    """The documents `git status --porcelain` says have moved, named and in
    order.

    Sorted and deduplicated because a message is a list a person reads and not
    a diff: a drawing saved twice moved once, and a rename that shows as one
    line naming two paths moved the document it arrived at.
    """
    names: set[str] = set()
    for line in porcelain.splitlines():
        path = line[3:].strip()  # `XY path`, the two status letters and a space
        if not path:
            continue
        _, arrow, renamed = path.partition(" -> ")
        names.add(document(renamed if arrow else path))
    return sorted(names)


class Backup:
    """Git over one store root: the timers, the refusals, and what to say.

    Constructed for every store the server opens, whether or not that store is
    a repository and whether or not anybody has turned automation on — asking
    is a `git rev-parse`, and a `Backup` that answers *this is not a
    repository* is what lets the UI offer backup and say what it needs.

    The timers are read by the watch thread and armed by the thread serving a
    save, so the state they share is behind a lock. It is held across the
    *commit*: a save arriving mid-commit waits for the subprocess and is then
    counted, where without the lock it would be swallowed by the commit that
    was already running and the drawing would sit unbacked up until the next
    one. A commit is local and takes milliseconds, so nothing waits long.

    **The push is outside it, and off every thread that serves a request.**
    A `git push` to a host that is not answering takes as long as the
    operating system's connect timeout, and a lock held across it is a lock
    that stops saves: the store's server answers one request at a time, so a
    save waiting on the network is the whole store waiting on the network,
    which #321 forbids. The tick thread is the only one that pushes; the
    button asks for a push and returns once the commit it really wanted is
    made.
    """

    def __init__(
        self,
        root: Path,
        run: Driver = git,
        log: Callable[[str], None] | None = None,
        now: Callable[[], float] = time.monotonic,
        idle_s: float = IDLE_S,
        push_s: float = PUSH_S,
        push_timeout_s: float = PUSH_TIMEOUT_S,
        stale_s: float = STALE_S,
        wall: Callable[[], float] = time.time,
        keys: Path | None = None,
    ) -> None:
        """`keys` is where this store's own deploy key is kept, and `None`
        where it has none — a workstation, where git pushes with whatever
        the person's ssh already has."""
        self.root = root
        self._run = run
        self._keys = keys
        self._log = log if log is not None else _note
        self._now = now
        self._wall = wall
        self._idle_s = idle_s
        self._push_s = push_s
        self._push_timeout_s = push_timeout_s
        self._stale_s = stale_s
        self._lock = threading.RLock()
        # When the store was last written, `None` where nothing is waiting on
        # the idle timer. A commit clears it, which is what stops a quiet
        # store from ticking.
        self._touched: float | None = None
        # Whether there is a commit here that the remote has not been given,
        # and when a push was last attempted. Pushing on the timer only where
        # there is something to push keeps a quiet store off the network.
        self._unpushed = False
        self._pushed_at = now()
        # A push the button asked for, waiting for the next tick to make it.
        self._push_wanted = False
        # What the last attempt to push said, `None` before there was one.
        # Read by the UI, which is where a copy that keeps failing is said out
        # loud rather than only written to a terminal nobody is watching.
        self._push_said: Said | None = None
        # Held for the length of one `git push`, and never waited on: it is
        # what keeps a session ending from pushing over a tick that already
        # is.
        self._pushing_now = threading.Lock()

    # --- what the store is ---------------------------------------------------

    @property
    def automatic(self) -> bool:
        """Whether the timers run. Read from the store each time rather than
        held, because it is the store's own answer: a restore, or a person
        editing the file, changes it under a server that is already up."""
        try:
            said: Any = yaml.safe_load((self.root / SWITCH).read_text())
        except (OSError, yaml.YAMLError):
            # No switch is off, which is what a fresh installation is: backup
            # is optional and nothing turns it on but a person.
            return False
        if not isinstance(said, dict):
            return False
        return cast(dict[str, Any], said).get("automatic") is True

    def switch(self, on: bool) -> None:
        """Turn automated backup on or off, for good and not for this
        session."""
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / SWITCH).write_text(yaml.safe_dump({"automatic": on}))

    def repository(self) -> bool:
        """Whether this store is a git repository in its own right.

        The store has to be the *top* of it. A store inside a larger
        repository — a checkout's `bench/`, which is what a developer runs a
        session on — would have its backups land as commits in that
        repository, next to code, under whatever branch happened to be out.
        """
        return self._inside() == self.root.resolve()

    def _inside(self) -> Path | None:
        """The top of the repository this store is in, `None` where git could
        not say — because there is no repository, or because there is no git
        on this machine at all."""
        said = self._run(self.root, "rev-parse", "--show-toplevel")
        if not said.ok:
            return None
        try:
            return Path(said.words).resolve()
        except OSError:
            return None

    def needs(self) -> list[str]:
        """What backup has not got, in the words a person is offered it in.

        A list because two things can be missing at once, and because the
        answer with nothing missing is empty rather than a sentence saying so.

        The three ways of having no repository are told apart, because they
        send a person to different places. A store **inside** another
        repository is not one to adopt into — it is `bench/`, and the
        repository it is in is this checkout. A store that is in none is told
        what to make and where to enter it (:meth:`adopt`), with git's own
        words after it, because git itself may be what is missing and those
        words are the only way to tell.
        """
        top = self._inside()
        if top is not None and top != self.root.resolve():
            return [
                (
                    f"{self.root} is inside the git repository at {top} rather"
                    " than being one, so backing it up would commit into that"
                    " repository — back up a store of its own instead"
                )
            ]
        if top is None:
            said = self._run(self.root, "rev-parse", "--show-toplevel")
            key = (
                " add the key below to it under Settings ▸ Deploy keys, with"
                " write access, and"
                if self.key() is not None
                else ""
            )
            return [
                (
                    f"{self.root} is not a git repository — create an empty"
                    f" private repository on github.com,{key} enter its address"
                    f" below. git said: {said.words}"
                )
            ]
        if not self._run(self.root, "remote").words:
            return [
                (
                    "no remote, so a backup stays on this machine — `git"
                    f" remote add origin <url>` in {self.root}"
                )
            ]
        return []

    def outstanding(self) -> list[str]:
        """The documents that have moved since the last backup.

        `-uall` names each file rather than the directory holding them, so a
        store that has never been committed reads as its railroads instead of
        as `layouts/`. Scoped to the root by `-- .`, which says the same thing
        twice for a store that is its own repository and is what keeps this
        honest if that ever stops being required.
        """
        said = self._run(self.root, "status", "--porcelain", "-uall", "--", ".")
        return documents(said.words) if said.ok else []

    def backups(self, count: int = 10) -> list[dict[str, str]]:
        """The last backups, newest first: what to name to :meth:`restore`,
        what it was called, and when it was made."""
        said = self._run(
            self.root,
            "log",
            f"-{count}",
            "--format=%h\t%s\t%ad",
            "--date=format:%Y-%m-%d %H:%M",
        )
        if not said.ok:
            return []  # no commits yet, or no repository: nothing to restore to
        made: list[dict[str, str]] = []
        for line in said.words.splitlines():
            commit, _, rest = line.partition("\t")
            message, _, when = rest.partition("\t")
            made.append({"commit": commit, "said": message, "when": when})
        return made

    def copy(self) -> dict[str, Any]:
        """How the copy off this machine stands: how many backups the remote
        has not been given, how long the oldest of them has been waiting, and
        what the last attempt said.

        Asked of git rather than remembered, so it survives a restart. A
        person who turned backup on, drew for weeks and never opened this
        dialog is exactly who a failing copy has to reach, and a count kept in
        this process would be zero every morning.

        `waiting` is wall-clock seconds since the oldest uncopied backup was
        made, and `stale` is that against :data:`STALE_S`. Both are absent
        where there is nothing waiting or no upstream to measure against — a
        store with no remote is :meth:`needs`'s to talk about, not this.
        """
        said = self._run(self.root, "log", "@{u}..HEAD", "--format=%ct")
        made = [int(line) for line in said.words.split() if line.isdigit()]
        waiting = self._wall() - min(made) if said.ok and made else None
        last = self._push_said
        return {
            "waiting": len(made) if said.ok else 0,
            "since": waiting,
            "stale": waiting is not None and waiting >= self._stale_s,
            "ok": None if last is None else last.ok,
            "said": "" if last is None else last.words,
        }

    def remote(self) -> str | None:
        """Where the copy off this machine goes, `None` where nowhere."""
        said = self._run(self.root, "remote", "get-url", "origin")
        return said.words if said.ok and said.words else None

    def key(self) -> str | None:
        """The public half of this store's own deploy key, made the first
        time it is asked for.

        `None` where the store was given nowhere to keep one, and for a store
        inside another repository, which is nobody's to adopt into. Made
        unasked because it is not a document: it is the box's own identity,
        like the host key sshd makes on first start, and a person cannot
        paste it into a repository's deploy keys before it exists. The
        private half is written beside it and read by nothing here — git's
        ssh is told where it is (:meth:`adopt`) and that is all.
        """
        if self._keys is None:
            return None
        public = self._keys / f"{KEY}.pub"
        try:
            return public.read_text().strip()
        except OSError:
            pass
        top = self._inside()
        if top is not None and top != self.root.resolve():
            return None
        self._keys.mkdir(parents=True, exist_ok=True)
        try:
            done = subprocess.run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "tc49 backup",
                    "-f",
                    str(self._keys / KEY),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as missing:  # no ssh-keygen on this machine
            self._log(f"backup: no key could be made: {missing}")
            return None
        if done.returncode != 0:
            self._log(f"backup: no key could be made: {done.stderr.strip()}")
            return None
        return public.read_text().strip()

    def status(self) -> dict[str, Any]:
        """The whole of what the UI reads: where the store is, whether it can
        be backed up, whether it is being, what is outstanding and what there
        is to restore to."""
        return {
            "root": str(self.root),
            "repository": self.repository(),
            "remote": self.remote(),
            "key": self.key(),
            "automatic": self.automatic,
            "needs": self.needs(),
            "outstanding": self.outstanding(),
            "backups": self.backups(),
            "copy": self.copy(),
        }

    # --- the timers ----------------------------------------------------------

    def saved(self) -> None:
        """A document was written. Arm the idle deadline, or push it out where
        one is already armed: a burst of saves is one editing session and gets
        one commit."""
        with self._lock:
            self._touched = self._now()

    def due(self) -> None:
        """One tick of the watch. Commit where the store has gone quiet, push
        where the timer is up and there is something to push.

        Both are silent where automation is off, which is the state a fresh
        installation is in: nothing is committed until somebody asks for it,
        by the switch or by the button.
        """
        with self._lock:
            if not self.automatic:
                return
            now = self._now()
            if self._touched is not None and now - self._touched >= self._idle_s:
                self._touched = None
                self._backed_up(self.commit())
            due = self._push_wanted or now - self._pushed_at >= self._push_s
            pushing = self._unpushed and due
            if pushing:
                # Claimed here, under the lock, so that the next tick does not
                # decide the same push is due while this one is still running.
                self._push_wanted = False
                self._pushed_at = now
        if pushing:
            self._pushing()

    def quit(self) -> None:
        """The session is ending: commit what is outstanding and attempt a
        push.

        The one place both happen together. A person closing the lid has said
        everything they are going to say, so there is nothing to coalesce with
        and no timer worth waiting out.
        """
        with self._lock:
            if not self.automatic:
                return
            self._touched = None
            self._backed_up(self.commit())
            pushing = self._unpushed
            if pushing:
                self._pushed_at = self._now()
        if pushing:
            self._pushing()

    # --- driving git ---------------------------------------------------------

    def adopt(self, url: str) -> Said:
        """Make the store a repository by cloning the empty one at `url`.

        `git clone` refuses a directory with anything in it, and a store
        worth backing up has drawings in it, so the clone goes to a directory
        of its own inside the store and its `.git` is moved up one level. The
        documents stay where they are and read as outstanding, which makes
        them the first backup. Inside the store rather than in `/tmp`, so the
        move is a rename on one filesystem and never a copy of a repository.

        **Refused where the repository holds anything.** A repository with
        backups in it is a restore onto a new box, which is a different act
        with a different question in it — which of two stores wins — and this
        says so rather than guessing. Refused too for a store that is already
        a repository, or is inside one; both are :meth:`needs`'s words.

        The clone carries two settings into the repository it makes, by
        `clone -c`, which writes them to the new `.git/config` and nowhere
        else: where the store's own key is, so that git's ssh offers that and
        not whatever else the machine has; and `push.autoSetupRemote`, so
        that the first push of a branch that has never been pushed sets its
        upstream rather than asking for a flag. Neither is `init`, a branch
        or a remote: the branch is the one the clone gave and the remote came
        with the address.

        The one route that waits on the network on the thread serving it,
        because the person who pressed the button is waiting for the answer;
        it is given the push's deadline.
        """
        with self._lock:
            top = self._inside()
            if top == self.root.resolve():
                where = self.remote()
                return Said(
                    False,
                    f"{self.root} is a repository already"
                    + (f", backing up to {where}" if where else ""),
                )
            if top is not None:
                return Said(False, self.needs()[0])
            url = url.strip()
            if not url:
                return Said(False, "no address was given")
            self.root.mkdir(parents=True, exist_ok=True)
            into = Path(tempfile.mkdtemp(prefix=".adopting-", dir=self.root))
            try:
                settings = ["-c", "push.autoSetupRemote=true"]
                if self._keys is not None and self.key() is not None:
                    ssh = f"ssh -i {self._keys / KEY} -o IdentitiesOnly=yes"
                    settings += ["-c", f"core.sshCommand={ssh}"]
                said = self._run(
                    self.root,
                    "clone",
                    "--quiet",
                    *settings,
                    "--",
                    url,
                    str(into),
                    timeout=self._push_timeout_s,
                )
                if not said.ok:
                    return said
                if self._run(into, "rev-parse", "--verify", "--quiet", "HEAD").ok:
                    return Said(
                        False,
                        f"{url} already holds backups. Bringing those onto"
                        " this box is a restore, not this; to back this store"
                        " up, give it an empty repository",
                    )
                (into / ".git").rename(self.root / ".git")
            finally:
                shutil.rmtree(into, ignore_errors=True)
            return Said(True, f"backing up to {url}; nothing is in it yet")

    def commit(self) -> Said:
        """Commit what has moved, under a message naming the documents.

        Everything under the root and nothing else: the store is what is being
        backed up, and `-- .` is what keeps that true. Nothing outstanding is
        answered rather than committed — an empty commit is the noise the idle
        timer exists to avoid.
        """
        if not self.repository():
            return Said(False, self.needs()[0])
        changed = self.outstanding()
        if not changed:
            return Said(True, "nothing has moved since the last backup")
        staged = self._run(self.root, "add", "-A", "--", ".")
        if not staged.ok:
            return staged
        said = self._run(self.root, "commit", "-m", f"backup: {', '.join(changed)}")
        if said.ok:
            self._unpushed = True
        return said

    def push(self) -> Said:
        """Hand the commits to the remote. Whatever git makes of the branch
        that is out and the upstream it has — none of that is this app's to
        decide, and a store with no remote reads git's own refusal.

        **Called with no lock held**, and given a deadline, because this is
        the one thing here that waits on another machine.
        """
        if not self.repository():
            return Said(False, self.needs()[0])
        said = self._run(self.root, "push", timeout=self._push_timeout_s)
        with self._lock:
            self._pushed_at = self._now()
            self._push_said = said
            if said.ok:
                self._unpushed = False
        return said

    def back_up(self) -> Said:
        """Back the store up now: commit what is outstanding, then attempt a
        push. What the button means, and what :meth:`quit` does on the way
        out.

        The commit is the answer. A push that could not reach the remote is
        logged like any other, because the backup a person just asked for has
        been made either way and a dialog about the network would be about
        something else.
        """
        with self._lock:
            self._touched = None
            said = self.commit()
            self._backed_up(said)
            if said.ok and self._unpushed:
                # Asked for rather than made here. The press is answered by
                # the commit, which is the backup; the copy off this machine
                # is the next tick's, so that a remote nobody can reach does
                # not hold this reply — and with it every other route the
                # store serves — open for the length of a connect timeout.
                self._push_wanted = True
            return said

    def restore(self, commit: str = "HEAD") -> Said:
        """Bring the store back to a backup, refusing over a dirty tree.

        **Refused where anything is outstanding.** Restoring writes over the
        documents in the store, and the ones that have not been backed up are
        exactly the ones git could not give back. The refusal names them and
        stops; backing up first is one press, and then the same restore is
        safe.

        What it does is put the store back **as that backup held it**, staged
        as well as in the working tree, so a document made after it goes as
        well as one edited since. Nothing is lost by that: the later backup is
        still in the history, restoring it is the same one press, and the next
        backup records the restore as the change it is.
        """
        with self._lock:
            if not self.repository():
                return Said(False, self.needs()[0])
            dirty = self.outstanding()
            if dirty:
                return Said(
                    False,
                    "refused: "
                    + ", ".join(dirty)
                    + " changed since the last backup, and restoring would"
                    " write over that — back the store up first",
                )
            said = self._run(
                self.root,
                "restore",
                "--source",
                commit,
                "--worktree",
                "--staged",
                "--",
                ".",
            )
            if not said.ok:
                return said  # git's words: an unknown commit, a lock, a mode
            moved = self.outstanding()
            return Said(
                True,
                (
                    f"restored {', '.join(moved)} from {commit}"
                    if moved
                    else f"the store already held {commit}"
                ),
            )

    # --- saying so -----------------------------------------------------------

    def _backed_up(self, said: Said) -> None:
        self._log(f"backup: {said.words}" if said.words else "backup: done")

    def _pushing(self) -> None:
        """Attempt the push and log what came of it, whatever came of it.

        **A lost network is logged and nothing else** — it never reaches a
        caller and never becomes a dialog. The commit is on this disk, which
        is the backup; the push is the copy off it, and the next timer tries
        again. What a person is told instead is in :meth:`status`: a copy that
        has been failing for a day says so in the editor, because a month of
        silence is the failure backup exists to prevent.

        Skipped where a push is already running, which is a session ending
        over a tick that is still waiting on the network. There is nothing to
        wait for: the copy in flight is carrying the same commits.
        """
        if not self._pushing_now.acquire(blocking=False):
            self._log("backup: a copy is already on its way")
            return
        try:
            said = self.push()
        finally:
            self._pushing_now.release()
        self._log(f"backup: {said.words}" if said.words else "backup: pushed")


class Watch:
    """The thread that lets the idle and push timers fire.

    A thread rather than a scheduled callback because the store's server is a
    blocking `serve_forever`, and a daemon so that a store which never comes to
    a tidy stop cannot keep the process up. It decides nothing: it wakes,
    calls :meth:`Backup.due` and goes back to sleep.
    """

    def __init__(self, backup: Backup, period: float = TICK_S) -> None:
        self._backup = backup
        self._period = period
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._tick, name="backup", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        """Stop ticking and wait for the tick in flight. Whatever is
        outstanding is the caller's to commit — :meth:`Backup.quit` is that,
        and it is the caller's so that a session ending on a signal still
        makes it."""
        self._stop.set()
        self._thread.join(timeout=self._period * 2)

    def _tick(self) -> None:
        while not self._stop.wait(self._period):
            self._backup.due()


def _note(words: str) -> None:
    """Where backup talks when nobody said where. Standard error, because a
    session's own output is its banner and its trace, and a push that failed
    is neither."""
    print(words, file=sys.stderr)
