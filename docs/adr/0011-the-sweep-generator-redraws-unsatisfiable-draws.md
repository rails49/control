# The sweep generator redraws unsatisfiable draws

The workload generator of [BENCHMARKS.md](../bench/BENCHMARKS.md#the-generator) could
draw a first wave no dispatcher can start: a head-on swap, where each train's
arrival blocks are held by trains that are themselves stuck. Every such block
is a permanent obstacle, `safe()` correctly refuses every launch, and the run
quiesces `stalled` at tick 0 with station tracks sitting empty. 24 of the
grid's 120 workloads drew one, all at `|dest| ∈ {1, 2}`, so those columns
measured the generator's draw rather than the dispatcher (#36).

**Decision: the generator redraws until every train's first request can
eventually launch.** A train can launch once one of its arrival blocks is
free, and a block frees once its occupant launches; the fixed point of that
rule must cover every train. While it does not, each stuck first request is
redrawn, end first then arrival ends, from the same seeded RNG after the main
draw.

Two alternatives were considered:

- **Report drain rate as a first-class finding instead.** Rejected: a workload
  that is unsatisfiable as written measures the generator, not the value of
  constraining arrival ends.
- **Stagger arrivals.** Rejected: contradicts the batch-arrivals decision,
  which is what makes makespan drain time and contention maximal.

## Measured effect

Re-running the sweep, runs stalled before anything moved at `|dest| ∈ {1, 2}`
drop from 28 to 0; drain is otherwise unchanged (390 → 389 stalled of 560).
So most of the grid's stalls were never head-on swaps. They happen after
trains have moved, typically a finished train parked across a route, and they
stay in the output as findings: the measured cost of constraining arrival
ends under contention, which is what the `|dest|` axis exists to price. The
`|dest| = 6` columns are untouched; their tick-0 stalls at `k < 6` are the
lexicographic bias BENCHMARKS.md already tells the reader to expect.

## Consequences

- **The axes hold.** Trains, workings per train, `|dest|`, seeds are all
  unchanged; a redraw replaces a request, never drops one.
- **Determinism holds.** Redraws consume the same seeded RNG in a fixed
  order, so a `(layout, trains, workings, |dest|, seed)` tuple still names
  one exact workload, and a draw that needs no redraw is byte-identical to
  the pre-redraw generator's.
- **Only first requests are checked.** Where a later working departs from is
  the dispatcher's choice, so its stalls are dispatch findings rather than
  draws to reject.
- **The trains axis ends at five because no satisfiable draw exists at six.**
  At six every station track is occupied and the fixed point is empty for
  every draw; at five a free track always exists and a satisfiable redraw is
  reachable. The former rationale ("a free track for the first launch") was
  false at `|dest| < 6`, where no pending request need name the free track.
- **`|dest| = 6` never redraws.** Its arrival set is every track of the other
  station, forced, and a station can only fill if the other has a free track.
