#!/usr/bin/env bash
#
# The gate: everything that has to be green before work lands. One exit code,
# so a verdict never rests on remembering which six commands to run.
#
#   ruff, black    style, over src and tests
#   pyright        strict, over src and tests
#   pytest         the Python suite
#   tsc, vitest    the ui, which carries its own toolchain
#
# Every check runs even after one has failed, and the failures are named again
# at the end. Stopping at the first red would report one broken thing per
# invocation — the wrong shape for anyone, agent or human, handed the output
# and asked to fix what they broke.

set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

[ -d ui/node_modules ] || (cd ui && pnpm install)

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
run pytest uv run pytest -q
# pnpm verifies node_modules against the lockfile before running a script and,
# without a TTY, aborts rather than replace it. That happens whenever this tree
# is mounted into a container while node_modules holds the host's binaries, and
# it kept the gate from going green inside implement-loop's sandbox. Both
# scripts are one binary each, so call them and leave node_modules to the
# install above.
run tsc ui/node_modules/.bin/tsc -p ui/tsconfig.json --noEmit
run vitest ui/node_modules/.bin/vitest run --root ui

if [ -z "$failed" ]; then
  printf '\ngreen\n'
  exit 0
fi

printf '\nred:%s\n' "$failed"
exit 1
