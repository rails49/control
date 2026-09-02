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

Then turn automated backup on — `Backup ▸ Automatic backup` in the UI, which
writes `backup.yaml` in the store. It is a document of the installation like
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

## Restoring

`Backup ▸ Restore…` lists the backups there are and puts the store back as the
one you pick held it. It is usually not the last one you want: the editing
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
  beside code, under whatever branch was out. It reads as *not a repository*
  and says the same thing.
