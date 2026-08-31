"""A scenario played back as a person's gestures (#171).

A scenario is the harness's file format — a roster's worth of placement and a
canned request list — and `tc49 live --scenario` is the harness running one as
a test run. It does that from **outside**: one
`tc49/dispatch/placement_wanted` per train, a
`tc49/schedule/reversal_wanted` where the document faces a train the other
way, `tc49/dispatch/run_wanted` to release the hold, and then the requests at
their `at` boundaries, all over the topics a browser writes.

So no app is given a scenario and every app keeps one placement path; the
branch lives here, in the harness, which is ADR-0030's shape. It also makes a
replayed scenario a better test than a seeded one was, since running it
exercises `placement_wanted` itself.

What it cannot carry is a request's stated **departure end**. A gesture names
a train and where to put it, and the scheduler supplies the end off facing
(ADR-0036) — so a scenario whose `from` contradicts its facing replays by the
facing. That is the whole of the difference, and it is a difference a browser
has too.

A gesture the dispatcher cannot act on is **dropped in silence** (ADR-0034),
which is right for a person and wrong for a document: a placement it refused
would leave that train off the layout and every request for it answered
`no_origin`, a run silently unlike the one the file describes. So a replay
raises where a placement was not taken. It is the harness, and a fixture that
cannot be stood up is a broken fixture rather than a run to report on.
"""

from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import RUNNING
from tc49.lib.layout import Layout, connected_end
from tc49.lib.scenario import RequestSpec, Scenario

PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REVERSAL_WANTED = "tc49/schedule/reversal_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"
RUN_WANTED = "tc49/dispatch/run_wanted"


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
    """Lays the railroad out from `scenario`, releases the run, and feeds the
    timetable at its boundaries. Built onto an assembly that is already up.
    """

    def __init__(self, bus: Bus, layout: Layout, scenario: Scenario) -> None:
        self._bus = bus
        self._pending = list(scenario.requests)
        self._standing: set[str] = set()
        bus.subscribe("tc49/dispatch/train_placed", self._on_placed)
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
            # was off the layout the letter `A`, and turning it around is the
            # correction (ADR-0019, ADR-0039). Both ends go through
            # `connected_end`, so a terminal block is already right and no
            # gesture is sent for it.
            placed = connected_end(layout, f"{spec.at}.A")
            if placed != connected_end(layout, f"{spec.at}.{spec.facing}"):
                self._send(REVERSAL_WANTED, {"train": train})
        # The railroad is laid out, so the operator this stands in for presses
        # GO. Every placement had to land before it: a placement is honoured
        # while held and dropped while running (ADR-0037).
        self._send(RUN_WANTED, {"run": RUNNING})
        bus.subscribe("tc49/layout/boundary", self._on_boundary)

    def _on_placed(self, topic: str, payload: Payload) -> None:
        self._standing.add(payload["train"])

    def _send(self, topic: str, payload: Payload) -> None:
        self._bus.publish(topic, payload)
        self._bus.drain()

    def _on_boundary(self, topic: str, payload: Payload) -> None:
        now = payload["boundary"]
        due = [request for request in self._pending if request.at <= now]
        self._pending = [request for request in self._pending if request.at > now]
        for request in due:
            self._drag(request)

    def _drag(self, request: RequestSpec) -> None:
        """One request as the drag that asks for it: the train, and the ends
        it may arrive at. The id is the scheduler's and so is the departure
        end, exactly as they are for a person's drag (ADR-0036)."""
        self._bus.publish(
            REQUEST_WANTED,
            {"train": request.train, "dest": arrival_ends(request.arrivals)},
        )
