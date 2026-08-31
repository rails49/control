# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues in [rails49/control](https://github.com/rails49/control). Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

> **Note** `gh` may fail here with a TLS certificate error (`x509: OSStatus -26276`) when run inside the command sandbox. Retry the same command with the sandbox disabled.

## Issue scope: implementation or communication

Every issue is one of two kinds, declared in the title (#253). The components
are isolated on purpose — they meet only over the bus and the store's
contract — and an issue shaped any wider turns into a discussion of
everything at once.

- **Implementation** — work inside one component. Title `<component>: <what>`,
  e.g. `dispatcher: …`, `simulator: …`. The discussion stays inside that
  component; other components appear only as the contracts they expose
  (SYSTEM.md).
- **Communication** — one new or changed contract element: a bus topic or a
  REST route. Title `bus: <topic> — <what>` or `rest: <path> — <what>`. The
  body carries the draft contract element itself — topic, kind, publisher,
  full payload fields, and the consumers it obliges — so the issue is
  reviewable as the inventory entry it will become.

An issue that seems to need both is a communication issue: the contract
change is what makes it span components. Hardware protocols are
implementation detail of the translator apps and appear only in those apps'
implementation issues. No third kind and no new labels — the five triage
labels stay canonical, and a title prefix is greppable.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api --method POST repos/rails49/control/issues/<map>/sub_issues -F sub_issue_id=<child-db-id>`). Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/rails49/control/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/rails49/control/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate).
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.

### Live maps

- [Milestone 2 map: connect hardware and run trains](https://github.com/rails49/control/issues/193)
  — the way to `docs/MILESTONE-2.md`: a physical binding of the layout
  interface, a driver that turns an aspect into a speed, stock a real railroad
  has, a scheduler that runs trains unattended, and a person's throttle.

### Completed maps

- [System organization map](https://github.com/rails49/control/issues/13) — the way to `docs/SYSTEM.md`: component decomposition (asset store, scheduler, dispatcher, driver, layout interface) and the bus/CRUD contracts between them. Reached; the spec is `docs/SYSTEM.md` with ADRs 0008–0010.
- [Milestone 1 spec map](https://github.com/rails49/control/issues/1) — the way to a buildable spec for the simulator, dispatcher, and benchmark harness. Reached; the spec is `docs/`.
