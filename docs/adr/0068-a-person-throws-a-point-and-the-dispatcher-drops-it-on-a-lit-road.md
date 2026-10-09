# A person throws a point, and the dispatcher drops it on a lit road

The contract is [#662](https://github.com/rails49/control/issues/662) and
[#663](https://github.com/rails49/control/issues/663); the work is
[#664](https://github.com/rails49/control/issues/664),
[#665](https://github.com/rails49/control/issues/665) and
[#666](https://github.com/rails49/control/issues/666).

[PANEL.md](../ui/PANEL.md) ruled out throwing a turnout by hand: a second
party judging what is safe would sit beside the dispatcher. This reverses that
for one purpose, testing: checking that an address moves the turnout it is
wired to, after wiring or after a track plan is rebuilt, and throwing again a
point that stuck. Shunting a manual train off its route is not a purpose here;
trains still move only on granted routes ([GOALS.md](../GOALS.md)).

## Decision

1. **Clicking a point in the panel asks for its other position.** A point
   whose position is unknown asks for `thrown`. A point with no address
   offers no click. Slips behave as turnouts do, both being points.
2. **The panel asks the dispatcher.** `tc49/dispatch/point_wanted`,
   browser-writable, `{addr, position}`.
3. **The dispatcher drops it on a lit road.** If no point on the loaded
   railroad wears that address, or any point wearing it lies on the way of a
   transit that is locked or committed, the request is dropped with no
   reply. Otherwise the dispatcher publishes `tc49/layout/throw`,
   `{addr, position}`.
4. **`layout` writes `wanted/point`** on `throw` as it does on `align`, and
   checks nothing. Whatever drives the point acts on that row.
5. **The panel reads point positions from `wanted/point`**, not from `align`.
   The row is retained, so a panel opened mid-session knows every position
   commanded since the broker came up.

## Why the dispatcher decides

It already holds the locks and the committed routes, and handles requests one
at a time. A click and a route commit therefore cannot overlap: either the
throw is published before the commit, and the commit's own `align` sets the
point again before the train moves, or the commit comes first and the throw is
dropped. The panel's picture of the lit roads can be a moment old, so a panel
that decided would let a throw through under a route committed a moment
before. The dispatcher stays the one party that judges safety, which is what
PANEL.md's objection protected.

## Why committed counts as well as locked

On the layout only a locked transit is dangerous: its `align` has been sent
and a train may be on it. A point on a committed transit is safe to throw, but
the transit's `align` would set it back before the train arrives, undoing the
throw without telling anyone. Refusing both gives one rule that matches the
panel: a point on a road the panel lights does not throw.

## Alternatives not taken

- **The panel checks and publishes `align` itself.** `align` is browser-sendable
  today. This puts a second judge of safety beside the dispatcher, and the
  panel's picture can be out of date.
- **The dispatcher publishes `align` for the throw.** `align` names a
  connection and a transit, and a throw by hand has neither.
- **`layout` checks.** It holds no locks and no routes.

## Consequences

- The inventory gains two rows: `tc49/dispatch/point_wanted` (event,
  browser-writable) and `tc49/layout/throw` (command, the dispatcher's).
- An address no point wears is dropped. Points and signals share the
  accessory addresses on the hardware, so a throw sent to a signal's address
  would change its aspect.
- A dropped request leaves no trace beyond the request itself. The panel
  shows no click cursor on a lit point, so the drop is visible before the
  click.
- A throw while the run is held or the power is off is accepted. With power
  off the row is stored, and the point moves when power returns
  ([ADR-0054](0054-the-railroad-comes-up-at-rest-and-points-replay.md)).
- The dispatcher holds no point positions after a throw. Every `align` sends
  all the points its transit needs, so a thrown point is set right by the
  next route through it.
- The panel still shows the commanded position, not a measured one
  ([ADR-0017](0017-turnout-position-is-inferred-by-the-panel.md)).
- Under the simulator no point carries an address, so nothing is offered,
  and a request sent anyway is dropped.
