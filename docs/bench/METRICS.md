# Metrics

How each number in [BENCHMARKS.md](BENCHMARKS.md) is derived. Terminology
follows [CONTEXT.md](../../CONTEXT.md).

`metrics(trace) -> Metrics` is a pure function of the trace. Nothing is
accumulated live, and no component computes a metric at runtime. Everything
derives from the tapped events of [SYSTEM.md](../SYSTEM.md#the-trace):

- **Makespan** — first `request_admitted` stamp to last `request_completed`
  stamp.
- **Per-request latency** — `request_completed` stamp minus the
  `request_submitted` stamp, correlated by id; mean and max.
- **Utilization** — `lock_granted`/`lock_released` spans per resource, as a
  fraction of the whole run: the start through the trace's last stamp.
  Standing locks are in the trace from the dispatcher's startup emission
  ([SYSTEM.md](../SYSTEM.md#dispatcher)), so idle trains count.
- **Throughput** — `move` commands per simulated minute.
- **Stall report** — for each request admitted but never completed when the
  trace ends, the last `grant_refused` for its id names the obstacles: which
  train (`holder`), which block (`resource`), how many candidates were
  blocked (the list's length).

This is deliberate. It keeps the trace **load-bearing**: an event that stops
being emitted breaks a metric and fails a test, rather than leaving the trace
to rot quietly until a future UI discovers it is missing what it needs. It
also makes every metric testable against a hand-written trace, with no run
required.

Metrics reads traces but is not itself an app: it runs offline over a
recorded file. The trace tap that produces the file is `lib/trace.py`, since
a future UI reads the same format ([ARCHITECTURE.md](../ARCHITECTURE.md)).
