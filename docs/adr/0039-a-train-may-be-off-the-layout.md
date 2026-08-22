# A train may be off the layout

A train is **known** by being in its railroad's roster and **placed** by being
in the dispatcher's `block_of`. The two are separate, and a train that is known
and placed nowhere is an ordinary state rather than a fault: it is off the
layout. Putting one on the track and taking it off are the same gesture in two
directions ([#170](https://github.com/rails49/control/issues/170)).

This is what the railroad does. Initially there is only track; locomotives come
out of a box, go onto the layout, and go back into the box. It is also what a
railroad at rest in the store has to be able to say once a run is built from a
drawing and a roster rather than from a scenario that names where every train
starts ([ADR-0038](0038-the-ui-is-one-app-with-views-of-one-railroad.md)).

## Absence, not a sentinel

`State.block_of` is `dict[str, str]`. Off the layout is **absence from it**. No
block name means nowhere, no facing has to spell nowhere, and nothing acquires a
second meaning.

That is about what the dispatcher *holds*. The **gesture** that asks for it
carries `block: null`, and that is not the sentinel this rules out: a gesture
has to name a destination, and nowhere is one of the destinations. It is also
the safer of the two readings on an inbound topic, where nothing is trusted
(`lib/payload.py`): an omitted key cannot be told from a frame that lost one,
where an explicit `null` a page wrote is a positive statement. So the key's
presence is load-bearing — a missing `block` fails the read, an explicit
`null` succeeds.

ADR-0037's issue ([#152](https://github.com/rails49/control/issues/152)) parked
this and quoted
four costs. Re-priced against the code, they come to less than the quote, which
was fair for the restored run it was written about — where every train is
already placed — and not for an operator holding a locomotive.

- **Two call sites** index `block_of` unconditionally, both in the dispatcher's
  launch path: where a request's expected origin is read, and where a working's
  launch origin and departure end are settled. Both already return `None` for
  "not a question that can be answered yet", so an unplaced train is a second
  reason for an answer that already exists.
- **The lock table iterates** `block_of` to collect idle trains, so an absent
  train is simply not idle. No change.
- **The allocation topic publishes** `dict(block_of)`, so an unplaced train is
  simply not in it, and every view that renders placement from it draws nothing.
  No change.
- **One rejection reason**, for a request naming a known but unplaced train.
  `lib/rejection.py` is the single set both sides answer to, and its generator
  makes a reason the browser cannot word a compile error rather than a raw token
  on screen ([#126](https://github.com/rails49/control/issues/126)).

The fifth objection — that a view has nowhere to draw such a train — is answered
by the **roster**, the pane listing what the railroad owns. It draws ownership
and not placement, so a train standing nowhere still has a row. That pane is
the feature; the domain change is what it needs.

## Facing is placement's, and only placement's

An unplaced train has no facing.
[ADR-0019](0019-facing-is-scheduler-state.md) defines facing as the end of *its
block* a parked train would depart through, so with no block there is no facing
to hold, and the scheduler drops it on removal and sets it on placement — the
end letter carried across, arbitrarily, because the layout is topological and
there is nothing better to derive from. Reversal at rest corrects it, which is
the gesture that already exists.

The dispatcher stays clear of facing throughout, as ADR-0019 requires. It reads
the placement gesture, because whether a block is free is knowledge only it has;
the scheduler follows the past-tense event, not the gesture. One payload read by
two apps would make them agree on every precondition, and the picture would
split exactly where a person is working.

## Placing and removing are one gesture

The gesture names a train and where it is; off the layout is one of the places
it can be. Both directions take the same preconditions — the run held (ADR-0037,
landing with #152), the train known, no request in flight — and removal
additionally releases what the train held.

Requiring the run **held** is not caution about the browser. A placement moves a
train's lock; doing that while the dispatcher is granting against the picture it
had would invalidate locks it has already granted on. The hold exists precisely
so a person can say where things are.

What decides which gesture a drag is, is **where the drag began** — never the
run's state. A drag from a train's row in the roster places it; a drag from a
train's marker on the canvas asks for a request. Deciding by the run state
instead would make one motion mean two things depending on a word in the band,
and would cost queuing a request while held, which ADR-0037 deliberately keeps
working for a timetable.

## Consequences

**A run may come up with an empty layout.** That is the cold start once a
scenario no longer places trains: nothing on the rails, every train known and
off the layout, the run held, and nothing to do but place them and press GO.

**A roster is a thing the store serves.** Trains are owned by the railroad they
run on, so the store's unit grows from a drawing to a railroad. What a train
carries beyond a name and a length — cars, type, addresses, priority, and
trains that split and merge during operation — is a separate design, and this
decision takes none of it.

**Removal is not deletion.** A train taken off the layout is still on its
railroad's roster and can be placed again. Adding a train to a railroad and
taking one off it are different acts, and only the second is decided here.
