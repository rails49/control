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
run tsc pnpm --dir ui check
run vitest pnpm --dir ui test

if [ -z "$failed" ]; then
  printf '\ngreen\n'
  exit 0
fi

printf '\nred:%s\n' "$failed"
exit 1
