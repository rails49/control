"""A scenario played back as a person's gestures (#171).

A scenario is the harness's file format — a roster's worth of placement and a
canned request list — and this is the harness running one as a test run. It
does that from **outside**: one
`tc49/dispatch/placement_wanted` per train, a
`tc49/schedule/reversal_wanted` where the document faces a train the other
way, `tc49/layout/power_wanted` to turn the power on, and then the requests in
the file's order, all over the topics a browser writes.

So no app is given a scenario and every app keeps one placement path; the
branch lives here, in the harness, which is ADR-0030's shape. It also makes a
replayed scenario a better test than a seeded one was, since running it
exercises `placement_wanted` itself.

What it cannot carry is a request's stated **departure end**. A gesture names
a train and where to put it, and the scheduler supplies the end off facing
(ADR-0036) — so a scenario whose `from` contradicts its facing replays by the
facing. That is the whole of the difference, and it is a difference a browser
has too.

Nor can it drag a train again while that train has a request in flight: a
drag then **chains** after it (ADR-0080, #827), carrying on out of the far end
of the block it arrives in, where a document's next request for the train
states a departure end of its own — a return working out of a stub, which no
chain can leave. So a train's next request waits, here, until the one before
it has been answered, which is what a person who wanted it run that way would
do: watch the train arrive, then drag it again.

A gesture the dispatcher cannot act on is **dropped in silence** (ADR-0034),
which is right for a person and wrong for a document: a placement it refused
would leave that train off the layout and every request for it answered
`no_origin`, a run silently unlike the one the file describes. So a replay
raises where a placement was not taken. It is the harness, and a fixture that
cannot be stood up is a broken fixture rather than a run to report on.
"""

from collections import deque

from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import ON
from tc49.lib.layout import Layout, connected_facing
from tc49.lib.payload import named_train, readable_id
from tc49.lib.scenario import RequestSpec, Scenario

PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REVERSAL_WANTED = "tc49/schedule/reversal_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"
POWER_WANTED = "tc49/layout/power_wanted"


def arrival_ends(arrivals: tuple[str, ...]) -> list[str]:
    """A scenario's arrival list as the ends a gesture names: a bare block
    means both of its ends.

    A page computes its ends from where the drop landed, so a gesture always
    carries them and nothing downstream expands one. The scenario file is
    allowed to write a block, so the expansion happens here — where the
    browser's own would.
    """
    ends: list[str] = []
    for entry in arrivals:
        ends += [entry] if "." in entry else [f"{entry}.A", f"{entry}.B"]
    return ends


class Replay:
    """Lays the railroad out from `scenario`, turns the power on, and feeds the
    timetable in the file's order. Built onto an assembly that is already up.
    """

    def __init__(self, bus: Bus, layout: Layout, scenario: Scenario) -> None:
        self._bus = bus
        self._standing: set[str] = set()
        self._train_of: dict[str, str] = {}  # request id in flight -> its train
        self._waiting: dict[str, deque[RequestSpec]] = {}  # train -> drags held
        bus.subscribe("tc49/dispatch/train_placed", self._on_placed)
        bus.subscribe("tc49/dispatch/#", self._on_answer)
        for train, spec in scenario.trains.items():
            # Each gesture drains before the next: the scheduler learns a
            # train's facing from the `train_placed` the dispatcher answers a
            # placement with, and a reversal published ahead of that answer
            # would name a train it holds no facing for.
            self._send(PLACEMENT_WANTED, {"train": train, "block": spec.at})
            if train not in self._standing:
                raise ValueError(
                    f"scenario '{scenario.name}': the dispatcher would not"
                    f" stand '{train}' in '{spec.at}' — the block is taken,"
                    f" or the train does not fit it"
                )
            # A placement carries no facing: the scheduler gives a train that
            # was off the layout `B-to-A`, and turning it around is the
            # correction (ADR-0019, ADR-0039). Both go through
            # `connected_facing`, so a terminal block is already right and no
            # gesture is sent for it.
            placed = connected_facing(layout, f"{spec.at}.B-to-A")
            if placed != connected_facing(layout, f"{spec.at}.{spec.facing}"):
                self._send(REVERSAL_WANTED, {"train": train})
        # The railroad is laid out, so the operator this stands in for presses
        # ON. The dispatcher routes only while the power reads `on`, and a
        # placement is taken at any power, so this is the press that starts
        # the run whether or not the assembly already had the power on.
        self._send(POWER_WANTED, {"power": ON})
        # One drain per drag, as a person's sequential drags land: each
        # request's cascade settles — grants, facing — before the next is
        # composed against it. A train with a request in flight has its next
        # one held until that one is answered (`_on_answer`).
        for request in scenario.requests:
            if request.train in self._train_of.values():
                self._waiting.setdefault(request.train, deque()).append(request)
            else:
                self._drag(request)

    def _on_placed(self, topic: str, payload: Payload) -> None:
        self._standing.add(payload["train"])

    def _on_answer(self, topic: str, payload: Payload) -> None:
        """Which trains have a request in flight, and the held drag of one
        whose last has been answered. Published and not drained: this runs
        inside the drain that delivered the answer, which goes on to deliver
        the drag."""
        leaf = topic.rsplit("/", 1)[-1]
        rid = readable_id(payload)
        if rid is None:
            return
        if leaf == "request_submitted":
            train = named_train(payload)
            if train is not None:
                self._train_of[rid] = train
        elif leaf in ("request_completed", "request_rejected", "request_cancelled"):
            train = self._train_of.pop(rid, None)
            waiting = self._waiting.get(train) if train is not None else None
            if waiting and train not in self._train_of.values():
                self._publish_drag(waiting.popleft())

    def _send(self, topic: str, payload: Payload) -> None:
        self._bus.publish(topic, payload)
        self._bus.drain()

    def _drag(self, request: RequestSpec) -> None:
        """One request as the drag that asks for it: the train, and the ends
        it may arrive at. The id is the scheduler's and so is the departure
        end, exactly as they are for a person's drag (ADR-0036)."""
        self._publish_drag(request)
        self._bus.drain()

    def _publish_drag(self, request: RequestSpec) -> None:
        self._bus.publish(
            REQUEST_WANTED,
            {"train": request.train, "dest": arrival_ends(request.arrivals)},
        )
