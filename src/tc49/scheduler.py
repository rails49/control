"""Scheduler: releases the scenario's requests at their `at` ticks.

Layout-blind and tick-only (SYSTEM.md, scheduler footprint). Ids are minted
deterministically in scenario order (`<train>-1`, `<train>-2`, ...), the
arrival-end expansion is purely mechanical (a bare block becomes both of
its ends), and when the last request is out the `exhausted` state topic is
set — the milestone-1 termination signal.
"""

from collections import Counter

from tc49.bus import Bus, Payload
from tc49.store import Scenario


class Scheduler:
    def __init__(self, bus: Bus, scenario: Scenario) -> None:
        self._bus = bus
        counters: Counter[str] = Counter()
        self._pending: list[tuple[int, Payload]] = []
        for request in scenario.requests:
            counters[request.train] += 1
            self._pending.append(
                (
                    request.at,
                    {
                        "id": f"{request.train}-{counters[request.train]}",
                        "train": request.train,
                        "depart": request.depart,
                        "dest": _expand(request.arrivals),
                    },
                )
            )
        self._exhausted = False
        bus.subscribe("tc49/layout/tick", self._on_tick)

    def _on_tick(self, topic: str, payload: Payload) -> None:
        now = payload["tick"]
        due = [event for at, event in self._pending if at <= now]
        self._pending = [(at, event) for at, event in self._pending if at > now]
        for event in due:
            self._bus.publish("tc49/schedule/request_submitted", event)
        if not self._pending and not self._exhausted:
            self._exhausted = True
            self._bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})


def _expand(arrivals: tuple[str, ...]) -> list[str]:
    """Mechanical arrival-end expansion: a bare block means both its ends."""
    ends: list[str] = []
    for entry in arrivals:
        if "." in entry:
            ends.append(entry)
        else:
            ends += [f"{entry}.A", f"{entry}.B"]
    return ends
