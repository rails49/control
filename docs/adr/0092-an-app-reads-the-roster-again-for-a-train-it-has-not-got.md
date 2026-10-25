# An app reads the roster again for a train it has not got, and a refused placement says why

Part of [#1015](https://github.com/rails49/control/issues/1015). Supersedes
[ADR-0091](0091-an-app-reads-the-roster-again-for-a-train-it-has-not-got.md),
from [#1008](https://github.com/rails49/control/issues/1008),
[#1009](https://github.com/rails49/control/issues/1009),
[#1010](https://github.com/rails49/control/issues/1010) and
[#1011](https://github.com/rails49/control/issues/1011).

The dispatcher and `layout` read the roster when a railroad is built. A
roster's Save names the railroad again only when it changed a length
([ADR-0071](0071-a-rebuild-under-the-same-name-keeps-the-placements.md),
decision 6), and `layout` builds only with power off. So a train made,
renamed or filled in the stock view after the last build is unknown to both
apps. The dispatcher dropped a placement of such a train with no answer
(`dispatch.py`, `_place`). On 2026-10-24 a train made in the stock view could
not be dragged onto any block until the railroad was named again with power
off.

On the layout, a person makes up a train in the stock view, sets the
locomotive on the track and drags the train onto its block. A placement is
accepted at any power
([ADR-0080](0080-the-waiting-requests-are-a-list-a-person-orders.md)), and a
new train is no different.

Until now `layout` read the roster again only for a take. In `automatic`
`layout` drives a train no throttle holds, and nothing sends a take, so a new
train placed and granted a route was never told a speed and its granted
blocks stayed held.

## Decision

1. **The dispatcher reads the roster again for a placement naming a train
   it has not got**, then judges the placement as before. The read adds the
   trains it lacks. A train it already has keeps the entry it was built
   with until the next build. The read is one attempt with no retry, so the
   bus loop never waits on the store; a store that does not answer leaves
   the train unknown.
2. **`layout` does the same for a placement the dispatcher accepted
   (`train_placed`) or a take naming a train it has not got**, so the train
   it places can also be driven: its cars, their addresses and their
   functions come from that read. The accept is the first `layout` hears of
   a new train, so the read happens before any move. A take reads again for
   a train placed while the store did not answer. A `move` never reads.
3. **A placement the dispatcher does not accept is answered** on
   `tc49/dispatch/placement_refused`, naming the train, the block and why:
   `unknown_train` (the store's roster lacks it too), `unknown_block`,
   `not_free` or `no_fit`. The run view says it. The answer names what the
   gesture named, so it needs no id
   ([ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

## Consequences

- A train made in the stock view can be placed and driven at any power,
  with no build.
- A change to a train the apps already have still waits for a build, as
  ADR-0071 says: its cars, its length, and a rename, which to the apps is a
  new train beside the old name. The old name stays known to them, off the
  layout, until the next build.
- Every open page sees a refusal, not only the one that made the drag.
- A placement of a name the store lacks costs one store read each time.

## Considered

- **Every roster Save names the railroad again.** `layout` builds only with
  power off, so a train made during a run still could not be placed.
- **The Save announces the roster on the bus and the apps read it again.**
  It covers changes to trains the apps have, but needs a topic per app and a
  rule for a placed train whose length changes during a run.
- **`layout` reads on a `move` naming a train it lacks.** The read would sit
  on the move path, and a store that does not answer would delay the train's
  start.
