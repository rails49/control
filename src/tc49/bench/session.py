"""A live session: the bridge on a port, and one railroad at a time behind it.

`tc49 live` is a session. The scenario is not fixed at launch — the panel
names it in the socket path, and switching is a reconnect (#148, ui/PANEL.md)
— so this holds the swap loop that the bridge's `rebind` is the other half
of.

`assemble_live` builds bus, scheduler, dispatcher, driver and simulator *from*
a scenario, so a switch is a new assembly and never a mutation. The thread
that calls `run` owns every one of them: it waits to be told which railroad,
builds it, hands the bus to the bridge, and runs it until somebody names
another. A client's handler thread only calls `wants`, which is one scenario
recorded and one event set — the same size as the `publish` it already makes.

A scenario that does not exist is refused there, on the handler's own thread
and before anything is recorded, so a typo cannot take down a live railroad.
A run outlives its clients: closing the browser leaves the railroad running,
and it is the process ending that ends the session.

This is milestone-1 wiring and stays small. There is no session registry and
no run manager; what persists is the bus's own retained state, where the
session was given a file to keep it in (#123). When the bus becomes a real
broker the bridge is deleted, the panel subscribes to the broker, and there
is no scenario to pick (ADR-0013 wiring note).
"""

import threading
from pathlib import Path
from typing import TextIO

from tc49.bench.runner import assemble_live, load
from tc49.lib.bridge import Bridge
from tc49.lib.bus import Bus
from tc49.lib.layout import Layout
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore


def state_for(state: Path, layout: str) -> Path:
    """One railroad's own state file, beside the one the session was given.

    A picture belongs to the railroad it is a picture of. The panel may switch
    railroads (#148) and a session keeps one path, so a single file would
    offer a gotthard picture to single-track-meet — and train names do not
    tell them apart, `fixed` and `flexible` standing on both of those layouts
    in the scenarios shipped here. Adopting across would place a train in a
    block of another layout, which no gesture on this one can clear.
    """
    return state.with_name(f"{state.stem}.{layout}{state.suffix}")


class Session:
    """Serving from construction; `run` works it until `stop`."""

    def __init__(
        self,
        root: Path,
        period_s: float,
        port: int = 0,
        state: Path | None = None,
    ) -> None:
        self._store = AssetStore(root)
        self._period_s = period_s
        # Where the runs' pictures live between processes, or None to forget
        # them with the process. The path names one file per railroad, since
        # switching railroads is the panel's to do and a picture belongs to
        # the railroad it is of (#123).
        self._state = state
        self._lock = threading.Lock()
        # Set while a scenario is waiting to be built, and again by `stop`,
        # which is what cuts a boundary's sleep short: picking a railroad in
        # the panel must not wait out a ten-second period.
        self._swap = threading.Event()
        self._wanted: tuple[str, Layout, Scenario] | None = None
        # A bridge wants a bus, and an idle session has no assembly to give
        # it: this one is relayed until the first `rebind` replaces it, and
        # nothing ever publishes to it.
        self.bridge = Bridge(Bus(), port, wants=self.wants)

    def wants(self, scenario_id: str) -> str | None:
        """Run this scenario next: a refusal in words, or `None` to accept.

        Called on a client's own handler thread. A scenario the store does
        not have is refused here and nothing is recorded, so the railroad
        already running is untouched by a typo.
        """
        if scenario_id not in self._store.scenarios():
            return f"no scenario '{scenario_id}'"
        try:
            wanted = load(self._store, scenario_id)
        except ValueError as refused:
            return f"scenario '{scenario_id}': {refused}"
        with self._lock:
            self._wanted = (scenario_id, *wanted)
            self._swap.set()
        return None

    def stop(self) -> None:
        """End the session: the run stops and none replaces it."""
        with self._lock:
            self._wanted = None
            self._swap.set()

    def run(self, out: TextIO) -> None:
        """Railroad after railroad, until `stop`. Each one is handed to the
        bridge before it is run, so its opening drain — the startup cascade,
        placement, facing and aspects — reaches whoever named it as live
        frames, in order, with nothing to seed.

        `rebind` is called with this lock released, and has to be: a handler
        thread takes the bridge's lock and then this one, so a thread holding
        this one and reaching for the bridge's would close the cycle.
        """
        while True:
            self._swap.wait()
            with self._lock:
                self._swap.clear()
                wanted = self._wanted
            if wanted is None:
                return
            scenario_id, layout, scenario = wanted
            kept = (
                None if self._state is None else state_for(self._state, scenario.layout)
            )
            assembly = assemble_live(layout, scenario, state=kept)
            self.bridge.rebind(assembly.bus, scenario_id)
            out.write(f"  running {scenario_id}\n")
            out.flush()
            assembly.simulator.run_live(
                self._period_s, sleep=self._pause, stop=self._swap.is_set
            )

    def _pause(self, period_s: float) -> None:
        """The live loop's sleep, cut short by a swap: a railroad picked in
        the panel must not wait out the boundary already under way."""
        self._swap.wait(period_s)
