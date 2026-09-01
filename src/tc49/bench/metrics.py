"""metrics(trace) -> Metrics: the four metrics, as a pure function.

Nothing is accumulated live and no component computes a metric at runtime
(bench/METRICS.md). Everything below derives from the tapped events
of SYSTEM.md, which is what keeps the trace **load-bearing**: an event that
stops being emitted breaks a metric and fails a test, rather than leaving
the trace to rot until a future UI discovers it is missing what it needs.
It also makes every metric testable against a hand-written trace, with no
run required.

Every metric is stated in simulated seconds, read off the trace lines'
`time` stamps (ADR-0047): latency is completion minus submission,
utilization is the fraction of the run a resource was locked, and
throughput is moves per simulated minute.

A run's `stalled` status and its diagnosis are derived here too, never
stored (BENCHMARKS.md, termination): a stalled request is one
`request_admitted` and then never answered at all — neither
`request_completed`, nor `request_rejected`, nor `request_cancelled` — and the
last `grant_refused` for its id names the obstacles. Stalled runs report no
makespan at all, so they cannot leak into a makespan aggregate.
"""

import json
from dataclasses import dataclass
from statistics import mean

from tc49.lib.bus import Payload


@dataclass(frozen=True)
class Stall:
    """One request admitted but never completed, diagnosed from its last
    `grant_refused`: which block, which train holding it, and how many
    candidate routes that refusal found blocked."""

    id: str
    reason: str  # 'held' | 'transit_conflict' | 'unsafe' | 'queued'
    resource: str  # '' when the request was never even attempted
    holder: str
    candidates_blocked: int


@dataclass(frozen=True)
class Metrics:
    seconds: float  # the trace's last stamp; the run spans 0..seconds
    completed: tuple[str, ...]
    rejected: tuple[str, ...]  # work the run never even attempted to do
    cancelled: tuple[str, ...]  # work a person ended before it arrived
    makespan: float | None  # None when the run stalled — never aggregated
    mean_latency: float | None
    max_latency: float | None
    utilization: dict[str, float]  # resource -> fraction of the run held
    moves: int  # move commands the run executed
    stalls: tuple[Stall, ...]

    @property
    def stalled(self) -> bool:
        return bool(self.stalls)

    @property
    def status(self) -> str:
        """`ok` only when the run both drained and dropped nothing.

        A rejected request is work the run never attempted, and dropping it
        makes the makespan *shorter* — so a run that quietly rejected half
        its workload would otherwise outscore one that did all of it. A
        rejection is an authoring or reachability fault rather than a
        dispatch outcome, hence its own status rather than a stall.

        A **cancelled** request is work somebody ended on purpose (ADR-0049),
        so it is neither a fault of the run nor a run that drained: it ranks
        between the two, and it is emphatically not `stalled` — a cancelled
        request has been answered, and calling it stalled would put a
        deliberate act in the diagnosis of a wedged railroad.
        """
        if self.stalled:
            return "stalled"
        if self.rejected:
            return "rejected"
        return "cancelled" if self.cancelled else "ok"

    @property
    def mean_utilization(self) -> float:
        """Averaged over the resources the trace ever locked — the trace does
        not carry the layout, so unlocked track is not in the denominator."""
        return mean(self.utilization.values()) if self.utilization else 0.0

    @property
    def moves_per_minute(self) -> float:
        return self.moves * 60.0 / _span(self.seconds)


def _span(seconds: float) -> float:
    """The run's extent as a divisor: a run whose every event landed at the
    start still has to divide by something."""
    return seconds if seconds > 0 else 1.0


def parse(trace: str) -> list[Payload]:
    return [json.loads(line) for line in trace.splitlines() if line]


def metrics(trace: str) -> Metrics:
    lines = parse(trace)
    seconds = max((line["time"] for line in lines), default=0.0)

    released = _stamps(lines, "request_submitted")
    admitted = _stamps(lines, "request_admitted")
    completed = _stamps(lines, "request_completed")
    rejected = _stamps(lines, "request_rejected")
    cancelled = _stamps(lines, "request_cancelled")

    # Keyed off `request_completed` alone: a cancelled request has no arrival
    # to measure to, so it contributes no latency rather than a short one.
    latencies: dict[str, float] = {}
    for rid, done in completed.items():
        if rid not in released:
            raise ValueError(
                f"trace is missing 'request_submitted' for '{rid}':"
                f" per-request latency cannot be derived"
            )
        latencies[rid] = done - released[rid]

    # Every way a request can be answered comes off the admitted set: what is
    # left is the requests nothing ever said anything more about, which is
    # what a stall is (BENCHMARKS.md). Without the cancellations, every run
    # carrying one would report `stalled`.
    stalls = _stalls(
        lines, set(admitted) - set(completed) - set(rejected) - set(cancelled)
    )
    return Metrics(
        seconds=seconds,
        completed=tuple(completed),
        rejected=tuple(rejected),
        cancelled=tuple(cancelled),
        makespan=(
            None
            if stalls or not completed or not admitted
            else max(completed.values()) - min(admitted.values())
        ),
        # `statistics.mean` hands back an int when the mean is exact, which
        # would make this field's type depend on the data.
        mean_latency=float(mean(latencies.values())) if latencies else None,
        max_latency=max(latencies.values()) if latencies else None,
        utilization=_utilization(lines, seconds),
        moves=sum(1 for line in lines if line["event"] == "move"),
        stalls=stalls,
    )


def _stamps(lines: list[Payload], event: str) -> dict[str, float]:
    """Request id -> the time that event was recorded at, first wins."""
    stamps: dict[str, float] = {}
    for line in lines:
        if line["event"] == event:
            stamps.setdefault(line["id"], line["time"])
    return stamps


def _stalls(lines: list[Payload], ids: set[str]) -> tuple[Stall, ...]:
    last_refusal: dict[str, Payload] = {
        line["id"]: line for line in lines if line["event"] == "grant_refused"
    }
    stalls: list[Stall] = []
    for rid in sorted(ids):
        refusal = last_refusal.get(rid)
        if refusal is None:
            # Never attempted: an earlier working of the same train is itself
            # still pending, and a train's chained workings run in order.
            stalls.append(Stall(rid, "queued", "", "", 0))
            continue
        obstacles = refusal["obstacles"]
        stalls.append(
            Stall(
                rid,
                refusal["reason"],
                obstacles[0]["resource"] if obstacles else "",
                obstacles[0]["holder"] if obstacles else "",
                len(obstacles),
            )
        )
    return tuple(stalls)


def _utilization(lines: list[Payload], seconds: float) -> dict[str, float]:
    """Locked time per resource over the whole run, as a fraction.

    A grant at time g and its release at r cover [g, r); a resource still
    held when the trace ends covers [g, seconds) — which is how the startup
    standing locks make idle trains count.
    """
    held_since: dict[str, float] = {}
    locked: dict[str, float] = {}
    for line in lines:
        if line["event"] == "lock_granted":
            for resource in line["resources"]:
                held_since.setdefault(resource, line["time"])
        elif line["event"] == "lock_released":
            for resource in line["resources"]:
                if resource not in held_since:
                    raise ValueError(
                        f"trace releases '{resource}' at {line['time']}"
                        f" without a matching 'lock_granted': utilization"
                        f" cannot be derived"
                    )
                locked[resource] = locked.get(resource, 0.0) + (
                    line["time"] - held_since.pop(resource)
                )
    for resource, since in held_since.items():
        locked[resource] = locked.get(resource, 0.0) + (seconds - since)
    span = _span(seconds)
    return {resource: held / span for resource, held in sorted(locked.items())}
