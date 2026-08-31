# The dispatcher grants on events, and the boundary leaves the contract

Resolves [#243](https://github.com/rails49/control/issues/243);
[#264](https://github.com/rails49/control/issues/264) executes it.

`tc49/layout/boundary` is a requirement the simulator invented. The simulator
simulates a subset of the app's features — it is not the app, and it adds no
requirement of its own to any contract.
[ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md) already
forbids a simulator field, topic, or branch in any other app; the boundary
predates that rule and is its largest standing violation: a topic in the
inventory, a field on every trace line, and a branch in the dispatcher.

The layout does not need it to run. **The dispatcher grants on the events that
arrive** — no buffer, no periodic grant phase — and the boundary leaves the
contract.

The boundary bought determinism, byte-identical replay and a fast edit loop,
the three things ADR-0030 names when it rejects letting the simulator shape
another app. The safety argument for keeping it does not hold: every grant is
`safe()`-checked before it commits
([SAFETY.md](../dispatcher/SAFETY.md), *When it runs*), so arrival order
cannot reach an unsafe state. It can only pick an arbitrary winner among
options that were all safe, which is non-determinism rather than
incorrectness, and non-determinism is wanted in operation.

## Sensors are levels, not edges

A block detector reports presence, and presence can be asked for at any time.
The bus carries changes to that state because it is an event bus, but the
underlying fact is a level. Two consequences:

- A repeated reading is a no-op. It re-asserts a level the dispatcher already
  holds, so at-least-once delivery needs no counter and no dedup.
- There is no state-inquiry event. One could be added; nothing needs it today.

**A block has two detectors, and both stay inside the layout interface.** A
train entering block Y trips Y's first detector with its head, and its second
once it is fully in. The layout publishes `block_occupied(Y)` on the first and
`block_vacated(X)` on the second — it executed the move, so it knows which
block X is. The bus vocabulary does not change: two anonymous topics, no
detector geometry above the layout interface
([ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).

The physical order is therefore **occupied then vacated** — the reverse of
what the simulator publishes today. On the layout the head is in the next
block before the tail clears the previous one; there is no other order for it
to arrive in.

## What the boundary did, and what replaces each

**1. Order-independent grants.** The move's two facts split by role:
`block_occupied` records where the train arrived, `block_vacated` releases the
origin block and the transit, ends the move and completes the request.
Between the two the train is between blocks and takes no further grant.

**2. Unconditional retry of a refused train.** Nothing needed. The dispatcher
sweeps whenever the lock table or the waiting set changes — hooked where they
change, not at an enumerated list of topics — so a refused train is
reconsidered exactly when the resource it waited on frees. No backstop timer.

**3. Starvation-freedom.** Carried unchanged. A sweep covers the whole
waiting set, so every pending request accrues a refusal in the same sweep and
[ADR-0012](0012-the-pending-scan-ages-by-refusal-count.md)'s aging keeps the
order it has today. Only the trigger changes.

**4. A steady pulse for the expiry window, the relay and the metrics.** The
expiry is deleted, below. The relay goes back to being kicked by the
translator's own timer, where
[ADR-0040](0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md) put
it before ADR-0044 rerouted it. Metrics measure elapsed simulated time
directly.

## A move does not expire

ADR-0040 stamps a `move` with the boundary it was granted on so the layout can
drop a redelivery that arrives minutes late after a reconnect. The hazard is
real; the stamp is not the answer, and it was never implemented — the rule
lived only in SYSTEM.md.

**The layout acts on a `move` only if that train is standing at the transit's
near end.** After arrival it is not, so a stale redelivery is a no-op on state
alone. This is strictly stronger than the window — it also rejects a stale
command that arrives inside it — and it needs no clock, no stamp and no
agreement between apps.

A move ends by arrival, or by cancellation: an agent revokes the permission
and the request is deleted. A train that breaks down is the same case — a
person takes it off the layout, and the request goes with it. Cancellation is
contract surface that exists nowhere today;
[#244](https://github.com/rails49/control/issues/244) owns it, and until it
lands a dead train's locks survive until restart.

ADR-0040's other two legs stand: the local timer that stops a locomotive whose
detector never fires, and the track-power relay under all the software.

## Time is the scheduler's responsibility

A schedule says "this train, every workday at 7:00"; the scheduler posts the
request that morning. The dispatcher's contract carries no time — it grants
on the events that arrive. A simulator that wants timed submissions owns that
timing itself, inside the `simulator` app.

**A scenario's `at` is therefore deleted.** Requests go in at the start of a
run in the order the file writes them; the queue does the staggering, because
there are never enough tracks to satisfy them all at once anyway. `exhausted`
fires immediately, and a batch run ends when nothing is pending and no train
is active. A timetable released against the fast clock is a milestone-2
feature nothing needs yet, and when it arrives it is the scheduler's.

## The simulator becomes discrete-event

It mimics what real trains do, with fixed delays standing in for travel time.
On a `move` it schedules `block_occupied(destination)` after the transit
delay, then `block_vacated(origin)` after a second, shorter one. Both
configurable, 30 s the default, and both private to the `simulator` app. No
RNG: transit times are fixed, so a run is reproducible by construction and
byte-identical replay survives as a test net rather than being replaced.

One event queue, ordered by (time, sequence), with the wait injected: batch
advances the clock to the next scheduled event, live sleeps. Same code path
and same trace, which is how `run_live` already takes its `sleep`.

## The trace carries `time`, and no payload carries any

The trace line's first key becomes `time` where `boundary` sat: float seconds
since the session started — the run clock, which is simulated time in batch
and wall time live, the same injected clock either way. The tap stamps it as
it records. `time` is observation only: no event, request or grant carries a
timestamp, so no app can read one or come to depend on it.

All four metrics restate on simulated seconds. Latency is completion minus
submission; utilization is the fraction of the run a resource was locked;
crosses per boundary becomes moves per simulated minute. Every benchmark
re-baselines, and the standing start changes what the workloads measure.

## The fast clock needs no carrier

It is the wall clock with a start time and a multiplier, both railroad
configuration, so anything that wants it derives it. Nothing in the control
path reads it — that rule of ADR-0044 stands. The UI's session clock, wired
to the boundary counter today, shows the last event's `time` until a session
clock derived from the railroad configuration arrives.

## Assumed, and watched

`safe()` is assumed to hold unchanged. A sweep can run between the two facts
of one move, when the lock table shows a train holding its origin, its transit
and its destination at once — a superset of what it really holds, which can
only refuse. Whether the result is too conservative in practice is something
the running railroad answers, and the algorithm changes then if it does.

## What it rules on

- Supersedes [ADR-0027](0027-the-tick-is-the-simulators-grant-boundary.md):
  there is no grant boundary and no buffered sensor set.
- Supersedes
  [ADR-0044](0044-the-boundary-period-is-real-time-and-the-fast-clock-is-out-of-the-control-path.md)
  except its rule that the fast clock never feeds dispatch or safety, which
  stands: the boundary period and the liveness pulse go, and `at` as a
  fast-clock instant goes with the scenario `at`.
- Deletes ADR-0040's first leg (the expiry), replaced by the near-end rule
  above; its other two legs stand.
  [#172](https://github.com/rails49/control/issues/172), which would have
  implemented the expiry, closes as superseded.
- [ADR-0009](0009-layout-interface-owns-time.md) stands, reread: the layout
  interface owns time in that the run clock advances on the events it
  publishes. No payload carries a timestamp; the trace tap stamps.
- [ADR-0012](0012-the-pending-scan-ages-by-refusal-count.md) stands as
  written.
