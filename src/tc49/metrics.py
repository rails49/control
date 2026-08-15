"""metrics(trace) -> Metrics: the four metrics, as a pure function.

Nothing is accumulated live and no component computes a metric at runtime
(ARCHITECTURE.md, metrics). Everything below derives from the tapped events
of SYSTEM.md, which is what keeps the trace **load-bearing**: an event that
stops being emitted breaks a metric and fails a test, rather than leaving
the trace to rot until a future UI discovers it is missing what it needs.
It also makes every metric testable against a hand-written trace, with no
run required.

A run's `stalled` status and its diagnosis are derived here too, never
stored (BENCHMARKS.md, termination): a stalled request is one
`request_admitted` but never `request_completed`, and the last
`grant_refused` for its id names the obstacles. Stalled runs report no
makespan at all, so they cannot leak into a makespan aggregate.
"""

import json
from collections import Counter
from dataclasses import dataclass
from statistics import mean

from tc49.bus import Payload


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
    ticks: int  # the trace's final tick; the run spans ticks 0..ticks
    completed: tuple[str, ...]
    rejected: tuple[str, ...]  # work the run never even attempted to do
    makespan: int | None  # None when the run stalled — never aggregated
    mean_latency: float | None
    max_latency: int | None
    utilization: dict[str, float]  # resource -> fraction of the run held
    crosses_per_tick: dict[int, int]
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
        """
        if self.stalled:
            return "stalled"
        return "rejected" if self.rejected else "ok"

    @property
    def mean_utilization(self) -> float:
        """Averaged over the resources the trace ever locked — the trace does
        not carry the layout, so unlocked track is not in the denominator."""
        return mean(self.utilization.values()) if self.utilization else 0.0

    @property
    def mean_parallelism(self) -> float:
        return sum(self.crosses_per_tick.values()) / (self.ticks + 1)


def parse(trace: str) -> list[Payload]:
    return [json.loads(line) for line in trace.splitlines() if line]


def metrics(trace: str) -> Metrics:
    lines = parse(trace)
    ticks = max((line["tick"] for line in lines), default=0)
    duration = ticks + 1  # the run occupies ticks 0..ticks inclusive

    released = _stamps(lines, "request_submitted")
    admitted = _stamps(lines, "request_admitted")
    completed = _stamps(lines, "request_completed")
    rejected = _stamps(lines, "request_rejected")

    latencies: dict[str, int] = {}
    for rid, done in completed.items():
        if rid not in released:
            raise ValueError(
                f"trace is missing 'request_submitted' for '{rid}':"
                f" per-request latency cannot be derived"
            )
        latencies[rid] = done - released[rid]

    stalls = _stalls(lines, set(admitted) - set(completed) - set(rejected))
    return Metrics(
        ticks=ticks,
        completed=tuple(completed),
        rejected=tuple(rejected),
        makespan=(
            None
            if stalls or not completed or not admitted
            else max(completed.values()) - min(admitted.values())
        ),
        # `statistics.mean` hands back an int when the mean is exact, which
        # would make this field's type depend on the data.
        mean_latency=float(mean(latencies.values())) if latencies else None,
        max_latency=max(latencies.values()) if latencies else None,
        utilization=_utilization(lines, duration),
        crosses_per_tick=Counter(
            line["tick"] for line in lines if line["event"] == "cross"
        ),
        stalls=stalls,
    )


def _stamps(lines: list[Payload], event: str) -> dict[str, int]:
    """Request id -> the tick that event was recorded on, first wins."""
    stamps: dict[str, int] = {}
    for line in lines:
        if line["event"] == event:
            stamps.setdefault(line["id"], line["tick"])
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


def _utilization(lines: list[Payload], duration: int) -> dict[str, float]:
    """Locked-ticks per resource over the whole run, as a fraction.

    A grant at tick g and its release at tick r cover [g, r); a resource
    still held when the trace ends covers [g, duration) — which is how the
    startup standing locks make idle trains count.
    """
    held_since: dict[str, int] = {}
    locked: Counter[str] = Counter()
    for line in lines:
        if line["event"] == "lock_granted":
            for resource in line["resources"]:
                held_since.setdefault(resource, line["tick"])
        elif line["event"] == "lock_released":
            for resource in line["resources"]:
                if resource not in held_since:
                    raise ValueError(
                        f"trace releases '{resource}' at tick {line['tick']}"
                        f" without a matching 'lock_granted': utilization"
                        f" cannot be derived"
                    )
                locked[resource] += line["tick"] - held_since.pop(resource)
    for resource, since in held_since.items():
        locked[resource] += duration - since
    return {resource: held / duration for resource, held in sorted(locked.items())}
