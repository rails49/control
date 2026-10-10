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
the rest, and a box that takes the store over from its repository comes back
with backup on.

**The address is ssh form**, `git@github.com:you/my-railroad.git`, which is
what github.com shows under *Code ▸ SSH*. The store pushes over ssh with its
own key, so an https address is refused before anything is cloned, and the
refusal carries the ssh form of the same repository to paste instead
([#688](https://github.com/rails49/control/issues/688)) — the same words
whether the address was copied with `.git`, without it, or with a trailing
`/` ([#692](https://github.com/rails49/control/issues/692)). A path on this
machine or a `file://` address is let through too, needing no key; any other
address is refused.

**What the address does depends on the store and the repository**, and the
dialog says which happened:

| Store | Repository | What happens |
| --- | --- | --- |
| empty, no repository | empty | backed up to it |
| has documents, no repository | empty | backed up to it; the documents are the first backup |
| empty, no repository | has backups | its latest backup is brought in ([Moving to a new box](#moving-to-a-new-box)) |
| has documents, no repository | has backups | refused, naming both — the two are never merged |
| a repository | empty | backup moves there ([Moving to another repository](#moving-to-another-repository)) |
| a repository | has backups | refused |

An empty store has no document in it; `backup.yaml` alone counts as empty.
Until a repository is adopted the store still works: the server comes up, the
editor saves, and backup says what is missing.

**The key.** It is made by the store the first time the dialog asks for it,
where `tc49 serve --keys` gave it somewhere to keep one — on the layout server
a docker volume, `keys`, so that it is outside the store and no commit can
carry it, and on nothing the host has to make. It opens that one repository
and nothing else of yours, so a box on a wireless anybody can join reaches
nothing else of yours either. Revoking it is deleting it from the repository's
deploy keys. The store names its key on every push, whatever the
repository's own config holds, so a repository cloned by hand pushes under it
too; and every push sets the branch's upstream where it has none. A store with
nowhere to keep a key — `tc49 serve` on a workstation without `--keys` —
pushes with whatever ssh key that machine already has, and the dialog says so.

**A deploy key opens one repository.** GitHub refuses a key already
registered on another repository with *Key is already in use*. To move to
another, delete it from the old repository under *Settings ▸ Deploy keys*
before deleting that repository, because a deleted repository keeps its keys
in use; the dialog's setup text says the same
([#692](https://github.com/rails49/control/issues/692)).

**New key** is for when that was not done: the old repository is gone and
GitHub still answers *Key is already in use*, or the key has leaked. It
deletes the store's key pair and makes a new one, and shows the new public half
to add to the repository with write access; take the old one off the
repository that has it, where that repository still exists. It asks once
first, because the key in use stops working until the new one is added
([#688](https://github.com/rails49/control/issues/688),
[#693](https://github.com/rails49/control/issues/693)). A store with nowhere
to keep a key, or inside another repository, has none to replace and is
refused.

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

**Every push names the store's key and sets an upstream**
([#688](https://github.com/rails49/control/issues/688)): the key as git's ssh
command where the store has one, and `push.autoSetupRemote`, passed on every
push whatever the repository's own config holds. A store cloned onto a box by
hand carries neither, and its pushes went out under whatever key the machine
had into a branch with no upstream — for five weeks, with nobody told.

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

**A press pushes with automatic backup off.** The switch governs what happens
unasked — the idle commit and the push timer. *Back up now* and a restore ask
for a push, which the next tick makes whatever the switch says, so a backup
somebody asked for leaves the box rather than reading a day later as a network
fault ([#688](https://github.com/rails49/control/issues/688)).

**A copy that keeps failing does get said out loud, after a day.** Each
failure on its own is a network coming and going and is only logged. What the
store reports instead is how far behind the copy is — how many backups the
remote has not been given and how old the oldest is, which is asked of git
(`git log @{u}..HEAD`, or the whole branch where a remote has no upstream)
rather than remembered, so a restart does not forget it. Past `STALE_S` the
run view says *backup behind* in the band, with git's words from the last push
as its tooltip — a missing key and a deleted repository read differently —
and the editor marks `File ▸ Backup…` the same way. Without that, a remote
that moved is invisible until the disk it was protecting against fails.

**What the band says** ([#688](https://github.com/rails49/control/issues/688)).
The run view's note and the menu's mark follow one rule, the first that holds:

| The store | Says |
| --- | --- |
| inside another repository (a checkout's `bench/`) | nothing |
| no repository — never set up, or copied to a box without one | *no backup set up* |
| the copy more than a day behind | *backup behind*, git's words as tooltip |
| a repository missing something — no remote, a key it cannot read | *backup cannot run*, the reason as tooltip |
| a repository with automatic backup off | *backup is off* |
| anything else, a single failed push included | nothing |

Pressing the note opens `File ▸ Backup…`. The app asks again every hour, so a
copy that went behind after the page loaded still shows.

## Restoring

*Restore*, in the footer of the `File ▸ Backup…` dialog, lists the backups
there are and puts the store back as the one you pick held it. It is usually not the last one you want: the editing
session you are trying to get out of was itself backed up.

**A restore over documents that have not been backed up is refused**, in words
naming them. Those are exactly the ones git cannot give back. Back the store
up first — one press — and then restore.

**A restore waits while the layout could disagree with the store.** The
dialog greys *Restore* and says why (#684,
[#688](https://github.com/rails49/control/issues/688),
[#699](https://github.com/rails49/control/issues/699)):

- a train placed — *trains are on the layout — take them off to restore*: the
  backup may not have the track a train stands on;
- a railroad loaded and track power not off — *track power is on — turn it
  off to restore*: the rails and the drawing are never changed under a moving
  train;
- the picked backup without the loaded railroad — *this backup has no*
  `<railroad>` *— load another railroad first*: the apps would go on running a
  railroad the store no longer holds. Each backup lists the railroads it holds
  by their drawings, so a railroad drawn after it is the one it lacks
  ([#697](https://github.com/rails49/control/issues/697)).

The app wears these rules; the store server checks none of them, as it checks
nothing for edits — it hears nothing from the bus.

**A restore is a complete act.** It leaves `backup.yaml` as it is, so undoing
a drawing mistake never stops backups, and a backup made before there was one
does not take it away; it is itself a backup, committed at once as
`restore <short commit> of <date>: <documents>`, so a power cut does not lose
it and a second restore — a wrong pick put right — is the same one press; and
it is pushed like any press. Restoring the backup the store already holds
changes nothing and makes no backup.

**After a restore that worked, the run and the page read what it wrote.** With
a railroad loaded, the app names it again on `tc49/layout/railroad_wanted`,
which every app answers by building it again from the store — the track is
already off, so this is the same build as picking it in the band — and then
the page reloads, so the editor cannot save back a copy it read before the
restore. With no railroad loaded the page only reloads. A refused restore
changed nothing, so it names nothing and reloads nothing. The dialog says so
above the backups: *Restore puts the store back as the picked backup held it;
the apps and this page then reload*
([#699](https://github.com/rails49/control/issues/699)).

Restoring drops a railroad drawn after that backup along with an edit made
since, because the store comes back as that backup held it. Nothing is lost by
it: the backup you came from is still in the history and restoring it is the
same one press.

## Moving to a new box

The new box's store is empty. In order:

1. On the new box, open `File ▸ Backup…` and copy the key it shows.
2. On github.com, in the repository's *Settings ▸ Deploy keys*, remove the
   old box's key — a deploy key opens one repository, and the old box should
   no longer push here — and add the new box's, with *Allow write access*.
   A dead box's key is removed the same way: it is listed there whether or
   not the box still runs.
3. In the dialog, enter the repository's ssh address and press *Back up to
   it*. The store clones it and holds the latest backup, `backup.yaml` with it,
   so backup is on again if it was on before, and pushes go out under the new
   box's key.

The answer names the backup brought in, `restored <short commit> from
<address>`, and every backup the old box made is in the list to restore from.
No railroad is loaded until one is chosen.

Drawing anything on the new box before step 3 makes its store not empty, and
the dialog then refuses, naming both the store's documents and the
repository's backups: the two are never merged. `backup.yaml` alone is not a
document, so turning backup on or off first changes nothing. The dialog's
setup text, on a store that is no repository yet, points here
([#694](https://github.com/rails49/control/issues/694)).

## Moving to another repository

A store already backed up can move to another repository from the dialog — the
old one deleted, or another wanted — with no terminal
([#698](https://github.com/rails49/control/issues/698)):

1. Make an **empty** repository, as in [Setting one up](#setting-one-up).
2. Move the deploy key from the old repository to it: remove the key under the
   old one's *Settings ▸ Deploy keys* first, since GitHub refuses one key on
   two repositories, then add it to the new one's with write access. An old
   repository already deleted took the key with it; if GitHub still says the
   key is in use, *New key* makes another ([the key](#setting-one-up)).
3. Open *Backup…*, unfold *back up to another repository*, enter the new
   address and press *Back up to it*.

The store asks the address with `git ls-remote` first. Anything listed there is
refused — "… already holds backups, and backup moves only to an empty
repository" — and an address git cannot reach is refused in git's words. An
empty one is given the store's branch, every earlier backup with it so each
stays restorable, and only once that push worked does `origin` name the new
address and the branch follow it; the dialog says "backing up to *address*,
with *n* backups". A push that fails leaves the store backing up where it did.

## What it will not do

- **Make the repository or the remote.** The person makes the repository, in
  a web form, and the remote arrives with the address they enter; the store
  clones and never runs `git init` or `git remote add`. A move changes the
  address of the remote the clone brought, and still never adds one: a store
  with none has nothing to move.
- **Fetch or pull.** The store reaches the repository only to clone it, list
  its refs and push. A repository edited elsewhere — on github.com, or by a
  second box pushing to it — refuses the store's pushes; the store reports
  git's words, reads as behind after a day, and does not fetch or merge.
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
