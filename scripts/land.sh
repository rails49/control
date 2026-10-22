#!/usr/bin/env bash
#
# Land the current branch: push it, open its PR, rebase-merge it once `ci` is
# green, then delete the branch and leave the checkout on the new main (a
# worktree is left detached there, since main is checked out elsewhere).
# Run it from the branch with the work committed. It waits as long as `ci`
# takes, about ten minutes, so an agent runs it in the background.
#
#   scripts/land.sh                       title and body from the commits
#   scripts/land.sh --title … --body …    any `gh pr create` arguments
#
# Without `-u` on the push: the sandbox cannot write `.git/config`.
# LAND_INTERVAL, 5 by default, is the seconds between reads of GitHub; the
# tests shorten it.

set -euo pipefail

interval=${LAND_INTERVAL:-5}

branch=$(git branch --show-current)
[ -n "$branch" ] && [ "$branch" != main ] || { echo "land.sh: not on a branch other than main" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "land.sh: uncommitted changes" >&2; exit 1; }

git push -q origin "$branch"

if ! gh pr view "$branch" --json number > /dev/null 2>&1; then
  if [ $# -eq 0 ]; then set -- --fill; fi
  gh pr create --head "$branch" "$@"
fi
gh pr merge "$branch" --auto --rebase

# `gh pr checks --watch` fails at once while no check has been reported yet.
# gh exits non-zero then and while a check is pending, so its text decides
# the wait and its status does not.
for _ in $(seq 30); do
  checks=$(gh pr checks "$branch" 2>&1) || true
  case $checks in *'no checks reported'*) ;; *) break ;; esac
  sleep "$interval"
done
gh pr checks "$branch" --watch --fail-fast --interval 20 > /dev/null || {
  gh pr checks "$branch" || true
  echo "land.sh: ci failed; the PR stays open" >&2
  exit 1
}

# GitHub starts the auto-merge when it gets round to it, minutes after ci on
# #930, with the merge state UNKNOWN meanwhile: up to five minutes.
for _ in $(seq 60); do
  state=$(gh pr view "$branch" --json state --jq .state)
  case $state in MERGED | CLOSED) break ;; esac
  sleep "$interval"
done
[ "$state" = MERGED ] || { echo "land.sh: ci passed but the PR is $state" >&2; exit 1; }
gh pr view "$branch" --json url --jq '"merged: " + .url'

git fetch -q origin main
if [ "$(git rev-parse --git-dir)" = "$(git rev-parse --git-common-dir)" ]; then
  git switch -q main
  git merge -q --ff-only origin/main
else
  git switch -q --detach origin/main
fi
git branch -D "$branch" 2> /dev/null
git log --oneline -1
