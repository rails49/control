"""How a binding of the layout interface answers a power press: the one rule
both bindings keep.

Whichever binding is running answers `tc49/layout/power_wanted` — `layout`
over hardware, `simulator` over none (ADR-0070) — and the rule is the same
rule about the railroad either way, so it is written once, here, rather than
once in each binding where it could be fixed in one and left wrong in the
other (#752, #753). Power is one switch, `on`, `draining` or `off`
(ADR-0078), and three things make up the rule:

- **`off` is the emergency stop**, applied at once in every state. No guard
  stands in front of it: a person who wants the supply gone now has seen
  something the railroad cannot.
- **`draining` is the ordinary shutdown**, answered from `on` only. The
  supply stays on while each moving train stops, and it ends in `off` the
  first moment `tc49/dispatch/state/moving` reads false — at the press, if it
  already does. `on` during a drain ends it.
- **The moving row.** Kept stamp-guarded (#240), read by `payload.moving`, so
  a row that cannot be read reads as a train moving, and so does no row at
  all: cutting the supply under a train strands it (ADR-0062), and a drain
  left running waits only for a person to press `off`.

What the supply itself reads is the binding's own: the layout folds it from
what the hardware reports, and the simulator, having none, states the last
`on` or `off` it applied. `TrackPower.stated` puts a drain, and a cut not yet
undone by `on`, over it.
"""

import logging

from tc49.lib.bus import Payload
from tc49.lib.inventory import DRAINING, OFF, ON
from tc49.lib.payload import Ordering, moving, wanted_power

_log = logging.getLogger(__name__)


class TrackPower:
    def __init__(self) -> None:
        # Whether the dispatcher says a train is moving, true until it says
        # otherwise: no row is no evidence that nothing moves.
        self._moving = True
        self._ordering = Ordering()
        # The last word applied, and None until a press is: the railroad
        # comes up with the supply commanded off, and what the hardware then
        # reports is what the binding states (ADR-0030).
        self._word: str | None = None

    def moving(self, topic: str, payload: Payload) -> str | None:
        """The dispatcher's moving row, kept if it is the later one: `off`
        where it ends a drain and there is a cut to apply, else None."""
        if not self._ordering.accepts(topic, payload):
            return None
        self._moving = moving(payload)
        return self._drained()

    def answer(self, payload: Payload, supply: str) -> str | None:
        """The word to apply for this press over `supply`, the binding's own
        reading of it, or None where the press is dropped: one that cannot be
        read, and a `draining` from anything but `on`, to the log. A drain
        over a railroad already standing still applies as `off`."""
        wanted = wanted_power(payload)
        if wanted is None:
            return None
        if wanted == DRAINING:
            stated = self.stated(supply)
            if stated != ON:
                _log.info("power draining dropped: the power reads %s", stated)
                return None
            self._word = DRAINING
            return self._drained() or DRAINING
        self._word = wanted
        return wanted

    def stated(self, supply: str) -> str:
        """What `state/power` reads over this supply: `draining` through a
        drain, `off` from a cut until `on` is pressed, else the supply's own
        word. A cut is held over the supply because a supply is reported, and
        the hardware goes on reporting `on` for as long as it takes to go
        dark: a railroad read as `on` in that moment would be routed."""
        if self._word in (DRAINING, OFF):
            return self._word
        return supply

    def _drained(self) -> str | None:
        """`off` where a drain has nothing left moving, which ends it."""
        if self._word != DRAINING or self._moving:
            return None
        self._word = OFF
        return OFF
