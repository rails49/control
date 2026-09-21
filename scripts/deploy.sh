#!/usr/bin/env bash
#
# Update the layout server and bring its stack back up (docs/DEPLOY.md).
#
#   scripts/deploy.sh
#
# Every command runs on the layout server. An ssh command on a line of its own
# opens a session, and what came after it would run on this machine instead,
# so the whole sequence is fed to a shell there.
#
# The host is named in full rather than as `rails49`, which is an ssh alias and
# lives in `~/.ssh/config` — a personal file that is in no repository. A machine
# whose config has lost the stanza had a broken deploy (#488, #496); naming the
# host here means the deploy depends on nothing outside this checkout. `ssh
# rails49` stays what you type by hand (docs/DEPLOY.md).
#
# The box is `gleis49.org`, which is the name it is declared under and reached
# at now that the door is the installation's (#557). This UI is a label under
# that name, `control.gleis49.org`, and ssh goes to the box rather than to the
# label.
#
# A login shell, so pnpm is on PATH the way it is when you log in. The strict
# options are set inside it rather than as `bash -leu`, because
# /etc/profile.d/apps-bin-path.sh reads XDG_DATA_DIRS unset and would stop the
# deploy before it began.
set -euo pipefail

ssh ttmetro@gleis49.org bash -l -s <<'REMOTE'
set -euo pipefail
# The heredoc is this shell's stdin, so a prompt for a git credential would
# read the rest of the script as the answer. Fail instead.
export GIT_TERMINAL_PROMPT=0
cd ~/control
# Which repository this box pulls from is state outside the checkout, the way
# the ssh alias was before #496: a line in `.git/config` on this one machine
# that the deploy depends on and cannot see. A box whose remote had an ssh URL
# GitHub no longer had a key for stopped the deploy before it did anything
# (#541), so the deploy sets it rather than trusting it.
#
# HTTPS, because the repository is public: nothing to register, no key to
# rotate, and no credential on the box. The prompt is off above, so a challenge
# fails rather than stalls.
#
# Written out here rather than kept in a script under `scripts/`, which is
# where `store-root.sh` belongs. This runs *before* the pull, and everything
# under `scripts/` on that box is whatever it last pulled — on the box this
# rescues, which cannot pull at all, a script would never arrive (#543). These
# lines come from the dev box's checkout with the rest of the heredoc.
ORIGIN=https://github.com/rails49/control.git
was=$(git remote get-url origin)
if [ "$was" != "$ORIGIN" ]; then
  # Only when it changed one: a box that drifted leaves the old URL in the
  # deploy log, and a box that was right says nothing.
  echo "origin was $was; pulling from $ORIGIN" >&2
  git remote set-url origin "$ORIGIN"
fi
git pull
pnpm --dir ui build
# The two files this box is started against, neither of them in this clone.
# `box.env` is the box's declaration of itself, which every stack on the box
# reads, and is where the name in the routers' labels comes from; `deploy.env`
# is this stack's own settings, read by compose below and by the script above
# it, so the two cannot come to different answers about the same variable
# (#442). Both sit in the installation's directory, so the box has one rather
# than two (#557).
BOX_ENV=/etc/rails49/box.env
DEPLOY_ENV=/etc/rails49/deploy.env
# The store's directory, made here rather than left to Docker. A bind mount
# whose source is missing is created by the daemon as root, and the person is
# then shut out of their own documents: no editing, no `git init`, no putting
# a catalogue in by hand (#387). Which directory that is, compose decides —
# `TC49_STORE` moves the store and a box that moves it says so in the env
# file, which this shell knows nothing about — so the path is resolved the
# way compose resolves it rather than expanded here.
mkdir -p "$(scripts/store-root.sh "$DEPLOY_ENV")"
# The translator's startup file — this installation's per-district trip
# currents (#217) — made here for the same reason and never written over: the
# values in it are edited on the box, and the deploy that truncated them would
# move every district to the firmware's default without saying so.
#
# `/etc/rails49` is root's, holding the box's declaration and the door's
# credential, so this account may not be able to make a file in it. A deploy
# that stopped there would take the whole railroad down over a file that is
# allowed to be empty — a railroad with none powers on at the firmware's own
# limits (ADR-0050) — so it says what to run by hand and goes on. The second
# test catches a directory the daemon made there before this line existed,
# which `touch` updates rather than replaces.
DCCEX_STARTUP=/etc/rails49/dccex-startup.txt
# What that second test advises, built here so docs/DEPLOY.md can give the
# same line and tests/system/test_startup_file_is_mounted.py can hold the two
# together. It removes what is at the path before making the file: `install`
# takes a directory as a *destination*, so against the directory this test
# exists to catch it wrote a file called `null` inside it and reported
# success — nothing to see, the translator still opening a directory as its
# startup file, and the next deploy printing this line again (#529). `rm -rf`
# and not `rmdir`, because a run of that old advice left the `null` behind.
# The guard goes with it. Nothing is at the path at the moment this is
# printed, but the line is run whenever the operator gets to it — pasted out
# of a deploy log an hour later, after a colleague made the file — and
# unguarded `rm -rf` would take this installation's trip currents with it
# (#536). It also makes this line and the page's literally the same.
remedy="[ -f $DCCEX_STARTUP ] || { sudo rm -rf $DCCEX_STARTUP && sudo install -m 644 /dev/null $DCCEX_STARTUP; }"
if [ ! -f "$DCCEX_STARTUP" ]; then
  touch "$DCCEX_STARTUP" 2>/dev/null || true
fi
if [ ! -f "$DCCEX_STARTUP" ]; then
  echo "no $DCCEX_STARTUP and this account cannot make one: the districts" \
    "run at the limits the station's firmware was built with until" \
    "'$remedy' is run on the box" >&2
fi
# The uid and gid are this account's, and compose reads them as the user the
# store and a session run as — the shell's environment wins over the
# `--env-file` below, which is what makes exporting them here enough.
TC49_UID=$(id -u)
TC49_GID=$(id -g)
export TC49_UID TC49_GID
# `--build`, because compose builds only when no image is tagged for the
# service and would otherwise keep one from before the pull. The store, the
# session and the mirror all build from one context now, so a change under
# `src/` reaches none of them without it (#365).
# Two profiles: `layout` is the software of a running railroad — the store,
# the built ui and the four apps — and `hardware` is what this box owns
# because of what is plugged into it (ADR-0059, decision 5). A box with no
# command station on it asks for the first alone. JMRI is neither: it is an
# operator's tool with a compose project of its own, started once by hand from
# the installation's checkout (rails49/installation ADR-0002).
docker compose --env-file "$BOX_ENV" --env-file "$DEPLOY_ENV" \
  -f deploy/compose.yaml --profile layout --profile hardware \
  up -d --build --remove-orphans
REMOTE
