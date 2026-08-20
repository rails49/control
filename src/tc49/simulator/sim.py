"""Simulator: the milestone-1 layout interface.

Commands in, observations out, plus ownership of time (SYSTEM.md, layout
interface; ADR-0009). The commands have two publishers — `align` is the
dispatcher's, `cross` the driver's — so it subscribes to both, and the
obligation that comes with the split is satisfied for free: batching to the
tick is why it can never act on a `cross` before the `align` naming the same
transit (ADR-0031). The **tick** is this binding's word for its beat; what
goes on the bus is the grant boundary every binding publishes
(`tc49/layout/boundary`, ADR-0027). Each advance executes the buffered
commands, publishes their sensor events, then the boundary — a tick's
sensors precede the boundary itself. Batch mode (``run``) stops when the
scheduler was already exhausted at the start of a tick and that tick's
cascade produced no commands (BENCHMARKS.md, termination); the tick budget
is a backstop against live-lock bugs only. Live mode (``run_live``, #69)
paces the same advance on a wall clock and never terminates on quiescence —
an idle railroad keeps ticking until the session is stopped. The dispatcher
cannot tell the modes apart: ADR-0009 stands, and the boundary counter stays
a deterministic integer.
"""

import time
from collections.abc import Callable

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
        bus.subscribe("tc49/dispatch/align", self._on_command)
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
            self._bus.publish("tc49/layout/boundary", {"boundary": now})
            self._bus.drain()
            if exhausted_at_start and not self._saw_command:
                return
        raise RuntimeError(f"no quiescence within {tick_limit} ticks")

    def run_live(
        self,
        period_s: float,
        sleep: Callable[[float], None] = time.sleep,
        stop: Callable[[], bool] = lambda: False,
    ) -> None:
        """The live loop: one sleep of the period before every tick, and no
        quiescence termination. `sleep` is the injectable time source, so
        tests pace the loop without waiting; `stop` is polled once per tick,
        and the interactive session ignores it and stops on Ctrl-C instead."""
        self._bus.drain()  # the startup cascade: standing locks reach the trace
        now = 0
        while not stop():
            sleep(period_s)
            crosses, self._crosses = self._crosses, []
            for cross in crosses:
                train, into = cross["train"], cross["into"]
                origin = self._position[train]
                self._position[train] = into
                self._bus.publish("tc49/layout/block_vacated", {"block": origin})
                self._bus.publish("tc49/layout/block_occupied", {"block": into})
            self._bus.publish("tc49/layout/boundary", {"boundary": now})
            self._bus.drain()
            now += 1
