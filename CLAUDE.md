# Control Model Railroad Trains

Software for scheduling, dispatching, and driving trains on a model railroad. See
[README.md](README.md) for the doc map; the research core is deadlock-free,
high-throughput dispatch ([docs/dispatcher/DISPATCH.md](docs/dispatcher/DISPATCH.md)).

[docs/GOALS.md](docs/GOALS.md) is the **end state**: the three functions —
scheduling, dispatching, driving — and how they meet. Most of the repo is a
first slice of it ([docs/MILESTONE-1.md](docs/MILESTONE-1.md)), so read GOALS.md
before any design change and say which of the two a change belongs to. Where a
doc and GOALS.md disagree, GOALS.md is right and the doc is a bug.

**The physical railroad decides.** Before designing anything, say how it
behaves on the actual layout. Consider the simulator only once that has an
answer, and where the two pull apart the physical railroad wins even at cost to
the simulator. Simulation stays behind the layout interface, in the `simulator`
app, never a field, a topic or a branch in any other app
([ADR-0030](docs/adr/0030-the-physical-railroad-is-the-normative-binding.md)).

## Apps

Apps import `tc49.lib` and themselves, never each other;
`tests/system/test_app_boundaries.py` enforces it. `desired_speed`,
`desired_position`, `desired_aspect` and `desired_function` in
`lib/payload.py` have no caller in `src/tc49`: the `dccex` translator reads
them through the package (#587). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Landing work

History is linear, and `main` only moves by PR with the `ci` check green — a
ruleset with no bypass, so this applies to everyone. Open an issue, commit on
a branch in reviewable steps referencing it, then
`git push -u origin <branch> && gh pr create --fill && gh pr merge --auto --rebase`;
close the issue once it lands. Rebase merge keeps the history linear. Keep
mechanical moves in their own commit so renames stay legible in the diff.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `rails49/control`, driven by the `gh` CLI.
Every issue is **implementation** (one component, title `<component>: …`) or
**communication** (one contract element, title `bus: <topic> …` or
`rest: <path> …`). See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

What `ready-for-agent` asserts, and why an issue does not carry it: `docs/agents/ready-for-agent.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root plus `docs/adr/`. See `docs/agents/domain.md`.

What each doc holds, and that an accepted ADR does not change: the
organisation's
[ADR-0017](https://github.com/rails49/.github/blob/main/docs/adr/0017-each-fact-has-one-owner-and-an-accepted-adr-does-not-change.md).

### Batch implementation

`/implement-loop` lands `ready-for-agent` issues unattended: one cold agent per
issue in a Docker sandbox, `scripts/check.sh` run by the host between them, and
the batch landing as one PR that `ci` must pass. It is a user skill rather than
a repo one — `~/.claude/skills/implement-loop/SKILL.md` — and derives the repo
and the gate from wherever it is run.
