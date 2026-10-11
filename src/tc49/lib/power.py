"""Whether a plain `off` may be applied: the one check both bindings make.

A plain `off` on `tc49/layout/power_wanted` is applied only while the run is
held and nothing moves (ADR-0062). Whichever binding of the layout interface
is running answers the press — `layout` over hardware, `simulator` over none
(ADR-0070) — and the check is the same rule about the railroad either way, so
it is written once, here, rather than once in each binding where it could be
fixed in one and left wrong in the other.

What it reads is the `Run` that `lib.payload.kept_run` takes off
`tc49/dispatch/state/run`; how a binding keeps that row, stamp-guarded and
falling back on the last one it could read, is that binding's own.
"""

from tc49.lib.inventory import HELD
from tc49.lib.payload import Run


def off_refused(run: Run | None) -> str | None:
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
