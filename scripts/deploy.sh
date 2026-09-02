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
TC49_SITE=layout docker compose --env-file /etc/tc49/deploy.env \
  -f deploy/compose.yaml --profile layout up -d --remove-orphans
REMOTE
