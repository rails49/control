# Benchmarks

What the benchmark harness runs and what it reports. The four metrics are
defined in [DISPATCH.md](../dispatcher/DISPATCH.md#metrics), the trace they are computed from
in [SYSTEM.md](../SYSTEM.md#the-trace), and the file formats in
[LAYOUT.md](../store/LAYOUT.md).

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
the starvation job [SAFETY.md](../dispatcher/SAFETY.md) assigns it. Named scenarios stay free
to stagger `at:` for storytelling.

**Line workings** — generated requests run station to station,
`claro_{1,2,3} ↔ airolo_{1,2,3}`, chained into a connected walk per train:
request *n+1* departs from wherever request *n* parked the train. The departure
end is a free choice, since ADR-0001 permits reversal at rest between requests.

Chained requests therefore name **no departure block** — which track the
dispatcher parked the train on is its choice among the previous request's
arrival ends, so the generator emits `from: A` or `from: B` and only a train's
first working states a block ([LAYOUT.md](../store/LAYOUT.md#scenario-schema)).

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
([LAYOUT.md](../store/LAYOUT.md#the-encoded-railroads)), so a train parked in one blocks
nothing but a request destined to it — and no generated request is. Siding
stock is inert scenery for the sweep. The permanent obstacles that actually
bite are **idle trains on station tracks**: a working train before it launches,
or one that has finished its last working and now sits where somebody else is
headed.

**Sweep axes**: trains 2–5, 3 workings each, seeds 0–9, `|dest| ∈ {1, 2, 6}`,
`k ∈ {1, 2, 4, 6}`, locking ∈ {`FullRoute`, `Incremental`}.

**`|dest|` is the flexibility axis** — how many arrival ends a request names
([ADR-0007](../adr/0007-requests-name-a-set-of-arrival-ends.md)). It exists
because the claim that arrival-end sets buy throughput is a claim, and this
suite measures rather than assumes:

The axis is really three *intents* — one end, one track, one station — and the
counts are what Gotthard's three-track stations make of them. A layout with
four-track stations sweeps `{1, 2, 8}` for the same three intents:

| `\|dest\|` | What the request says | Written |
| --- | --- | --- |
| 1 | one track, one way round | `to: [claro_2.B]` |
| 2 | one track, either way round — **the old semantics** | `to: [claro_2]` |
| 6 | any track at the other station, either way round | `to: [claro_1, claro_2, claro_3]` |

`|dest| = 2` is the continuity point: it is exactly the request this model had
before arrival ends existed, so it is the column every other column is read
against.

Working trains start on station tracks, of which Gotthard has six. **The axis
stops at 5 for that reason**: at six, every station track holds an idle train,
every arrival block is therefore a permanent obstacle at every `|dest|`,
`safe()` refuses every launch, and the run quiesces `stalled` at tick 0 on
every seed. That point measures the stall detector, not throughput, so it is
excluded rather than swept. At five a free station track always exists, and it
helps because the generator redraws until every train's first request can
eventually reach one (step 4 below); a free track no pending request can name
would be unreachable to the workload
([ADR-0011](../adr/0011-the-sweep-generator-redraws-unsatisfiable-draws.md)).

### The generator

Everything below is drawn from a single seeded RNG, in this order, so a
`(layout, trains, workings, |dest|, seed)` tuple names one exact workload:

1. **Placement** — sample `trains` distinct station tracks from the six, one
   train each. Train lengths are fixed per train id so the fit check is
   deterministic; any length that fits every station track will do.
2. **Workings** — for each train in id order, chain `workings` requests. The
   first departs from its placement and states that block; each later one
   states only its end. The departure end is uniform over `A`/`B`, and the
   arrival ends are drawn at the swept `|dest|`: at 6, all three tracks of the
   *other* station; at 2, one track uniform over the three; at 1, one track
   uniform and then one of its two ends uniform.
3. **Arrival** — every request at tick 0.
4. **Redraw** — while any train's first request is one no dispatcher could
   launch, redraw each such request: end first, then arrival ends. A train
   can launch once one of its arrival blocks is free, and a block frees once
   its occupant launches; the fixed point of that rule must cover every
   train, or the draw contains a head-on swap: trains whose arrival blocks
   are each other's standing locks, stalling the run at tick 0 with track to
   spare ([ADR-0011](../adr/0011-the-sweep-generator-redraws-unsatisfiable-draws.md)).

Only first requests are checked. Where a later working departs from is the
dispatcher's choice, so a stall after trains have moved — typically a finished
train parked across a route — is a finding the sweep reports, not a draw it
rejects. Redraws consume the same seeded RNG after the main draw, so the
determinism property holds and a draw that needs no redraw is byte-identical
to one made without the rule.

**Routability needs no redraw on Gotthard.** Reachability depends on the
origin block, which for a chained working is not known when the file is
written, so the generator cannot check it — it is settled at the first launch
attempt ([DISPATCH.md](../dispatcher/DISPATCH.md#requests)). What makes this safe here is a
property of the railroad, verified against the encoding: every one of the six
station-to-station arrival ends is reachable from every origin track by either
departure end, so no draw can be unroutable at any `|dest|`. A layout without
that property extends step 4's redraw to unroutable requests too, since the
workings-per-train count is a sweep axis and must hold. Occupancy is the case
reachability cannot cover — it is per-origin and silent about an arrival block
held by another idle train — and is why step 4 exists.

## The `k` axis

`k` caps the candidate routes a launch may try before giving up
([SAFETY.md](../dispatcher/SAFETY.md#route-selection)). `k = 1` is a pure gate — wait for the
one route; `k > 1` is route-around, and with arrival-end sets it is also
finish-somewhere-else. That contrast is the headline measurement.

**`k` and `|dest|` are not independent axes.** Enumerated on the finished
encoding, Gotthard yields **exactly one minimal route per arrival end** — every
station-to-station route is two transits, so the candidate count a launch has
to work with is `|dest|` itself:

| `\|dest\|` | Direction | Minimal routes | Distinct lines | `k` |
| --- | --- | --- | --- | --- |
| 1 | either | 1 | 1 | inert |
| 2 | Claro → Airolo | 2 | 1 | arrival end only |
| 2 | Airolo → Claro | 2 | 2 | `k = 2` chooses a line |
| 6 | Claro → Airolo | 6 | 1 | arrival track only |
| 6 | Airolo → Claro | 6 | 3 | `k` chooses among all three lines |

Three things to read off it:

- **`k > |dest|` is a dead cell.** The minimal set is exhausted at `|dest|`
  candidates and the next tier is a 6-transit detour, so the sweep runs `k` up
  to `|dest|` and no further.
- **`k` is wholly inert at `|dest| = 1`.** One arrival end is one route, in
  both directions. This is the cost of constraining the arrival end, and it is
  why [ADR-0007](../adr/0007-requests-name-a-set-of-arrival-ends.md) does not
  constrain it without also allowing a set.
- **The old asymmetry is gone at `|dest| ≥ 2`.** `k` used to bite on half the
  workload — Claro departures had one line and nothing to choose. They still
  have one line, but now several arrival tracks on it, so `k` chooses *where
  the train finishes* rather than *how it gets there*. Both directions are
  live; only what `k` buys differs, and the sweep should still report the two
  directions separately because those are different mechanisms.

The line asymmetry itself is structural and unchanged. At Claro each track's
east end is served by exactly one blue line (blue 1 reaches tracks 2 and 3;
blue 2 reaches track 1) and its west end by the yellow, so the departure end
and arrival end together fix the line. Departing Airolo, all three lines meet
at the single WX310 connection and every one of them reaches every Claro track,
so at `|dest| = 6` a train has all three to choose between.

**The lexicographic bias at `k < |dest|`, and its fix.** Every candidate ties
at two transits, so before congestion-aware costing (#33) the lexicographic
tie-break alone ordered them and every train tried `claro_1`, then `claro_2`,
first. The predicted cost was real and worse than predicted: authoring
`gotthard/saturation` (#31) at `|dest| = 6` and running it at the default
`k = 2` did not merely cost throughput. The run **stalled outright**, under
both locking strategies, because both tracks every train tried first were
occupied and the rotation never started.

Costing removes the bias: tied candidates are ordered by how many of their
blocks other trains hold or are committed to
([DISPATCH.md](../dispatcher/DISPATCH.md#route-selection)), so equidistant arrival tracks
spread rather than concentrate. Measured on the sweep, the `|dest| = 6` drain
rate went 0 → 71 of 80 at `k = 1`, 11 → 72 at `k = 2`, 49 → 75 at `k = 4` and
75 → 75 at `k = 6`; runs that drained before drained slightly faster on net.
Below `|dest|`, `k` now measures the budget rather than the bias. Costing
alone left the widened saturation workload at 11 of 15 workings; the residue
was queue order rather than route choice (the oldest-first scan let older
trains park on the last free arrival tracks for good), and the aging rule
(#34) removed it — the widened workload now drains fully at `k = 2` under
both strategies. The committed scenario stays at `|dest| = 2`, the continuity
column the sweep reads every other against.

`k ≥ 7` reaches only 6-transit detours that consume all three line sections
where the direct route needs one — verified: between the two tiers there is
nothing. They are worse under contention, not better, and less likely to pass
the safety check. A layout where `k` could pay past `|dest|` would need a
fourth path between the stations; this railroad has none.

## Termination

**Quiescence, exactly detected — not a timeout.** The simulator stops
advancing ticks when the scheduler's `exhausted` state is set and a tick's
cascade produced no commands ([SYSTEM.md](../SYSTEM.md#layout-interface)). That
is exact, not heuristic: under batch arrivals no request arrives after tick 0,
so a commandless tick leaves the state byte-identical next tick — the
dispatcher is deterministic and event-driven; no events means no change,
forever. The stop rule is milestone-1 pacing, not bus contract; a hardware
adapter never terminates.

If requests remain pending when the trace ends, [SAFETY.md](../dispatcher/SAFETY.md) leaves
exactly one possible cause: a permanent obstacle — an idle train parked across
every candidate route. The run's `stalled` status and its diagnosis are
**derived from the trace**, not stored: a stalled request is one
`request_admitted` but never `request_completed`, and the last
`grant_refused` for its id names the obstacles — which train (`holder`),
which block (`resource`), how many candidates it blocked (the list's length)
([SYSTEM.md](../SYSTEM.md#event-inventory)). Stalled runs are excluded from
makespan aggregates.

This turns the conditional-liveness proviso of SAFETY.md from a paragraph into
a visible, tested output. The same detector powers property 2 in
[ARCHITECTURE.md](../ARCHITECTURE.md#tests): any *other* cause of quiescence is a
policy bug. A tick budget survives only as a backstop against a live-lock bug,
never as the normal stop condition.

## Named scenarios

| Scenario | What it shows |
| --- | --- |
| `gotthard/meet` | two trains, opposite directions — `FullRoute` serialises, `Incremental` should split them across two lines |
| `gotthard/saturation` | 5 trains × 3 workings, batch — the headline makespan gap; five is the ceiling, per the axis note above |
| `gotthard/obstacle` | an idle train parked on the one line a pending request can use — stock left on `line_blue_1` while a request departs `claro_3.B`, which is served by blue 1 alone. The departure end fixes the line by itself, so the request stalls however many arrival ends it names. Expected status `stalled`, with the obstacle named |
| `gotthard/flexibility` | the same working twice, once as `to: [claro_2.B]` and once as `to: [claro_1, claro_2, claro_3]` — the `\|dest\|` contrast as a story rather than a sweep row |
| `crossover-yard/meet` | small and fast; one `concurrent` pair, composed from a scissors crossover |

## Output

- **`tc49 bench <scenario>`** runs one scenario under both strategies at the
  default `k = 2`, prints the comparison, and asserts against a committed
  `benchmarks/expected/<name>.json` in pytest. `k` is overridable, but the
  golden numbers are recorded at the default. There is no `|dest|` flag: a
  named scenario writes its arrival ends out request by request, so `|dest|` is
  a property of the file rather than a knob on the run.
- **`tc49 sweep`** takes no arguments and runs exactly the grid above — the
  grid is the research design, not a knob, and this page is its single
  source of truth; flags arrive when a second grid is actually wanted. It
  writes one JSONL row per run — every axis plus every metric — to a
  gitignored `out/`. No aggregation is baked in.

**How a number becomes golden.** The gotthard scenarios above and the two
property-test layouts of [ARCHITECTURE.md](../ARCHITECTURE.md#tests) are
implementation work, authored from these descriptions. Golden numbers are
recorded from the first run made *after* the four Hypothesis properties and
the boundary-condition tests pass — never before, or "golden" means
"whatever the first run printed, bugs included". The comparison table is
reviewed by the owner before the goldens are committed, and any later
intentional change to a golden states its reason in the commit.

**Golden numbers are viable here**, which they usually are not, for a specific
reason: every metric is in **ticks**, not wall-clock, and the determinism
property already guarantees byte-identical traces. A makespan is exactly
reproducible on any machine, so a throughput regression fails CI with a readable
diff instead of going unnoticed. Sweep output is deliberately *not* committed —
it is a research finding, not a contract, and committing it would churn.
