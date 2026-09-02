# Backup drives git and does not own it

Resolves [#321](https://github.com/rails49/control/issues/321). Since
[#320](https://github.com/rails49/control/issues/320) an installation's
documents live in `~/tc49/` rather than in a checkout, and nothing keeps a
copy of them: a railroad drawn over months, the stock entered item by item and
the addresses the decoders answer to are on one disk.

## The rule

**The app drives git; it does not own it.** It commits, pushes and restores
when the timer or a person asks, and it surfaces what git said. It never runs
`git init`, never makes a branch or a remote, never resolves a conflict, never
moves `HEAD` and never handles a credential.

The two rejected positions are on either side of it.

**Owning the repository** — initializing it, choosing a branch, holding a
token, merging what came back — puts a model railroad program in the business
of detached heads and expired credentials for what is one button. Every one of
those states needs a screen and a vocabulary, and the person in front of it
already has `git` and a terminal.

**Knowing nothing about git** — a zip file per day, a numbered directory,
rsync to a share — means reinventing versioning, worse than git does it and
with none of the history, the diff or the off-machine copy. Driving it gets
all three for the cost of shelling out.

## A store that is not a repository is a normal state

A fresh installation's store is a directory nobody has run `git init` in, and
that is not a fault. Backup is offered, says what is missing in the words of
the command that would fix it, and changes nothing else: saving works, the
server answers, the panel comes up. Backup is refused the same way for a store
that is *inside* another repository rather than being one — a checkout's
`bench/`, which is what a developer runs a session on
([#320](https://github.com/rails49/control/issues/320)). Backing that up would
land somebody's railroad as commits in the control repository, beside code,
under whatever branch was out, so backup names the repository it found and
stops there. Which of the three it is gets its own words, a person with no git
installed and a person whose store is `bench/` having different things to do
about it.

**Automated backup is off until somebody turns it on**, and the switch is kept
in the store, so *on* survives the restart that follows it.

## What the timers are, and why they are not one timer

**Commit on idle**, some seconds after the last save with no further save,
plus a commit on quit. Commit-per-save is history nobody reads for somebody
who saves often. A fixed interval cuts commits at clock ticks, so one edit
straddles two of them and a quiet hour ticks anyway. Idle coalesces a burst of
saves into one commit covering the editing session, and a quiet store produces
no commits at all — the store is committed only where git says something
moved, so nothing empty is ever recorded.

**The message names the documents that moved**, in the store's own names:
`backup: reversing-loops, re460 model` rather than a path or a date. A timer
commit with a generic message is exactly the noise the timer exists to avoid,
and the list is one `git status` away.

**Push on its own timer, and on quit.** The commit is the backup that matters
and the push is the copy off this machine, so the two are not one act: an
unreachable remote is logged, the commit stands, and the next timer tries
again. **A lost network never blocks a save and never raises a dialog** — the
person drawing has nothing to answer about the wifi, and a modal there would
be a question about something they did not ask for.

That rule is about *time*, and it takes three things to hold. **No lock is
held across a push**, because the lock the timers share is taken by the thread
serving a save. **No thread serving a request ever pushes**: the store answers
one request at a time, so a push on that thread stops every route, and `Back
up now` therefore answers with the commit and leaves the copy to the next
tick. And **a push is given a deadline**, because a remote that refuses
answers at once while a remote that is merely unreachable does not answer at
all, and a session being stopped has to be able to stop. Killing a push loses
nothing: the commit is the backup and the next timer tries again.

**What a lost network does say, eventually.** Silence per failure is right and
silence for a month is the failure backup exists to prevent, so the store
reports how far behind the copy is — how many backups the remote has not been
given and how old the oldest is, asked of git rather than remembered so a
restart does not forget it — and the editor marks its `Backup…` item once that
passes a day. The same mark says when a store has never been backed up at all,
which is what automated backup being off by default leaves a person with.

## Restore is refused over a dirty tree

Documents that have not been backed up are exactly the ones git cannot give
back, so a restore over them is refused in words naming them, and backing up
first is one press. Over a clean tree it is `git restore` doing the work.

It restores **to a backup a person names**, not merely to the last one: the
editing session somebody wants undone was itself backed up, so the last
backup is usually the one they are trying to get out of. The store comes back
as that backup held it, which drops a document made after it as well as an
edit made since — and nothing is lost by that, because the later backup is
still in the history and restoring it is the same one press.

## What it rules on

- **The store owns it**, not an app of its own and not the UI. The routes are
  operations on the installation's store, which is why they sit beside the
  other five on the store's HTTP face
  ([ADR-0013](0013-apps-are-deployment-units.md),
  [SYSTEM.md](../SYSTEM.md)). A browser cannot shell out; what the UI has is
  the menu, the words and the choice.
- **Conflict resolution is out of scope.** The app reports and stops. A store
  is one person's, and sharing one between people is not a thing this offers.
- **It coins two words**, *backup* and *restore*, in
  [CONTEXT.md](../../CONTEXT.md). *Restore* there is already the word for
  bringing a run's placement back after a restart; the store's documents and a
  run's placement are far enough apart that the qualifier does the work, and
  inventing a second word for the same act would be worse.
- **Nothing in the dispatch path changes.** Backup reads and writes files in
  the store between sessions' worth of edits; no app learns about it, no event
  carries it, and a run that is up neither waits for it nor hears about it.
