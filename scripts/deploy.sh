#!/usr/bin/env bash
#
# Update the layout server and bring its stack back up (docs/DEPLOY.md).
#
#   scripts/deploy.sh
#
# Every command runs on the layout server. `ssh blocks` on a line of its own
# opens a session, and what came after it would run on this machine instead,
# so the whole sequence is fed to a shell there.
#
# A login shell, so pnpm is on PATH the way it is when you log in. The strict
# options are set inside it rather than as `bash -leu`, because
# /etc/profile.d/apps-bin-path.sh reads XDG_DATA_DIRS unset and would stop the
# deploy before it began.
set -euo pipefail

ssh blocks bash -l -s <<'REMOTE'
set -euo pipefail
# The heredoc is this shell's stdin, so a prompt for a git credential would
# read the rest of the script as the answer. Fail instead.
export GIT_TERMINAL_PROMPT=0
cd ~/control
git pull
pnpm --dir ui build
# Where the deploy settings of this box sit, read by compose below and by the
# script above it, so the two cannot come to different answers about the same
# variable (#442).
DEPLOY_ENV=/etc/tc49/deploy.env
# The store's directory, made here rather than left to Docker. A bind mount
# whose source is missing is created by the daemon as root, and the person is
# then shut out of their own documents: no editing, no `git init`, no putting
# a catalogue in by hand (#387). Which directory that is, compose decides —
# `TC49_STORE` moves the store and a box that moves it says so in the env
# file, which this shell knows nothing about — so the path is resolved the
# way compose resolves it rather than expanded here.
mkdir -p "$(scripts/store-root.sh "$DEPLOY_ENV")"
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
# command station on it asks for the first alone.
TC49_SITE=layout docker compose --env-file "$DEPLOY_ENV" \
  -f deploy/compose.yaml --profile layout --profile hardware \
  up -d --build --remove-orphans
REMOTE
