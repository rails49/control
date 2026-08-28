# Reaching `ready-for-agent`

What the label asserts, and the reasons an open issue does not carry it.
Label strings are in [triage-labels.md](triage-labels.md); the `gh` commands
are in [issue-tracker.md](issue-tracker.md).

## What the label asserts

A cold agent, with no access to the author, can finish the issue and leave
`scripts/check.sh` green. That needs four things:

- every decision made, including names, payload shapes and contract changes;
- targets named by path, verified against a stated commit;
- acceptance criteria that can be checked rather than judged;
- out-of-scope stated, so neighbouring work is not swept in.

An issue can be correct, wanted and well written and still fail this. The
label is about whether it can be worked unattended, not whether it is good.

## The label is a snapshot, not a warranty

All four can hold and the issue can still be stale by the time it runs. The
label is checked when the issue is written; a word it names can be retired
afterwards, and nothing rewrites the body when that happens.

#177 retired **closet** from the glossary. #171, written before that landed
and still saying "closet" in its own third criterion, put the word back in
four places.
The agent was not careless — the body is what it was given, and following it is
the right thing for a cold agent to do.

So a stale body out-argues a fresh ruling unless something else carries the
ruling. `/batch-implement` does: it hands every issue that runs after a ruling
the ruling itself, and tells the agent that a stated ruling beats a word in its
own body (`~/.claude/skills/batch-implement/SKILL.md`). Triage may still rewrite
a stale body by hand, and should where it can; the handoff exists because that
will sometimes not have been done.

## An open blocker is not a reason to remove the label

`/batch-implement` reads `blocked_by` and sorts so a blocker runs first, so a
blocked issue may keep the label. Record the edge as a native GitHub
dependency (see [issue-tracker.md](issue-tracker.md#wayfinding-operations)).

Withholding the label instead loses information twice: the reason lives in a
comment that the next reader has to find, and nothing states what the issue is
waiting for. #155 removed its own label for this and put it back once the edge
existed.

## The reasons an issue is not ready

**It is a parent.** An epic carries the decisions and its children carry the
work, so it is never labelled and closes when they close. #166 and #123 are
both written this way.

**A decision is unmade.** The issue asks for a ruling the agent would have to
invent: what to call something, what a payload carries, what a contract
serves. An agent deciding unattended is the failure this label prevents, and a
ruling landed wrong costs more than the delay. #156 states this in the issue
itself; #170 deferred one payload shape and was ruled on before it was worked.

**It is parked.** A structural change is coming and the issue is written
against the structure that is about to move. Working it would be work against
a moving target, not wrong work. Parking needs a comment naming the re-entry
condition, and the label goes back when that condition is met.

Parking is recorded per issue but usually applies to part of one. An issue
whose other half is untouched by the coming change can be split or worked in
part, so say which half is parked. The 2026-08-21 parking of #155, #156, #157,
#163 and #165 covered five whole issues where four had a half that the change
could not reach.
