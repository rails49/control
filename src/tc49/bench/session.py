"""A live session: the bridge on a port, and one railroad at a time behind it.

`tc49 live` is a session. The railroad is not fixed at launch — the panel
names it in the socket path, and switching is a reconnect (#148, ui/PANEL.md)
— so this holds the swap loop that the bridge's `rebind` is the other half
of.

`assemble_live` builds bus, scheduler, dispatcher, driver and simulator from
**a railroad**: its drawing and its roster, and nothing else (#171). A switch
is a new assembly and never a mutation. The thread that calls `run` owns every
one of them: it waits to be told which railroad, builds it, hands the bus to
the bridge, and runs it until somebody names another. A client's handler
thread only calls `wants`, which is one railroad recorded and one event set —
the same size as the `publish` it already makes.

A railroad that does not exist, or whose drawing does not derive, is refused
there, on the handler's own thread and before anything is recorded, so a typo
cannot take down a live railroad. A run outlives its clients: closing the
browser leaves the railroad running, and it is the process ending that ends
the session.

This is milestone-1 wiring and stays small. There is no session registry and
no run manager; what persists is the bus's own retained state, where the
session was given a file to keep it in (#123). When the bus becomes a real
broker the bridge is deleted, the panel subscribes to the broker, and there
is no railroad to pick (ADR-0013 wiring note).
"""

import threading
from pathlib import Path
from typing import TextIO

from tc49.bench.replay import Replay
from tc49.bench.runner import assemble_live, railroad
from tc49.lib.bridge import Bridge
from tc49.lib.bus import Bus
from tc49.lib.clock import Clock
from tc49.lib.durable import sibling
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore


def state_for(state: Path, layout: str) -> Path:
    """One railroad's own state file, beside the one the session was given.

    The panel may switch railroads (#148) while a session keeps one path, and
    train names do not tell two layouts apart, so a single file would offer
    one railroad's picture to another and place a train in a block no gesture
    here can clear.
    """
    return sibling(state, layout)


class Session:
    """Serving from construction; `run` works it until `stop`."""

    def __init__(
        self,
        root: Path,
        period_s: float,
        port: int = 0,
        state: Path | None = None,
        host: str = "127.0.0.1",
    ) -> None:
        self._store = AssetStore(root)
        self._period_s = period_s
        # Where the runs' pictures live between processes, or None to forget
        # them with the process. The path names one file per railroad, since
        # switching railroads is the panel's to do and a picture belongs to
        # the railroad it is of (#123).
        self._state = state
        self._lock = threading.Lock()
        # Set while a railroad is waiting to be built, and again by `stop`,
        # which is what cuts the run loop's sleep short: picking a railroad
        # in the panel must not wait out a pending transit delay.
        self._swap = threading.Event()
        # The railroad to build next, and the scenario to replay onto it once
        # it is up, or None for the empty layout a run ordinarily starts from.
        # A replay is the harness's own way in and never a browser's, so it
        # is recorded here with the railroad rather than reached for later:
        # a client naming another railroad replaces both.
        self._wanted: tuple[str, Layout, Roster, Scenario | None] | None = None
        # A bridge wants a bus, and an idle session has no assembly to give
        # it: this one is relayed until the first `rebind` replaces it, and
        # nothing ever publishes to it.
        self.bridge = Bridge(Bus(Clock()), port, wants=self.wants, host=host)

    def wants(self, name: str) -> str | None:
        """Run this railroad next: a refusal in words, or `None` to accept.

        Called on a client's own handler thread. A railroad the store does
        not have, or whose drawing does not derive, is refused here and
        nothing is recorded, so the railroad already running is untouched by
        a typo.
        """
        return self._want(name, None)

    def plays(self, scenario_id: str) -> str | None:
        """Run the railroad a scenario names, and replay the scenario onto it
        as gestures: a refusal in words, or `None` to accept.

        `tc49 live --scenario`, and nothing else — a scenario is CLI-only and
        never browser-reachable (#171). It is played once, onto the assembly
        it named; a client that names another railroad replaces it, and the
        railroad it left behind is not replayed a second time.
        """
        try:
            scenario = self._store.get(scenario_id)
        except FileNotFoundError:
            return f"no scenario '{scenario_id}'"
        except ValueError as refused:
            return f"scenario '{scenario_id}': {refused}"
        if not isinstance(scenario, Scenario):
            return f"no scenario '{scenario_id}'"
        return self._want(scenario.layout, scenario)

    def _want(self, name: str, scenario: Scenario | None) -> str | None:
        """What both of those are: the documents read, then one railroad and
        one replay recorded together under the lock, so the run loop can never
        pick up a railroad before the scenario meant for it."""
        try:
            wanted = railroad(self._store, name)
        except FileNotFoundError:
            return f"no railroad '{name}'"
        except ValueError as refused:
            return f"railroad '{name}': {refused}"
        with self._lock:
            self._wanted = (name, *wanted, scenario)
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
            name, layout, roster, scenario = wanted
            kept = None if self._state is None else state_for(self._state, name)
            # No strategy named, so the session locks the way `assemble_live`
            # defaults: incrementally, which is what the panel's two colours
            # mean and what ui/PANEL.md says a live run does (#165).
            assembly = assemble_live(layout, roster, state=kept)
            self.bridge.rebind(assembly.bus, name)
            # After the rebind, so a client that named this railroad is
            # already registered and sees the replay's gestures and their
            # answers as the live frames they are.
            if scenario is not None:
                Replay(assembly.bus, layout, scenario)
            out.write(f"  running {name}\n")
            out.flush()
            assembly.simulation.run_live(
                self._period_s, sleep=self._pause, stop=self._swap.is_set
            )

    def _pause(self, period_s: float) -> None:
        """The live loop's sleep, cut short by a swap: a railroad picked in
        the panel must not wait out the sleep already under way."""
        self._swap.wait(period_s)
