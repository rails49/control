"""Dispatcher: admission, queue, lock table, buffered sensors, grant phase.

Fully asynchronous at the bus boundary (SYSTEM.md, dispatcher footprint):
requests arrive as events, every fate is announced as an event, and the
request id is both correlation and idempotency key. Sensor events are
buffered until the boundary and treated as a set, so grants are a pure
function of the buffered set, never of delivery order (DISPATCH.md, time
model). Standing locks are seeded from the scenario and published at
startup. The locking discipline is the pluggable strategy of locking.py.

It is also the sole payload authority (SYSTEM.md, dispatcher footprint):
anything at all may be published on the inbound topic, so admission reads a
payload rather than trusting one and never raises on what it finds — an
unreadable request is an answer where it can be addressed and a drop where
it cannot (ADR-0034).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from tc49.dispatcher.locking import Launched, LockingStrategy, Move, Refused
from tc49.dispatcher.routing import Route
from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import Layout
from tc49.lib.scenario import Scenario


@dataclass
class Request:
    id: str
    train: str
    depart: str  # end, or bare letter for a chained request
    arrivals: tuple[str, ...]  # surviving arrival ends
    seq: int  # admission order; the pending queue's tie-break key
    phase: int  # grant phases run when admitted; the arrival-order key
    refusals: int = 0  # launch refusals so far; the aging key (#34)


def aging_order(req: Request) -> tuple[int, int]:
    """The pending scan's key: most-refused first, admission order among
    equals. Refusal count is dispatcher state, never wall-clock, so the
    order stays a deterministic function of the run."""
    return (-req.refusals, req.seq)


@dataclass
class Active:
    request: Request
    route: Route
    cur_index: int  # index into route.blocks of cur(t)
    outstanding: Move | None  # granted move whose sensors are pending


@dataclass
class State:
    layout: Layout
    train_lengths: dict[str, int]
    locks: dict[str, str]  # resource -> holding train
    block_of: dict[str, str]  # train -> block it stands in (or last parked)
    active: dict[str, Active]

    def obstacle(self, resource: str, train: str) -> tuple[str, str, str] | None:
        """Why `train` cannot lock `resource`: (reason, resource, holder),
        or None if it can. Transits also require no conflicting locked
        transit at their connection (instantaneous admissibility)."""
        holder = self.locks.get(resource)
        if holder is not None and holder != train:
            return ("held", resource, holder)
        if "." in resource:  # a transit: check the conflict matrix
            for locked, by in sorted(self.locks.items()):
                if (
                    by != train
                    and "." in locked
                    and self.layout.conflicts(resource, locked)
                ):
                    return ("transit_conflict", locked, by)
        return None


def locked_ahead(state: State, train: str, route: Route, standing: int) -> int:
    """How many blocks of `route` past index `standing` are locked to
    `train`, counted until the first that is not."""
    depth = 0
    for block in route.blocks[standing + 1 :]:
        if state.locks.get(block) != train:
            break
        depth += 1
    return depth


def aspect_of(depth: int) -> str:
    """The aspect a signal shows for a locked-ahead depth (ADR-0025)."""
    if depth >= 2:
        return "clear"
    return "approach" if depth else "stop"


def departure_end(layout: Layout, block: str, transit: str) -> str:
    """The end of `block` that `transit` crosses: the end a train leaving by
    that transit departs through, and so the signal the aspect belongs to."""
    connection, _, name = transit.partition(".")
    first, second = layout.connections[connection].transits[name]
    return first if first.rpartition(".")[0] == block else second


def aspects(state: State) -> dict[str, str]:
    """Every signalled block end's aspect. An end nothing ever leaves carries
    no signal and does not appear; an end no train is authorised to leave by
    shows `stop`, which falls out of there being nothing locked beyond it
    rather than being a rule of its own.

    A train mid-transit has already had `cur_index` advanced, so the block it
    stands in is one back. The aspect belongs to where it stands, not where
    it is going.
    """
    shown = {end: "stop" for end in sorted(state.layout.end_connection)}
    for train, active in state.active.items():
        standing = active.cur_index - (1 if active.outstanding else 0)
        if standing >= len(active.route.transits):
            continue  # in its arrival block; nothing left to leave by
        end = departure_end(
            state.layout,
            active.route.blocks[standing],
            active.route.transits[standing],
        )
        shown[end] = aspect_of(locked_ahead(state, train, active.route, standing))
    return shown


def allocation(state: State, pending: Sequence[Request]) -> Payload:
    """The run's picture: where every train stands, the lock table with its
    holders, and every request still alive — carrying the route a committed
    one is running.

    A projection of the lock table and the queue, published beside its source
    exactly as `aspects` is (ADR-0032). Everything a joining client draws is
    here, because the events that built it were published before it connected
    and an event topic is never replayed. Ordered by admission, and the maps
    sorted, so the picture is a function of the state and not of a dict's
    insertion history.
    """
    routes = {active.request.id: active.route for active in state.active.values()}
    live = sorted(
        [*pending, *(active.request for active in state.active.values())],
        key=lambda request: request.seq,
    )
    return {
        "trains": dict(sorted(state.block_of.items())),
        "locks": dict(sorted(state.locks.items())),
        "requests": [
            {
                "id": request.id,
                "train": request.train,
                "depart": request.depart,
                "dest": list(request.arrivals),
                **(
                    {"route": routes[request.id].interleaved()}
                    if request.id in routes
                    else {}
                ),
            }
            for request in live
        ],
    }


@dataclass
class Submission:
    """A payload read as the request it claims to be: the fields of
    `request_submitted` with the shapes the inventory promises (SYSTEM.md).

    Anything at all can be published on that topic, so reading it is a step
    of its own rather than four subscripts that raise (ADR-0034).
    """

    id: str
    train: str
    depart: str
    dest: tuple[str, ...]


def readable_id(payload: object) -> str | None:
    """The id an answer would be addressed to, or None where there is none.

    Every rejection is addressed by id and broadcast, so a frame carrying no
    readable one is answered to nobody; it is dropped instead, and the trace
    line it already has is what keeps a client bug diagnosable (ADR-0034).
    """
    if not isinstance(payload, dict):
        return None
    rid = cast(Payload, payload).get("id")
    return rid if isinstance(rid, str) and rid else None


def submission(payload: Payload, rid: str) -> Submission | None:
    """The request the payload states, or None where it states none —
    `malformed`, the one structural reason."""
    train, depart, dest = (payload.get(key) for key in ("train", "depart", "dest"))
    if not isinstance(train, str) or not isinstance(depart, str):
        return None
    if not isinstance(dest, list):
        return None
    ends = cast(list[object], dest)
    if not all(isinstance(end, str) for end in ends):
        return None
    return Submission(rid, train, depart, tuple(cast(list[str], ends)))


class Dispatcher:
    def __init__(
        self, bus: Bus, layout: Layout, scenario: Scenario, strategy: LockingStrategy
    ) -> None:
        self._bus = bus
        self._strategy = strategy
        self._state = State(
            layout,
            {train: spec.length for train, spec in scenario.trains.items()},
            {},
            {},
            {},
        )
        for train, spec in scenario.trains.items():
            self._state.locks[spec.at] = train
            self._state.block_of[train] = spec.at
            bus.publish(
                "tc49/dispatch/lock_granted", {"train": train, "resources": [spec.at]}
            )
        self._pending: list[Request] = []
        self._seen_ids: set[str] = set()
        self._next_seq = 0
        self._phases = 0  # grant phases run; stamps admissions for grant order
        # (leaf, block) sensor events buffered since the last grant boundary.
        self._buffered: list[tuple[str, str]] = []
        self._aspects: dict[str, str] = {}  # last published, so only changes go
        self._allocation: Payload = {}  # likewise: the picture, when it moves
        self._publish_allocation()
        bus.subscribe("tc49/layout/+", self._on_layout)
        bus.subscribe("tc49/schedule/request_submitted", self._on_request)

    # -- live state, for the property tests' oracles ------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def pending(self) -> tuple[Request, ...]:
        return tuple(self._pending)

    # -- admission ---------------------------------------------------------

    def _on_request(self, topic: str, payload: Payload) -> None:
        """The one place a payload from outside is read, and nothing in it
        raises: the submitter may be a browser, and once the relay is deleted
        nothing stands in front of the dispatcher at all (ADR-0034)."""
        rid = readable_id(payload)
        if rid is None:  # nothing to address an answer to; the trace has it
            return
        if rid in self._seen_ids:  # idempotency: duplicates are dropped
            return
        self._seen_ids.add(rid)
        request = submission(payload, rid)
        if request is None:
            self._reject(rid, "malformed")
            return
        if request.train not in self._state.train_lengths:
            self._reject(rid, "unknown_train")
            return
        if self._names_no_such_block(request):
            self._reject(rid, "unknown_block")
            return
        expected = self._expected_block(request.train)
        if self._departs_elsewhere(request.depart, expected):
            self._reject(rid, "wrong_origin")
            return

        surviving: list[str] = []
        pruned: list[dict[str, str]] = []
        for end in request.dest:
            block = end.rpartition(".")[0]
            if block == expected:
                # Possibly degenerate — the request names the block the train
                # stands in, accepted whichever end it names (DISPATCH.md);
                # the first launch attempt decides.
                surviving.append(end)
            elif (
                self._state.train_lengths[request.train]
                > self._state.layout.blocks[block]
            ):
                pruned.append({"end": end, "reason": "no_fit"})
            elif end not in self._state.layout.end_connection:
                pruned.append({"end": end, "reason": "no_entry"})
            else:
                surviving.append(end)
        if not surviving:
            self._reject(
                rid,
                (
                    "no_fit"
                    if any(p["reason"] == "no_fit" for p in pruned)
                    else "no_entry"
                ),
            )
            return
        self._pending.append(
            Request(
                rid,
                request.train,
                request.depart,
                tuple(surviving),
                self._next_seq,
                self._phases,
            )
        )
        self._next_seq += 1
        self._bus.publish(
            "tc49/dispatch/request_admitted",
            {"id": rid, "dest": surviving, "pruned": pruned},
        )
        self._publish_allocation()

    def _reject(self, rid: str, reason: str) -> None:
        self._publish("request_rejected", {"id": rid, "reason": reason})

    def _names_no_such_block(self, request: Submission) -> bool:
        """Whether the request names track the layout does not have — its
        arrival blocks, and the departure block where it states one. A fact
        only the dispatcher holds, so it is answered rather than raised, and
        it is not `wrong_origin`: the train is not standing there, but
        neither is anything else."""
        blocks = [end.rpartition(".")[0] for end in request.dest]
        if "." in request.depart:
            blocks.append(request.depart.rpartition(".")[0])
        return any(block not in self._state.layout.blocks for block in blocks)

    def _expected_block(self, train: str) -> str | None:
        """Where the train stands, active route or not (#99) — None when an
        earlier pending request makes that a future dispatcher choice."""
        if any(req.train == train for req in self._pending):
            return None
        return self._state.block_of[train]

    def _departs_elsewhere(self, depart: str, expected: str | None) -> bool:
        """Whether a stated departure block disagrees with where the train
        stands. A bare end letter states no block, and an earlier pending
        request makes the block a future dispatcher choice; neither can
        disagree."""
        if "." not in depart or expected is None:
            return False
        return depart.rpartition(".")[0] != expected

    # -- the grant phase ---------------------------------------------------

    def _on_layout(self, topic: str, payload: Payload) -> None:
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "boundary":
            self._grant_phase()
        else:
            self._buffered.append((leaf, payload["block"]))

    def _grant_phase(self) -> None:
        self._phases += 1
        self._apply_sensors()
        state = self._state
        # Active trains first, by request arrival then train id (DISPATCH.md).
        for train in sorted(
            state.active, key=lambda t: (state.active[t].request.phase, t)
        ):
            active = state.active[train]
            if active.outstanding is not None:
                continue
            self._apply_move(active, self._strategy.grant(train, state))
        # A train's chained workings run in order: once one of them is left
        # pending — refused, or launched and now active — the rest of that
        # train's queue waits. Letting a later working overtake a refused one
        # would run the scenario out of order and from the wrong origin.
        # Across trains the scan ages (#34): a request refused N times is
        # tried before fresher ones, so a starved request gets first claim on
        # whatever just freed. A train's own chain order is preserved for
        # free — an untried later working has no refusals and a later seq.
        waiting: set[str] = set(state.active)
        for req in sorted(self._pending, key=aging_order):
            if req.train in waiting:
                continue
            origin = state.block_of[req.train]
            if any(end.rpartition(".")[0] == origin for end in req.arrivals):
                # Degenerate: already standing in an arrival block, whichever
                # end that arrival names. Empty route, complete in this phase.
                self._pending.remove(req)
                self._publish(
                    "route_chosen", {"id": req.id, "route": [origin], "k_tried": 0}
                )
                self._publish("request_completed", {"id": req.id})
                continue
            result = self._strategy.launch(req, origin, state)
            if result is None:
                self._pending.remove(req)
                self._publish(
                    "request_rejected", {"id": req.id, "reason": "unreachable"}
                )
            elif isinstance(result, Refused):
                waiting.add(req.train)
                req.refusals += 1
                self._publish(
                    "grant_refused",
                    {
                        "id": req.id,
                        "reason": result.reason,
                        "obstacles": result.obstacles,
                    },
                )
            else:
                waiting.add(req.train)
                self._launch(req, result)
        self._publish_aspects()
        self._publish_allocation()

    def _apply_sensors(self) -> None:
        """The buffered set, in canonical order — never delivery order."""
        state = self._state
        vacated = sorted(b for leaf, b in self._buffered if leaf == "block_vacated")
        occupied = sorted(b for leaf, b in self._buffered if leaf == "block_occupied")
        self._buffered.clear()
        for block in vacated:
            train = state.locks[block]
            move = state.active[train].outstanding
            assert move is not None and move.from_block == block
            del state.locks[block]
            del state.locks[move.transit]
            self._publish(
                "lock_released", {"train": train, "resources": [block, move.transit]}
            )
        for block in occupied:
            train = state.locks[block]
            active = state.active[train]
            active.outstanding = None
            state.block_of[train] = block
            if active.cur_index == len(active.route.blocks) - 1:
                del state.active[train]
                self._publish("request_completed", {"id": active.request.id})

    def _launch(self, req: Request, launched: Launched) -> None:
        self._pending.remove(req)
        self._publish(
            "route_chosen",
            {
                "id": req.id,
                "route": launched.route.interleaved(),
                "k_tried": launched.k_tried,
            },
        )
        self._publish(
            "lock_granted", {"train": req.train, "resources": launched.locked}
        )
        self._state.active[req.train] = Active(req, launched.route, 0, None)
        move = self._strategy.grant(req.train, self._state)
        assert isinstance(move, Move)  # the launch just granted the first increment
        self._apply_move(self._state.active[req.train], move)

    def _apply_move(self, active: Active, result: Move | Refused) -> None:
        if isinstance(result, Refused):
            self._publish(
                "grant_refused",
                {
                    "id": active.request.id,
                    "reason": result.reason,
                    "obstacles": result.obstacles,
                },
            )
            return
        for resources in (result.locked, result.ahead):
            # Two grants, not one of four: a grant is a transit with its far
            # block, and the second increment is a separate one (ADR-0029).
            if resources:
                self._publish(
                    "lock_granted",
                    {"train": active.request.train, "resources": resources},
                )
        self._align(result.transit)
        self._publish(
            "move_granted",
            {
                "id": active.request.id,
                "train": active.request.train,
                "transit": result.transit,
                "into": result.into,
                # Read off the locks the strategy has just taken, from where
                # the train still stands: cur_index advances below.
                "aspect": aspect_of(
                    locked_ahead(
                        self._state,
                        active.request.train,
                        active.route,
                        active.cur_index,
                    )
                ),
            },
        )
        active.outstanding = result
        active.cur_index += 1

    def _align(self, transit_id: str) -> None:
        """Set the connection to the transit, before the move that takes it.

        Setting the route is the dispatcher's responsibility — it answers for
        the route being free and correctly set up — so `align` is its command
        and not the driver's (ADR-0022). It carries the points the transit
        needs, read off the layout (ADR-0031), so the layout interface throws
        what it is told and holds no table of its own. Always `points`, `[]`
        where nothing needs throwing: the document is quiet, the wire explicit.
        """
        connection, _, transit = transit_id.partition(".")
        needed = self._state.layout.connections[connection].points.get(transit, ())
        self._publish(
            "align",
            {
                "connection": connection,
                "transit": transit,
                "points": [
                    {"addr": point.addr, "position": point.position} for point in needed
                ],
            },
        )

    def _publish_aspects(self) -> None:
        """The signalled ends, on a last-value topic, when any of them has
        changed. Every end each time rather than the ones that moved: a late
        subscriber wants the whole picture on connect, not the first change
        after it arrives (SYSTEM.md)."""
        shown = aspects(self._state)
        if shown != self._aspects:
            self._aspects = shown
            self._publish("state/aspects", {"aspects": shown})

    def _publish_allocation(self) -> None:
        """The run's picture, on a last-value topic, when any of what it
        carries has moved. Published from the two places that move it: a
        request joining the queue, and the grant phase that runs it."""
        picture = allocation(self._state, self._pending)
        if picture != self._allocation:
            self._allocation = picture
            self._publish("state/allocation", picture)

    def _publish(self, leaf: str, payload: Payload) -> None:
        self._bus.publish(f"tc49/dispatch/{leaf}", payload)
