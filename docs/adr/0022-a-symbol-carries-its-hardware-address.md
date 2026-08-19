# A symbol carries its hardware address

A turnout and a slip carry `addr`, a string the user types, naming whatever the
hardware answers to. A block already carried the same thing per end as
`sensors`. A route is set by commanding each point by its address and the
position it needs, and the position is then assumed to have been taken.

This supersedes [ADR-0017](0017-turnout-position-is-inferred-by-the-panel.md),
which inferred turnout positions in the panel because nothing addressed a
turnout. Something does now, so the inference goes and the panel reads the
command instead.

`addr` is a plain string and nothing checks it. A DCC accessory number is a
string that happens to be digits. What address a physical point answers to is
knowledge the drawing cannot hold and the editor cannot verify. The only check
is that a motorised symbol has some address, since a drawing without one
derives but cannot be driven.

## One motor, two positions

Every motorised kind has one motor. A turnout lies straight or diverging; a
slip lies straight or curved, both roads together. Derivation already assumes
no more than this: the library declares nothing concurrent through a crossing
or a slip, because every route through one takes the shared frog, so two ways
never run through a slip at once. One address with two positions costs the
concurrency model nothing.

A turnout's legs are already named for its positions. A slip's are not, so
`LIBRARY` gains a leg-to-position table beside the transits it declares,
generated into the editor's TypeScript with the rest:

| Kind | straight | curved |
| --- | --- | --- |
| `turnout` | `straight` | `diverging` |
| `single_slip` | `a`, `b` | `slip` |
| `double_slip` | `a`, `b` | `slip_1`, `slip_2` |

Fixed crossings have no motor and take no address.

## Setting the route is the dispatcher's

The dispatcher assigns a route and is responsible that it is free and correctly
set up, turnouts and signal states included. So `align` is the dispatcher's
command rather than the driver's. It names a connection and a transit, and
carries the points that transit needs as address-and-position pairs. A
`move_granted` is then the green signal: the driver sees it and publishes
`cross`, nothing else. Today the driver is a stateless translator publishing
both (`src/tc49/driver/driver.py`).

The dispatcher knows an `addr` because the drawing's yaml holds it. How it
reaches the dispatcher is not settled here, being plumbing rather than
contract, and the overall account of how the railroad runs is being written
separately.

`addr` does not enter the layout document.
[LAYOUT.md](../store/LAYOUT.md#layout-schema)'s "there are no turnouts in the
layout" stands and derivation still drops every hardware id. The
transit-to-turnout-positions table [SYSTEM.md](../SYSTEM.md#layout-interface)
called private hardware configuration is now built from the drawing: a
transit's way is a list of symbol-and-leg pairs, the leg gives the position and
the symbol gives the address. An adapter throws what it is told and keeps no
table.

Moving the publisher has two consequences. Topics are publisher-first
([SYSTEM.md](../SYSTEM.md#event-inventory)), so `tc49/drive/align` becomes
`tc49/dispatch/align`. And the layout interface, which subscribed to the one
prefix `tc49/drive/+`, needs `tc49/dispatch/align` beside it. That is an
individual topic rather than a prefix, which SYSTEM.md calls a design smell and
which is accepted here as the price of putting route setup where the
responsibility for it sits.

The alternative was to leave publication with the driver and read "the
dispatcher is responsible" as being about safety rather than about who writes.
It changes no code and no topic, and it leaves route setup in the component
named for locomotives.

What is given up is what ADR-0017 gave up: commanded position is not measured
position, so a point that fails to throw looks correct. Reported position
arrives additively the day hardware reports it. The owner's turnouts do not.
