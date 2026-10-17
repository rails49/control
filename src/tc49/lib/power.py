"""How a binding of the layout interface answers a power press: the one rule
both bindings keep.

Whichever binding is running answers `tc49/layout/power_wanted` — `layout`
over hardware, `simulator` over none (ADR-0070) — and the rule is the same
rule about the railroad either way, so it is written once, here, rather than
once in each binding where it could be fixed in one and left wrong in the
other (#752, #753). Three things make it up:

- **The run row.** A plain `off` is judged against `tc49/dispatch/state/run`,
  kept stamp-guarded (#240), and a value that cannot be read leaves the last
  one standing: forgetting what the dispatcher said on one bad frame would
  leave no evidence, and no evidence applies an `off`.
- **The guard on `off`.** It is applied only while the run is held and
  nothing moves (ADR-0062).
- **The emergency stop.** `stopped` stands on `state/power` from the press
  that asked for it until `on`, and an `off` does not clear it: no hardware
  can report a stop, so the binding that was told is the one that holds it
  (ADR-0063, ADR-0070).

What the supply itself reads is the binding's own: the layout folds it from
what the hardware reports, and the simulator, having none, states the last
`on` or `off` it applied. `TrackPower.stated` puts the held stop over it.
"""

import logging

from tc49.lib.bus import Payload
from tc49.lib.inventory import HELD, OFF, ON, STOPPED
from tc49.lib.payload import Ordering, Run, commanded_power, kept_run

_log = logging.getLogger(__name__)


class TrackPower:
    def __init__(self) -> None:
        # The last run row the dispatcher stated, and None until it states
        # one: no evidence, which is no reason to refuse.
        self._run: Run | None = None
        self._ordering = Ordering()
        self._stopped = False

    def run(self, topic: str, payload: Payload) -> None:
        """The dispatcher's run row, kept if it is the later one and can be
        read."""
        if not self._ordering.accepts(topic, payload):
            return
        held = kept_run(payload)
        if held is None:
            return
        self._run = held

    def answer(self, payload: Payload) -> str | None:
        """The word to apply for this press, or None where it is dropped: a
        press that cannot be read, and a plain `off` refused, to the log with
        the reason. A refusal is not kept for later (ADR-0062). `stopped`
        starts holding the stop and `on` clears it."""
        wanted = commanded_power(payload)
        if wanted is None:
            return None
        if wanted == OFF:
            refusal = _off_refused(self._run)
            if refusal is not None:
                _log.info("power off refused: %s", refusal)
                return None
        if wanted == STOPPED:
            self._stopped = True
        elif wanted == ON:
            self._stopped = False
        return wanted

    def stated(self, supply: str) -> str:
        """What `state/power` reads over this supply: `stopped` while a stop
        is held, else the supply's own word."""
        return STOPPED if self._stopped else supply


def _off_refused(run: Run | None) -> str | None:
    """Why a plain `off` may not be applied now, or None where it may.

    The guard refuses **on evidence that something moves and on nothing
    else** (ADR-0062). Two things are evidence: a run the dispatcher has
    not stopped committing over — an `off` on a running railroad would
    race the next grant by milliseconds — and a train that is moving,
    which a held run can still have, a move already granted running to
    its sensor. No `state/run` at all is not evidence: with no dispatcher
    up nothing has been granted, and a railroad that could not be turned
    off would be worse than the race.
    """
    if run is None:
        return None
    if run.run != HELD and run.moving:
        return f"the run reads {run.run} and a train is moving"
    if run.run != HELD:
        return f"the run reads {run.run}"
    if run.moving:
        return "a train is moving"
    return None
