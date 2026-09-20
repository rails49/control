#!/usr/bin/env bash
#
# Point this checkout's `origin` at the repository the deploy pulls from
# (docs/DEPLOY.md).
#
#   scripts/pin-origin.sh
#
# Which remote a box pulls from is state outside the checkout. It sits in
# `.git/config` on that one machine, put there by whatever `git clone` line
# somebody typed once, and `scripts/deploy.sh` depends on it and cannot see
# it. That is the fault #496 removed for the ssh alias by naming the host in
# full; the remote was the one thing the deploy still rested on. On 2026-09-20
# the layout box had an ssh remote whose key GitHub no longer accepted and the
# deploy stopped before it did anything (#541).
#
# HTTPS, because the repository is public: nothing to register, no key to
# rotate, and no credential on the box. `scripts/deploy.sh` exports
# GIT_TERMINAL_PROMPT=0, so a request for one fails loudly rather than reading
# the rest of the deploy as the answer.
#
# Set rather than checked. The deploy makes the box right instead of requiring
# it to be right, so a rebuilt box, a second box, or a clone somebody made over
# ssh out of habit deploys with nothing typed. The startup file next to it in
# `deploy.sh` is advised and not written, because it holds values a person
# edited on the box; a pull-only checkout's remote is not that kind of thing.
set -euo pipefail

ORIGIN=https://github.com/rails49/control.git

was=$(git remote get-url origin)
if [ "$was" != "$ORIGIN" ]; then
  # Only when it changed one: a box that drifted leaves the old URL in the
  # deploy log, and a box that was right says nothing.
  echo "origin was $was; pulling from $ORIGIN" >&2
  git remote set-url origin "$ORIGIN"
fi
