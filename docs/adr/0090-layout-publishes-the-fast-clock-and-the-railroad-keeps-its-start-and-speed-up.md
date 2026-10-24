# `layout` publishes the fast clock, and the railroad keeps its start and speed-up

The work is [#987](https://github.com/rails49/control/issues/987),
[#988](https://github.com/rails49/control/issues/988),
[#989](https://github.com/rails49/control/issues/989),
[#990](https://github.com/rails49/control/issues/990) and
[#991](https://github.com/rails49/control/issues/991).
Supersedes "The fast clock needs no carrier" in
[ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md).
ADR-0044's rule that the fast clock never feeds dispatch or safety stands.

The band showed a session clock: how long this page had been joined, timed by
the browser. Nobody used it. The throttle's station clock showed the
browser's wall time. Both were placeholders for the railroad's fast clock,
which ADR-0047 left with no carrier: anything that wanted it was to work it
out from the wall clock, a start time and a speed-up.

Working it out on each page needs each page's wall clock to agree with the
moment the clock was set. A tablet 30 s off shows a fast clock 4 minutes off
at a speed-up of 8, and a box on the railroad's own network may have no time
source the tablets share.

## Decision

1. **`layout` publishes the fast clock once a real second** on
   `tc49/layout/state/clock`: the time of day and the speed-up. Every page
   draws what it is sent and reads no wall clock, as
   [ADR-0009](0009-layout-interface-owns-time.md) asks. The simulator, as the
   other binding, publishes the same row from its own run clock.
2. **A person sets the clock** with `tc49/layout/clock_wanted`, from any page:
   a time of day, a speed-up, or both. The clock takes the new time at once
   and runs at the new speed-up.
3. **The railroad keeps a start time and a speed-up** in a store document of
   its own, `layouts/<layout>.clock.yaml`, written by `layout` when a person
   sets the clock. Setting the time saves it as the start time. Copy carries
   the document and backup saves it, as they do the roster.
4. **Loading the railroad starts the clock at its start time.** A railroad
   with no clock document starts at the box's wall time of day, at a speed-up
   of 1.
5. **The clock is a time of day.** It wraps at midnight and has no date. It
   runs whatever track power and the run are doing.
6. **The band shows it as a small round face**, hour and minute hands, with
   `×8` beside it when the speed-up is not 1 and the time as its tooltip.
   Pressing it opens a dialog with the time and the speed-up. The throttle's
   station clock shows it too. With no railroad loaded or no broker
   answering, the band shows no clock and the throttle's face no hands.

## Consequences

- The session clock goes from the band, and BUS.md's "the fast clock has no
  carrier" goes with it.
- A railroad's documents are its drawing, roster, script and clock.
- The store is written only when a person sets the clock, so the backup has
  nothing new to save while the clock runs.

## Considered

- **Each page works the clock out from its own wall clock**, `layout`
  publishing only when it is set. One message per change instead of one a
  second, but every page is as wrong as its clock, times the speed-up.
- **Resume where the clock last stood.** `layout` would write the time to the
  store as it runs, and every write is a change for the backup to save.
- **Keep running while the box is off.** A railroad loaded the next morning
  would show whatever the night's hours times the speed-up came to.
- **A field on the drawing.** Setting the clock would be an edit: unsaved
  until saved, saved only with power off, and a rebuild after.
