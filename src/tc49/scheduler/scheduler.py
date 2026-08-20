"""Scheduler: the one writer of requests, and the holder of facing.

Its sources are configuration rather than a rule (ADR-0036): a timetable
released at its `at` ticks, and a person gesturing on the panel. `tc49 bench`
runs with the timetable on, `tc49 live` with it off while `at` is still a tick
number. Ids are minted deterministically in scenario order (`<train>-1`,
`<train>-2`, ...) from one undivided counter, the arrival-end expansion is
purely mechanical (a bare block becomes both of its ends), and when the last
timetable request is out the `exhausted` state topic is set — the milestone-1
termination signal.

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
        counters: Counter[str] = Counter()
        self._pending: list[tuple[int, Payload]] = []
        if timetable:
            for request in scenario.requests:
                counters[request.train] += 1
                self._pending.append(
                    (
                        request.at,
                        {
                            "id": f"{request.train}-{counters[request.train]}",
                            "train": request.train,
                            "depart": request.depart,
                            "dest": _expand(request.arrivals),
                        },
                    )
                )
        self._exhausted = False
        self._published: Payload = {}  # the facing last sent, so only changes go
        self._publish_facing()
        bus.subscribe("tc49/layout/tick", self._on_tick)
        bus.subscribe("tc49/dispatch/#", self._on_dispatch)

    def _on_tick(self, topic: str, payload: Payload) -> None:
        now = payload["tick"]
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
