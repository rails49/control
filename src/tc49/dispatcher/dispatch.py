"""Dispatcher: admission, queue, lock table, buffered sensors, grant phase.

Fully asynchronous at the bus boundary (SYSTEM.md, dispatcher footprint):
requests arrive as events, every fate is announced as an event, and the
request id is both correlation and idempotency key. Sensor events are
buffered until the boundary and treated as a set, so grants are a pure
function of the buffered set, never of delivery order (DISPATCH.md, time
model). Standing locks are seeded and published at startup — from the last
picture where the bus binding has kept one across a restart, and from the
scenario where it has not (#123). The locking discipline is the pluggable
strategy of locking.py.

It is also the sole payload authority (SYSTEM.md, dispatcher footprint):
anything at all may be published on the inbound topic, so admission reads a
payload rather than trusting one and never raises on what it finds — an
unreadable request is an answer where it can be addressed and a drop where
it cannot (ADR-0034).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

from tc49.dispatcher.locking import Launched, LockingStrategy, Move, Refused
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import Layout, block_of, end_on, leaving_end, opposite_end
from tc49.lib.payload import gesture
from tc49.lib.rejection import Reason
from tc49.lib.scenario import Scenario

ALLOCATION = "tc49/dispatch/state/allocation"


@dataclass
class Request:
    id: str
    train: str
    depart: str  # end, or bare letter for a chained request
    arrivals: tuple[str, ...]  # surviving arrival ends
    seq: int  # admission order; the pending queue's tie-break key
    phase: int  # grant phases run when admitted; the arrival-order key
    refusals: int = 0  # launch refusals so far; the aging key (#34)


def departure_end(layout: Layout, route: Route) -> str:
    """The end a train that has run `route` leaves its arrival block by: the
    other end of the one it entered through, or a terminal block's single
    connected end.

    `lib`'s rule, asked here by its second caller — the scheduler asks it of
    a train's facing (#145), the dispatcher of a route it chose itself.
    """
    return leaving_end(
        layout, opposite_end(end_on(layout, route.arrival_block, route.transits[-1]))
    )


def resolve_depart(depart: str, origin: str) -> str:
    """A bare end letter (chained request) resolves against the origin."""
    return depart if "." in depart else f"{origin}.{depart}"


def departs_elsewhere(depart: str, expected: str | None) -> bool:
    """Whether a stated departure block disagrees with the block the train
    departs from. A bare end letter states no block and so cannot disagree,
    and neither can anything while an earlier pending request leaves that
    block a future dispatcher choice (`expected` is None). Admission and the
    launch stage both ask it, of the origin each by then has, so one rule
    serves both (#146)."""
    if "." not in depart or expected is None:
        return False
    return block_of(depart) != expected


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
    # train -> the end it will leave by once the last route committed for it
    # is done. Written when a route is chosen, since a route is fixed from
    # then on (ADR-0002), and so already true of a train still running one.
    leaving: dict[str, str] = field(default_factory=dict[str, str])
    # train -> the transit it is crossing: written at the grant, dropped when
    # the sensor says it arrived. `block_of` already names the far block,
    # `cur_index` having advanced at the grant, so the transit is the whole of
    # what says a train is between two blocks rather than standing in one
    # (#123). It restores across a restart with no route behind it, which is
    # what makes it a placement hint and not a resumed move.
    crossing: dict[str, str] = field(default_factory=dict[str, str])

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


def departure(origin: str, depart: str, leaving: str | None) -> str | None:
    """The end a working leaves `origin` by, or None where the end it states
    is one the dispatcher can neither use nor correct.

    Normally the end the request states, resolved against `origin` where it
    states only a letter — the device a chained working already has for a
    block it could not know (LAYOUT.md). Where it states another block
    altogether it was composed against the block its train stood in at the
    time of asking, and the origin was then a future dispatcher choice; the
    dispatcher replaces it with `leaving`, the end the route it chose itself
    leaves the train facing (#135). Routes are strict pass-throughs
    (ADR-0001), so that end is a fact about the route and not about the
    stock, and facing stays the scheduler's (ADR-0019).

    Where the train ran no route there is nothing to replace it with — the
    work ahead of it was degenerate, or was itself refused — and the working
    is refused rather than routed from a block the train is not in (#146).
    """
    if not departs_elsewhere(depart, origin):
        return resolve_depart(depart, origin)
    return leaving


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
        end = end_on(
            state.layout,
            active.route.blocks[standing],
            active.route.transits[standing],
        )
        shown[end] = aspect_of(locked_ahead(state, train, active.route, standing))
    return shown


def allocation(state: State, pending: Sequence[Request]) -> Payload:
    """The run's picture: where every train stands and which of them are
    crossing a transit, the lock table with its holders, and every request
    still alive — carrying the route a committed one is running.

    A crossing train appears in both maps: `trains` goes on naming the block
    the sensors last confirmed it in, and `crossing` names the transit that
    is taking it out of there. The transit is the whole of the mark — there
    is no suspect flag — and it is what a restarted session restores as a
    placement hint, with no route and no request behind it (#123).

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
        "crossing": dict(sorted(state.crossing.items())),
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
    Read rather than trusted, in `lib.payload`'s terms.
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
    `malformed`, the one structural reason.

    A request is a gesture with an id and a departure end (ADR-0036), so the
    gesture is read where the scheduler reads one and the departure end,
    which only a request carries, is read here."""
    wanted = gesture(payload)
    depart = payload.get("depart")
    if wanted is None or not isinstance(depart, str):
        return None
    return Submission(rid, wanted.train, depart, wanted.arrivals)


class Dispatcher:
    def __init__(
        self, bus: Bus, layout: Layout, scenario: Scenario, strategy: LockingStrategy
    ) -> None:
        self._bus = bus
        self._strategy = strategy
        # The last picture, where the bus binding held one across a restart:
        # the dispatcher's own state topic, found waiting exactly as it would
        # be against a broker that outlived the app (#123). Read here rather
        # than through `subscribe`, because placement has to be settled before
        # the standing locks below are published, and a subscription delivers
        # at the drain.
        picture = bus.last_values.get(ALLOCATION, {})
        placed, crossing = picture.get("trains", {}), picture.get("crossing", {})
        self._state = State(
            layout,
            {train: spec.length for train, spec in scenario.trains.items()},
            {},
            {},
            {},
            # Adoption is selective: `locks` and `requests` are left behind,
            # the lock table below being rebuilt one block per train exactly
            # as a cold start builds it, the queue coming back empty and no
            # request id resuming (ADR-0033). Stock stays the scenario's, so
            # a train it does not carry is not one this session has and the
            # picture's word for it is dropped.
            crossing={
                train: transit
                for train, transit in crossing.items()
                if train in scenario.trains
            },
        )
        for train, spec in scenario.trains.items():
            at = placed.get(train, spec.at)
            self._state.locks[at] = train
            self._state.block_of[train] = at
            bus.publish(
                "tc49/dispatch/lock_granted", {"train": train, "resources": [at]}
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
            self._reject(rid, Reason.MALFORMED)
            return
        if request.train not in self._state.train_lengths:
            self._reject(rid, Reason.UNKNOWN_TRAIN)
            return
        if self._names_no_such_block(request):
            self._reject(rid, Reason.UNKNOWN_BLOCK)
            return
        expected = self._expected_block(request.train)
        if departs_elsewhere(request.depart, expected):
            self._reject(rid, Reason.WRONG_ORIGIN)
            return

        surviving: list[str] = []
        pruned: list[dict[str, str]] = []
        for end in request.dest:
            block = block_of(end)
            if block == expected:
                # Possibly degenerate — the request names the block the train
                # stands in, accepted whichever end it names (DISPATCH.md);
                # the first launch attempt decides.
                surviving.append(end)
            elif (
                self._state.train_lengths[request.train]
                > self._state.layout.blocks[block]
            ):
                pruned.append({"end": end, "reason": Reason.NO_FIT})
            elif end not in self._state.layout.end_connection:
                pruned.append({"end": end, "reason": Reason.NO_ENTRY})
            else:
                surviving.append(end)
        if not surviving:
            self._reject(
                rid,
                (
                    Reason.NO_FIT
                    if any(p["reason"] == Reason.NO_FIT for p in pruned)
                    else Reason.NO_ENTRY
                ),
            )
            return

        launch = self._launch_to_come(request)
        if launch is not None:
            origin, depart = launch
            reachable: list[str] = []
            for end in surviving:
                # An end in the origin block is the degenerate case: it has no
                # route to look for, and the launch stage decides it.
                if block_of(end) == origin or self._reaches(
                    origin, depart, end, request.train
                ):
                    reachable.append(end)
                else:
                    pruned.append({"end": end, "reason": Reason.UNREACHABLE})
            surviving = reachable
            if not surviving:
                self._reject(rid, Reason.UNREACHABLE)
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

    def _reject(self, rid: str, reason: Reason) -> None:
        self._publish("request_rejected", {"id": rid, "reason": reason})

    def _names_no_such_block(self, request: Submission) -> bool:
        """Whether the request names track the layout does not have — its
        arrival blocks, and the departure block where it states one. A fact
        only the dispatcher holds, so it is answered rather than raised, and
        it is not `wrong_origin`: the train is not standing there, but
        neither is anything else."""
        blocks = [block_of(end) for end in request.dest]
        if "." in request.depart:
            blocks.append(block_of(request.depart))
        return any(block not in self._state.layout.blocks for block in blocks)

    def _has_pending(self, train: str) -> bool:
        """Whether a working of the train's own is still queued, which is
        what makes both where it will stand and where it will depart from a
        future dispatcher choice."""
        return any(req.train == train for req in self._pending)

    def _expected_block(self, train: str) -> str | None:
        """Where the train stands, active route or not (#99) — None when an
        earlier pending request makes that a future dispatcher choice."""
        return None if self._has_pending(train) else self._state.block_of[train]

    def _launch_to_come(self, request: Submission) -> tuple[str, str] | None:
        """The origin and departure end the working will launch from, or None
        where an earlier working of its own train leaves them a future
        dispatcher choice.

        Behind an **active** route both are already settled: a route is fixed
        once chosen (ADR-0002), so the block it arrives at is known and the
        end it leaves the train facing with it. Behind a still **pending**
        one nothing is, which is the only case DISPATCH.md's deferral to the
        launch stage was ever about (#135).
        """
        if self._has_pending(request.train):
            return None
        active = self._state.active.get(request.train)
        origin = (
            active.route.arrival_block
            if active
            else self._state.block_of[request.train]
        )
        depart = departure(
            origin, request.depart, self._state.leaving.get(request.train)
        )
        return None if depart is None else (origin, depart)

    def _reaches(self, origin: str, depart: str, end: str, train: str) -> bool:
        """Whether any route out of `origin` by `depart` arrives at `end`.

        A pure function of layout, origin, departure end, arrival end and
        train length: `candidates` prunes only on fit and on the simple-path
        rule, congestion enters solely as a sort key and `k` only caps the
        list, so one route is all this has to find and nothing between here
        and the launch can change the answer.
        """
        return bool(
            candidates(
                self._state.layout,
                origin,
                depart,
                (end,),
                self._state.train_lengths[train],
                1,
            )
        )

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
            depart = departure(origin, req.depart, state.leaving.get(req.train))
            if depart is None:
                # The stated end names a block the train is not in and no
                # route of its own supplies a better one, so there is nothing
                # to route from: the enumerator walks from the departure end
                # while recording the origin as the route's first block, and
                # an end off the origin returns a route claiming to start
                # where the train stands and leave somewhere else (#146).
                # Asked ahead of the degenerate arrival below, as admission
                # asks it ahead of pruning: a stale working is refused, not
                # completed because the train happens to be there already.
                self._pending.remove(req)
                self._reject(req.id, Reason.WRONG_ORIGIN)
                continue
            if any(block_of(end) == origin for end in req.arrivals):
                # Degenerate: already standing in an arrival block, whichever
                # end that arrival names. Empty route, complete in this phase.
                self._pending.remove(req)
                self._publish(
                    "route_chosen", {"id": req.id, "route": [origin], "k_tried": 0}
                )
                self._publish("request_completed", {"id": req.id})
                continue
            result = self._strategy.launch(req, origin, depart, state)
            if result is None:
                self._pending.remove(req)
                self._reject(req.id, Reason.UNREACHABLE)
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
            del state.crossing[train]
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
        # A route is fixed once chosen (ADR-0002), so the end it leaves the
        # train facing is settled here rather than on arrival — which is what
        # lets a working dragged in mid-route be answered while it is asked.
        self._state.leaving[req.train] = departure_end(
            self._state.layout, launched.route
        )
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
        self._state.crossing[active.request.train] = result.transit
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
