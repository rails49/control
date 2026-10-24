# A throttle holds one train

Part of [#966](https://github.com/rails49/control/issues/966),
[#967](https://github.com/rails49/control/issues/967) and
[#968](https://github.com/rails49/control/issues/968). Visual reference:
[throttle-mockup.html](../ui/images/throttle-mockup.html).

A page had one throttle id. That throttle could hold several trains, and the
throttle view drew one column of controls per train, with a take column
beside them on a wide screen
([#853](https://github.com/rails49/control/issues/853),
[#855](https://github.com/rails49/control/issues/855)). On a phone the
columns stood one below the other.

A person drives with one thumb on a phone held upright. The controls for one
train fill that screen: the picture, the signal, the functions and a slider
as tall as the screen allows. A tablet has room for several such screens side
by side.

## Decision

1. **A throttle holds at most one train.** The throttle view shows a row of
   throttles. Each is a panel the size of a phone screen, with the same layout
   on every device. On a phone there is one; a wider view shows as many as fit.
2. **Each throttle has its own id.** The session mints one per panel and sends
   `throttle_alive` for each id that holds a train. A train held by the panel
   beside yours is held by another throttle.
3. **Taking a train another throttle holds asks first, then sends a release and
   a take.** `layout` keeps dropping a take of a held train. In `manual` the
   release stops the train before the new throttle has it.
4. **Picking another train releases the one held**, in the same order: release,
   then take.
5. **A resize releases nothing.** A panel holding a train that no longer fits
   wraps onto a further row. An empty one is dropped.
6. **Take back and Turn around leave the throttle.** Take back has no single
   owner once a page has several throttles. Turn around sets a train's facing,
   which only matters to whoever composes requests, and the run view has it.

## Consequences

- `Cab` says which id holds a train, not "here" or "elsewhere"; each panel
  compares the id with its own.
- Force release goes: confirming a take is the same release frame.
- A person can no longer hold two trains on one phone. They switch with the
  selector, which releases the first.

## Considered

- **One id per page, a column per train** (#853, #855). It shrinks every
  train's controls on a phone and needs a take column on a wide screen.
- **`layout` accepts a take of a held train.** It changes the bus contract, and
  any client could take a train from another in one frame.
- **Keep Turn around in the throttle.** The reverser already drives the train
  either way, and the signal shown follows the reverser. Facing changes nothing
  on the rails.
