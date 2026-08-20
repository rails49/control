"""Scheduler: the one writer of requests, and the holder of facing.

Its sources are configuration rather than a rule (ADR-0036): a timetable
released at its `at` boundaries, and a person gesturing on
`tc49/ui/request_wanted`. `tc49 bench` runs with the timetable on, `tc49 live`
with it off while `at` is still a boundary count. A gesture is not a request —
it names a train and where to put it, and the id and the departure end are
what the scheduler adds. Ids are minted deterministically in scenario order
(`<train>-1`, `<train>-2`, ...) from one undivided counter, the arrival-end
expansion is purely mechanical (a bare block becomes both of its ends), and
when the last timetable request is out the `exhausted` state topic is set —
the milestone-1 termination signal.

It **holds facing** (ADR-0019), seeded from the scenario's placement and
carried forward from the bus: a train faces away from the end it entered
through, and a committed route's departure end is the end it will leave by.
That is what the layout read is for — `move_granted` names a transit and the
block entered, not the end entered through — and why the scheduler subscribes
`tc49/dispatch/#` (ADR-0028's growth, spent on facing). The last-value topic
it publishes is what every view reads to draw a direction arrow, a train that
has never moved having no other source for one.
"""

from collections import Counter
from typing import cast

from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import Layout
from tc49.lib.scenario import Scenario


class Scheduler:
    def __init__(
        self, bus: Bus, layout: Layout, scenario: Scenario, timetable: bool = True
    ) -> None:
        self._bus = bus
        self._layout = layout
        self._facing = {
            train: f"{spec.at}.{spec.facing}"
            for train, spec in sorted(scenario.trains.items())
        }
        self._train_of: dict[str, str] = {}  # request id -> the train it moves
        self._counters: Counter[str] = Counter()  # one undivided minter
        self._pending: list[tuple[int, Payload]] = []
        if timetable:
            for request in scenario.requests:
                self._counters[request.train] += 1
                self._pending.append(
                    (
                        request.at,
                        {
                            "id": f"{request.train}-{self._counters[request.train]}",
                            "train": request.train,
                            "depart": request.depart,
                            "dest": _expand(request.arrivals),
                        },
                    )
                )
        self._exhausted = False
        self._published: Payload = {}  # the facing last sent, so only changes go
        self._publish_facing()
        bus.subscribe("tc49/layout/boundary", self._on_boundary)
        bus.subscribe("tc49/dispatch/#", self._on_dispatch)
        bus.subscribe("tc49/ui/#", self._on_gesture)

    def _on_boundary(self, topic: str, payload: Payload) -> None:
        now = payload["boundary"]
        due = [event for at, event in self._pending if at <= now]
        self._pending = [(at, event) for at, event in self._pending if at > now]
        for event in due:
            self._submit(event)
        if not self._pending and not self._exhausted:
            self._exhausted = True
            self._bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})

    def _submit(self, event: Payload) -> None:
        self._train_of[event["id"]] = event["train"]
        self._bus.publish("tc49/schedule/request_submitted", event)

    # -- gestures ----------------------------------------------------------

    def _on_gesture(self, topic: str, payload: Payload) -> None:
        """A person's drag, composed into the request it asks for.

        A gesture names a train and where to put it; the two fields it omits
        are the two the scheduler owns — the id it mints and the departure
        end it holds as facing (ADR-0036). It judges nothing else: a train
        that is not idle is composed and submitted like any other, and
        answered `wrong_origin` or queued.

        What it cannot compose it **drops**, in silence and to the trace. A
        gesture carries no id, so there is nothing to address an answer to
        and a broadcast refusal would be uncorrelatable — the dispatcher's
        own reasoning one component upstream (ADR-0034). Like the dispatcher
        it never raises on a bus payload: anything at all can be published
        here, and once the relay is deleted nothing stands in front of it.
        """
        if topic.rsplit("/", 1)[-1] != "request_wanted":
            return  # a throttle is a second leaf under this role, later
        gesture = _wanted(payload)
        if gesture is None:
            return
        train, dest = gesture
        depart = self._facing.get(train)
        if depart is None:  # a train this session does not hold
            return
        self._counters[train] += 1
        self._submit(
            {
                "id": f"{train}-{self._counters[train]}",
                "train": train,
                "depart": depart,
                "dest": dest,
            }
        )

    # -- facing ------------------------------------------------------------

    def _on_dispatch(self, topic: str, payload: Payload) -> None:
        """Facing, carried forward from what the dispatcher announces.

        A route is a strict pass-through, so a train faces away from the end
        it entered through; and a committed route's departure end is the end
        it will leave by, which a request departing against facing is allowed
        to state (ADR-0019 makes facing a discipline, not an invariant).
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "move_granted":
            entered = _end_on(self._layout, payload["transit"], payload["into"])
            self._facing[payload["train"]] = _opposite(entered)
        elif leaf == "route_chosen":
            train = self._train_of.get(payload["id"])
            route = payload["route"]
            if train is not None and len(route) > 1:
                self._facing[train] = _end_on(self._layout, route[1], route[0])
        elif leaf in ("request_completed", "request_rejected"):
            self._train_of.pop(payload["id"], None)
        self._publish_facing()

    def _publish_facing(self) -> None:
        facing = {"facing": dict(sorted(self._facing.items()))}
        if facing != self._published:
            self._published = facing
            self._bus.publish("tc49/schedule/state/facing", facing)


def _wanted(payload: object) -> tuple[str, list[str]] | None:
    """The train and arrival ends a gesture names, or None where it names
    none. Anything at all can be published where a person's page writes, so
    reading it is a step of its own rather than two subscripts that raise."""
    if not isinstance(payload, dict):
        return None
    train, dest = (cast(Payload, payload).get(key) for key in ("train", "dest"))
    if not isinstance(train, str) or not isinstance(dest, list):
        return None
    ends = cast(list[object], dest)
    if not all(isinstance(end, str) for end in ends):
        return None
    return train, cast(list[str], ends)


def _expand(arrivals: tuple[str, ...]) -> list[str]:
    """Mechanical arrival-end expansion: a bare block means both its ends."""
    ends: list[str] = []
    for entry in arrivals:
        if "." in entry:
            ends.append(entry)
        else:
            ends += [f"{entry}.A", f"{entry}.B"]
    return ends


def _end_on(layout: Layout, transit: str, block: str) -> str:
    """The end of `block` that `transit` crosses — the end a train entering
    that way comes in through, and the end one leaving that way departs
    through. Neither is on the bus: `move_granted` names the transit and the
    block, and `route_chosen` names the route."""
    connection, _, name = transit.partition(".")
    first, second = layout.connections[connection].transits[name]
    return first if first.rpartition(".")[0] == block else second


def _opposite(end: str) -> str:
    """The other end of the same block: a block has exactly A and B."""
    block, _, letter = end.rpartition(".")
    return f"{block}.{'B' if letter == 'A' else 'A'}"
