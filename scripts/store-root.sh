#!/usr/bin/env bash
#
# Print the directory the store is rooted at on this box, the way compose
# resolves it (docs/DEPLOY.md).
#
#   scripts/store-root.sh [env-file]
#
# `scripts/deploy.sh` makes that directory before compose starts, because a
# bind mount whose source is missing is created by the Docker daemon as root
# and the person is then shut out of their own documents (#387). Making the
# wrong one is the same fault: nothing mounts it, the real source is still
# missing when compose starts, and the daemon makes that one instead (#442).
#
# So the answer has to be compose's answer, and compose reads the same
# variable out of `--env-file /etc/tc49/deploy.env` with the deploy shell's
# own environment winning over the file. That precedence is what a box moving
# its store depends on: the value sits in the file, which the deploy shell
# knows nothing about, and expanding `${TC49_STORE:-$HOME/tc49}` in the shell
# would answer `$HOME/tc49` there.
#
# The file is read rather than sourced. It is the one place a secret sits on
# disk (docs/DEPLOY.md), and sourcing it would put the Cloudflare token into
# the environment of everything the deploy runs after it.
set -euo pipefail

ENV_FILE=${1:-/etc/tc49/deploy.env}
DEFAULT=$HOME/tc49
NAME=TC49_STORE

# Set in the shell wins, empty or not: compose looks the variable up in its
# own environment first and only falls back to the file for one it does not
# find there. Which leaves `:-` below to answer for an empty value, exactly
# as `${TC49_STORE:-~/tc49}` in `deploy/compose.yaml` does.
if [ -n "${TC49_STORE+set}" ]; then
  store=$TC49_STORE
else
  store=""
  # Unreadable is not a failure. The file is root-owned and mode 640, and a
  # box that has none is a box with nothing to say about where its store is:
  # either way today's default is the answer, and the deploy goes on.
  if [ -r "$ENV_FILE" ]; then
    # The last assignment, which is the one a later line overrides an earlier
    # one with; `grep` finds nothing on a file that never names it.
    line=$(grep -E "^[[:space:]]*$NAME=" "$ENV_FILE" | tail -n 1) || line=""
    store=${line#*=}
    # Quotes are the env file's, not the value's.
    case $store in
    \"*\") store=${store#\"} && store=${store%\"} ;;
    \'*\') store=${store#\'} && store=${store%\'} ;;
    esac
  fi
fi

# `~` is expanded here rather than left to the `mkdir` that reads this, which
# would take it literally and make a directory named `~`. Compose expands the
# one its own default carries.
case $store in
"~") store=$HOME ;;
"~/"*) store=$HOME/${store#\~/} ;;
esac

printf '%s\n' "${store:-$DEFAULT}"
