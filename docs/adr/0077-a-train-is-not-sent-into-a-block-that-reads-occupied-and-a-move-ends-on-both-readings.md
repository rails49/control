# A train is not sent into a block that reads occupied, and a move ends on both readings

Resolves [#791](https://github.com/rails49/control/issues/791): the three paths
[ADR-0076](0076-a-broken-lock-table-holds-the-run.md) named, each of which
leaves a placed train without the lock on the block it stands in, or residue
without its lock.

- A train sent into a block that already reads occupied, a stuck detector or a
  cut of cars with GO pressed over the dispute. Its arrival repeats a level
  already held and is dropped, and the vacate behind ends the move with the
  train still recorded where it left.
- The same through a train's own residue: a train taken off where a detector
  still reads it, put down elsewhere, and routed back through that block.
- `block_vacated(X)` before `block_occupied(Y)`. The layout interface publishes
  a vacate when X's own detectors go clear, so a dead or dirty detector at Y's
  entry gives this order. So does a train shorter than the track between X's
  exit detector and Y's entry detector, and the layout has such trains: this
  order happens in normal running.

## Decision

1. **No move is granted into, and no lock is taken on, a block that reads
   occupied**, whoever holds it, a train's own residue included. `obstacle`
   refuses it `held`, with holder `""` where nobody holds it, and the train
   waits until the block reads clear. `FullRoute` asks the same of the block
   each move goes into.
2. **Route choice and `safe()` treat such a block as an idle train's block**
   where nobody holds it or it is residue: congestion counts it, the safety
   check counts it among the permanent obstacles, and an unsafe refusal names
   it.
3. **A clear reading on a block nobody holds is explained.** It does not hold
   the run, and it sweeps, so a train waiting on that block is reconsidered.
4. **A move ends when its origin reads clear and its arrival block reads
   occupied, in either order.** A vacate of the origin first releases nothing,
   grants nothing and does not hold the run: the origin and the transit stay
   locked. The arrival then records where the train is and ends the move as
   the vacate does in the usual order — release, completion or a cancelled
   request's retirement, then a sweep.
5. **A placement gives up the train's previous block only if the train holds
   it.**

The `grant_refused` contract, ADR-0048's hold on every other unexplained
reading, and ADR-0076's check are unchanged.

This amends [ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)'s
"there is no other order for it to arrive in": occupied then vacated is the
usual order, not the only one.

## Why

- A cut of cars in the block would be hit. A stuck detector takes the block
  out of use until it is fixed, which is what
  [ADR-0050](0050-broken-hardware-is-reported-never-worked-around.md) asks of
  broken hardware.
- The layout's arrival stop fires only on an end whose reading changes, so a
  train sent into a block already reading occupied is not stopped there.
- A vacate first may leave the train standing on the connection's points, so
  the transit and the origin are not free until the train is seen ahead.
- Some trains on the layout are shorter than the gap between one block's exit
  detector and the next block's entry detector, so a vacate first happens in
  normal running. Holding the run on it would stop ordinary operation.

## Consequences

- GO over a disputed block is still allowed; the block waits until it reads
  clear.
- None of the three paths breaks a rule of the lock table, so the test of
  ADR-0076's check breaks the table by hand.
- A train whose arrival block never reads occupied — a dropped frame, a block
  with no detectors — stays drawn as crossing until a person places it.

## Considered

- **Record the arrival from the vacate behind.** It would place the train in
  a block nothing has seen it in, on the points or still short of the block.
- **Hold the run on a vacate first.** It stops ordinary running for every
  short train.
- **Release on a vacate first.** It frees the transit and the origin while
  the train may still stand on the connection's points.
