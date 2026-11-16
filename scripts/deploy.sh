#!/usr/bin/env bash
#
# Update the layout server and bring its stack back up (docs/DEPLOY.md).
#
#   scripts/deploy.sh
#   CONTROL_BOX=<user>@<host> scripts/deploy.sh
#
# Every command runs on the layout server. An ssh command on a line of its own
# opens a session, and what came after it would run on this machine instead,
# so the whole sequence is fed to a shell there.
#
# The box is the ssh alias `rails49`, which each developer maps to their own
# box in `~/.ssh/config`, and `CONTROL_BOX` names another. The repository names
# no box (#1240). ssh goes to the box rather than to the label this UI is under.
#
# The box builds both images under the commit it pulled, so it needs Docker
# and git and no node or pnpm: the UI is built inside the `control-web` image
# (#1216). A login shell, so PATH is what it is when you log in. The strict
# options are set inside it rather than as `bash -leu`, because
# /etc/profile.d/apps-bin-path.sh reads XDG_DATA_DIRS unset and would stop the
# deploy before it began.
set -euo pipefail

BOX=${CONTROL_BOX:-rails49}

ssh "$BOX" bash -l -s <<'REMOTE'
set -euo pipefail
# The heredoc is this shell's stdin, so a prompt for a git credential would
# read the rest of the script as the answer. Fail instead.
export GIT_TERMINAL_PROMPT=0
cd ~/control
# The two files this box is started against, neither of them in this clone.
# `box.env` is the box's declaration of itself, which every stack on the box
# reads, and is where the name in the routers' labels comes from;
# `control.env` is this stack's own settings, read by compose and by
# `scripts/store-root.sh` below, so the two cannot come to different answers
# about the same variable (#442). Both sit in the installation's directory, so
# the box has one rather than two (#557).
BOX_ENV=/etc/rails49/box.env
CONTROL_ENV=/etc/rails49/control.env
# A tree with changes in it, tracked or not, would be built under a commit
# that is not what was built (dccex ADR-0005 d.4). So the deploy refuses one,
# before a pull merges around the changes.
dirty=$(git status --porcelain)
if [ -n "$dirty" ]; then
  echo "~/control is not clean, and the images would be named after a commit" >&2
  echo "that is not what was built:" >&2
  echo "$dirty" >&2
  exit 1
fi
git pull
# The name of both images, `ghcr.io/rails49/control:<commit>` and
# `control-web:<commit>`, and the revision they carry (deploy/compose.yaml).
CONTROL_COMMIT=$(git rev-parse HEAD)
export CONTROL_COMMIT
# The store's directory, made here rather than left to Docker. A bind mount
# whose source is missing is created by the daemon as root, and the person is
# then shut out of their own documents: no editing, no `git init`, no putting
# a catalogue in by hand (#387). Which directory that is, compose decides —
# `TC49_STORE` moves the store and a box that moves it says so in the env
# file, which this shell knows nothing about — so the path is resolved the
# way compose resolves it rather than expanded here.
mkdir -p "$(scripts/store-root.sh "$CONTROL_ENV")"
# The uid and gid are this account's, and compose reads them as the user the
# store runs as. The image is not told them: the store names its uid when it
# starts (#1216). The shell's environment wins over the `--env-file` below,
# which is what makes exporting them here enough.
TC49_UID=$(id -u)
TC49_GID=$(id -g)
export TC49_UID TC49_GID
# `--build`, because compose builds only when no image is tagged for the
# service and would otherwise keep one from before the pull. Every app here
# builds from one context, so a change under `src/` reaches none of them
# without it (#365). A deploy builds on the box and pulls nothing: a CI outage
# never blocks one (rails49/.github#71 decision 5).
# Two profiles, because two things are being asked for. `layout` is the
# software of a running railroad — the store, the built ui, and the scheduler,
# dispatcher and driver (ADR-0059, decision 5), the same on every box. `steel`
# adds the layout interface bound to the hardware, which only a box wired to a
# command station runs; a box with nothing attached asks for `sim` in its
# place and never for both (#604). This deploy is the wired box's.
# Nothing here answers for what is plugged into the box: the translator that
# spoke to the command station is `rails49/dccex` now, a stack of its own on
# the box (#587), so `--remove-orphans` below is what takes the container this
# stack used to start. JMRI is another again: an operator's tool with a compose
# project of its own, started once by hand from the installation's checkout
# (rails49/installation ADR-0002).
# `compose.https.yaml` adds the routers on the door's `websecure` entry point,
# which need the box's name (#1243).
docker compose --env-file "$BOX_ENV" --env-file "$CONTROL_ENV" \
  -f deploy/compose.yaml -f deploy/compose.https.yaml \
  --profile layout --profile steel \
  up -d --build --remove-orphans
REMOTE
