---
name: batch-implement
description: Implement a batch of ready-for-agent issues unattended — one cold subagent per issue, a gate between each, and one review over the whole range at the end.
disable-model-invocation: true
---

Lands several issues while nobody is watching. Each issue gets its own cold
subagent, the parent gates the result before moving on, commits stay local
until the end, and a single review covers the whole range rather than each
step.

The shape earns its cost twice. A cold subagent per issue means the second
issue is not implemented through the lens of the first. A gate the *parent*
runs means the agent that wrote the code is not the one that decides it
passed.

Arguments: issue numbers, or nothing at all.

## Pre-flight

Refuse to start unless all of these hold. Each is a way the run could destroy
work that is not its own.

- **Working tree clean** — `git status --porcelain` empty. The failure path
  below resets hard; anything in flight would go with it.
- **Nothing listening on 8765** — `lsof -nP -iTCP:8765 -sTCP:LISTEN`.
  `scripts/dev.sh` leaves `tc49 serve` up and the editor saves through it into
  `layouts/`, so a live editor and an unattended batch cannot share a working
  tree. Say how to stop them (`kill $(cat out/dev/*.pid)`) and abort.
- **`git pull --rebase` clean**, so the night's commits sit on the current tip.
- **`scripts/check.sh` green** on the starting commit. A gate that was already
  red would blame the first subagent for something it did not do.

Record the starting SHA. It is the base for the final review.

## Choose the batch and order it

With no arguments, the batch is every open issue labelled `ready-for-agent`.
With arguments, it is exactly those numbers.

Order it either way by GitHub's native dependencies rather than by number —
number order agrees with dependency order only by luck:

```
gh api repos/rails49/control/issues/<n> --jq '.issue_dependencies_summary'
```

Read `blocked_by` for each issue in the batch and resolve the blockers with
`gh api repos/rails49/control/issues/<n>/dependencies/blocked_by`. Sort so a
blocker runs before what it blocks. An issue whose blocker is open and *not*
in the batch does not run at all — report it as skipped and why.

Print the ordered plan before dispatching anything.

## Per issue

Record `pre=$(git rev-parse HEAD)`. This is what the failure path returns to.

### Dispatch

One `Agent` call, `subagent_type: general-purpose`, running in the foreground —
the loop is serial on purpose, because issues in one batch usually touch the
same files.

The prompt carries `/implement`'s brief inline. It cannot be reached with the
Skill tool: `/implement` is marked `disable-model-invocation`, so only a human
typing it can invoke it.

> Implement issue #NN in this repo.
>
> Read it first: `gh issue view NN --comments`. Then read `CONTEXT.md` for the
> vocabulary and any ADR in `docs/adr/` touching the area — use the glossary's
> terms, not its listed synonyms.
>
> Use `/tdd` where the seams are already agreed. Typecheck and run the
> individual test files you are touching as you go.
>
> When you believe you are done, run `./scripts/check.sh` and get it green —
> it is the same gate that will be run against your work afterwards. Then run
> `/code-review` over your own change and act on what it finds.
>
> Commit to the current branch as `CLAUDE.md` requires: linear, each commit a
> reviewable step referencing #NN, any mechanical move in its own commit so
> the rename stays legible.
>
> Do not push. Do not close the issue. Do not write into `scratch/` — that
> directory is the owner's.
>
> [handoff, when it applies]

### Handoff

When this issue is blocked by another one *in this batch* that has already
landed, append to the prompt:

> Issue #AA in this same batch blocked this one and has already landed as
> <sha…>. It <two sentences on what it changed and where>. Read that commit
> before starting; it is the only prior work in this run that bears on yours.

Nothing else crosses between subagents. That edge is the one piece of
cross-issue context that is relevant rather than noise — without it the second
agent cold-derives what the first just learned, and with more than it the
context drift the split exists to prevent comes back.

### Gate

Both of these, in this order:

1. **`./scripts/check.sh`** — the exit code is the verdict, no interpretation.
2. **Read `git diff $pre..HEAD` against the issue body.** Green tests say
   nothing broke; they cannot say the issue was addressed. Check each thing
   the issue actually asked for. Check too that the commit messages reference
   the issue — the final review resolves its spec sources from them.

### Repair, once

If either half fails, send the failing output back to the *same* subagent with
`SendMessage` — it still holds the context of what it tried. One round only. A
second cold attempt rarely beats the first, and an unbounded retry loop spends
the whole night on the issue that is fighting you.

### Give up

Still failing after the repair round:

```
git reset --hard $pre
git clean -fd            # untracked only; scratch/ and out/ are ignored and survive
```

Then leave the morning's triage already done: `gh issue comment NN` with what
failed (the failing section of the check output, trimmed), and
`gh issue edit NN --remove-label ready-for-agent --add-label ready-for-human`.

Any issue in the batch blocked by this one is skipped too — its premise never
landed. Report it.

Then continue with the next issue. Two of three landing beats zero.

## After the last issue

### Review the whole range

Run `/code-review` — the mattpocock two-axis one — over `<start-sha>...HEAD`.
Its Spec axis resolves the originating issues from the `#NN` references in the
commit messages, which is why the gate checks they are there.

This is the first look at the *union*: issues in one batch touch overlapping
code, and each subagent only ever reviewed its own slice.

### What the findings do

A **Spec** finding that a requirement was not met holds everything: leave the
commits local, close nothing, file the report, and say plainly in the summary
that nothing was pushed and why. That claim is exactly the one under which a
commit must not land saying `Closes #NN`.

Anything else — **Standards** findings, smells, suggestions — is follow-up
work, not a reason to withhold a batch of green code. Push, then file them.

File findings as one issue:

```
gh label create needs-triage --description "Maintainer needs to evaluate this issue" --color FBCA04 2>/dev/null || true
gh issue create --label needs-triage --title "..." --body "..."
```

The label creation is idempotent because `needs-triage` is named in
`docs/agents/triage-labels.md` but has never actually been created in the
repo.

### Push and close

```
git push
```

Rejected because the remote moved during the run: `git pull --rebase`, re-run
`./scripts/check.sh`, push again. If the rebase conflicts, stop and report —
resolving a conflict is not an unattended act.

Then `gh issue close NN --comment "..."` naming the commits, for each issue
that landed.

## Report

Close with a summary that stands on its own in the morning: what landed and as
which commits, what failed and what its issue now says, what was skipped and
why, whether the push happened, and the findings issue's number.
