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
from tc49.lib.inventory import HELD, ON, RUNNING
from tc49.lib.layout import Layout, block_of, end_on, leaving_end, opposite_end
from tc49.lib.payload import gesture, placement, run_state
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
    # the sensor says it arrived, and so exactly the trains with an
    # outstanding move. `block_of` goes on naming the block the sensors last
    # confirmed, so this is the whole of what says a train is between two
    # blocks rather than standing in one (#123). It restores across a restart
    # with no route behind it, which is what makes it a placement hint and
    # not a resumed move.
    crossing: dict[str, str] = field(default_factory=dict[str, str])
    # `held` or `running`: whether the dispatcher may commit anything at the
    # next boundary (ADR-0037). A brake and not an emergency stop — a move
    # already granted is not retractable — so it gates the grant phase and
    # the aspects, and nothing else. State rather than a flag on the
    # dispatcher because `aspects()` answers off it.
    run: str = RUNNING
    # `on`, `stopped` or `off`: what the layout last said about whether a
    # train may move at all (ADR-0041). Read only as "not `on`", the two ways
    # of standing still differing for the person recovering and not here.
    # `on` until the layout says otherwise, which is the same opening the run
    # takes: the binding states it from its constructor, so the word arrives
    # before the first boundary.
    power: str = ON
    # block -> whether the layout last reported it occupied. What the
    # detectors have *said*, which is not the same as what the dispatcher has
    # acted on: a block enters this from the report that named it, while the
    # buffered set below is about when a grant may follow (#153). Only blocks
    # the layout has actually reported on are keys — silence is not a clear
    # reading, and a binding that reports nothing disputes nothing rather
    # than the whole railroad.
    reported: dict[str, bool] = field(default_factory=dict[str, bool])

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

    **A held run puts every signal to stop.** An aspect answers "may the
    train in this block leave via this end", and while held the answer is no
    at every end (ADR-0037). Reading the locks instead would show `clear`
    over a railroad that is going nowhere, and on the physical layout would
    leave a lineside signal green over dead track. It qualifies ADR-0025
    rather than superseding it: the depth still decides which of the other
    two shows.
    """
    shown = {end: "stop" for end in sorted(state.layout.end_connection)}
    if state.run == HELD:
        return shown
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


def disputed(state: State) -> Payload:
    """Where the placement and the detectors contradict each other: trains
    standing in a block that reads clear, and blocks that read occupied with
    nothing claiming them (#153).

    On power-up the detectors assert straight away — anonymously, so no
    reading names a train — at exactly the moment the placement is least
    trustworthy: it is where the last session *believed* the railroad was,
    and the steel has stood unwatched since (CONTEXT.md, recovery). Naming
    the two contradictions turns walking the whole railroad into checking a
    handful of trains. It **resolves** nothing: the check points, and a
    person ends every entry with a `placement_wanted`.

    **Only while held**, which is the moment it is about: before anything
    commits, over a placement nobody has looked at. A running dispatcher's
    placement is what its sensors have just told it, so the two agree by
    construction and a comparison would catch nothing but itself mid-transit.
    Releasing therefore empties the set rather than freezing it — the person
    has decided, and a set left standing would go on disputing a railroad
    they accepted.

    Only blocks `reported` carries take part, which is the load-bearing rule:
    a block the layout has said nothing about is not clear, it is unknown.

    Two exclusions, both of them the picture agreeing with itself rather
    than a dispute suppressed:

    - A **crossing** train stands in no block. `block_of` goes on naming the
      block the sensors last confirmed it in and `crossing` says it has left
      it, so a clear reading there is what the picture already claims. That
      train is in any case the one a person is sent to first, drawn on its
      connection (#154).
    - A block the dispatcher holds a **lock** on is claimed. At the moment
      this runs the lock table is one standing lock per placed train and
      nothing else — the queue does not restore (#123) — so this is the
      placement read off the table that carries it. Mid-run it also covers
      the block a train has been granted a move into, which reads occupied
      the moment it arrives and is not a stray.
    """
    if state.run != HELD:
        return {"trains": [], "blocks": []}
    return {
        "trains": sorted(
            train
            for train, block in state.block_of.items()
            if train not in state.crossing and state.reported.get(block) is False
        ),
        "blocks": sorted(
            block
            for block, occupied in state.reported.items()
            if occupied and block not in state.locks
        ),
    }


def restored(
    picture: Payload, scenario: Scenario
) -> tuple[dict[str, str], dict[str, str]]:
    """Placement and crossing hints off the last picture the bus kept across
    a restart, or the scenario's own placement where there is none (#123).

    Adoption is **selective**: `trains` and `crossing` are taken, `locks` and
    `requests` left behind — the lock table is rebuilt one block per train
    exactly as a cold start builds it, the queue comes back empty and no
    request id resumes (ADR-0033). Stock stays the scenario's, so a train it
    does not carry is not one this session has and the picture's word for it
    is dropped, and a train the picture does not name falls back to its
    placement: one added since the last run is a cold start of one.

    It is also taken **per train** (#164). Where the two contradict each
    other only the trains in the collision pay for it: the fallback can put a
    train the picture never named in the very block the picture stands
    another in, and that is a one-block disagreement, not a reason to send a
    whole railroad back to the document. What the all-or-nothing rule was
    protecting holds train by train anyway — no block ends with two trains in
    it, and no train ends standing in a block nothing holds, which is the
    standing lock every parked train always has (CONTEXT.md).

    So a contested block goes to the train with **fewer answers**: one the
    picture does not name has only the document and nowhere else to stand,
    while one it does name still has its own starting block to fall back to.
    A train both of whose answers are taken is placed by neither and comes up
    in the closet (ADR-0039) — nothing is resolved automatically, and #153 is
    what points a person at what is left. A train that did not keep its
    restored position loses its crossing hint with it: the hint names a
    transit the placement it came with was consistent with, and says nothing
    about the block the document put the train in.
    """
    cold = {train: spec.at for train, spec in scenario.trains.items()}
    named: Payload = picture.get("trains", {})
    pictured = {train: named[train] for train in cold if train in named}
    settled: dict[str, str] = {}

    def place(train: str, block: str) -> None:
        if block not in settled.values():
            settled[train] = block

    for train, at in cold.items():  # named by no picture: the document
        if train not in pictured:
            place(train, at)
    for train, at in pictured.items():  # the picture's word, where it is free
        place(train, at)
    for train in pictured:  # pushed off it: the document, or nowhere
        if train not in settled:
            place(train, cold[train])
    # Back into the document's order, whatever order they were settled in:
    # the standing locks are published one train at a time from this.
    standing = {train: settled[train] for train in cold if train in settled}
    kept = {train for train, at in pictured.items() if standing.get(train) == at}
    return standing, {
        train: transit
        for train, transit in picture.get("crossing", {}).items()
        if train in kept
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
        standing, crossing = restored(picture, scenario)
        self._state = State(
            layout,
            {train: spec.length for train, spec in scenario.trains.items()},
            {},
            {},
            {},
            crossing=crossing,
            # **A restored session comes up held** (#154), which is the whole
            # point of the hold on a real railroad: the steel is wherever the
            # last session left it, and coming up running on the strength of a
            # picture nobody has looked at is the failure the hold exists to
            # prevent. The retained `state/run` is not what decides it — a
            # session cut while running left `running` waiting on that topic —
            # and neither is how much of the picture was taken: a train the
            # document overruled, or that adoption placed nowhere at all
            # (`restored`), is one more thing to come and look at rather than
            # a reason to start running. A cold session has no picture and
            # comes up running.
            run=HELD if picture else RUNNING,
        )
        for train, at in standing.items():
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
        self._disputed: Payload = {}  # and what the detectors dispute
        # The opening statement is the whole of what the dispatcher holds, in
        # the order a grant phase says it. Aspects are in it because a restart
        # has a previous value on that topic too: the last session's
        # `approach` for a route this one did not restore would stand until
        # the first grant phase, and a panel joining in that window draws a
        # clear road nothing holds a lock on. The run state opens it for the
        # same reason and one step earlier: it is the frame the rest is read
        # in, and a joining client is served the word rather than left to
        # read one out of an absence (ADR-0032). The disputed set closes it
        # for the same reason again: nothing has been reported yet, so the
        # set is empty, and saying so is what clears whatever the last
        # session left standing on that topic.
        self._publish_run()
        self._publish_aspects()
        self._publish_allocation()
        self._publish_disputed()
        bus.subscribe("tc49/layout/#", self._on_layout)
        bus.subscribe("tc49/schedule/request_submitted", self._on_request)
        bus.subscribe("tc49/ui/#", self._on_gesture)

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
        if request.train not in self._state.block_of:
            # On the roster but not on the layout: the closet (ADR-0039), which
            # adoption reaches when a train's picture block and its starting
            # block are both taken (#164). Answered here rather than guarded at
            # each launch lookup, because this is the only way in: nothing
            # unplaces a train once the constructor has run, so a request that
            # gets past this line names a train with a block, and `_pending`
            # holds none that did not.
            self._reject(rid, Reason.NO_ORIGIN)
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

    # -- gestures ----------------------------------------------------------

    def _on_gesture(self, topic: str, payload: Payload) -> None:
        """A person's action on a page, on the leaves the dispatcher owns.

        `request_wanted` and `reversal_wanted` are the scheduler's and pass
        by here unread — the filter is the role, as every consumer's is
        (SYSTEM.md, rule 3). What it cannot act on it drops, in silence and
        to the trace: a gesture carries no id and there is nothing to address
        an answer to (ADR-0034).
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "run_wanted":
            self._set_run(payload)
        elif leaf == "placement_wanted":
            self._place(payload)

    def _set_run(self, payload: Payload) -> None:
        """Hold the run, or release it.

        Releasing sets the state and nothing else: the next
        `tc49/layout/boundary` runs an ordinary grant phase. Granting from
        here would make the boundary no longer the sole trigger, and would
        grant against a sensor buffer filled over part of a period, which is
        the one thing the time model rules out (DISPATCH.md). The cost is up
        to one period between the press and the first wheel turning.

        A release is **refused while the track has no power**, dropped in
        silence and to the trace as every other gesture the dispatcher cannot
        act on is (ADR-0034). Releasing into dead rails would choose routes,
        grant moves and publish `cross` over track nothing can move on, and
        strand the next train exactly as the cut stranded the first
        (ADR-0041). A hold is honoured whatever the power is doing: it asks
        for less, and there is no state of the railroad in which a person may
        not ask for it.
        """
        wanted = run_state(payload)
        if wanted is None:
            return
        if wanted == RUNNING and self._state.power != ON:
            return
        self._move_run(wanted)

    def _move_run(self, wanted: str) -> None:
        """Where the run stands, however it was moved there: a person's
        gesture, or the layout saying the track has no power. One path, so
        the two cannot come to publish different things — and a value that
        changes nothing publishes nothing."""
        if wanted == self._state.run:
            return
        self._state.run = wanted
        self._publish_run()
        self._publish_aspects()
        # Held, and the detectors are asked what they make of the placement;
        # released, and the set empties. Not a dispute swept away: a person
        # releasing has decided the railroad is as they want it, and a
        # running dispatcher's placement follows the sensors move by move, so
        # there is nothing left for the check to compare (#153).
        self._publish_disputed()

    def _place(self, payload: Payload) -> None:
        """Where a train actually stands, said by the person who can see it.

        Accepted only when every precondition holds: the run is held, the
        train is known, the block exists and is free of every claim, the
        train fits it, and the train has no request in flight. The last
        mirrors `reversal_wanted` and adds a worse reason of its own — on release the
        grant phase launches from `block_of`, so a pending request would
        depart from wherever the train was just put, having been admitted
        against the block it was in when it was asked for.

        Where the train stands *now* is no precondition at all: one adoption
        placed nowhere (`restored`) is exactly the train a person has to say
        something about.

        Having accepted, the dispatcher moves the train's standing lock and
        announces `train_placed`. That event is the ledger line for a
        placement: a `lock_released` and a `lock_granted` would say a route
        gave a block up and took another, which is not what happened — a hand
        lifted a locomotive, and the fact has its own leaf so a reader can
        tell the two apart.
        """
        wanted = placement(payload)
        state = self._state
        if wanted is None or state.run != HELD:
            return
        if wanted.train not in state.train_lengths:
            return
        if wanted.block not in state.layout.blocks:
            return
        if not self._free(wanted.block):
            return
        if state.train_lengths[wanted.train] > state.layout.blocks[wanted.block]:
            return
        if self._has_pending(wanted.train) or wanted.train in state.active:
            return
        # A train adoption placed nowhere holds no standing lock and has none
        # to give up: it is in the closet, and this gesture is what takes it
        # out (ADR-0039, #164). Placing one is otherwise the same act.
        standing = state.block_of.get(wanted.train)
        if standing is not None:
            del state.locks[standing]
        state.locks[wanted.block] = wanted.train
        state.block_of[wanted.train] = wanted.block
        # Whatever the last picture said this train was crossing, it is not
        # crossing it now: a person has said where it stands. The hint is
        # restored with no route behind it (`restored`), so this train is
        # exactly the one whose hint nothing else will ever clear — and
        # affirming the block the dispatcher already believes in is not a way
        # out, that block not being free.
        state.crossing.pop(wanted.train, None)
        self._publish("train_placed", {"train": wanted.train, "block": wanted.block})
        self._publish_allocation()
        # The entry the person just resolved leaves the set, which is what
        # empties it as the railroad is walked (#153).
        self._publish_disputed()

    def _free(self, block: str) -> bool:
        """Whether nothing else has a claim on `block`.

        Both claims a route carries, not just the stronger one: a resource is
        **committed** when it is on a route the dispatcher has chosen and not
        yet locked, and that is a claim (CONTEXT.md). Under `FullRoute` the
        two sets coincide, since a launch locks the whole route; under
        `Incremental` a fixed route runs on ahead of its locks, and reading
        the lock table alone would call those blocks free.

        Placing a train into one strands the working that owns it: the route
        is fixed (ADR-0002), the placed train is idle and its standing lock
        is therefore a permanent obstacle (SAFETY.md), and nothing cancels a
        request — so the committed train is refused `unsafe` at every
        boundary for the rest of the session.
        """
        if block in self._state.locks:
            return False
        return not any(
            block in active.route.blocks[active.cur_index :]
            for active in self._state.active.values()
        )

    # -- the grant phase ---------------------------------------------------

    def _on_layout(self, topic: str, payload: Payload) -> None:
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "boundary":
            self._grant_phase()
        elif leaf == "power":
            self._on_power(payload)
        else:
            block = payload["block"]
            self._buffered.append((leaf, block))
            # Recorded where it arrives rather than where the buffer is
            # applied. A reading is a fact the moment the layout states it,
            # and the dispute it may settle commits nothing — the buffer
            # exists so that *grants* are a function of a whole period's
            # sensors (DISPATCH.md, time model), which is a rule about
            # acting. It also has to be so for the case this is for: the
            # detectors asserting on power-up explain no move the dispatcher
            # granted, and a boundary is not where such a reading survives
            # (SYSTEM.md, the standing assumption).
            self._state.reported[block] = leaf == "block_occupied"
            self._publish_disputed()

    def _on_power(self, payload: Payload) -> None:
        """What the layout says about whether a train may move at all.

        Anything but `on` **holds the run**, by the path a person's HOLD
        takes: the dispatcher commits nothing more, and every signalled end
        shows `stop` rather than going on showing `clear` over track with no
        volts in it (ADR-0041). Which of `stopped` and `off` it is changes
        nothing here — the two differ for the person recovering, who clears an
        emergency stop or switches a supply back on, and the panel is where
        that is said.

        Power **returning** to `on` releases nothing. That is the bar the hold
        exists for: an explicit GO before anything moves, whatever the rails
        did in the meantime, and the same guarantee the hardware gives at
        power-up by coming back idle.

        What it cannot do is undo the cut. A train granted a move that no
        sensor will ever answer keeps its locks and its `crossing` entry, and
        every train waiting on those resources waits with it, until somebody
        restarts the session — the hold is a brake and not an emergency stop,
        and nothing on the bus retracts a `cross` already sent.
        """
        self._state.power = payload["power"]
        if self._state.power != ON:
            self._move_run(HELD)

    def _grant_phase(self) -> None:
        """The boundary's work: the buffered sensors, then the grants.

        While the run is held the sensors are applied and the phase stops
        there (ADR-0037). The hold is a brake and not an emergency stop —
        nothing on the bus retracts a `cross` already sent — so an
        outstanding move still completes and releases its locks, and what is
        withheld is everything that would commit something new. `_phases`
        keeps counting either way: a held run is still a run, and the count
        is what stamps an admission with the grant order it joined at.
        """
        self._phases += 1
        self._apply_sensors()
        if self._state.run == RUNNING:
            self._grant()
        self._publish_aspects()
        self._publish_allocation()
        # The sensors just applied moved the placement the check compares
        # against: an outstanding move completing while held is the one thing
        # that resolves a dispute without a person saying anything.
        self._publish_disputed()

    def _grant(self) -> None:
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

    def _publish_run(self) -> None:
        """Whether the run is held or running, on a last-value topic. The
        word carries a value and not a boolean because the ordinary-shutdown
        drain will add `draining` as a third one (#123)."""
        self._publish("state/run", {"run": self._state.run})

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

    def _publish_disputed(self) -> None:
        """What the detectors make of the placement, on a last-value topic,
        when it moves — the panel points a person at it, and a panel joining
        later must find it there (ADR-0032). Published from every place that
        moves either side of the comparison: a reading arriving, the sensors
        applied at a boundary, a placement, and the hold itself."""
        found = disputed(self._state)
        if found != self._disputed:
            self._disputed = found
            self._publish("state/disputed", found)

    def _publish(self, leaf: str, payload: Payload) -> None:
        self._bus.publish(f"tc49/dispatch/{leaf}", payload)
