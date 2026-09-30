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
# The uid and gid are this account's, and compose reads them as the user the
# store and a session run as, and as the uid the image names (ADR-0067) — the
# shell's environment wins over the `--env-file` below, which is what makes
# exporting them here enough.
TC49_UID=$(id -u)
TC49_GID=$(id -g)
export TC49_UID TC49_GID
# `--build`, because compose builds only when no image is tagged for the
# service and would otherwise keep one from before the pull. The store, the
# session and the mirror all build from one context now, so a change under
# `src/` reaches none of them without it (#365).
# One profile: `layout` is the software of a running railroad — the store,
# the built ui and the four apps (ADR-0059, decision 5). Nothing here answers
# for what is plugged into the box: the translator that spoke to the command
# station is `rails49/dccex` now, a stack of its own on the box (#587), so
# `--remove-orphans` below is what takes the container this stack used to
# start. JMRI is another again: an operator's tool with a compose project of
# its own, started once by hand from the installation's checkout
# (rails49/installation ADR-0002).
docker compose --env-file "$BOX_ENV" --env-file "$DEPLOY_ENV" \
  -f deploy/compose.yaml --profile layout \
  up -d --build --remove-orphans
REMOTE
