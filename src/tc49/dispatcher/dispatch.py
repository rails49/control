"""Dispatcher: admission, queue, lock table, sensor roles, grant sweep.

Fully asynchronous at the bus boundary (SYSTEM.md, dispatcher footprint):
requests arrive as events, every fate is announced as an event, and the
request id is both correlation and idempotency key. The dispatcher grants on
the events that arrive (ADR-0047): a sensor reading is applied where it
lands, and a **sweep** — one grant pass over the active trains and the whole
pending queue — runs wherever the lock table or the waiting set changes: a
request admitted, a vacated block releasing what a move held, the run
released. Every grant is `safe()`-checked before it commits, so arrival
order picks among safe options and never reaches an unsafe state.
Standing locks are seeded and published at startup — from the last
picture where the bus binding has kept one across a restart, and from the
placement the run was built with where it has not (#123). The locking
discipline is the pluggable strategy of locking.py.

It is also the sole payload authority (SYSTEM.md, dispatcher footprint):
anything at all may be published on a topic it declares, so admission reads a
payload rather than trusting one and never raises on what it finds — an
unreadable request is an answer where it can be addressed and a drop where
it cannot (ADR-0034). Who sent one is not asked and is nowhere to be read:
`tc49/dispatch/request_submitted` names the dispatcher that answers it, and a
second scheduler submitting alongside the first needs no change here
(SYSTEM.md, rule 4).

The whole of what arrives is read that way (#260). Two filters: the requests
this app answers — `request_submitted`, `run_wanted`, `placement_wanted` and
`cancel_wanted`, from the ui, the scheduler, or a second scheduler introduced
later — and what
the layout interface observes, on a filter that also carries the `align` and
`move` commands, which name the layout and are passed by unread. Every leaf
goes through a reader in `lib.payload` and nothing subscripts a frame it has
not read. The one thing left that could take the app off the bus was a sensor
reading no granted move accounts for; it holds the run instead (ADR-0048).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from tc49.dispatcher.locking import Launched, LockingStrategy, Move, Refused
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.bus import Bus, Payload
from tc49.lib.cancellation import Reason as Cancellation
from tc49.lib.inventory import HELD, ON, RUNNING
from tc49.lib.layout import Layout, block_of, departure_end, end_on
from tc49.lib.payload import (
    gesture,
    named_train,
    occupancy,
    placement,
    power,
    readable_id,
    run_state,
)
from tc49.lib.rejection import Reason
from tc49.lib.roster import Roster

# The two state topics named in full, because each is read as well as
# written: the allocation by a dispatcher coming back up, and either by a
# test seeding the file a session comes up on.
ALLOCATION = "tc49/dispatch/state/allocation"
ASPECTS = "tc49/dispatch/state/aspects"


@dataclass
class Request:
    id: str
    train: str
    depart: str  # end, or bare letter for a chained request
    arrivals: tuple[str, ...]  # surviving arrival ends
    seq: int  # admission order; the pending queue's tie-break key
    phase: int  # sweeps run when admitted; the arrival-order key
    refusals: int = 0  # launch refusals so far; the aging key (#34)
    # Whether the request has been cancelled while a move of its own was
    # outstanding: nothing further is granted for it, and it retires as
    # `request_cancelled` when that move's sensors finish (ADR-0049).
    cancelled: bool = False


def resolve_departure(depart: str, origin: str) -> str:
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
    # train -> its length: the railroad's **roster**, and the whole of what
    # the dispatcher knows about stock. Being in it is what makes a train
    # **known**, which is separate from being **placed** — a request naming a
    # train that is not here is answered `unknown_train`, and one naming a
    # train that is here and not in `block_of` is answered `no_origin`
    # (ADR-0039).
    roster: dict[str, int]
    locks: dict[str, str]  # resource -> holding train
    block_of: dict[str, str]  # train -> block it stands in (or last parked)
    active: dict[str, Active]
    # train -> the end it will leave by once the last route committed for it
    # is done. Written when a route is chosen, since a route is fixed from
    # then on (ADR-0002), and so already true of a train still running one.
    departure: dict[str, str] = field(default_factory=dict[str, str])
    # train -> the transit it is crossing: written at the grant, dropped when
    # the sensor says it arrived, and so exactly the trains with an
    # outstanding move. `block_of` goes on naming the block the sensors last
    # confirmed, so this is the whole of what says a train is between two
    # blocks rather than standing in one (#123). It restores across a restart
    # with no route behind it, which is what makes it a placement hint and
    # not a resumed move.
    crossing: dict[str, str] = field(default_factory=dict[str, str])
    # `held` or `running`: whether the dispatcher may commit anything
    # (ADR-0037). A brake and not an emergency stop — a move already granted
    # is not retractable — so it gates the sweep's grant pass and the
    # aspects, and nothing else. State rather than a flag on the dispatcher
    # because `aspects()` answers off it.
    run: str = RUNNING
    # `on`, `stopped` or `off`: what the layout last said about whether a
    # train may move at all (ADR-0041). Read only as "not `on`", the two ways
    # of standing still differing for the person recovering and not here.
    # `on` until the layout says otherwise, which is the same opening the run
    # takes: the binding states it from its constructor, so the value arrives
    # before anything is granted.
    power: str = ON
    # block -> whether the layout last reported it occupied: the level each
    # detector last stated, which is what makes an at-least-once repeat a
    # no-op (ADR-0047), and what the dispute check compares (#153). Only blocks
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

    def free(self, block: str) -> bool:
        """Whether nothing at all has a claim on `block`.

        Both claims a route carries, not just the stronger one: a resource is
        **committed** when it is on a route the dispatcher has chosen and not
        yet locked, and that is a claim (CONTEXT.md). Under `FullRoute` the
        two sets coincide, since a launch locks the whole route; under
        `Incremental` a fixed route runs on ahead of its locks, and reading
        the lock table alone would call those blocks free.

        Placing a train into one strands the request that owns it: the route
        is fixed (ADR-0002), and the placed train is idle, so its standing
        lock is a permanent obstacle (SAFETY.md) and the committed train is
        refused `unsafe` at every sweep for the rest of the session. That is
        why the placement's *own* request is cancelled before this is asked
        (ADR-0049) — the cancellation releases what that train held, and what
        is left here is another train's claim, which a placement may not walk
        into.
        """
        if block in self.locks:
            return False
        return not any(
            block in active.route.blocks[active.cur_index :]
            for active in self.active.values()
        )


def effective_departure(origin: str, depart: str, remembered: str | None) -> str | None:
    """The end the dispatcher will actually route from, or None where the end
    the request states is one it can neither use nor correct: what a request
    *stated* turned into what is *used*.

    Normally the end the request states, resolved against `origin` where it
    states only a letter — the device a chained request already has for a
    block it could not know (LAYOUT.md). Where it states another block
    altogether it was composed against the block its train stood in at the
    time of asking, and the origin was then a future dispatcher choice; the
    dispatcher replaces it with `remembered`, the end the route it chose
    itself leaves the train facing (`State.departure`, #135). Routes are
    strict pass-throughs (ADR-0001), so that end is a fact about the route and
    not about the stock, and facing stays the scheduler's (ADR-0019).

    Where the train ran no route there is nothing to replace it with — the
    work ahead of it was degenerate, or was itself refused — and the request
    is refused rather than routed from a block the train is not in (#146).
    """
    if not departs_elsewhere(depart, origin):
        return resolve_departure(depart, origin)
    return remembered


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
    return "caution" if depth else "stop"


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


@dataclass(frozen=True)
class Adopted:
    """What a restart takes from the last picture (`restored`)."""

    standing: dict[str, str]  # train -> the block it comes up in
    crossing: dict[str, str]  # train -> the transit it was crossing


def restored(picture: Payload, roster: Roster, cold: dict[str, str]) -> Adopted:
    """Placement and crossing hints off the last picture the bus kept across
    a restart, or the run's own `cold` placement where there is none (#123).

    Adoption is **selective**: `trains` and `crossing` are taken, `locks` and
    `requests` left behind. The lock table is rebuilt one block per train as a
    cold start builds it, the queue comes back empty, and no request id
    resumes (ADR-0033). Stock stays the **roster**'s, so the picture's word
    for a train it does not carry is dropped, and a train the picture does not
    name falls back to its cold placement.

    It is taken **per train** (#164), so only the trains in a collision pay
    for one, and what the all-or-nothing rule protected holds train by train
    anyway: no block ends with two trains in it, and no train ends standing in
    a block nothing holds (CONTEXT.md). A contested block goes to the train
    with **fewer answers**: one the picture does not name has only the
    document to stand on, while one it does name still has its own starting
    block. A train both of whose answers are taken is placed by neither and
    comes up off the layout (ADR-0039); nothing is resolved automatically, and
    #153 points a person at what is left. A train that did not keep its
    restored position loses its crossing hint with it: the hint names a
    transit its own placement was consistent with, and says nothing about the
    block the document put the train in.
    """
    named: Payload = picture.get("trains", {})
    pictured = {train: at for train, at in named.items() if train in roster.trains}
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
        if train not in settled and train in cold:
            place(train, cold[train])
    # Back into one stated order, whatever order they were settled in: the
    # standing locks are published one train at a time from this. The
    # document's trains first, then whatever else the picture placed, so a
    # railroad a document describes reads as it always did.
    order = list(cold) + [train for train in pictured if train not in cold]
    standing = {train: settled[train] for train in order if train in settled}
    kept = {train for train, at in pictured.items() if standing.get(train) == at}
    return Adopted(
        standing,
        {
            train: transit
            for train, transit in picture.get("crossing", {}).items()
            if train in kept
        },
    )


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
        self,
        bus: Bus,
        layout: Layout,
        roster: Roster,
        placement: dict[str, str],
        strategy: LockingStrategy,
    ) -> None:
        """The railroad's `roster` is the stock: every train it owns, whether
        anything places it or not. `placement` is train to block, and it is
        the whole of what a run can be *built* standing somewhere — the
        harness's batch loop, which is built from a scenario document
        (`bench/runner.py`). A run an operator drives passes none: its trains
        arrive by gesture, and a train nothing places comes up **off the
        layout** — known, standing nowhere, and waiting for a person to put it
        somewhere (ADR-0039).
        """
        self._bus = bus
        self._strategy = strategy
        # The last picture, where the bus binding held one across a restart:
        # the dispatcher's own state topic, found waiting exactly as it would
        # be against a broker that outlived the app (#123). Read here rather
        # than through `subscribe`, because placement has to be settled before
        # the standing locks below are published, and a subscription delivers
        # at the drain.
        picture = bus.last_values.get(ALLOCATION, {})
        adopted = restored(picture, roster, placement)
        self._state = State(
            layout,
            roster.lengths(),
            {},
            {},
            {},
            crossing=adopted.crossing,
            # **A run comes up held unless its own document stood its trains
            # on the rails** (ADR-0037 as #171 amends it, ADR-0039).
            #
            # A **restored** session comes up held (#154), which is the whole
            # point of the hold on a real railroad: the steel is wherever the
            # last session left it, and coming up running on the strength of a
            # picture nobody has looked at is the failure the hold exists to
            # prevent. The retained `state/run` is not what decides it — a
            # session cut while running left `running` waiting on that topic —
            # and neither is how much of the picture was taken: a train the
            # document overruled, or that adoption placed nowhere at all
            # (`restored`), is one more thing to come and look at rather than
            # a reason to start running.
            #
            # A cold session with an **empty layout** comes up held too, and
            # for a plainer reason: the only thing there is to do on one is
            # place trains, and `placement_wanted` is honoured while held and
            # dropped while running. Coming up running would refuse the first
            # gesture an operator makes. That is every run an operator starts
            # (#171) — the hold is what lets them lay the railroad out.
            #
            # What is left is the harness's batch loop, whose document stands
            # its trains before anything runs: nothing is left to place,
            # and a run that refused to grant with nobody at a panel would be
            # a fault that looks like a hang (ADR-0037).
            run=HELD if picture or not adopted.standing else RUNNING,
        )
        for train, at in adopted.standing.items():
            self._state.locks[at] = train
            self._state.block_of[train] = at
            bus.publish(
                "tc49/dispatch/lock_granted", {"train": train, "resources": [at]}
            )
        self._pending: list[Request] = []
        self._seen_ids: set[str] = set()
        self._next_seq = 0
        self._phases = 0  # sweeps run; stamps admissions for grant order
        self._aspects: dict[str, str] = {}  # last published, so only changes go
        self._allocation: Payload = {}  # likewise: the picture, when it moves
        self._disputed: Payload = {}  # and what the detectors dispute
        # The opening statement is the whole of what the dispatcher holds, in
        # the order a grant phase says it. Aspects are in it because a restart
        # has a previous value on that topic too: the last session's
        # `caution` for a route this one did not restore would stand until
        # the first grant phase, and a panel joining in that window draws a
        # clear road nothing holds a lock on. The run state opens it for the
        # same reason and one step earlier: it is the frame the rest is read
        # in, and a joining client is served a value rather than left to
        # read one out of an absence (ADR-0032). The disputed set closes it
        # for the same reason again: nothing has been reported yet, so the
        # set is empty, and saying so is what clears whatever the last
        # session left standing on that topic.
        self._publish_run()
        self._publish_aspects()
        self._publish_allocation()
        self._publish_disputed()
        bus.subscribe("tc49/layout/#", self._on_layout)
        bus.subscribe("tc49/dispatch/#", self._on_dispatch)

    # -- live state, for the property tests' oracles ------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def pending(self) -> tuple[Request, ...]:
        return tuple(self._pending)

    # -- admission ---------------------------------------------------------

    def _on_request(self, payload: Payload) -> None:
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
        if request.train not in self._state.roster:
            self._reject(rid, Reason.UNKNOWN_TRAIN)
            return
        if self._names_no_such_block(request):
            self._reject(rid, Reason.UNKNOWN_BLOCK)
            return
        if request.train not in self._state.block_of:
            # Known but off the layout (ADR-0039): a train nothing placed,
            # one adoption could not place (#164), or one a person has
            # lifted off. Answered here rather than guarded at
            # each launch lookup, because this is the only way in — the one
            # thing that unplaces a train, `_remove`, refuses a train with a
            # request in flight, so a request that gets past this line names a
            # train with a block and `_pending` holds none that stopped
            # having one.
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
            elif self._state.roster[request.train] > self._state.layout.blocks[block]:
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
        # The waiting set grew: the request is considered now, not at a beat.
        self._sweep()

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
        """Whether a request of the train's own is still queued, which is
        what makes both where it will stand and where it will depart from a
        future dispatcher choice."""
        return any(req.train == train for req in self._pending)

    def _expected_block(self, train: str) -> str | None:
        """Where the train stands (#99) — None while a request of its own is
        pending or running. Requests go in at the start of a run (ADR-0047),
        so a chained one arrives while its train is under way, and the block
        it states was composed against a snapshot: the launch stage judges
        it, correcting a stated block from the end the committed route leaves
        the train facing (#135)."""
        if self._has_pending(train) or train in self._state.active:
            return None
        return self._state.block_of[train]

    def _launch_to_come(self, request: Submission) -> tuple[str, str] | None:
        """The origin and departure end the request will launch from, or None
        where an earlier request of its own train leaves them a future
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
        depart = effective_departure(
            origin, request.depart, self._state.departure.get(request.train)
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
                self._state.roster[train],
                1,
            )
        )

    # -- what is addressed to the dispatcher --------------------------------

    def _on_dispatch(self, topic: str, payload: Payload) -> None:
        """The four topics the dispatcher responds to, on one filter.

        A request, and the three gestures a person makes on a page: all four
        name the dispatcher because the dispatcher is what answers them, and
        none of them says who sent it. The scheduler submits requests today
        and a second one could submit them tomorrow with nothing here to
        change (SYSTEM.md, rule 4).

        Everything else on `tc49/dispatch/#` is the dispatcher's own
        announcements coming back past it, and is ignored — the filter is the
        component, as every consumer's is (SYSTEM.md, rule 3). What it cannot
        act on it drops, in silence and to the trace: a gesture carries no id
        and there is nothing to address an answer to (ADR-0034).
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "request_submitted":
            self._on_request(payload)
        elif leaf == "run_wanted":
            self._set_run(payload)
        elif leaf == "placement_wanted":
            self._place(payload)
        elif leaf == "cancel_wanted":
            self._revoke(payload)

    def _set_run(self, payload: Payload) -> None:
        """Hold the run, or release it.

        Releasing runs a sweep: the release is what re-opens the gate the
        hold closed, so the waiting set is reconsidered here and the first
        wheel turns with the press (ADR-0047).

        A release is **refused while the track has no power**, dropped in
        silence and to the trace as every other gesture the dispatcher cannot
        act on is (ADR-0034). Releasing into dead rails would choose routes,
        grant moves and publish `move` over track nothing can move on, and
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
        if wanted == RUNNING:
            self._sweep()

    def _place(self, payload: Payload) -> None:
        """Where a train actually is, said by the person who can see it: the
        block it stands in, or nowhere at all.

        **One gesture in two directions** (ADR-0039). Putting a locomotive on
        the track and lifting it off are the same act said with a different
        destination, so `block: null` is a placement whose answer is *off the
        layout* rather than a leaf of its own.

        Two preconditions are the same either way: the run is held, and the
        train is known. A **request in flight was a third** and is not one any
        more (ADR-0049): the gesture cancels it first and then places the
        train, so `request_cancelled` precedes `train_placed` or
        `train_removed` and those two always describe a train with no request.
        The reason says which direction the gesture pointed — `removed` off
        the layout, `displaced` into a block.

        Cancelling first is what makes the placement possible at all rather
        than merely permitted: the train's own route holds the blocks it was
        going to run through, so a person standing it in one of them would be
        refused by `free` for a claim that belongs to the very request their
        gesture is ending. What the old precondition protected still holds
        with nothing left to protect it — a cancelled request departs from
        nowhere, and no queued request outlives the placement to depart from
        the wrong block.

        The placement itself is judged where it always was, after the
        cancellation and by `_stand`: a block has to exist, fit the train and
        be free of every claim, and one of those claims may be the
        cancellation's own to release. So a gesture the railroad cannot
        accept still ends the request and leaves the train where it was —
        the person said this train is not running that request any more,
        which is honoured, and then said where it is, which is refused. What
        it leaves behind is exactly what a `cancel_wanted` would have.

        Where the train stands *now* is no precondition at all: one adoption
        placed nowhere (`restored`) is exactly the train a person has to say
        something about.
        """
        wanted = placement(payload)
        state = self._state
        if wanted is None or state.run != HELD:
            return
        if wanted.train not in state.roster:
            return
        self._cancel(
            wanted.train,
            Cancellation.REMOVED if wanted.block is None else Cancellation.DISPLACED,
        )
        if wanted.block is None:
            self._remove(wanted.train)
        else:
            self._stand(wanted.train, wanted.block)

    def _stand(self, train: str, block: str) -> None:
        """A train put on the layout, or moved by hand from where it was.

        The block has to exist, be free of every claim, and fit the train.
        Having accepted, the dispatcher moves the train's standing
        lock and announces `train_placed`. That event is the ledger line for a
        placement: a `lock_released` and a `lock_granted` would say a route
        gave a block up and took another, which is not what happened — a hand
        lifted a locomotive, and the fact has its own leaf so a reader can
        tell the two apart.
        """
        state = self._state
        if block not in state.layout.blocks:
            return
        if not state.free(block):
            return
        if state.roster[train] > state.layout.blocks[block]:
            return
        # A train that is off the layout holds no standing lock and has none
        # to give up: this gesture is what puts it back on (ADR-0039, #164).
        # Placing one is otherwise the same act.
        standing = state.block_of.get(train)
        if standing is not None:
            del state.locks[standing]
        state.locks[block] = train
        state.block_of[train] = block
        # Whatever the last picture said this train was crossing, it is not
        # crossing it now: a person has said where it stands. The hint is
        # restored with no route behind it (`restored`), so this train is
        # exactly the one whose hint nothing else will ever clear — and
        # affirming the block the dispatcher already believes in is not a way
        # out, that block not being free.
        state.crossing.pop(train, None)
        self._publish("train_placed", {"train": train, "block": block})
        self._settled()

    def _remove(self, train: str) -> None:
        """A train taken off the layout: lifted out of its block by hand.

        It is not deletion. The train stays on the roster and can be placed
        again; what it loses is its place on the rails, which is absence from
        `block_of` and not a sentinel (ADR-0039).

        **What it held is released**, all of it. A train at rest holds its
        standing block, and a restored crossing train holds the transit it
        was on and the block behind it as well (#154) — which is exactly the
        train an operator most wants to lift out, so the sweep is by holder
        rather than of one block. `lock_released` is the ledger line, because
        that is what happened: the resources are free and nothing took them.

        A train that is already off the layout is left alone. The gesture
        asks for a state it is in, and there is no fact to announce.
        """
        state = self._state
        if train not in state.block_of and train not in state.crossing:
            return
        self._release(train)
        state.block_of.pop(train, None)
        # A crossing train stands in no block, and off the layout it is not on
        # a transit either: the hint goes with the placement it belonged to.
        state.crossing.pop(train, None)
        self._publish("train_removed", {"train": train})
        self._settled()

    def _release(self, train: str, keep: str | None = None) -> list[str]:
        """Everything the train holds, given up as one `lock_released` — all
        of it, or all of it but `keep`.

        **One release path**, because there is only one fact to state: the
        resources are free and nothing took them. A train at rest holds its
        standing block, a restored crossing train holds the transit it was on
        and the block behind it as well (#154), and a train under `FullRoute`
        holds every block of a route it will now never run — so the sweep is
        by **holder** rather than of a named set, and a caller that knew the
        set would be re-deriving the lock table.

        `keep` is the block a train goes on standing in. A cancellation
        releases everything the request took and leaves the train where it
        is, which is a train at rest and its standing lock (ADR-0049); a
        removal keeps nothing, the train being off the rails.
        """
        state = self._state
        released = sorted(
            resource
            for resource, holder in state.locks.items()
            if holder == train and resource != keep
        )
        for resource in released:
            del state.locks[resource]
        if released:
            self._publish("lock_released", {"train": train, "resources": released})
        return released

    def _revoke(self, payload: Payload) -> None:
        """A person ending a train's request without it arriving (ADR-0049).

        The gesture names a **train** and no request: a page shows a train
        and the work under it, and the id is the dispatcher's own. So it ends
        whatever that train has — the active request and every one still
        queued behind it — and a train with nothing in flight is dropped in
        silence and to the trace, as an unknown train is: the gesture carries
        no id, and there is nothing to address an answer to (ADR-0034).

        It does **not** require a held run. Cancelling is how a person ends
        work the railroad cannot finish — a train that broke down, a route
        chosen against a railroad that has since changed under it — and
        making them hold the whole run first would stop every other train to
        let one go. The hold is a brake on new commitment; this retires one
        request, and what it frees the next sweep hands to somebody else.
        """
        train = named_train(payload)
        if train is None or train not in self._state.roster:
            return
        if self._cancel(train, Cancellation.REVOKED, defer=True):
            # Something was actually given up, so the waiting set is
            # reconsidered here: what a cancelled route was holding is
            # exactly what somebody else has been refused for (ADR-0047). A
            # gesture that freed nothing sweeps nothing — a sweep publishes a
            # `grant_refused` for every waiting request and ages the queue
            # with it, and neither belongs to a gesture that did nothing.
            self._sweep()

    def _cancel(self, train: str, reason: Cancellation, defer: bool = False) -> bool:
        """Every request the train has, retired without the train arriving.
        Answers whether the lock table or the waiting set moved.

        The active one first and its queue behind it, so a reader of the
        trace sees the request that was running end before the ones that were
        waiting on it. Each gets its own `request_cancelled`: an id is what
        ties a request's events together, and a single event naming a train
        would leave a reader to work out which ids it had just been told
        about.

        A queued request has taken nothing and needs no release. The active
        one is holding a route — every transit and every block beyond the
        origin under `FullRoute` — and gives up **all of it but the block the
        train stands in**: that block is the train's standing lock, which
        every parked train holds (CONTEXT.md), and releasing it would leave a
        locomotive in a block the dispatcher believes free.

        `defer` is for the one case where the release cannot happen yet: a
        move is outstanding, the train is between two blocks, and nothing on
        the bus retracts a `move` already sent (ADR-0037). The request is
        marked instead — no further move is granted for it — and it retires
        in `_cleared`, when the sensors say the move it was already making is
        over. A placement does not defer: the person is saying where the train
        actually *is*, which answers the move the sensors never will.

        The answer is what a caller sweeps on: a deferred cancellation frees
        nothing and dequeues nothing, so there is nothing for a sweep to hand
        anybody, and a train with nothing in flight moves nothing at all.
        """
        state = self._state
        moved = False
        active = state.active.get(train)
        if active is not None:
            if defer and active.outstanding is not None:
                active.request.cancelled = True
            else:
                self._retire(train, active, reason)
                moved = True
        for req in [req for req in self._pending if req.train == train]:
            self._pending.remove(req)
            self._publish("request_cancelled", {"id": req.id, "reason": reason})
            moved = True
        if moved:
            self._settled()
        return moved

    def _retire(self, train: str, active: Active, reason: Cancellation) -> None:
        """The active request ended: what it holds released, the train
        dropped out of everything that says it is running one, and the one
        event that says so.

        `_seen_ids` is not pruned. A cancelled id stays used for the session,
        because an id is unique and not meaningful (ADR-0033) and a resubmit
        of it is the duplicate it looks like.
        """
        state = self._state
        self._release(train, keep=state.block_of.get(train))
        del state.active[train]
        state.crossing.pop(train, None)
        state.departure.pop(train, None)
        self._publish("request_cancelled", {"id": active.request.id, "reason": reason})

    def _settled(self) -> None:
        """What a placement changes besides the lock table: the picture a
        joining client draws from, and the disputed set — the entry the person
        just resolved leaves it, which is what empties it as the railroad is
        walked (#153)."""
        self._publish_allocation()
        self._publish_disputed()

    # -- the sensors, and the sweep they trigger ----------------------------

    def _on_layout(self, topic: str, payload: Payload) -> None:
        """What the layout interface says, and the two commands sent to it.

        `align` and `move` are on this filter because they name the component
        that responds to them, and the dispatcher is not that component: the
        sensor leaves are named here so a command passes by unread rather
        than being taken for a reading with no block in it.
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "power":
            self._on_power(payload)
        elif leaf in ("block_occupied", "block_vacated"):
            block = occupancy(payload)
            if block is None:
                # Dropped, and on the trace already by virtue of having been
                # published (ADR-0034): the block stays out of `reported`, so
                # it takes no part in the check and the next report settles
                # it. Why this direction and not the power enum's is
                # SYSTEM.md, sole payload authority (#181).
                return
            self._on_sensor(leaf == "block_occupied", block)

    def _on_sensor(self, occupied: bool, block: str) -> None:
        """One detector reading, applied where it lands (ADR-0047).

        A detector reports presence, which is a level: a reading that
        re-asserts what `reported` already holds is an at-least-once repeat
        and a no-op, so delivery needs no counter and no dedup. A reading
        that *changes* the level either explains a granted move — recorded
        arrival for `block_occupied`, a finished move for `block_vacated` —
        or explains nothing, which holds the run (ADR-0048). Either way the
        level is recorded first: what the dispute check compares is every
        reading that arrived, explained or not (#153).
        """
        if self._state.reported.get(block) == occupied:
            return
        self._state.reported[block] = occupied
        self._publish_disputed()
        if occupied:
            self._arrived(block)
        else:
            self._cleared(block)

    def _explained(self, block: str) -> tuple[str, Active, Move] | None:
        """The train whose outstanding move this reading reports on, or None
        where no grant accounts for it."""
        train = self._state.locks.get(block)
        if train is None:
            return None
        active = self._state.active.get(train)
        if active is None or active.outstanding is None:
            return None
        return train, active, active.outstanding

    def _unexplained(self) -> None:
        """A reading no granted move accounts for: **the run holds**
        (ADR-0048).

        A hand putting a locomotive on a detected block, a train pushed while
        the supply was off, a cut of cars a broken coupling left standing, a
        detector asserting on dirt — they differ for the person recovering and
        not here. All of them say the lock table has stopped describing the
        steel, and the dispatcher's whole safety argument runs over that table
        (SAFETY.md): a block reading occupied with nothing claiming it is one
        `safe()` believes free, and granting it is a collision the check would
        call safe.

        So the run holds, by the path track power takes (ADR-0041) — nothing
        new commits, every signalled end shows `stop`, and the move already
        outstanding still runs to its sensors. It does not raise: the frame is
        well formed and a handler that raised would take the app off the bus
        for an ordinary act of a person's hand (SYSTEM.md, rule 4). It is not
        dropped either, and nothing is placed: occupancy is anonymous, so
        there is no train to place, and the reading is on the trace and in the
        dispute set the hold turns on, which is what points a person at it
        (#153). They walk the railroad, place what they find, and press GO.
        """
        self._move_run(HELD)

    def _arrived(self, block: str) -> None:
        """`block_occupied` records where the train arrived. The move is not
        over: the tail is still in the origin block, the train is between
        blocks, and it takes no further grant until the vacate ends the move
        (ADR-0047)."""
        found = self._explained(block)
        if found is None or found[2].into != block:
            self._unexplained()
            return
        train, _active, _move = found
        self._state.block_of[train] = block
        self._publish_allocation()

    def _cleared(self, block: str) -> None:
        """`block_vacated` releases the origin block and the transit, ends
        the move and completes the request — and what it released is why a
        sweep runs here (ADR-0047).

        **A cancelled request retires here instead**, wherever along its route
        it had got to: the person's gesture landed while this move was
        outstanding, so it was marked rather than acted on, and the move it
        could not retract has now run to its sensors (ADR-0049). What it gives
        up is the whole remaining hold and not just this move's block and
        transit — the rest of the route is track it will never run — and what
        it publishes is `request_cancelled` in place of `request_completed`,
        because the train did not arrive.
        """
        state = self._state
        found = self._explained(block)
        if found is None or found[2].from_block != block:
            self._unexplained()
            return
        train, active, move = found
        active.outstanding = None
        del state.crossing[train]
        if active.request.cancelled:
            self._retire(train, active, Cancellation.REVOKED)
        else:
            del state.locks[block]
            del state.locks[move.transit]
            self._publish(
                "lock_released", {"train": train, "resources": [block, move.transit]}
            )
            if active.cur_index == len(active.route.blocks) - 1:
                del state.active[train]
                self._publish("request_completed", {"id": active.request.id})
        self._sweep()

    def _on_power(self, payload: Payload) -> None:
        """What the layout says about whether a train may move at all.

        Anything but `on` **holds the run**, by the path a person's HOLD
        takes: the dispatcher commits nothing more, and every signalled end
        shows `stop` rather than going on showing `clear` over track with no
        volts in it (ADR-0041). Which of `stopped` and `off` it is changes
        nothing here — the two differ for the person recovering, who clears an
        emergency stop or switches a supply back on, and the panel is where
        that is said.

        "Anything but `on`" is read literally, so a payload that cannot be
        read at all is one of those cases rather than an exception: the value
        comes through `payload.power`, which answers `off` where a
        subscript would have raised (#175).

        Power **returning** to `on` releases nothing. That is the bar the hold
        exists for: an explicit GO before anything moves, whatever the rails
        did in the meantime, and the same guarantee the hardware gives at
        power-up by coming back idle.

        What it cannot do is undo the cut. A train granted a move that no
        sensor will ever answer keeps its locks and its `crossing` entry, and
        every train waiting on those resources waits with it, until somebody
        restarts the session — the hold is a brake and not an emergency stop,
        and nothing on the bus retracts a `move` already sent.
        """
        self._state.power = power(payload)
        if self._state.power != ON:
            self._move_run(HELD)

    def _sweep(self) -> None:
        """One grant pass, run where the lock table or the waiting set
        changed: a request admitted, a vacated block releasing what a move
        held, the run released. A sweep covers the whole waiting set, so
        every pending request accrues a refusal in the same sweep and the
        aging keeps its order (ADR-0012, ADR-0047).

        While the run is held nothing commits (ADR-0037): the hold is a brake
        and not an emergency stop — nothing on the bus retracts a `move`
        already sent — so a sensor still applies where it lands, and what is
        withheld is everything that would commit something new. `_phases`
        keeps counting either way: a held run is still a run, and the count
        is what stamps an admission with the grant order it joined at.
        """
        self._phases += 1
        if self._state.run == RUNNING:
            self._grant()
        self._publish_aspects()
        self._publish_allocation()
        self._publish_disputed()

    def _grant(self) -> None:
        state = self._state
        # Active trains first, by request arrival then train id (DISPATCH.md).
        for train in sorted(
            state.active, key=lambda t: (state.active[t].request.phase, t)
        ):
            active = state.active[train]
            if active.outstanding is not None or active.request.cancelled:
                # A cancelled request is waiting for the move it was already
                # making to end, and takes no other (ADR-0049).
                continue
            self._apply_move(active, self._strategy.grant(train, state))
        # A train's chained requests run in order: once one of them is left
        # pending — refused, or launched and now active — the rest of that
        # train's queue waits. Letting a later request overtake a refused one
        # would run a train's chain out of order and from the wrong origin.
        # Across trains the scan ages (#34): a request refused N times is
        # tried before fresher ones, so a starved request gets first claim on
        # whatever just freed. A train's own chain order is preserved for
        # free — an untried later request has no refusals and a later seq.
        waiting: set[str] = set(state.active)
        for req in sorted(self._pending, key=aging_order):
            if req.train in waiting:
                continue
            origin = state.block_of[req.train]
            depart = effective_departure(
                origin, req.depart, state.departure.get(req.train)
            )
            if depart is None:
                # The stated end names a block the train is not in and no
                # route of its own supplies a better one, so there is nothing
                # to route from: the enumerator walks from the departure end
                # while recording the origin as the route's first block, and
                # an end off the origin returns a route claiming to start
                # where the train stands and leave somewhere else (#146).
                # Asked ahead of the degenerate arrival below, as admission
                # asks it ahead of pruning: a stale request is refused, not
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
        # lets a request dragged in mid-route be answered while it is asked.
        # Which end the route comes in through is read here: `lib` states the
        # rule and takes the end, knowing nothing of routes (#155).
        entered = end_on(
            self._state.layout,
            launched.route.arrival_block,
            launched.route.transits[-1],
        )
        self._state.departure[req.train] = departure_end(self._state.layout, entered)
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
        and not the driver's (ADR-0022). The topic is the layout interface's,
        `tc49/layout/align`, because that is what responds to it; nothing on
        it says the dispatcher sent it. It carries the points the transit
        needs, read from the layout (ADR-0031), so the layout interface throws
        what it is told and holds no table of its own. Always `points`, `[]`
        where nothing needs throwing: the document is quiet, the wire explicit.
        """
        connection, _, transit = transit_id.partition(".")
        needed = self._state.layout.connections[connection].points.get(transit, ())
        self._bus.publish(
            "tc49/layout/align",
            {
                "connection": connection,
                "transit": transit,
                "points": [
                    {"addr": point.addr, "position": point.position} for point in needed
                ],
            },
        )

    def _publish_run(self) -> None:
        """Whether the run is held or running, on a last-value topic. An
        enum and not a boolean because the ordinary-shutdown drain will add
        `draining` as a third value (#123)."""
        self._publish("state/run", {"run": self._state.run})

    def _publish_aspects(self) -> None:
        """The signalled ends, on a last-value topic, when any of them has
        changed. Every end each time rather than the ones that moved: a late
        subscriber wants the whole picture on connect, not the first change
        after it arrives (SYSTEM.md)."""
        shown = aspects(self._state)
        if shown != self._aspects:
            self._aspects = shown
            self._bus.publish(ASPECTS, {"aspects": shown})

    def _publish_allocation(self) -> None:
        """The run's picture, on a last-value topic, when any of what it
        carries has moved. Published from the two places that move it: a
        request joining the queue, and the grant phase that runs it."""
        picture = allocation(self._state, self._pending)
        if picture != self._allocation:
            self._allocation = picture
            self._bus.publish(ALLOCATION, picture)

    def _publish_disputed(self) -> None:
        """What the detectors make of the placement, on a last-value topic,
        when it moves — the panel points a person at it, and a panel joining
        later must find it there (ADR-0032). Published from every place that
        moves either side of the comparison: a reading arriving, a placement,
        and the hold itself."""
        found = disputed(self._state)
        if found != self._disputed:
            self._disputed = found
            self._publish("state/disputed", found)

    def _publish(self, leaf: str, payload: Payload) -> None:
        self._bus.publish(f"tc49/dispatch/{leaf}", payload)
