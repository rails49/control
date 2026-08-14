# Requests name a set of arrival ends

A request no longer names one destination block with the arrival end left free.
It names a **set of arrival ends** — block plus the end the train enters
through — any one of which satisfies it. The dispatcher commits to one when it
chooses the route.

These are two changes and they ship as one, because separately each is a
mistake.

**Constraining the arrival end** is the half that costs. Which way round a
train finishes is a real operational fact — which end the locomotive is on,
which way the coaches face — and the previous rule, that this is "the
scheduler's concern, resolved by reversal at rest between requests", quietly
assumed a flip is free. On this railroad it is not: turning a train needs the
yellow reversing loop and a second request
([LAYOUT.md](../LAYOUT.md#reading-a-layout)). The request was the only place
that fact could be expressed and it had no way to express it.

But constraining it alone would have gutted the benchmark. At Claro each end of
each through track is served by exactly one line — blue 1 reaches track 3, blue
2 reaches tracks 1 and 2, the yellow reaches all three from the west — so
naming the arrival end *is* naming the line. Every request would have had
exactly one minimal route, `k` would have been inert in both directions, and
[BENCHMARKS.md](../BENCHMARKS.md#the-k-axis)'s headline measurement would have
had nothing left to measure.

**The set is what pays for it.** Naming both ends of one block reproduces the
old semantics exactly, so nothing is lost; naming several tracks says the thing
a station actually offers — more than one track will take this train — which
the old form could not say at all. Measured on the encoding, one minimal route
exists per arrival end, so the candidate count a launch may try is now the
caller's to set. `k` becomes live on the whole workload rather than half of it.

## Consequences

- **The departure block becomes unauthorable for chained workings.** Where the
  previous request parks a train is now a dispatcher decision, so a scenario
  cannot write the next request's departure block ahead of time. `from` keeps
  the end and makes the block optional, asserted when present
  ([LAYOUT.md](../LAYOUT.md#scenario-schema)).
- **Admission splits in two.** The fit check needs only lengths and stays at
  `submit`; routability needs the origin block and moves to the first launch
  attempt, so `advance` can now emit `request_rejected` too
  ([DISPATCH.md](../DISPATCH.md#requests)).
- **Dedupe-by-resource-set is retired.** Its motivating case — one route
  entering the destination at `A`, another at `B` — is now a genuine choice the
  caller asked for rather than one option spelled twice.
- **[ADR-0002](0002-fixed-route-per-request.md) is untouched.** A route is
  still chosen once and never changed; the set is resolved at that same moment,
  not carried into the journey. The safety check still sees a single-valued
  `dest(t)` for every active train.

## Open

Whether the request needs to name the **train** at all. Identity is
load-bearing inside the dispatcher — `safe()` quantifies over trains, grant
order breaks ties on train id, and the lock table is what recovers identity
from anonymous sensors — but that is an argument for the dispatcher tracking
it, not necessarily for the request carrying it. The departure end plus the
train's position could in principle name the mover instead. Left as it is:
under destination sets a chained working has no stable positional handle, so
the train id is currently the only thing that identifies it across a queue.
