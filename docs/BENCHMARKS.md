# Benchmarks

What the benchmark harness runs and what it reports. The four metrics are
defined in [DISPATCH.md](DISPATCH.md#metrics), the trace they are computed from
in [ARCHITECTURE.md](ARCHITECTURE.md#event-trace), and the file formats in
[LAYOUT.md](LAYOUT.md).

The suite has **two roles over one layout library**. Hand-authored named
scenarios are the *story* — committed, quotable, with golden numbers in CI. A
seeded generator sweep is the *evidence* — density and route-around swept, the
research finding rather than a contract.

## Layouts

| Layout | Role |
| --- | --- |
| `gotthard` | headline benchmark — 14 blocks, two stations, three line sections between them |
| `crossover-yard` | fast smoke benchmark — 6 blocks |
| `facing-pair`, `single-track-meet` | property tests only |

`facing-pair` is deliberately **excluded** from the benchmark set: both locking
strategies serialise on it, so a makespan comparison there is a null result by
construction. Its job is deadlock hunting, not throughput.

Gotthard replaces the invented large layout this suite was originally going to
need. Using the owner's real railroad is what makes the numbers mean something,
and its three line sections are what give the `k` sweep anything to measure.

## Workloads

**Batch arrivals** — every request at tick 0. Makespan is then drain time,
density collapses to trains × workings with no arrival rate to tune, and
contention is maximal, which is exactly where `FullRoute` and `Incremental`
separate. Latency degenerates to completion time, but max latency still does
the starvation job [SAFETY.md](SAFETY.md) assigns it. Named scenarios stay free
to stagger `at:` for storytelling.

**Line workings** — generated requests run station to station,
`claro_{1,2,3} ↔ airolo_{1,2,3}`, destination track uniform, chained into a
connected walk per train: request *n+1* departs from wherever request *n* parked
the train. The departure end is a free choice, since ADR-0001 permits reversal
at rest between requests.

**The departure end is picked uniformly**, not "the end facing the chosen
route". A request departing Claro *west* has one line available and one
departing *east* has two, so a workload that always departs the same way
systematically under-uses the railroad — always east and the yellow line is
never touched; always west and `k` is inert.

**Sidings appear only as initial placements**, never as generated destinations,
so every *generated* request stays a long run that faces the line choice. A
uniform-over-all-blocks generator was rejected for the opposite reason: roughly
a third of its requests would be siding moves and most of the rest short hops,
diluting the one signal the sweep exists to find. A `--profile uniform`
robustness check remains available later at the cost of a second sweep.

Note what this does *not* mean. Gotthard's sidings are trailing dead ends
([LAYOUT.md](LAYOUT.md#the-encoded-railroads)), so a train parked in one blocks
nothing but a request destined to it — and no generated request is. Siding
stock is inert scenery for the sweep. The permanent obstacles that actually
bite are **idle trains on station tracks**: a working train before it launches,
or one that has finished its last working and now sits where somebody else is
headed.

**Sweep axes**: trains 2–5, 3 workings each, seeds 0–9, `k ∈ {1, 2}`,
locking ∈ {`FullRoute`, `Incremental`}.

Working trains start on station tracks, of which Gotthard has six. **The axis
stops at 5 for that reason**: at six, every station track holds an idle train,
every request's destination is therefore a permanent obstacle, `safe()` refuses
every launch, and the run quiesces `stalled` at tick 0 on every seed. That
point measures the stall detector, not throughput, so it is excluded rather
than swept. At five there is always a free track for the first launch, and each
completion frees another.

### The generator

Everything below is drawn from a single seeded RNG, in this order, so a
`(layout, trains, workings, seed)` tuple names one exact workload:

1. **Placement** — sample `trains` distinct station tracks from the six, one
   train each. Train lengths are fixed per train id so the fit check is
   deterministic; any length that fits every station track will do.
2. **Workings** — for each train in id order, chain `workings` requests. The
   first departs from its placement; each later one departs from where the
   previous parked it. The destination is uniform over the three tracks at the
   *other* station, and the departure end is uniform over `A`/`B`.
3. **Arrival** — every request at tick 0.

A generated request may be unroutable from the end drawn (a departure end that
fits no route to that destination); redraw the end, then the destination. Do
not silently drop the request — the workings-per-train count is a sweep axis
and must hold.

## The `k` axis

`k` caps the candidate routes a launch may try before giving up
([SAFETY.md](SAFETY.md#route-selection)). `k = 1` is a pure gate — wait for the
one route; `k = 2` is route-around — take the other line instead. That contrast
is the headline measurement.

**`k ∈ {1, 2}` because two is all this railroad offers**, measured on the
finished encoding rather than argued. For all 36 station-to-station requests:

| Requests | Minimal routes | Distinct lines | `k` |
| --- | --- | --- | --- |
| Claro → Airolo (18) | 2 | 1 | inert |
| Airolo → Claro (18) | 2 | 2 | `k = 2` chooses |

The asymmetry is structural. At Claro each track's east end is served by
exactly one blue line (blue 1 reaches track 3; blue 2 reaches tracks 1 and 2)
and its west end by the yellow, so the departure end and destination track
together fix the line — nothing left to choose. Departing Airolo, all three
lines meet at the single WX310 junction and two of them reach any given Claro
track, so a train for `claro_3` can take blue 1 or the yellow.

Two consequences a reader will otherwise get wrong:

- **`k` bites on half the workload.** Report the `k=1` → `k=2` comparison
  **per direction**. An aggregate makespan improvement is diluted by the 18
  requests where `k` could not have done anything.
- **`k` candidates are not `k` alternatives.** Where a request has only one
  line, its two minimal routes differ solely in which end they enter the
  destination track by — same blocks, same contention. Hence the dedupe-by-
  resource-set rule in [DISPATCH.md](DISPATCH.md#route-selection).

`k ≥ 3` reaches only 6-transit detours that consume all three line sections
where the direct route needs one. They are worse under contention, not better,
and less likely to pass the safety check. A layout where `k` could pay past 2
would need a fourth path between the stations; this railroad has none.

## Termination

**Quiescence, exactly detected — not a timeout.** Under batch arrivals no
request arrives after tick 0, so a tick yielding no move and no completion
leaves the state byte-identical next tick. The dispatcher is deterministic and
event-driven; no events means no change, forever. This is a proof, not a
heuristic.

If requests remain pending at quiescence, [SAFETY.md](SAFETY.md) leaves exactly
one possible cause: a permanent obstacle — an idle train parked across every
candidate route. The harness therefore **names it** (which train, which block,
how many candidates it blocks), emits `run_stalled`, and reports the run
`stalled`. Stalled runs are excluded from makespan aggregates.

This turns the conditional-liveness proviso of SAFETY.md from a paragraph into
a visible, tested output. The same detector powers property 2 in
[ARCHITECTURE.md](ARCHITECTURE.md#tests): any *other* cause of quiescence is a
policy bug. A tick budget survives only as a backstop against a live-lock bug,
never as the normal stop condition.

## Named scenarios

| Scenario | What it shows |
| --- | --- |
| `gotthard/meet` | two trains, opposite directions — `FullRoute` serialises, `Incremental` should split them across two lines |
| `gotthard/saturation` | 5 trains × 3 workings, batch — the headline makespan gap; five is the ceiling, per the axis note above |
| `gotthard/obstacle` | an idle train parked on the one line a pending request can use — e.g. stock left on `line_blue_1` while a request departs `claro_3.B`, whose departure end and destination fix that line. Expected status `stalled`, with the obstacle named |
| `crossover-yard/meet` | small and fast; the only layout with a `concurrent` pair |

## Output

- **`tc49 bench <scenario>`** runs one scenario under both strategies at the
  default `k = 2`, prints the comparison, and asserts against a committed
  `benchmarks/expected/<name>.json` in pytest. `k` is overridable, but the
  golden numbers are recorded at the default.
- **`tc49 sweep`** writes one JSONL row per run — every axis plus every metric
  — to a gitignored `out/`. No aggregation is baked in.

**Golden numbers are viable here**, which they usually are not, for a specific
reason: every metric is in **ticks**, not wall-clock, and the determinism
property already guarantees byte-identical traces. A makespan is exactly
reproducible on any machine, so a throughput regression fails CI with a readable
diff instead of going unnoticed. Sweep output is deliberately *not* committed —
it is a research finding, not a contract, and committing it would churn.
