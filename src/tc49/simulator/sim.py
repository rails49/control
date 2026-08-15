"""Simulator: the milestone-1 layout interface.

Commands in, observations out, plus ownership of time (SYSTEM.md, layout
interface; ADR-0009). Each advance executes the buffered commands, publishes
their sensor events, then the tick — a tick's sensors precede the tick
itself. It stops when the scheduler was already exhausted at the start of a
tick and that tick's cascade produced no commands (BENCHMARKS.md,
termination); the tick budget is a backstop against live-lock bugs only.
"""

from tc49.lib.bus import Bus, Payload
from tc49.lib.scenario import Scenario


class Simulator:
    def __init__(self, bus: Bus, scenario: Scenario) -> None:
        self._bus = bus
        self._position = {train: spec.at for train, spec in scenario.trains.items()}
        self._crosses: list[Payload] = []
        self._saw_command = False
        self._exhausted = False
        bus.subscribe("tc49/drive/+", self._on_command)
        bus.subscribe("tc49/schedule/state/exhausted", self._on_exhausted)

    def _on_command(self, topic: str, payload: Payload) -> None:
        self._saw_command = True
        if topic.endswith("/cross"):
            self._crosses.append(payload)

    def _on_exhausted(self, topic: str, payload: Payload) -> None:
        self._exhausted = payload["exhausted"]

    def run(self, tick_limit: int = 10_000) -> None:
        self._bus.drain()  # the startup cascade: standing locks reach the trace
        for now in range(tick_limit):
            exhausted_at_start = self._exhausted
            self._saw_command = False
            crosses, self._crosses = self._crosses, []
            for cross in crosses:
                train, into = cross["train"], cross["into"]
                origin = self._position[train]
                self._position[train] = into
                self._bus.publish("tc49/layout/block_vacated", {"block": origin})
                self._bus.publish("tc49/layout/block_occupied", {"block": into})
            self._bus.publish("tc49/layout/tick", {"tick": now})
            self._bus.drain()
            if exhausted_at_start and not self._saw_command:
                return
        raise RuntimeError(f"no quiescence within {tick_limit} ticks")
