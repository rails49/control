# A reported point lies where `device/point` says, and a train waits for it

Part of [#1103](https://github.com/rails49/control/issues/1103). Supersedes
the `device/point` clause of decision 7 of
[ADR-0063](0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md),
and the alternative it did not take of publishing a `device/point` for a
turnout without feedback. Supersedes, for `device/point` only, the sentence of
[ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)
that a translator publishes observed state only when the hardware reports it.

`wanted/point` is what `layout` asked for, and every app takes it for where
the point lies. A point that fails to throw looks thrown, and a train is sent
over it ([ADR-0022](0022-a-symbol-carries-its-hardware-address.md)). Some
points can say where they lie: a turnout with feedback, or a point a
translator moves by logic of its own, which only that translator knows about.

ADR-0063 allowed `device/point` only for a measured position, since a
position nothing measured could only have been copied from `wanted/point`. A
translator that moves a point by its own logic knows a position
`wanted/point` does not have.

## Decision

1. The drawing lists the addresses whose position is reported, as `reported`
   beside `symbols`. The editor sets it next to the address of any symbol
   that has the address, and the review refuses an address no symbol has.
2. For a reported address, a translator publishes `device/point` with the
   position the hardware measured, or, where it measures none, the position
   the translator last put the hardware in, whether from `wanted/point` or
   from its own logic.
3. For any other address, `device/point` is published only where the
   hardware measures a position, as before, and `wanted/point` stands for
   where the point lies.
4. For a reported address, `device/point` is where the point lies, and
   `wanted/point` is only what was asked for.
5. Each point in `tc49/layout/align` says whether its address is reported.
6. `layout` lets a `move` across a transit through only once each reported
   point in the transit's `align` reports the position the `align` asked for.
   Until then the train does not depart, and the dispatcher's locks stay
   held.
7. From the moment `layout` lets the `move` through until the block the train
   left reads vacated, a reported point of that transit that reports another
   position stops the train, as `layout` stops one at an arrival. A throttle
   can drive it on, as it can drive any locomotive while the power is on
   ([ADR-0081](0081-a-throttle-drives-outside-a-grant-and-a-release-keeps-its-speed.md)).
8. The Run view draws a reported point from `device/point` and marks it when
   a train waits for it for more than two seconds, or when it stopped a train.
   It draws any other point from `wanted/point`, as before.
9. The dispatcher does not read `device/point`.

## Alternatives not taken

**The dispatcher waits for the report before it locks the route.** It cannot:
a point is thrown only once the route over it is locked, so the report it
would wait for comes after the lock.

**Draw the report and change nothing else.** A train would still depart over
a point that reports the wrong position.

**`layout` reads `reported` from the drawing.** `layout` holds no table of
points, and the `align` carries the points its transit needs
([ADR-0031](0031-the-layout-carries-the-points-a-transit-needs.md)), so it
carries this too.

## Consequences

A reported point that never reports, or reports the wrong position, holds
every train routed over it. The Run view's mark is how a person learns of it.

`layout` keeps, per transit it has let a train onto, the reported points of
its `align` until the block the train left reads vacated. That is state it
did not hold before.

A position a translator set is trusted as much as a measured one. The Run
view and `layout` cannot tell the two apart; which a point has is in the
translator's configuration and not on the bus.

BUS.md's device vocabulary and `tc49/layout/align`, the `device/point`
passage in `src/tc49/lib/inventory.py`, and `layout`'s docstrings change with
the issues that implement this. Decisions 6 and 7 are an invariant over the
bus, added to `src/tc49/lib/invariants.py`
([ADR-0096](0096-invariants-are-stated-over-what-the-bus-shows-and-checked-in-tests.md)).
