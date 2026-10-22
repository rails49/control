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

set -euo pipefail

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
for _ in $(seq 30); do
  gh pr checks "$branch" 2>&1 | grep -q 'no checks reported' || break
  sleep 5
done
gh pr checks "$branch" --watch --fail-fast --interval 20 > /dev/null || {
  gh pr checks "$branch"
  echo "land.sh: ci failed; the PR stays open" >&2
  exit 1
}

for _ in $(seq 30); do
  state=$(gh pr view "$branch" --json state --jq .state)
  [ "$state" = MERGED ] && break
  sleep 5
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
