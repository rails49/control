"""Scheduler: the one writer of requests, and the holder of facing.

Its sources are configuration rather than a rule (ADR-0036): a timetable
released at its `at` boundaries, and a person gesturing on `tc49/ui/*`.
`tc49 bench` runs with the timetable on, `tc49 live` with it off while `at`
is still a boundary count. A gesture is not a request —
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
has never moved having no other source for one. Deliberate reversal at rest
is the one change routes do not account for, and it arrives as its own
gesture on `tc49/ui/reversal_wanted` (#124).
"""

from collections import Counter

from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import Layout, end_on, opposite_end
from tc49.lib.payload import gesture, reversal
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
        """A person's action on a page: which of the two leaves it came on.

        What the scheduler cannot act on it **drops**, in silence and to the
        trace, whichever leaf it was. A gesture carries no id, so there is
        nothing to address an answer to and a broadcast refusal would be
        uncorrelatable — the dispatcher's own reasoning one component
        upstream (ADR-0034). The reading itself is `lib.payload`'s, which is
        where nothing raises.
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "request_wanted":
            self._compose(payload)
        elif leaf == "reversal_wanted":
            self._reverse(payload)
        # a throttle is a third leaf under this role, later

    def _compose(self, payload: Payload) -> None:
        """A drag, composed into the request it asks for.

        A gesture names a train and where to put it; the two fields it omits
        are the two the scheduler owns — the id it mints and the departure
        end it holds as facing (ADR-0036). It judges nothing else: a train
        that is not idle is composed and submitted like any other, and
        answered `wrong_origin` or queued.
        """
        wanted = gesture(payload)
        if wanted is None:
            return
        depart = self._facing.get(wanted.train)
        if depart is None:  # a train this session does not hold
            return
        self._counters[wanted.train] += 1
        self._submit(
            {
                "id": f"{wanted.train}-{self._counters[wanted.train]}",
                "train": wanted.train,
                "depart": depart,
                "dest": list(wanted.arrivals),
            }
        )

    def _reverse(self, payload: Payload) -> None:
        """Turning a train around at rest: the little arrow in the block it
        stands in, and nothing else (#124).

        Facing is fully determined once placed — routes are strict
        pass-throughs — with this one exception, which ADR-0019 named and
        parked for want of a scheduler to gesture at. No request is composed
        and the dispatcher learns nothing: nothing moves.

        Dropped where the train has a request in flight, from submit to
        completion. Flipping the arrow under one produces a lie: the queued
        request still departs the old end, and `route_chosen` flips the arrow
        back when it launches, undoing the operator's gesture minutes later.
        A **rejected** request leaves the train idle — `_train_of` has dropped
        it — and that is precisely when you want to turn around.
        """
        train = reversal(payload)
        if train is None:
            return
        facing = self._facing.get(train)
        if facing is None:  # a train this session does not hold
            return
        if train in self._train_of.values():  # a request in flight
            return
        self._facing[train] = opposite_end(facing)
        self._publish_facing()

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
            entered = end_on(self._layout, payload["into"], payload["transit"])
            self._facing[payload["train"]] = opposite_end(entered)
        elif leaf == "route_chosen":
            train = self._train_of.get(payload["id"])
            route = payload["route"]
            if train is not None and len(route) > 1:
                self._facing[train] = end_on(self._layout, route[0], route[1])
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
