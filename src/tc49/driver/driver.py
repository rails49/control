"""Driver: the translator from granted moves to the command.

Per granted move it immediately publishes `move`, the move itself,
mirrored. Setting the route is the dispatcher's, which publishes `align`
(ADR-0022), so a grant is the driver's green signal. It reads no assets
(SYSTEM.md, driver footprint), and the one thing it holds is the speeds it
last heard.

Its whole judgement is **how fast**, and it is a pure function of the aspect
the grant shows (ADR-0025): the railroad's speeds for `clear` and `caution`,
which `layout` says on `tc49/layout/state/settings` and a person sets from the
Settings dialog (#1133), since how fast a railroad's trains should run depends
on its stock and scale. How fast is the only open question, because the
turnouts are already thrown when the aspect clears; and it is *how fast* and
not which way, direction being the layout interface's to compose out of
geometry the driver does not hold.

What it reads, the grant and the row, is **read** and never trusted (#261): a
topic under `dispatch` names the component that answers for it and not the
process that published this frame, the bus authenticates nobody, and a
consumer may not raise on a payload (BUS.md, rule 4). In process the
dispatcher publishing it is a call away; under MQTT it is another process, and
a bug there must not take the driver down.
"""

from collections.abc import Mapping

from tc49.lib.bus import Bus, Payload
from tc49.lib.payload import grant, granted_aspect, said_speeds

SETTINGS = "tc49/layout/state/settings"
"""Where `layout` says the railroad's speeds, retained from the moment a
railroad is loaded (#1130)."""


class Driver:
    def __init__(self, bus: Bus) -> None:
        """Subscribed to the row before the grants, so that the retained row
        is in hand by the time a grant can be."""
        self._bus = bus
        # What each aspect is worth as a speed, a fraction of the
        # locomotive's maximum (ADR-0025): the last `speeds` heard on
        # `state/settings`, and none until one is. `stop` is never here: a
        # grant showing it is no permission to move, so there is no command
        # to send and an entry would invent one.
        self._speeds: Mapping[str, float] = {}
        bus.subscribe(SETTINGS, self._on_settings)
        bus.subscribe("tc49/dispatch/move_granted", self._on_move)

    def _on_settings(self, topic: str, payload: Payload) -> None:
        """The railroad's speeds, from the next grant on: a train already
        moving keeps the speed its `move` gave it until its next grant.

        A row whose `speeds` does not read is ignored and the speeds held
        stay, rather than a grant being priced at half a pair or at nothing.
        A row cleared is never handed to a handler, on either binding; it is
        cleared on a reload, which builds a driver with no speeds anyway
        (`__main__`)."""
        speeds = said_speeds(payload)
        if speeds is not None:
            self._speeds = speeds

    def _on_move(self, topic: str, payload: Payload) -> None:
        """One grant restated as the command that moves the train.

        A frame that cannot be read is **dropped**, silently and to the trace:
        the driver commands and answers nothing, so there is nowhere to address
        a refusal to even where the frame carries an id (ADR-0034), and a
        dropped frame is already on the trace by virtue of having been
        published.

        Splitting the transit is what the driver does with what it read
        besides pricing the aspect — the inventory states the grant's transit
        qualified and `move`'s bare — and the split is the last thing that can
        fail. A
        transit missing either half names no connection or no transit to
        command with, and goes the way of any other frame that cannot be read.
        That the two halves name anything is the layout's question and not the
        driver's, which knows nothing of the layout: the form of the name is
        the whole of what there is to read here.

        An aspect the speeds do not price is dropped the same way, and the
        three cases that reach here are one: `stop` reads perfectly well and
        authorises no move, a name from outside the enum leaves nothing to
        run at, and before any `state/settings` is heard nothing is priced. There is no default to fall back on — a speed this
        component invented would be authority the dispatcher never gave — and
        a drop is what a grant this driver cannot act on is worth, since it
        commands and answers nothing (BUS.md, rule 4).
        """
        granted = grant(payload)
        if granted is None:
            return
        aspect = granted_aspect(payload)
        speed = self._speeds.get(aspect) if aspect is not None else None
        if speed is None:
            return
        connection, _, transit = granted.transit.partition(".")
        if not connection or not transit:
            return
        self._bus.publish(
            "tc49/layout/move",
            {
                "train": granted.train,
                "connection": connection,
                "transit": transit,
                "into": granted.into,
                "speed": speed,
            },
        )
