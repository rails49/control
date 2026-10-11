# A rebuild under the same name keeps the placements

*Amended by [ADR-0072](0072-the-railroad-is-loaded-from-a-settings-dialog-and-the-store-records-which.md) (#733): the editor has no Save As, so decision 5's "Save As names nothing" has nothing to apply to.*

The decision is [#707](https://github.com/rails49/control/issues/707). Amends
[ADR-0060](0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)
(a load is a cold start with no trains placed),
[ADR-0038](0038-the-ui-is-one-app-with-views-of-one-railroad.md) (trains on
the layout freeze the drawing) and
[ADR-0053](0053-backup-drives-git-and-does-not-own-it.md) as amended by
[#699](https://github.com/rails49/control/issues/699) (Restore is refused
while a train is placed).

Every rebuild dropped every placement. So Restore, the editor and the stock
view's length guard each asked a person to take every train off in control
first, and to drag each one back afterwards. On a large layout that is hours.

On the steel, with track power off, a restore or a saved edit changes the
drawing and not the track. Every train stands where it stood. A placement
whose block is still in the drawing, and still holds the train, is still true.

## Decision

1. **A rebuild under the same railroad name keeps the placements.** The
   dispatcher keeps its `allocation` row through the rebuild and places each
   train again with the checks any placement passes: the block exists and the
   train fits. It comes up held, as after a restart, and **Disputed** shows a
   train the detectors contradict. The scheduler keeps `facing`. The layout
   interface and the simulator carry their positions into the new build, less
   any train whose block the new drawing lacks.
2. **Loading a railroad under another name still starts with nothing
   placed.** A block's name in one railroad says nothing about the steel of
   another, and a person switching railroads is often rebuilding track.
3. **A train that does not fit comes off the layout**: its block is gone, or
   is now shorter than the train. The dispatcher lists it on
   `tc49/dispatch/state/unfit`, with its block and why. It leaves the list
   when it is placed again, and the next rebuild replaces the list.
4. **Restore needs track power off and the loaded railroad in the backup.**
   It is no longer refused while a train is placed.
5. **The editor and the length guard are read-only while track power is on
   or stopped**, not while a train is placed. With power off, saving the
   loaded railroad's drawing, or correcting a length, names the railroad
   again on `tc49/layout/railroad_wanted`, so every app builds what was
   written and keeps the placements that fit. Save As names nothing.
6. **ON is refused while the loaded railroad's drawing has unsaved edits.**
   STOP is never refused. A length correction is saved with the roster: while
   track power is on or stopped, the roster's Save is refused if its unsaved
   edits change a length, and a save that changed one names the railroad
   again.

ADR-0038 froze the drawing so the run view would never draw track the
dispatcher is not running. Power meets that: with power off nothing is granted
and nothing moves while the two differ, ON waits for the save, and the save
brings the apps up to date. The roster's Save waits for power off because a
length saved with power on could not be built: the layout answers
`railroad_wanted` only with power off.

## Consequences

- After a restore or an edit, a person puts back only the trains on the
  `unfit` list.
- A kept train keeps its facing. An edit that flipped its block needs the
  existing reversal.
- A restart of the layout interface or the simulator process still comes up
  with no positions. That is unchanged.
- After the box itself restarts, nothing is placed. The trains may have
  moved, and a swap between two occupied blocks is not something the
  detectors can see, so a person places them.
- The store enforces none of this; the UI does. A write while track power
  is on reaches no app until a build, and a build waits for power off. Two
  things can still show the edited drawing early: an app process that
  restarts reads it at startup, and a browser that reloads draws it. Both
  need a second writer working against a running layout, and a store is
  one person's ([ADR-0053](0053-backup-drives-git-and-does-not-own-it.md)).
  A check in the store's routes would also miss a file written into the
  store directly, as DecoderPro's profile is
  ([#700](https://github.com/rails49/control/issues/700)).
