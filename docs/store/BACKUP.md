# Backing a store up

An installation's store is a directory of documents somebody made — the
railroad they drew, the stock they entered, the addresses their decoders
answer to — and since [#320](https://github.com/rails49/control/issues/320) it
is `~/tc49/` rather than anything inside a checkout. Nothing else keeps a copy
of it.

**The app drives git; it does not own it**
([ADR-0053](../adr/0053-backup-drives-git-and-does-not-own-it.md)). It commits,
pushes and restores when the timer or a person asks, and surfaces what git
said. It never runs `git init`, never makes a branch or a remote and never
resolves a conflict. The one credential it holds is a deploy key it made for
itself, good for one repository and nothing else
([#355](https://github.com/rails49/control/issues/355)).

Terminology follows [CONTEXT.md](../../CONTEXT.md) — **backup** and
**restore**; the routes are in [SYSTEM.md](../SYSTEM.md#asset-store) and the
code is `src/tc49/store/backup.py`.

## Setting one up

Once, in a browser, and no terminal
([#355](https://github.com/rails49/control/issues/355)):

1. Make an **empty, private repository** on github.com — no README, no
   licence, nothing in it.
2. Open `File ▸ Backup…`. The dialog shows the key this store made for
   itself. Copy it and paste it into that repository under *Settings ▸ Deploy
   keys*, with *Allow write access* ticked. It is the public half; pasting it
   somewhere wrong loses nothing.
3. Enter the repository's ssh address — `git@github.com:you/my-railroad.git`
   — and press *Back up to it*.

The store clones the repository and moves the clone's `.git` in under the
drawings already there, which become the first backup. Then *Turn automatic
backup on* in the same dialog, which writes `backup.yaml` in the store. It is
a document of the installation like the catalogue is, so it is backed up with
the rest and a restored store comes back with backup still on.

A repository that already holds anything is refused: that is a restore onto a
new box, which is a different act, and the dialog says so rather than
guessing which was meant. Until a repository is adopted the store still works:
the server comes up, the editor saves, and backup says what is missing.

**The key.** It is made by the store the first time the dialog asks for it,
where `tc49 serve --keys` gave it somewhere to keep one — on the layout server
a docker volume, `keys`, so that it is outside the store and no commit can
carry it, and on nothing the host has to make. It opens that one repository
and nothing else of yours, so a box on a wireless anybody can join reaches
nothing else of yours either. Revoking it is deleting it from the repository's
deploy keys. A store with nowhere to keep a key — `tc49 serve` on a
workstation without `--keys` — pushes with whatever ssh key that machine
already has, and the dialog says so.

**A key is both halves, and the dialog shows one only where it holds the
other.** The public half is world-readable and the private half is not, so a
store can print a key it cannot push with — which is what a `keys` volume made
before the store ran as the person leaves behind, the volume being seeded from
the image only while it is empty
([#387](https://github.com/rails49/control/issues/387)). The dialog shows no
key there rather than one that looks fine, and what backup needs names the
file and the one removal that cures it
([../DEPLOY.md](../DEPLOY.md), [#443](https://github.com/rails49/control/issues/443)).
Nothing pushes or adopts under such a key: it is refused here, in those words,
rather than at the far end as `Permission denied (publickey)`.

## What it does while you draw

**A commit some seconds after the last save**, `IDLE_S` of them. Each save
pushes the deadline out, so a burst of saves is one commit covering the
editing session rather than one per keystroke's worth of work, and a store
nobody is editing produces no commits at all. Quitting `tc49 serve` or `tc49
live` commits what is outstanding without waiting the window out.

**Ctrl-C and SIGTERM end `tc49 serve` the same way**, which is what makes that
last commit a deploy's too
([#410](https://github.com/rails49/control/issues/410)). On the layout server
the store is PID 1 in its container, and PID 1 gets no default action for
SIGTERM: `docker stop` — which every `compose up` that recreates the service
does, and `scripts/deploy.sh` recreates it on each deploy — waited ten seconds
and then killed the process, so the commit and push before a deploy were
skipped and the store was away for those ten seconds. The signal now raises
the same interrupt Ctrl-C does, so both leave by the one door: the listener
stops accepting, the watch stops, and the quit commits and pushes.

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

- **Make the repository or the remote.** The person makes the repository, in
  a web form, and the remote arrives with the address they enter; the store
  clones and never runs `git init` or `git remote add`.
- **Resolve a conflict.** It reports what git said and stops. A store is one
  person's, and sharing one between people is not something this offers.
- **Hold a credential of yours.** The key it pushes with is its own, opens one
  repository, and its private half never leaves the machine.
- **Back up a store that is inside a larger repository.** A checkout's
  `bench/` is what a developer runs a session on with `--store bench`; backing
  it up would land somebody's railroad as commits in the control repository,
  beside code, under whatever branch was out. Backup says which repository it
  is in and stops there.
- **Install git.** A machine with none says so in git's own words rather than
  offering `git init`, which is a command nobody can run without it.
