"""Which railroad the apps are running, and what an app does when it moves.

One broker runs one railroad (ADR-0059, decision 2) and
[ADR-0060](../../../docs/adr/0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md)
makes which one a choice a person makes **while the apps run**: the layout
interface answers the picker and publishes `tc49/layout/state/railroad`, and
every other app follows that state row and never the gesture behind it.

Loading a railroad is a cold start that happens without a restart. An app
that hears another name on the row **clears the retained rows it owns and
rebuilds**. Dropping what it holds is not enough: the broker keeps retained
values while it runs, so the last railroad's rows — a desired speed per
locomotive, occupancy per block end — would still be handed to whatever
subscribes next, keyed to addresses and blocks the new railroad may not have,
and nothing republishes a row for a block that no longer exists. One writing
role (ADR-0035) is what lets each app say exactly which rows are its own.

This module is the seam the six apps share: the row's name, the follower that
watches it, and the clearing. An app's `__main__` names the filters it owns
and nothing else here knows them — what a row is about is the app's business,
and the rule is only that it is the row's owner who drops it.
"""

import threading
from collections.abc import Sequence

from tc49.lib.bus import Bus, Payload, matches
from tc49.lib.inventory import AT

RAILROAD = "tc49/layout/state/railroad"
"""The row every app follows: the railroad this broker runs, as the store
lists it. Published by whichever binding of the layout interface is running
(SYSTEM.md, the inventory), which is the one app bound to a railroad."""


class Loaded:
    """The railroad an app is running, and whether the bus has named another.

    A value rather than a callback, so that an app's loop reads it where it
    is convenient and a reload happens between two turns of that loop rather
    than inside a handler — the app being rebuilt is the one whose handler
    would be running.
    """

    def __init__(self, name: str) -> None:
        """`name` is what the process was started on: the `--railroad` a
        compose service passes, which is where a railroad with no row on the
        broker yet comes from."""
        self._name = name
        self._moved = False
        self._took: tuple[str, object] = (name, None)
        self._refused: tuple[str, object] | None = None

    @property
    def name(self) -> str:
        """The railroad to build on: the one named last, whoever named it."""
        return self._name

    @property
    def moved(self) -> bool:
        """Whether the row has named a railroad other than the one built."""
        return self._moved

    def follow(self, bus: Bus) -> None:
        """Watch the row, from now: a subscription this app made after the
        last one was forgotten, and the move that is being answered marked as
        answered. Called once per railroad, as the app on it is built."""
        self._moved = False
        bus.subscribe(RAILROAD, self._said)

    def _said(self, topic: str, payload: Payload) -> None:
        """A railroad named on the row. The same one is not a move — the
        binding of the interface that owns the row republishes it, and an app
        that rebuilt on every republication would rebuild on its own
        neighbour's heartbeat. A payload naming nothing readable is dropped:
        anything at all can arrive on a topic (SYSTEM.md, rule 4).

        **The row that was refused is not tried again.** A retained value is
        handed over afresh every time this app subscribes, and subscribing is
        what a rebuild does, so a railroad the store cannot give would
        otherwise be attempted, refused and attempted again for as long as
        the row stood — an app spending its life rebuilding and answering
        nothing. What is remembered is the row and not the name: a person who
        fixes the drawing and picks it again publishes a value with a later
        stamp, and that one is taken (#240).
        """
        name = payload.get("name")
        if not isinstance(name, str) or not name or name == self._name:
            return
        row = (name, payload.get(AT))
        if row == self._refused:
            return
        self._took = row
        self._name = name
        self._moved = True

    def keep(self, name: str) -> None:
        """Go back to running `name`: the railroad just named cannot be
        built — the store does not have it, or its drawing does not derive —
        and an app with nothing to run on is worse than one still running the
        railroad it had (ADR-0050)."""
        self._refused = self._took
        self._name = name
        self._moved = False


def dropped(
    bus: Bus, filters: Sequence[str], stop: threading.Event, retained_s: float
) -> list[str]:
    """The railroad that was running, left: the app built on it stops
    answering and the rows it owns go, so that what is built next starts on a
    broker holding nothing of the last one (ADR-0060).

    The filters are subscribed here and dropped again as soon as they have
    been read. Subscribing is how a broker hands over what it holds, and what
    has to be found is precisely the row **this process never wrote** — a
    desired speed for a locomotive the new railroad does not have, occupancy
    for a block end it does not have — which no rebuild republishes and
    nothing else would ever drop. A cold start has nothing to hand over, so
    an app coming up alone does none of this and comes up exactly as it did
    before there was a reload (ADR-0059, decision 5).

    `retained_s` is that moment, waited on `stop` so a signal arriving in it
    ends the process rather than being sat on.
    """
    bus.forget()
    for owned in filters:
        bus.subscribe(owned, _nothing)
    stop.wait(retained_s)
    gone = cleared(bus, filters)
    bus.forget()
    return gone


def _nothing(topic: str, payload: Payload) -> None:
    """What an app's own rows are subscribed with while they are being found.
    Nothing reads them: a row has one writing role and the app doing the
    subscribing is it (ADR-0035)."""


def cleared(bus: Bus, filters: Sequence[str]) -> list[str]:
    """Every retained row the bus holds under `filters`, dropped, and their
    topics in the order they were held.

    What the bus holds and not what this process published: the rows that
    matter are the ones a **previous** railroad left — one per address, one
    per block end — which no rebuild republishes and nothing else drops. An
    app subscribes the filters it owns so that the broker hands them over,
    and then this drops whatever came (ADR-0060).
    """
    gone = [
        topic
        for topic in bus.last_values
        if any(matches(one, topic) for one in filters)
    ]
    for topic in gone:
        bus.clear(topic)
    return gone
