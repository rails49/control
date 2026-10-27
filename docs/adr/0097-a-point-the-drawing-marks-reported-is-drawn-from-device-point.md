# A point the drawing marks reported is drawn from `device/point`

Part of [#1103](https://github.com/rails49/control/issues/1103). Supersedes
the `device/point` clause of decision 7 of
[ADR-0063](0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md),
and the alternative it did not take of publishing a `device/point` for a
turnout without feedback. Supersedes, for `device/point` only, the sentence of
[ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)
that a translator publishes observed state only when the hardware reports it.

ADR-0063 allowed `device/point` only for a position the hardware measured. It
gave two reasons for not publishing one where nothing measures it. A fake
could only have been built from `wanted/point`, which is already on the bus.
And it would hide which turnouts have feedback on a railroad where some do and
some do not.

The first reason no longer holds. Gotthard's dccex script keeps the WX-310
double crossover's two diagonals, points 104 and 105, from both being thrown:
throwing one sends the station a close for the other. After 105 and then 104
are thrown, the track is right, but `wanted/point/105` still says thrown, and
the Run view, which draws `wanted/point` only, shows both diagonals thrown.
Only the translator knows the position the station was put in.

## Decision

1. The drawing carries a per-point flag, off by default, set in the editor
   next to the address
   ([ADR-0022](0022-a-symbol-carries-its-hardware-address.md)). It says the
   point's position is reported on `device/point`.
2. For a flagged point, a translator publishes `device/point` with the
   position the hardware measured, or, where it measures none, the position
   the translator last put the hardware in, whether from `wanted/point` or
   from its own logic, such as a dccex script.
3. For an unflagged point, `device/point` stays as before: published only
   where the hardware measures a position.
4. The Run view draws a flagged point from `device/point` and shows when the
   report is missing or differs from `wanted/point`. It draws an unflagged
   point from `wanted/point`, as before.
5. `layout` and the dispatcher do not read `device/point`. It is for a person
   to read.

## Alternatives not taken

**The drawing states that the two diagonals exclude each other**, and the
dispatcher adds a close of the other diagonal to every `align` that throws
one. `wanted/point` would then match the track and `device/point` would not
change. Not taken: the constraint follows from how the crossover is wired,
and the station's script already enforces it, so a second copy in the drawing
would be one more place that has to agree with the wiring.

**Leave `device/point` as it is and let the Run view show the wrong
position.** A person reading the Run view sees two thrown diagonals where the
track has one, and cannot tell this from a fault.

## Consequences

The Run view no longer tells a measured position from one a translator set.
Both are drawn from `device/point` for a flagged point. Which a point has is
in the translator's configuration, such as its script, and not on the bus.

A flagged point that nothing reports shows as missing. That is how a person
learns the flag is set on a point no translator reports.

`device/point` carries the same payload as before. BUS.md's device vocabulary
and the `device/point` passage in `src/tc49/lib/inventory.py` change with the
issue that implements the flag.
