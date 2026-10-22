#!/usr/bin/env bash
#
# The gate: everything that has to be green before work lands. One exit code,
# so a verdict never rests on remembering which six commands to run.
#
#   ruff, black    style, over src and tests
#   pyright        strict, over src and tests
#   pytest         the Python suite
#   tsc, vitest    the ui, which carries its own toolchain
#   vite           the ui's production build
#   look-check     the ui styles none of look's chrome
#
# Every check runs even after one has failed, and the failures are named again
# at the end. Stopping at the first red would report one broken thing per
# invocation — the wrong shape for anyone, agent or human, handed the output
# and asked to fix what they broke.
#
#   scripts/check.sh --fast    every check but pytest: seconds, not minutes

set -uo pipefail

FAST=0
[ "${1:-}" = --fast ] && FAST=1

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

# pnpm keeps a copy of the lockfile it installed in node_modules/.pnpm, so a
# bumped dependency shows as a difference rather than as tsc errors against
# the old build.
cmp -s ui/pnpm-lock.yaml ui/node_modules/.pnpm/lock.yaml || (cd ui && pnpm install --frozen-lockfile)

# The link check reads other rails49 repositories through GitHub's REST API,
# which answers 60 requests an hour without a token. CI sets one; here it is
# gh's, read now and never written down.
if [ -z "${GITHUB_TOKEN:-}" ]; then
  GITHUB_TOKEN=$(gh auth token 2>/dev/null) && export GITHUB_TOKEN
fi

# Accumulated as a string rather than an array: macOS ships bash 3.2, where an
# empty array under `set -u` is itself an error.
failed=""

run() {
  local what=$1
  shift
  printf '\n=== %s ===\n' "$what"
  "$@" || failed="$failed $what"
}

run ruff uv run ruff check .
run black uv run black --check .
run pyright uv run pyright
[ "$FAST" = 1 ] || run pytest uv run pytest -q
# pnpm verifies node_modules against the lockfile before running a script and,
# without a TTY, aborts rather than replace it. That happens whenever this tree
# is mounted into a container while node_modules holds the host's binaries, and
# it kept the gate from going green inside implement-loop's sandbox. Both
# scripts are one binary each, so call them and leave node_modules to the
# install above.
run tsc ui/node_modules/.bin/tsc -p ui/tsconfig.json --noEmit
run vitest ui/node_modules/.bin/vitest run --root ui
run vite ui/node_modules/.bin/vite build ui --logLevel warn
run look-check ui/node_modules/.bin/look-check ui/src ui/index.html

if [ -z "$failed" ]; then
  printf '\ngreen\n'
  exit 0
fi

printf '\nred:%s\n' "$failed"
exit 1
