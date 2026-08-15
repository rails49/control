# The pending scan ages by refusal count

The pending queue was scanned strictly oldest-first by admission order
(`Request.seq`). That sounds fair but is not: the oldest request keeps being
*tried* and *refused* while younger requests with clear routes launch past
it, and a freed resource goes to whichever eligible request has the earliest
admission — even one that will park on it for good. After congestion-aware
route costing (#33) the cost was measurable twice over: max per-request
latency sat near twice the mean across the sweep (median ratio 1.73, worst
2.01), and `gotthard/saturation` widened to `|dest| = 6` wedged at 11 of 15
workings because the last airolo slots went to older trains finishing their
chains there while younger through-traffic starved. No candidate ordering
can prevent that — for the older request the free slot always sorts first —
so it is queue order, not route choice (#34).

**Decision: the scan orders by `(-refusals, seq)` — most-refused first,
admission order among equals.** A request's refusal count increments each
time its launch is refused; it is dispatcher state, never wall-clock, so the
order stays a deterministic function of the run and traces remain
byte-identical. A train's chained workings keep their order for free: an
untried later working has no refusals and a later seq. Aging only reorders
which *safe* launch is tried first — the safety argument is untouched, and
the Hypothesis safety invariant (property 1) is the check.

Two alternatives from #34 were considered:

- **Resource reservation** — the starved request claims its next block
  against younger launches. Rejected for now: it is the only version that
  interacts with `safe()` (a reservation is not a lock and must not enter
  the safety check as one), and the measured residue does not justify that
  care yet.
- **Do nothing, bound it by measurement.** Rejected by the numbers: costing
  (#33) did not shrink the latency gap, and the widened-saturation wedge
  shows starvation can be a permanent stall, not just latency.

## Measured effect

Against the post-#33 sweep: drained runs rise 330 → 364 of 560, with
`|dest| = 2` up 9 → 16 at both live `k` and `|dest| = 6` at 79 of 80 for
`k ∈ {1, 2, 4}`. On the 321 runs drained both before and after, max latency
and makespan fall on 153 and rise on 31; the max/mean latency ratio's median
moves 1.73 → 1.68. On committed `gotthard/saturation`, `Incremental` improves
from makespan 20, mean latency 11.2, max 20 to 18 / 10.0 / 18; `FullRoute` is
unchanged. The widened `|dest| = 6` workload drains fully at `k = 2`.

## Consequences

- **Not a liveness guarantee.** Aging reorders a greedy scan; on 9 sweep
  runs (all five-train `|dest| = 6`) the new trajectory ends with a finished
  train parked across a route and the run stalls at 13 of 15 where it drained
  before. That stall class predates aging and stays a priced finding of the
  sweep; removing it needs reservations, deliberately not taken.
- **Starvation is bounded in practice, not prevented in principle.** Max
  per-request latency remains the detector.
- **The ordering key stays a policy point.** It chooses which safe launch is
  tried first and can change again without touching the safety core.
