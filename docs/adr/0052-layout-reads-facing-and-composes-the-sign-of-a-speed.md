# `layout` reads facing, and composes the sign of a speed

Resolves [#292](https://github.com/rails49/control/issues/292) and closes the
one thing
[ADR-0045](0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)
left open: `layout` needs a train's **facing** to turn a `move` into a speed on
a decoder, and had no route to it. Facing is scheduler state
([ADR-0019](0019-facing-is-scheduler-state.md)) and `train_placed` carries a
train and a block, so the question was where the layout interface gets it.

## `layout` subscribes to `tc49/schedule/state/facing`

The retained state topic the scheduler already publishes, read like any other
payload and never trusted (SYSTEM.md, rule 4). It is the only topic the
interface reads that is neither a command nor a device row.

The alternative ADR-0045 named was for `layout` to keep its own facing, seeded
at placement and carried forward by every `move` it executed, routes being
strict pass-throughs. That is rejected: it is a **second copy of a fact one
component already holds**, and the two would drift the first time a person
turned a train round at rest — the one change routes do not account for
(CONTEXT.md, **Facing**) — or the first time a hand moved a train and the
placement said nothing about which way it now points.

Reading a scheduler topic from the layout interface is not the layering
inversion it looks like. Facing is not the scheduler's private working state:
it is on a state topic precisely because the panel and every other view read it
([ADR-0036](0036-the-scheduler-is-an-app-the-panel-is-a-view.md),
[ADR-0032](0032-a-joining-client-is-served-the-runs-retained-state.md)), and
apps meet over the bus rather than through each other. Being retained is what
makes the read safe: the last value is there with the scheduler down, so the
railroad does not stop moving because the app that names facing is restarting.

**The scheduler is unchanged**, and nothing else reads the topic for this
purpose. It stays the single writer of facing.

## The sign is composed here and nowhere else

A `move` carries a magnitude, unsigned
([#283](https://github.com/rails49/control/issues/283)). Two facts give it a
sign, and both are this side of the boundary:

1. **Whether the move leaves the end the train faces.** The move's departure
   end is the end of the origin block the transit crosses. Equal to the end the
   train's nose points at is nose-first; different is **propelled**, an
   ordinary movement.
2. **Which way round each car is coupled** — its `orientation` within the
   train (ADR-0045). This is what lets a locomotive at each end of a train run
   opposite, and it is why the sign is per car and not per train.

Positive when the move is nose-first and the car is `forward`, or propelled and
`reverse`; negative otherwise.

Nothing above the interface composes any part of this, and no address ever
reaches a command ([#199](https://github.com/rails49/control/issues/199)). The
turning of a train into the decoders that answer for it is the interface's, and
it is what `layout` reads the **roster** for — as ADR-0045 said it would.

## A missing facing drops the move

A `move` for a train with wheels to turn and a facing `layout` has not seen is
**dropped**: none published for it, one this build cannot spell
([#241](https://github.com/rails49/control/issues/241)), or one naming a block
other than the one the train is departing. Guessing is a locomotive driven the
wrong way down the track, and the interface answers nothing, so a drop is what
a failed read is worth (ADR-0034). Nothing holds the command waiting for a
facing: a facing arriving later does not retroactively run the train.

A train whose cars carry **no address** needs no facing and is not refused for
want of one. It gets its `align`, its near-end check and its crossing record,
and there is nothing to publish — the simulator's trains are like this, and so
is any stock a hand moves.

## Rejected

**`layout` keeps its own facing from placements and moves.** ADR-0045's other
option, above: a second copy of one fact, drifting on the first reversal at
rest.

**Facing on the `move`.** It would put a fact the driver does not hold on a
command the driver publishes, and make every publisher of a `move` carry the
scheduler's state. The topic names the component that responds to it, not the
one that sends it.

**A signed speed on the `move`.** The same thing one step worse: it would move
the composition above the boundary, where neither the orientation of a car nor
the geometry of the transit is known.
