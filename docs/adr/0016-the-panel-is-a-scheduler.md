# The panel is a scheduler

**Partly superseded by
[ADR-0036](0036-the-scheduler-is-an-app-the-panel-is-a-view.md).** The
conclusion below is reversed — the scheduler is an app and the panel is a view
that emits gestures — and the reasoning below is what reversed it. Exclusivity
keeps one writer per *component*, and a browser tab can be opened twice, so the
single-writer rule and the single minter both broke the moment a second tab
joined a session ([ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md)).
The `tc49/ui/request_wanted` alternative priced and refused below is the one
now bought, at that price. What stands is everything else: the dispatcher as
sole feasibility authority, one deterministic minter, and the refusal of manual
turnout throwing, which 0036 does not touch.

Clicking a train on the [panel](../ui/PANEL.md) and then one or more arrival ends publishes
`tc49/schedule/request_submitted`: the existing topic, in the existing
`schedule` role. The panel is therefore a scheduler, and a run uses the file
scheduler or the panel, never both.

This is what [SYSTEM.md](../SYSTEM.md#scheduler) already anticipates in
calling the milestone-1 scheduler "the honest template for a future scheduling
UI or freight generator: publish intents, let the dispatcher judge". The panel
needs no new authority. It submits, and the dispatcher answers with
`request_admitted` or `request_rejected`, so rejection feedback comes for free
and there remains exactly one feasibility authority.

Exclusivity is what keeps the contracts intact. Two independent publishers on
one topic would break the single-writer rule, which is what upgrades the
ordering promise to per-topic FIFO, and would give two minters of a request id
that is required to be deterministic in scenario order. Under exclusivity both
survive untouched. Scenario runs keep byte-identical replay; panel runs make no
such claim, which is correct, since a human clicking is not a reproducible
benchmark. Later the panel-scheduler can preload a scenario and also take
clicks, giving timetable-plus-ad-hoc while still being one writer.

Two alternatives were rejected.

**A new `tc49/ui/request_wanted` topic**, with the scheduler subscribing,
minting the id, and republishing. This preserves both rules and allows a
timetable and ad-hoc requests at once, but costs a topic, a role, and an inbound
path on a component that currently has none, to buy something exclusivity gives
later for free.

**Relaxing the single-writer rule with namespaced ids.** Cheapest in machinery
and worst in principle: rule 1 exists so ownership is checkable by inspecting a
topic name, and partitioning by writer is precisely what stops that working.

Manual turnout throwing, which RocRail offers, is not part of this. RocRail
allows it because it owns manual shunting, which this model excludes: trains
move only on granted routes, and reversal happens only between requests, at
rest. There is also nothing for such a command to address, since the app gives
turnouts no identity, and a panel deciding when a throw is safe would be a
second authority alongside the dispatcher, over a lock table it does not hold.
