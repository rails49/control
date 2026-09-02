# Backing a store up

An installation's store is a directory of documents somebody made — the
railroad they drew, the stock they entered, the addresses their decoders
answer to — and since [#320](https://github.com/rails49/control/issues/320) it
is `~/tc49/` rather than anything inside a checkout. Nothing else keeps a copy
of it.

**The app drives git; it does not own it**
([ADR-0053](../adr/0053-backup-drives-git-and-does-not-own-it.md)). It commits,
pushes and restores when the timer or a person asks, and surfaces what git
said. It never runs `git init`, never makes a branch or a remote, never
resolves a conflict and never handles a credential.

Terminology follows [CONTEXT.md](../../CONTEXT.md) — **backup** and
**restore**; the routes are in [SYSTEM.md](../SYSTEM.md#asset-store) and the
code is `src/tc49/store/backup.py`.

## Setting one up

Two commands, once, in the store:

```
cd ~/tc49
git init
git remote add origin git@github.com:you/my-railroad.git   # optional
```

Then turn automated backup on — `File ▸ Backup…` in the UI, and *Turn
automatic backup on* in the dialog it opens, which writes `backup.yaml` in the
store. It is a document of the installation like
the catalogue is, so it is backed up with the rest and a restored store comes
back with backup still on.

Nothing above is done for you, and until it is done the store still works: the
server comes up, the editor saves, and backup says what is missing in the
words of the command that would fix it.

## What it does while you draw

**A commit some seconds after the last save**, `IDLE_S` of them. Each save
pushes the deadline out, so a burst of saves is one commit covering the
editing session rather than one per keystroke's worth of work, and a store
nobody is editing produces no commits at all. Quitting `tc49 serve` or `tc49
live` commits what is outstanding without waiting the window out.

**The message names the documents that moved**, in the store's own names:

```
backup: reversing-loops, reversing-loops roster, re460 model
```

Which documents those are is `git status`'s answer and not a list this keeps,
so a roster edited by hand in another window is named as readily as a drawing
saved from the editor.

**A push on its own timer**, `PUSH_S`, and on quit. The commit is the backup
that matters and the push is the copy off this machine, so a remote that
cannot be reached is logged and the next timer tries again. **A lost network
never blocks a save and never raises a dialog** — the person drawing has
nothing to answer about the wifi.

That is a claim about how long a save takes, and three rules keep it true. The
lock the timers share is **not held across a push**, because the thread
serving a save takes the same lock. **Nothing serving a request pushes**: the
store answers one request at a time, so a push there would stop every route,
and `Back up now` answers with the commit and leaves the copy to the next
tick. And a push is **given up on after `PUSH_TIMEOUT_S`**, because a remote
that refuses answers at once while one that is unreachable does not answer at
all, and quitting has to be able to finish.

**A copy that keeps failing does get said out loud, after a day.** Each
failure on its own is a network coming and going and is only logged. What the
store reports instead is how far behind the copy is — how many backups the
remote has not been given and how old the oldest is, which is asked of git
(`git log @{u}..HEAD`) rather than remembered, so a restart does not forget
it. Past `STALE_S` the editor marks `File ▸ Backup…`. Without that, a remote
that moved is invisible until the disk it was protecting against fails.

## Restoring

*Restore*, in the footer of the `File ▸ Backup…` dialog, lists the backups
there are and puts the store back as the one you pick held it. It is usually not the last one you want: the editing
session you are trying to get out of was itself backed up.

**A restore over documents that have not been backed up is refused**, in words
naming them. Those are exactly the ones git cannot give back. Back the store
up first — one press — and then restore.

Restoring drops a railroad drawn after that backup along with an edit made
since, because the store comes back as that backup held it. Nothing is lost by
it: the backup you came from is still in the history and restoring it is the
same one press.

## What it will not do

- **Make the repository or the remote.** Two commands a person runs once, with
  their own account and their own host.
- **Resolve a conflict.** It reports what git said and stops. A store is one
  person's, and sharing one between people is not something this offers.
- **Handle credentials.** Whatever git already uses is what it uses.
- **Back up a store that is inside a larger repository.** A checkout's
  `bench/` is what a developer runs a session on with `--store bench`; backing
  it up would land somebody's railroad as commits in the control repository,
  beside code, under whatever branch was out. Backup says which repository it
  is in and stops there.
- **Install git.** A machine with none says so in git's own words rather than
  offering `git init`, which is a command nobody can run without it.
