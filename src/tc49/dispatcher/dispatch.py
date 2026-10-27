"""Dispatcher: admission, queue, lock table, sensor roles, grant sweep.

Fully asynchronous at the bus boundary (SYSTEM.md, dispatcher footprint):
requests arrive as events, every fate is announced as an event, and the
request id is both correlation and idempotency key. The dispatcher grants on
the events that arrive (ADR-0047): a sensor reading is applied where it
lands, and a **sweep** — one grant pass over the active trains and the whole
pending queue — runs wherever the lock table or the waiting set changes: a
request admitted, a vacated block releasing what a move held, the power
coming back `on`. Every grant is `safe()`-checked before it commits, so arrival
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
(BUS.md, rule 4).

The whole of what arrives is read that way (#260). Two filters: the requests
this app answers — `request_submitted`, `placement_wanted`,
`cancel_wanted`, `reorder_wanted` and `point_wanted`, from the ui, the scheduler, or a second scheduler introduced
later — and what
the layout interface observes, on a filter that also carries the `align` and
`move` commands, which name the layout and are passed by unread. Every leaf
goes through a reader in `lib.payload` and nothing subscripts a frame it has
not read. The one thing left that could take the app off the bus was a sensor
reading no granted move accounts for; it drains the railroad instead
(ADR-0048, ADR-0078).
"""

import sys
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field

from tc49.dispatcher.locking import Launched, LockingStrategy, Move, Refused
from tc49.dispatcher.routing import Route, candidates
from tc49.lib.bus import Bus, Payload
from tc49.lib.cancellation import Reason as Cancellation
from tc49.lib.inventory import DRAINING, OFF, ON, Aspect, Refusal
from tc49.lib.layout import (
    Layout,
    block_of,
    departure_end,
    opposite_end,
    transit_ends,
)
from tc49.lib.payload import (
    Ordering,
    gesture,
    kept_allocation,
    occupancy,
    placement,
    power,
    readable_id,
    wanted_point,
    wanted_power,
    wanted_reorder,
    withdrawal,
)
from tc49.lib.rejection import PlacementRefusal, Reason
from tc49.lib.roster import Roster

# The two state topics named in full, because each is read as well as
# written: the allocation by a dispatcher coming back up, and either by a
# test seeding the file a session comes up on.
ALLOCATION = "tc49/dispatch/state/allocation"
ASPECTS = "tc49/dispatch/state/aspects"
POWER = "tc49/layout/state/power"
WITHDRAW_WANTED = "tc49/layout/withdraw_wanted"
"""Where a deferred cancel asks `layout` to take its move back (#1068)."""
POWER_WANTED = "tc49/layout/power_wanted"
"""Where a fault asks `layout` for a drain, as a person's press would
(ADR-0078)."""
UNFIT = "tc49/dispatch/state/unfit"
"""The trains the last rebuild under the same name took off the layout (#709).
The UI's run view reads it."""

GONE = "gone"
"""`unfit`'s `why` for a train whose block the new drawing lacks."""
SHORT = "short"
"""`unfit`'s `why` for a train its block, in the new drawing, no longer holds."""


@dataclass
class Request:
    id: str
    train: str
    # The end the train departs through, or a bare letter for a request the
    # scheduler chained by naming only the end. None while a request chained
    # by `after` waits for the one it follows to arrive (ADR-0080).
    depart: str | None
    arrivals: tuple[str, ...]  # surviving arrival ends
    phase: int  # sweeps run when admitted; the arrival-order key
    # Whether the request has been cancelled while a move of its own was
    # outstanding: nothing further is granted for it, and it retires as
    # `request_cancelled` when that move's sensors finish (ADR-0049).
    cancelled: bool = False
    # The ids of the train's requests chained after this one when its cancel
    # was asked: plans to carry on from where it would arrive, cancelled with
    # it. One chained after it later departs from where the train stops
    # (#836).
    revoking: frozenset[str] = frozenset()
    # The train's `priority_key` from the roster, taken at admission: where
    # the request goes in the list, and nothing else (ADR-0080). The default
    # is the key of a train with no priority.
    priority: tuple[int, int] = (1, 0)
    # The id of the train's request this one follows, which it starts where
    # that one ends (ADR-0080).
    after: str | None = None


def resolve_departure(depart: str, origin: str) -> str:
    """A bare end letter (chained request) resolves against the origin."""
    return depart if "." in depart else f"{origin}.{depart}"


def departs_elsewhere(depart: str | None, expected: str | None) -> bool:
    """Whether a stated departure block disagrees with the block the train
    departs from. A bare end letter states no block and so cannot disagree,
    nor can a request chained by `after`, which states no end at all, and
    neither can anything while an earlier pending request leaves that
    block a future dispatcher choice (`expected` is None). Admission and the
    launch stage both ask it, of the origin each by then has, so one rule
    serves both (#146)."""
    if depart is None or "." not in depart or expected is None:
        return False
    return block_of(depart) != expected


@dataclass
class Active:
    request: Request
    route: Route
    cur_index: int  # index into route.blocks of cur(t)
    outstanding: Move | None  # granted move whose sensors are pending
    # the outstanding move's origin read clear since its grant
    origin_cleared: bool = False


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
    # `on`, `draining` or `off`: what the layout last said about the one
    # switch a person turns (ADR-0078). The dispatcher routes, grants and
    # locks only while it reads `on`; `draining` and `off` commit nothing, and
    # requests wait. Not an emergency stop for what is already granted — a
    # move already sent is not retractable and runs to its sensor whatever
    # the power — so it gates the sweep's grant pass and the aspects, and
    # admission goes on: it is cheap and reversible, and launching is the
    # commitment. `off` too is when the detectors are compared with the
    # placement (`disputed`). State rather than a flag on the dispatcher
    # because `aspects()` answers off it.
    #
    # `off` until the layout says otherwise, because the railroad comes up
    # `off` and nothing is routed over rails nobody has heard from.
    power: str = OFF
    # block -> whether the layout last reported it occupied: the level each
    # detector last stated, which is what makes an at-least-once repeat a
    # no-op (ADR-0047), and what the dispute check compares (#153). Only blocks
    # the layout has actually reported on are keys — silence is not a clear
    # reading, and a binding that reports nothing disputes nothing rather
    # than the whole railroad.
    reported: dict[str, bool] = field(default_factory=dict[str, bool])
    # What a train taken off the layout still holds, because a detector last
    # read it occupied (ADR-0069): each block, and the transit it was crossing
    # while either of that transit's blocks is here. The lock table names the
    # holder; this is what says the lock waits for a clear reading rather
    # than for a move, so that reading is explained and a clear reading under
    # a standing train still is not (ADR-0048).
    residue: set[str] = field(default_factory=set[str])

    def obstacle(self, resource: str, train: str) -> tuple[str, str, str] | None:
        """Why `train` cannot lock `resource`: (reason, resource, holder),
        or None if it can. Transits also require no conflicting locked
        transit at their connection (instantaneous admissibility).

        A block that reads occupied is not entered, whoever holds it, the
        train's own residue included, and with holder "" where nobody does
        (ADR-0077): a cut of cars would be hit, and a stuck detector takes
        the block out of use until it reads clear."""
        if self.reported.get(resource) is True:
            return (Refusal.HELD, resource, self.locks.get(resource, ""))
        holder = self.locks.get(resource)
        if holder is not None and holder != train:
            return (Refusal.HELD, resource, holder)
        if "." in resource:  # a transit: check the conflict matrix
            for locked, by in sorted(self.locks.items()):
                if (
                    by != train
                    and "." in locked
                    and self.layout.conflicts(resource, locked)
                ):
                    return (Refusal.TRANSIT_CONFLICT, locked, by)
        return None

    def free(self, block: str, train: str | None = None) -> bool:
        """Whether nothing at all has a claim on `block`.

        Both claims a route carries, not just the stronger one: a resource is
        **committed** when it is on a route the dispatcher has chosen and not
        yet locked, and that is a claim (GLOSSARY.md). Under `FullRoute` the
        two sets coincide, since a launch locks the whole route; under
        `Incremental` a fixed route runs on ahead of its locks, and reading
        the lock table alone would call those blocks free.

        Placing a train into one strands the request that owns it: the route
        is fixed (ADR-0002), and the placed train is idle, so its standing
        lock is a permanent obstacle (SAFETY.md) and the committed train is
        refused `unsafe` at every sweep for the rest of the session.

        `train` asking, the block is judged as its placement will leave the
        railroad: its own requests cancelled (ADR-0049), which happens only
        once the placement is accepted (#1062). So its own route is no claim,
        and of the locks it holds only the one it stands on stays. What is
        left is another train's claim, which a placement may not walk into.
        A block it still holds as residue of its own removal is free to it
        (ADR-0069): the claim is its own, and putting it back there is the
        person saying the loco never left.
        """
        holder = self.locks.get(block)
        if holder is not None and holder != train:
            return False
        if (
            holder is not None
            and block == self.block_of.get(holder)
            and block not in self.residue
        ):
            return False
        return not any(
            block in active.route.blocks[active.cur_index :]
            for owner, active in self.active.items()
            if owner != train
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


def transit_blocks(layout: Layout, transit: str) -> set[str]:
    """The two blocks a transit (as 'connection.transit') joins."""
    connection, _, name = transit.partition(".")
    return {block_of(end) for end in layout.connections[connection].transits[name]}


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
        return Aspect.CLEAR
    return Aspect.CAUTION if depth else Aspect.STOP


def aspects(state: State) -> dict[str, str]:
    """Every signalled block end's aspect. An end nothing ever leaves carries
    no signal and does not appear; an end no train is authorised to leave by
    shows `stop`, which falls out of there being nothing locked beyond it
    rather than being a rule of its own.

    **An aspect answers "may a train that reaches this end leave by it"**
    (ADR-0093). For each train, the exit of every block on its route from the
    one the dispatcher records it in (`block_of`) through its last locked
    block shows the depth counted from that block, so a train holding two
    ahead shows `clear`, then `caution`, then `stop`. The block it is recorded
    in is the origin of an outstanding move until the entered block reads
    occupied, and the entered block from then on, before the origin reads
    clear: the signal it has passed shows `stop` once the nose is past it, not
    once the move ends. The ends of blocks behind it show `stop`, and a block
    has one holder, so no end is set by two trains.

    **Power not `on` puts every signal to stop.** While `draining` or `off`
    the answer is no at every end: nothing is granted, so a train standing at
    a signal goes nowhere, and a drain stops each moving train in the block
    it is entering (ADR-0078). Reading the locks instead would show `clear`
    over a railroad that is going nowhere, and on the physical layout would
    leave a lineside signal green over a train that will not be let past it,
    or over dead track. It qualifies ADR-0025 rather than superseding it: the
    depth still decides which of the other two shows.
    """
    shown: dict[str, str] = {
        end: Aspect.STOP for end in sorted(state.layout.end_connection)
    }
    if state.power != ON:
        return shown
    for train, active in state.active.items():
        route = active.route
        # `cur_index` advances at the grant, so with a move outstanding the
        # train is recorded one back until the entered block reads occupied.
        standing = active.cur_index
        if active.outstanding and state.block_of.get(train) != route.blocks[standing]:
            standing -= 1
        last = standing + locked_ahead(state, train, route, standing)
        for i in range(standing, min(last + 1, len(route.transits))):
            ends = transit_ends(state.layout, route.blocks[i], route.transits[i])
            assert ends is not None  # a route's transits reach its blocks
            shown[ends[0]] = aspect_of(locked_ahead(state, train, route, i))
    return shown


def allocation(state: State, requests: Sequence[Request]) -> Payload:
    """The run's picture: where every train stands and which of them are
    crossing a transit, the lock table with its holders, and every request
    still alive — carrying the route a committed one is running.

    A crossing train appears in both maps: `trains` goes on naming the block
    the sensors last confirmed it in, and `crossing` names the transit that
    is taking it out of there. The transit is the whole of the mark — there
    is no suspect flag — and it is what a restarted session restores as a
    placement hint, with no route and no request behind it (#123).

    A projection of the lock table and the request list, published beside
    its source exactly as `aspects` is (ADR-0032). Everything a joining client
    draws is here, because the events that built it were published before it
    connected and an event topic is never replayed. The requests are in list
    order, the order the dispatcher serves them (ADR-0080), and the maps
    sorted, so the picture is a function of the state and not of a dict's
    insertion history.
    """
    routes = {active.request.id: active.route for active in state.active.values()}
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
                **({} if request.after is None else {"after": request.after}),
                **(
                    {"route": routes[request.id].interleaved()}
                    if request.id in routes
                    else {}
                ),
            }
            for request in requests
        ],
    }


def disputed(state: State) -> Payload:
    """Where the placement and the detectors contradict each other: trains
    standing in a block that reads clear, and blocks that read occupied with
    nothing claiming them (#153).

    On power-up the detectors assert straight away — anonymously, so no
    reading names a train — at exactly the moment the placement is least
    trustworthy: it is where the last session *believed* the railroad was,
    and the steel has stood unwatched since (GLOSSARY.md, recovery). Naming
    the two contradictions turns walking the whole railroad into checking a
    handful of trains. It **resolves** nothing: the check points, and a
    person ends every entry with a `placement_wanted`.

    **Only while power reads `off`**, which is the moment it is about: before
    anything commits, over a placement nobody has looked at, and after a
    fault has drained the railroad to a stand (ADR-0078). A routing
    dispatcher's placement is what its sensors have just told it, so the two
    agree by construction and a comparison would catch nothing but itself
    mid-transit — and a drain is still running trains to their sensors.
    Anything but `off` therefore empties the set rather than freezing it: a
    person turning the power on has decided, and a set left standing would
    go on disputing a railroad they accepted.

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
    if state.power != OFF:
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


def broken(state: State) -> list[str]:
    """The lock table's rules that `state` breaks, one line each and sorted,
    so equal states give equal lists (#761). Reads and writes nothing else.

    The rules are what the four maps — `locks`, `block_of`, `crossing` and
    `residue` — keep between them at the end of an event: a placed train
    holds the lock on its block; every lock is a placed train's or residue;
    an idle train holds its block and its residue and nothing more; residue
    is locked, and a block in it reads occupied with nobody standing there; an
    active train is placed, and holds and is crossing what its outstanding
    move took; a crossing train is placed; and no two trains' locked transits
    conflict (ADR-0006).

    The dispatcher drains the railroad on a rule newly broken (ADR-0076,
    ADR-0078). `safe()`
    is not among them: its cost grows exponentially with the active trains
    (ADR-0003).
    """
    lines: list[str] = []
    placed = state.block_of
    for train, block in placed.items():
        holder = state.locks.get(block)
        if holder != train:
            lines.append(
                f"{train} stands in {block}, which is locked to {holder or 'nobody'}"
            )
    for resource, holder in state.locks.items():
        if holder not in placed and resource not in state.residue:
            lines.append(f"{resource} is locked to {holder}, which is not placed")
    for resource, holder in state.locks.items():
        if (
            holder in placed
            and holder not in state.active
            and resource != placed[holder]
            and resource not in state.residue
        ):
            lines.append(f"{holder} is idle and holds {resource}")
    for resource in state.residue:
        holder = state.locks.get(resource)
        if holder is None:
            lines.append(f"{resource} is residue and not locked")
        elif resource in state.layout.blocks:
            if state.reported.get(resource) is not True:
                lines.append(f"{resource} is {holder}'s residue and not read occupied")
            if placed.get(holder) == resource:
                lines.append(f"{resource} is {holder}'s residue and it stands there")
        elif not any(
            block in state.residue and state.locks.get(block) == holder
            for block in transit_blocks(state.layout, resource)
        ):
            lines.append(f"{resource} is {holder}'s residue with neither block kept")
    for train, active in state.active.items():
        if train not in placed:
            lines.append(f"{train} is active and not placed")
        move = active.outstanding
        if move is None:
            if train in state.crossing:
                lines.append(f"{train} has no move and is crossing")
            continue
        for resource in (move.transit, move.into):
            if state.locks.get(resource) != train:
                lines.append(f"{train} is moving through {resource} and not holding it")
        if state.crossing.get(train) != move.transit:
            lines.append(
                f"{train} is moving through {move.transit} and not crossing it"
            )
    for train in state.crossing:
        if train not in placed:
            lines.append(f"{train} is crossing and not placed")
    transits = sorted(
        (resource, holder)
        for resource, holder in state.locks.items()
        if "." in resource
    )
    for i, (one, by) in enumerate(transits):
        for other, also in transits[i + 1 :]:
            if by != also and state.layout.conflicts(one, other):
                lines.append(f"{one} locked to {by} conflicts with {other} of {also}")
    return sorted(lines)


@dataclass(frozen=True)
class Adopted:
    """What a restart takes from the last picture (`restored`)."""

    standing: dict[str, str]  # train -> the block it comes up in
    crossing: dict[str, str]  # train -> the transit it was crossing
    # train -> (the block the picture stood it in, `GONE` or `SHORT`): the
    # pictured trains the drawing could not stand again and nothing else
    # placed, which come up off the layout (#709)
    unfit: dict[str, tuple[str, str]] = field(
        default_factory=dict[str, tuple[str, str]]
    )


def restored(
    picture: object, layout: Layout, roster: Roster, cold: dict[str, str]
) -> Adopted:
    """Placement and crossing hints off the last picture the bus kept across
    a restart, or the run's own `cold` placement where there is none (#123).

    The picture is **read**, in `lib.payload` where every payload is read: a
    value waiting on a broker that outlived the app is a payload like any
    other, and rule 4 does not exempt the moment one is read at construction
    (#278). A value that states no picture leaves this exactly where an
    absent one does — every train on its cold placement, the lock table
    rebuilt one block per train, the queue empty — because refusing to start
    recovers nothing and tells a person less than starting cold does. It is
    the same case and not a new one.

    Adoption is **selective**: `trains` and `crossing` are taken, `locks` and
    `requests` left behind. The lock table is rebuilt one block per train as a
    cold start builds it, the queue comes back empty, and no request id
    resumes (ADR-0033). Stock stays the **roster**'s, so the picture's word
    for a train it does not carry is dropped, and a train the picture does not
    name falls back to its cold placement.

    The picture's word is taken only where **`layout` can still stand the
    train there**, with the checks any placement passes (`_stand`): the block
    exists and the train fits in it. A picture is kept through a rebuild of
    the railroad under the same name (ADR-0071), and the drawing it was taken
    against may since have lost the block or shortened it. A train placed
    there is treated as one the picture does not name, so a run an operator
    drives — which has no cold placement — brings it up off the layout. Such
    a train is returned in `unfit` with the block it stood in and why it no
    longer stands there, `GONE` or `SHORT`, for a person to come and place
    (#709); one its cold placement stood somewhere else is not.

    It is taken **per train** (#164), so only the trains in a collision pay
    for one, and what the all-or-nothing rule protected holds train by train
    anyway: no block ends with two trains in it, and no train ends standing in
    a block nothing holds (GLOSSARY.md). A contested block goes to the train
    with **fewer answers**: one the picture does not name has only the
    document to stand on, while one it does name still has its own starting
    block. A train both of whose answers are taken is placed by neither and
    comes up off the layout (ADR-0039); nothing is resolved automatically, and
    #153 points a person at what is left. A train that did not keep its
    restored position loses its crossing hint with it: the hint names a
    transit its own placement was consistent with, and says nothing about the
    block the document put the train in.
    """
    stated = kept_allocation(picture)
    named = stated.trains if stated is not None else {}
    lengths = roster.lengths()
    misfit = {
        train: (at, GONE if at not in layout.blocks else SHORT)
        for train, at in named.items()
        if train in roster.trains
        and (at not in layout.blocks or lengths[train] > layout.blocks[at])
    }
    pictured = {
        train: at
        for train, at in named.items()
        if train in roster.trains and train not in misfit
    }
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
    hinted = stated.crossing if stated is not None else {}
    return Adopted(
        standing,
        {train: transit for train, transit in hinted.items() if train in kept},
        {train: misfit[train] for train in sorted(misfit) if train not in standing},
    )


@dataclass
class Submission:
    """A payload read as the request it claims to be: the fields of
    `request_submitted` with the shapes the inventory promises (BUS.md).
    Read rather than trusted, in `lib.payload`'s terms.
    """

    id: str
    train: str
    depart: str | None
    dest: tuple[str, ...]
    after: str | None = None


def submission(payload: Payload, rid: str) -> Submission | None:
    """The request the payload states, or None where it states none —
    `malformed`, the one structural reason.

    A request is a gesture with an id and a departure end (ADR-0036), so the
    gesture is read where the scheduler reads one and the departure end,
    which only a request carries, is read here. A request with `after` states
    no end: its `depart` is `null`, the end being the dispatcher's once the
    request it follows has arrived (ADR-0080). An `after` that is not a
    non-empty id, or that comes with a stated end, states no request."""
    wanted = gesture(payload)
    if wanted is None:
        return None
    depart = payload.get("depart")
    after = payload.get("after")
    if after is not None:
        if not isinstance(after, str) or not after or depart is not None:
            return None
        return Submission(rid, wanted.train, None, wanted.arrivals, after)
    if not isinstance(depart, str):
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
        reread: Callable[[], Roster | None] | None = None,
    ) -> None:
        """The railroad's `roster` is the stock: every train it owns, whether
        anything places it or not. `placement` is train to block, and it is
        the whole of what a run can be *built* standing somewhere — the
        harness's batch loop, which is built from a scenario document
        (`bench/runner.py`). A run an operator drives passes none: its trains
        arrive by gesture, and a train nothing places comes up **off the
        layout** — known, standing nowhere, and waiting for a person to put it
        somewhere (ADR-0039).

        `reread` reads the railroad's roster again, once and without waiting
        on a store that does not answer, and is None where it cannot be read
        (ADR-0092, decision 1). A placement naming a train this dispatcher was
        not built with asks it, because a train made in the stock view after
        the last build is on the store's roster and nowhere else. The bench
        passes none: its stock is the scenario's and nothing changes it.
        """
        self._bus = bus
        self._strategy = strategy
        self._reread = reread
        # The last picture, where the bus binding held one across a restart:
        # the dispatcher's own state topic, found waiting exactly as it would
        # be against a broker that outlived the app (#123). Read here rather
        # than through `subscribe`, because placement has to be settled before
        # the standing locks below are published, and a subscription delivers
        # at the drain. Being read rather than subscripted is `restored`'s,
        # and what is left here is whether there is a value at all (#278).
        picture = bus.last_values.get(ALLOCATION, {})
        adopted = restored(picture, layout, roster, placement)
        self._priority = {
            name: train.priority_key for name, train in roster.trains.items()
        }
        self._state = State(
            layout,
            roster.lengths(),
            {},
            {},
            {},
            # The railroad comes up `off` (`State.power`), restored or cold,
            # so nothing is routed until a person turns the power on
            # (ADR-0078): a restored picture is wherever the last session
            # left the steel, and the person turning it on is the one who has
            # looked.
            crossing=adopted.crossing,
        )
        # Before the opening rows and not after. Over a broker a publish is
        # asynchronous where a subscribe waits for the broker to acknowledge,
        # so publishing first opens a window a round trip wide in which a
        # gesture addressed to this app is lost — `state/moving` is what a
        # client waits for to know the dispatcher is up, and a gesture is an event
        # that nothing replays. In one process the window had no width and the
        # order did not show. Safe here because `_on_dispatch` already ignores
        # this app's own announcements coming back past it, and nothing on
        # `tc49/layout/#` is published from this constructor at all.
        bus.subscribe("tc49/layout/#", self._on_layout)
        bus.subscribe("tc49/dispatch/#", self._on_dispatch)
        for train, at in adopted.standing.items():
            self._state.locks[at] = train
            self._state.block_of[train] = at
            bus.publish(
                "tc49/dispatch/lock_granted", {"train": train, "resources": [at]}
            )
        # Every request still alive, waiting or started, in the order the
        # dispatcher serves them (ADR-0080). A restart loses it.
        self._requests: list[Request] = []
        self._seen_ids: set[str] = set()
        # id -> (train, the end it leaves its follower departing by): each
        # request that has ended, so one chained after it is settled however
        # late it arrives. The end is None where it was rejected, ended by a
        # placement or a removal, or cancelled while it waited.
        self._finished: dict[str, tuple[str, str | None]] = {}
        self._phases = 0  # sweeps run; stamps admissions for grant order
        self._aspects: dict[str, str] = {}  # last published, so only changes go
        self._allocation: Payload = {}  # likewise: the picture, when it moves
        self._disputed: Payload = {}  # and what the detectors dispute
        # The stamps held against the state topics this app consumes, which
        # is `state/power` and nothing else (#240). Two power values
        # delivered backwards would otherwise leave the dispatcher believing
        # the track is dead while it is live, or the other way about, with
        # nothing to notice.
        self._ordering = Ordering()
        # The power, where the bus already holds a value of it: read here for
        # the reason the picture is, so a railroad that is already on routes
        # what is admitted from the first event rather than from the drain
        # that delivers the subscription. Through the ordering, so the
        # replay of the same value is no change. A bus holding none leaves
        # the railroad `off` (`State.power`).
        stated = bus.last_values.get(POWER)
        if stated is not None and self._ordering.accepts(POWER, stated):
            self._state.power = power(stated)
        # The last `state/moving` value published, so the topic moves only
        # when what it says moves.
        self._published_moving: bool | None = None
        # The trains the rebuild left off, until a person places each one.
        self._unfit = dict(adopted.unfit)
        # The lock table's rules broken at the last check (`_check`), so only
        # a rule newly broken drains the railroad.
        self._broken: list[str] = []
        # Whether a drain has been asked for (`_drain`) and `layout` has not
        # yet answered it, so nothing is granted in between (#1087).
        self._drain_asked = False
        # The opening statement is the whole of what the dispatcher holds, in
        # the order a grant phase says it. Aspects are in it because a restart
        # has a previous value on that topic too: the last session's
        # `caution` for a route this one did not restore would stand until
        # the first grant phase, and a panel joining in that window draws a
        # clear road nothing holds a lock on. `moving` opens it for the
        # same reason and one step earlier: it is the frame the rest is read
        # in, and a joining client is served a value rather than left to
        # read one out of an absence (ADR-0032). The disputed set closes it
        # for the same reason again: nothing has been reported yet, so the
        # set is empty, and saying so is what clears whatever the last
        # session left standing on that topic.
        self._publish_moving()
        self._publish_aspects()
        self._publish_allocation()
        self._publish_disputed()
        self._publish_unfit()
        self._check()

    # -- live state, for the property tests' oracles ------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def pending(self) -> tuple[Request, ...]:
        """The requests waiting, those not yet started, in list order."""
        return tuple(req for req in self._requests if not self._started(req))

    @property
    def requests(self) -> tuple[Request, ...]:
        """Every request alive, waiting or started, in list order."""
        return tuple(self._requests)

    def _started(self, req: Request) -> bool:
        active = self._state.active.get(req.train)
        return active is not None and active.request is req

    def _listed(self, rid: str) -> Request | None:
        return next((req for req in self._requests if req.id == rid), None)

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
        if request.after is not None and not self._follows_own(request):
            self._reject(rid, Reason.MALFORMED)
            return
        if self._names_no_such_block(request):
            self._reject(rid, Reason.UNKNOWN_BLOCK, request.train)
            return
        if request.train not in self._state.block_of:
            # Known but off the layout (ADR-0039): a train nothing placed,
            # one adoption could not place (#164), or one a person has
            # lifted off. Answered here rather than guarded at
            # each launch lookup, because this is the only way in — the one
            # thing that unplaces a train, `_remove`, refuses a train with a
            # request in flight, so a request that gets past this line names a
            # train with a block and the list holds none that stopped
            # having one.
            self._reject(rid, Reason.NO_ORIGIN, request.train)
            return
        expected = self._expected_block(request.train)
        if departs_elsewhere(request.depart, expected):
            self._reject(rid, Reason.WRONG_ORIGIN, request.train)
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
                request.train,
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
                self._reject(rid, Reason.UNREACHABLE, request.train)
                return

        admitted = Request(
            rid,
            request.train,
            request.depart,
            tuple(surviving),
            self._phases,
            priority=self._priority[request.train],
            after=request.after,
        )
        self._list(admitted)
        self._bus.publish(
            "tc49/dispatch/request_admitted",
            {"id": rid, "dest": surviving, "pruned": pruned},
        )
        if request.after is not None and request.after in self._finished:
            # The request it follows ended before this one arrived, which a
            # scheduler racing the end of a short request can see.
            self._follow(admitted, self._finished[request.after][1])
        # The waiting set grew: the request is considered now, not at a beat.
        self._sweep()

    def _reject(self, rid: str, reason: Reason, train: str | None = None) -> None:
        """A request refused. Where its train is known the end is kept, so a
        request chained after it is cancelled rather than left waiting."""
        if train is not None:
            self._finished[rid] = (train, None)
        self._publish("request_rejected", {"id": rid, "reason": reason})

    def _list(self, req: Request) -> None:
        """A new request into the list: after every request whose train has
        the same priority or a higher one (ADR-0080). Priority does nothing
        else."""
        at = 0
        for index, listed in enumerate(self._requests):
            if listed.priority <= req.priority:
                at = index + 1
        self._requests.insert(at, req)

    def _follows_own(self, request: Submission) -> bool:
        """Whether `after` names a request of the same train, still in the
        list or already ended. Anything else names no request it could
        follow, and the payload states none."""
        assert request.after is not None
        listed = self._listed(request.after)
        if listed is not None:
            return listed.train == request.train
        ended = self._finished.get(request.after)
        return ended is not None and ended[0] == request.train

    def _ending(
        self, req: Request, onward: str | None, revoking: Collection[str] = ()
    ) -> None:
        """A request ended: `onward` is the end its train now leaves by,
        where it arrived or was cancelled underway, and None where it was
        rejected, cancelled while it waited, or ended by a placement or a
        removal. The requests chained after it are settled by it (`_follow`),
        but for those in `revoking`, chained before its cancel was asked,
        which are cancelled with it (#836)."""
        self._finished[req.id] = (req.train, onward)
        for follower in self._followers(req):
            self._follow(follower, None if follower.id in revoking else onward)

    def _followers(self, req: Request) -> list[Request]:
        """The requests listed that are chained after `req`."""
        return [each for each in self._requests if each.after == req.id]

    def _follow(self, follower: Request, onward: str | None) -> None:
        """A chained request whose predecessor has ended. Where that one
        arrived, or was cancelled underway before this one was chained after
        it, the follower departs by `onward`, the end of the block the train
        stands in opposite the one it came in through, so it carries on the
        way it was going; where that end leads nowhere it is rejected
        `unreachable`. Where the predecessor ended any other way it is
        cancelled `revoked`, and so is whatever follows it in turn
        (ADR-0080, #836)."""
        if onward is not None and onward in self._state.layout.end_connection:
            follower.depart = onward
            return
        self._requests.remove(follower)
        if onward is None:
            self._publish(
                "request_cancelled",
                {"id": follower.id, "reason": Cancellation.REVOKED},
            )
        else:
            self._publish(
                "request_rejected", {"id": follower.id, "reason": Reason.UNREACHABLE}
            )
        self._ending(follower, None)

    def _names_no_such_block(self, request: Submission) -> bool:
        """Whether the request names track the layout does not have — its
        arrival blocks, and the departure block where it states one. A fact
        only the dispatcher holds, so it is answered rather than raised, and
        it is not `wrong_origin`: the train is not standing there, but
        neither is anything else."""
        blocks = [block_of(end) for end in request.dest]
        if request.depart is not None and "." in request.depart:
            blocks.append(block_of(request.depart))
        return any(block not in self._state.layout.blocks for block in blocks)

    def _has_pending(self, train: str) -> bool:
        """Whether a request of the train's own is still waiting, which is
        what makes both where it will stand and where it will depart from a
        future dispatcher choice."""
        return any(req.train == train for req in self.pending)

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
        dispatcher choice. A request chained by `after` is left to its launch
        too: its end is settled when the one it follows arrives.

        Behind an **active** route both are already settled: a route is fixed
        once chosen (ADR-0002), so the block it arrives at is known and the
        end it leaves the train facing with it. Behind a still **pending**
        one nothing is, which is the only case DISPATCH.md's deferral to the
        launch stage was ever about (#135).
        """
        if request.depart is None or self._has_pending(request.train):
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
        """The five topics the dispatcher responds to, on one filter.

        A request, and the four gestures a person makes on a page: all five
        name the dispatcher because the dispatcher is what answers them, and
        none of them says who sent it. The scheduler submits requests today
        and a second one could submit them tomorrow with nothing here to
        change (BUS.md, rule 4).

        Everything else on `tc49/dispatch/#` is the dispatcher's own
        announcements coming back past it, and is ignored — the filter is the
        component, as every consumer's is (BUS.md, rule 3). What it cannot
        act on it drops, in silence and to the trace: a gesture carries no id
        and there is nothing to address an answer to (ADR-0034). A placement
        is the exception: its answer, `placement_refused`, names what the
        gesture named instead (ADR-0092).
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "request_submitted":
            self._on_request(payload)
        elif leaf == "placement_wanted":
            self._place(payload)
        elif leaf == "cancel_wanted":
            self._revoke(payload)
        elif leaf == "reorder_wanted":
            self._reorder(payload)
        elif leaf == "point_wanted":
            self._throw(payload)
        self._check()

    def _place(self, payload: Payload) -> None:
        """Where a train actually is, said by the person who can see it: the
        block it stands in, or nowhere at all.

        **One gesture in two directions** (ADR-0039). Putting a locomotive on
        the track and lifting it off are the same act said with a different
        destination, so `block: null` is a placement whose answer is *off the
        layout* rather than a leaf of its own.

        The train has to be known either way, on this dispatcher's roster or,
        read again, on the store's (ADR-0092), and **either direction is
        accepted at any power** (#821, ADR-0069): a person puts a train on
        the rails or lifts it off whenever they need to, and what decides
        whether a block can take it is whether the block is **free** — of
        every lock and every route committed through it (`State.free`) —
        rather than whether anything else is running. What a removal frees
        is freed the way a cancellation frees it, with the track a loco still
        stands on kept until it reads clear. A
        **request in flight was a precondition** and is not one any more
        (ADR-0049): the gesture cancels it first and then places the
        train, so `request_cancelled` precedes `train_placed` or
        `train_removed` and those two always describe a train with no request.
        The reason says which direction the gesture pointed — `removed` off
        the layout, `displaced` into a block.

        The block is judged first (`_judged`): it has to exist, fit the train
        and be free of every claim but those the cancellation would release.
        Leaving those out is what makes the placement possible at all rather
        than merely permitted: the train's own route holds the blocks it was
        going to run through, so a person standing it in one of them would
        otherwise be refused for a claim that belongs to the very request
        their gesture is ending. What the old precondition protected still
        holds with nothing left to protect it — a cancelled request departs
        from nowhere, and no queued request outlives the placement to depart
        from the wrong block.

        **A placement the railroad cannot accept changes nothing** (#1062):
        the requests stand, and so does the train's move. Cancelled first, a
        train crossing would have its route released under it and no
        `train_placed` to tell `layout`, which would go on driving it.

        **A refusal is answered**, never dropped in silence: `placement_refused`
        names the train and block the gesture named and why (ADR-0092,
        decision 3), an unknown train being one the store's roster lacks too.
        A payload that cannot be read as a placement names no train, and is
        dropped with no answer.

        Where the train stands *now* is no precondition at all: one adoption
        placed nowhere (`restored`) is exactly the train a person has to say
        something about.
        """
        wanted = placement(payload)
        state = self._state
        if wanted is None:
            return
        if wanted.train not in state.roster:
            self._learn()
        if wanted.train not in state.roster:
            self._refuse(wanted.train, wanted.block, PlacementRefusal.UNKNOWN_TRAIN)
            return
        if wanted.block is None:
            self._remove(wanted.train)
        else:
            refused = self._judged(wanted.train, wanted.block)
            if refused is not None:
                self._refuse(wanted.train, wanted.block, refused)
                return
            self._cancel(wanted.train, Cancellation.DISPLACED)
            self._stand(wanted.train, wanted.block)
            # What the cancellation gave up, or the block the train left, is
            # track somebody else may have been refused for (ADR-0047). The
            # sweep also publishes what a placement moves besides the lock
            # table: the picture, the disputed set the entry just resolved
            # leaves (#153), and `moving`, which saying where a crossing train
            # stands drops — the way out of a drain a wedged train holds open
            # (ADR-0062), so the row has to follow it or `layout` waits
            # forever to switch the supply off.
            self._sweep()

    def _learn(self) -> None:
        """The trains the store's roster has and this dispatcher lacks, added
        (ADR-0092, decision 1). A train it already has keeps the length and
        priority it was built with until the next build (ADR-0071): a placed
        train whose length changed under it is a rule nobody has written. A
        store that does not answer, or a roster it refuses, adds nothing."""
        if self._reread is None:
            return
        roster = self._reread()
        if roster is None:
            return
        for name, train in roster.trains.items():
            if name not in self._state.roster:
                self._state.roster[name] = train.length
                self._priority[name] = train.priority_key

    def _judged(self, train: str, block: str) -> PlacementRefusal | None:
        """Why the train may not be put in the block, or None where it may:
        the block has to exist, be free of every claim (`State.free`), and fit
        the train."""
        state = self._state
        if block not in state.layout.blocks:
            return PlacementRefusal.UNKNOWN_BLOCK
        if not state.free(block, train):
            return PlacementRefusal.NOT_FREE
        if state.roster[train] > state.layout.blocks[block]:
            return PlacementRefusal.NO_FIT
        return None

    def _stand(self, train: str, block: str) -> None:
        """A train put on the layout, or moved by hand from where it was, in
        a block `_judged` accepted.

        A block the train still holds as residue of its own removal becomes
        its standing lock (ADR-0069); whatever else it holds that way stays
        until it reads clear. The dispatcher moves the train's standing lock
        and announces `train_placed`. That event is the ledger line for a
        placement: a `lock_released` and a `lock_granted` would say a route
        gave a block up and took another, which is not what happened — a hand
        lifted a locomotive, and the fact has its own leaf so a reader can
        tell the two apart.
        """
        state = self._state
        state.residue.discard(block)
        # A train that is off the layout holds no standing lock and has none
        # to give up: this gesture is what puts it back on (ADR-0039, #164).
        # Placing one is otherwise the same act.
        # Released only if the train holds it: a lock table that has stopped
        # describing the railroad is the case a person is placing in front
        # of, and another train's lock is not this train's to give up.
        standing = state.block_of.get(train)
        if standing is not None and state.locks.get(standing) == train:
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
        if self._unfit.pop(train, None) is not None:
            self._publish_unfit()
        # A transit kept for this block alone has nothing left to wait for:
        # the block is a standing lock now, and no clear reading will come
        # for it as residue.
        self._open(train, self._spent(train))

    def _refuse(self, train: str, block: str | None, reason: PlacementRefusal) -> None:
        """A placement not accepted, answered with the train and block the
        gesture named and why (ADR-0092, decision 3). It carries no id: what
        it names is what a reader matches it to its drag by (ADR-0034)."""
        self._publish(
            "placement_refused", {"train": train, "block": block, "reason": reason}
        )

    def _remove(self, train: str) -> None:
        """A train taken off the layout: lifted out of its block by hand.

        It is not deletion. The train stays on the roster and can be placed
        again; what it loses is its place on the rails, which is absence from
        `block_of` and not a sentinel (ADR-0039).

        Accepted at any power (ADR-0069). Its requests are cancelled
        first, `removed`, so `train_removed` describes a train with none.

        **What it held is released**, except what a loco may still be
        standing on: each block a detector last read occupied stays held by
        the train, and so does the transit it was crossing while either of
        that transit's blocks does. Those wait in `residue` for a clear
        reading (`_lifted`). Everything else goes in one `lock_released` —
        the sweep is by holder, because a train mid-request holds its route,
        and a restored crossing train holds its block as any placed train
        does (#154). A block the layout has said
        nothing about has nothing to wait for and is released, as everywhere
        else in the dispatcher.

        Computed before the cancellation, which forgets which transit the
        train was crossing. Track a removal frees is what a cancellation
        frees, so it sweeps for it, and the sweep grants only while power
        reads `on`.

        A train that is already off the layout is left alone. The gesture
        asks for a state it is in, and there is no fact to announce.
        """
        state = self._state
        kept = self._kept(train)
        self._cancel(train, Cancellation.REMOVED, keep=kept)
        if train not in state.block_of and train not in state.crossing:
            self._sweep()  # for whatever the cancellation ended
            return
        self._release(train, keep=kept)
        state.residue |= kept
        state.block_of.pop(train, None)
        # A crossing train stands in no block, and off the layout it is not on
        # a transit either: the hint goes with the placement it belonged to.
        state.crossing.pop(train, None)
        self._publish("train_removed", {"train": train})
        self._sweep()

    def _kept(self, train: str) -> set[str]:
        """What a removal of `train` leaves held: each block it holds that a
        detector last read occupied, and the transit it is crossing if either
        of that transit's blocks is among them (ADR-0069)."""
        state = self._state
        kept = {
            resource
            for resource, holder in state.locks.items()
            if holder == train and state.reported.get(resource) is True
        }
        transit = state.crossing.get(train)
        if (
            transit is not None
            and state.locks.get(transit) == train
            and kept & transit_blocks(state.layout, transit)
        ):
            kept.add(transit)
        return kept

    def _spent(self, train: str) -> list[str]:
        """The transits `train` holds as residue that no residual block of its
        own is left to keep."""
        state = self._state
        return [
            resource
            for resource in state.residue
            if resource not in state.layout.blocks
            and state.locks.get(resource) == train
            and not any(
                state.locks.get(block) == train and block in state.residue
                for block in transit_blocks(state.layout, resource)
            )
        ]

    def _open(self, train: str, resources: list[str]) -> None:
        """Residue given up, as one `lock_released`."""
        state = self._state
        for resource in resources:
            del state.locks[resource]
            state.residue.discard(resource)
        if resources:
            self._publish(
                "lock_released", {"train": train, "resources": sorted(resources)}
            )

    def _release(self, train: str, keep: Collection[str] = ()) -> list[str]:
        """Everything the train holds, given up as one `lock_released` — all
        of it, or all of it but `keep`.

        **One release path**, because there is only one fact to state: the
        resources are free and nothing took them. A train at rest holds its
        standing block, a restored crossing train holds its block as any
        placed train does (#154), and a train under `FullRoute`
        holds every block of a route it will now never run — so the sweep is
        by **holder** rather than of a named set, and a caller that knew the
        set would be re-deriving the lock table.

        `keep` is what the train goes on holding. A cancellation releases
        everything the request took and leaves the train where it is, which is
        a train at rest and its standing lock (ADR-0049); a removal keeps what
        still reads occupied (ADR-0069). Residue of an earlier removal is
        never released here: it waits for its clear reading whatever the
        train does next.
        """
        state = self._state
        released = sorted(
            resource
            for resource, holder in state.locks.items()
            if holder == train
            and resource not in keep
            and resource not in state.residue
        )
        for resource in released:
            del state.locks[resource]
        if released:
            self._publish("lock_released", {"train": train, "resources": released})
        return released

    def _revoke(self, payload: Payload) -> None:
        """A person ending one request without it arriving (ADR-0049,
        ADR-0080), named by its id.

        A request waiting is cancelled at once. One underway gives up what it
        holds but the block its train stands in, unless a move of its own is
        outstanding: nothing on the bus retracts a `move` already sent, so
        the request is marked instead, granted nothing further, and retires
        when that move's sensors end it (`_ended`). The requests chained after
        it by then are cancelled `revoked` as it ends; one chained after it
        once the cancel was asked departs from where the train stops
        (`_follow`, #836). The deferral asks `layout` to take the move back,
        and ends at once where it does (`_withdrawn`, #1068). An id the
        dispatcher does not hold is dropped in silence and to the trace, as
        every gesture it cannot act on is (ADR-0034).

        It is accepted **at any power**. Cancelling is how a person ends work
        the railroad cannot finish — a train that broke down, a route chosen
        against a railroad that has since changed under it — and making them
        turn the power off first would stop every other train to let one go.
        This retires one request, and what it frees the next sweep hands to
        somebody else.
        """
        rid = readable_id(payload)
        req = None if rid is None else self._listed(rid)
        if req is None:
            return
        active = self._state.active.get(req.train)
        if active is not None and active.request is req:
            if req.cancelled:
                return
            req.revoking = frozenset(each.id for each in self._followers(req))
            if active.outstanding is not None:
                # Deferred: it frees nothing yet and dequeues nothing, so
                # there is nothing for a sweep to hand anybody. `layout` is
                # asked to take the move back, which it does where nothing
                # has driven the train since (`_withdrawn`, #1068).
                req.cancelled = True
                self._bus.publish(
                    WITHDRAW_WANTED,
                    {
                        "train": req.train,
                        "transit": active.outstanding.transit,
                        "into": active.outstanding.into,
                    },
                )
                return
            self._retire(req.train, active, Cancellation.REVOKED)
        else:
            self._requests.remove(req)
            self._publish(
                "request_cancelled", {"id": req.id, "reason": Cancellation.REVOKED}
            )
            self._ending(req, None)
        # What a cancelled route was holding is exactly what somebody else
        # has been refused for, and a request that waited can have been
        # what kept its train's next one from starting (ADR-0047).
        self._sweep()

    def _withdrawn(self, payload: Payload) -> None:
        """`layout` took back the move a cancelled request had outstanding:
        nothing had driven the train since it acted on the move, so the train
        never left its block (#1068).

        The request retires as the move's sensors would have retired it
        (`_ended`), `revoked`, keeping only the block the train stands in,
        which is the move's origin: the train is put back where it was before
        the grant, so a request chained after it departs from there. Anything
        else is dropped — a request not cancelled, a move not outstanding, a
        transit other than the one it crosses or a block other than the one
        it enters (#1080) — the answer being about a move this dispatcher no
        longer holds."""
        withdrawn = withdrawal(payload)
        if withdrawn is None:
            return
        active = self._state.active.get(withdrawn.train)
        if active is None or not active.request.cancelled:
            return
        move = active.outstanding
        if (
            move is None
            or move.transit != withdrawn.transit
            or move.into != withdrawn.into
        ):
            return
        active.outstanding = None
        active.cur_index -= 1
        del self._state.crossing[withdrawn.train]
        self._retire(withdrawn.train, active, Cancellation.REVOKED)
        self._sweep()

    def _reorder(self, payload: Payload) -> None:
        """A person moving one request in the list, in front of `before` or
        to the end (ADR-0080).

        Dropped in silence and to the trace where either request is unknown
        or has started, and where the move would put a train's chained
        request before the one it follows. Otherwise the list is served in
        its new order from this sweep on: an earlier request gets the first
        claim, and the train whose request moved ahead of its own others may
        now start that one first.
        """
        wanted = wanted_reorder(payload)
        if wanted is None:
            return
        moved = self._listed(wanted.id)
        if moved is None or self._started(moved):
            return
        order = [req for req in self._requests if req is not moved]
        if wanted.before is None:
            order.append(moved)
        else:
            target = self._listed(wanted.before)
            if target is None or target is moved or self._started(target):
                return
            order.insert(order.index(target), moved)
        at = {req.id: index for index, req in enumerate(order)}
        if any(req.after in at and at[req.after] > at[req.id] for req in order):
            return
        if order == self._requests:
            return
        self._requests = order
        self._sweep()

    def _cancel(
        self,
        train: str,
        reason: Cancellation,
        keep: Collection[str] | None = None,
    ) -> None:
        """Every request the train has, retired without the train arriving,
        for a placement that ends them (ADR-0049).

        The active one first and the waiting ones behind it in list order, so
        a reader of the trace sees the request that was running end before the
        ones that were waiting on it. Each gets its own `request_cancelled`
        with the placement's reason, the chained ones included: an id is what
        ties a request's events together.

        A waiting request has taken nothing and needs no release. The active
        one is holding a route — every transit and every block beyond the
        origin under `FullRoute` — and gives up **all of it but the block the
        train stands in**: that block is the train's standing lock, which
        every parked train holds (GLOSSARY.md), and releasing it would leave a
        locomotive in a block the dispatcher believes free.

        A placement does not defer, as a `cancel_wanted` does: the person is
        saying where the train actually *is*, and the placement is what
        answers the move — a move whose sensors may never come is the case
        they are standing in front of. So the request retires at the gesture,
        and an occupied reading that does arrive for it afterwards explains
        nothing and drains the railroad (ADR-0048), which is the right answer to a
        detector firing under a train somebody has just moved by hand. A clear
        reading on track the gesture gave up is a block nobody holds reading
        clear, and holds nothing (ADR-0077).

        `keep` overrides the standing lock as what the active request leaves
        held, for a removal, which keeps what still reads occupied instead.
        """
        waiting = [req for req in self.pending if req.train == train]
        for req in waiting:  # out first, so none is cancelled `revoked`
            self._requests.remove(req)
        active = self._state.active.get(train)
        if active is not None:
            self._retire(train, active, reason, keep)
        for req in waiting:
            self._publish("request_cancelled", {"id": req.id, "reason": reason})
            self._ending(req, None)

    def _retire(
        self,
        train: str,
        active: Active,
        reason: Cancellation,
        keep: Collection[str] | None = None,
    ) -> None:
        """The active request ended: what it holds released, the train
        dropped out of everything that says it is running one, and the one
        event that says so. A person's cancel leaves the requests chained
        after it once it was asked departing from where the train stopped
        (#836); a placement or a removal leaves none.

        `_seen_ids` is not pruned. A cancelled id stays used for the session,
        because an id is unique and not meaningful (ADR-0033) and a resubmit
        of it is the duplicate it looks like.
        """
        state = self._state
        if keep is None:
            standing = state.block_of.get(train)
            keep = () if standing is None else (standing,)
        self._release(train, keep=keep)
        del state.active[train]
        state.crossing.pop(train, None)
        state.departure.pop(train, None)
        self._requests.remove(active.request)
        self._publish("request_cancelled", {"id": active.request.id, "reason": reason})
        if reason is Cancellation.REVOKED:
            self._ending(active.request, self._stopped(active), active.request.revoking)
        else:
            self._ending(active.request, None)

    # -- the sensors, and the sweep they trigger ----------------------------

    def _on_layout(self, topic: str, payload: Payload) -> None:
        """What the layout interface says, and the two commands sent to it.

        `align` and `move` are on this filter because they name the component
        that responds to them, and the dispatcher is not that component: the
        sensor leaves are named here so a command passes by unread rather
        than being taken for a reading with no block in it. So is its own
        `withdraw_wanted`, and `layout`'s answer to it, `move_withdrawn`, is
        read (#1068). So is `power_wanted`, for a person's `on` (#1087).
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "move_withdrawn":
            self._withdrawn(payload)
        elif leaf == "power_wanted":
            # A person's `on` ends a hold `layout` has not answered (`_drain`).
            if wanted_power(payload) == ON and self._drain_asked:
                self._drain_asked = False
                self._sweep()
        elif leaf == "power":
            # An older value of the supply than the one already held means
            # the wire handed the pair over backwards: it is ignored, and
            # quietly — the trace has it, as it has every frame. The sensor
            # leaves below take no such guard, being event topics where a
            # repeat re-asserts a level (ADR-0047).
            if self._ordering.accepts(topic, payload):
                self._on_power(payload)
        elif leaf in ("block_occupied", "block_vacated"):
            block = occupancy(payload)
            # None is dropped, and on the trace already by virtue of having
            # been published (ADR-0034): the block stays out of `reported`,
            # so it takes no part in the check and the next report settles
            # it. Why this direction and not the power enum's is SYSTEM.md,
            # sole payload authority (#181).
            if block is not None:
                self._on_sensor(leaf == "block_occupied", block)
        self._check()

    def _on_sensor(self, occupied: bool, block: str) -> None:
        """One detector reading, applied where it lands (ADR-0047).

        A detector reports presence, which is a level: a reading that
        re-asserts what `reported` already holds is an at-least-once repeat
        and a no-op, so delivery needs no counter and no dedup. A reading
        that *changes* the level either explains a granted move — recorded
        arrival for `block_occupied`, a finished move for `block_vacated` —
        or explains nothing, which drains the railroad (ADR-0048). Either way the
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
        """A reading no granted move accounts for: **the railroad drains**
        (ADR-0048, ADR-0078).

        A hand putting a locomotive on a detected block, a train pushed while
        the supply was off, a cut of cars a broken coupling left standing, a
        detector asserting on dirt — they differ for the person recovering and
        not here. All of them say the lock table has stopped describing the
        steel, and the dispatcher's whole safety argument runs over that table
        (SAFETY.md): a block reading occupied with nothing claiming it is one
        `safe()` believes free, and granting it is a collision the check would
        call safe.

        So the dispatcher asks `layout` for a drain, as a person's press would
        (`_drain`): nothing new commits, every signalled end shows `stop`, the
        move already outstanding still runs to its sensors, and the supply
        goes off once nothing is moving. It does not raise: the frame is well
        formed and a handler that raised would take the app off the bus for
        an ordinary act of a person's hand (BUS.md, rule 4). It is not dropped
        either, and nothing is placed: occupancy is anonymous, so there is no
        train to place, and the reading is on the trace and in the dispute set
        power `off` turns on, which is what points a person at it (#153). They
        walk the railroad, place what they find, and turn the power on.
        """
        self._drain()

    def _check(self) -> bool:
        """The lock table's rules, checked (`broken`): a rule broken now and
        not at the last check **drains the railroad**, by the path an
        unexplained reading takes, and is written to stderr (ADR-0076,
        ADR-0078). Answers whether one was.

        A rule still broken from the last check does nothing, so a person who
        has looked and turned the power on again is not overruled by the next
        sweep (#811); one that clears and breaks again drains again. It does
        not raise, for ADR-0048's reason: an exception out of a handler takes
        the app off the bus.

        Called at the end of each event and before each grant pass, never
        after a single write: a handler changes several maps in steps, and
        the steps are not meant to agree with each other in between.
        """
        lines = broken(self._state)
        new = [line for line in lines if line not in self._broken]
        self._broken = lines
        for line in new:
            print(f"dispatcher: lock table: {line}", file=sys.stderr, flush=True)
        if new:
            self._drain()
        return bool(new)

    def _drain(self) -> None:
        """A fault asking `layout` for a drain: `power_wanted: draining`, the
        press a person makes for an ordinary shutdown (ADR-0078, decision 7).

        Asked, not done. `layout` owns the switch and states the answer on
        `state/power`, and the dispatcher stops routing when it reads it, as
        it does for a person's press; holding the dispatcher on a value of its
        own would split the switch again, and a person turning the power on
        could then find it reading `on` and nothing routing. Only while power
        reads `on`: `draining` is answered from `on` alone, so asking from
        anywhere else asks for nothing — and a railroad that is already
        draining or off is already where a fault would put it.

        **From the ask until the answer nothing is granted** (#1087). Power
        goes on reading `on` until `layout` answers, and a request or a vacate
        arriving in between would otherwise be granted from the table the
        fault just said is wrong. The hold ends on the first `state/power`
        that does not read `on`, after which power holds the grants itself,
        or on a person pressing `on`, which acknowledges the fault
        (ADR-0078, decision 7) and covers a `layout` that never answers.
        """
        if self._state.power == ON:
            self._drain_asked = True
            self._bus.publish(POWER_WANTED, {"power": DRAINING})

    def _arrived(self, block: str) -> None:
        """`block_occupied` records where the train arrived, and ends the move
        if its origin has read clear since the grant and still does (ADR-0077,
        #806). Otherwise the move is not over: the tail is still in the origin
        block, the train is between blocks, and it takes no further grant
        until the vacate ends the move (ADR-0047).

        Either way the allocation recording the arrival goes out before any
        grant the arrival leads to: the scheduler moves the train's facing
        when the allocation names it in the block its move entered, and
        `layout` reads that facing for the next `move`, dropping one whose
        facing names another block (#1025, #1038, ADR-0052)."""
        found = self._explained(block)
        if found is None or found[2].into != block:
            self._unexplained()
            return
        train, active, move = found
        self._state.block_of[train] = block
        # The train is recorded past the signal it left by, which now shows
        # `stop` (ADR-0093) — before `_ended`'s sweep can grant its next move.
        self._publish_aspects()
        self._publish_allocation()
        if active.origin_cleared and self._state.reported.get(move.from_block) is False:
            self._ended(train, active, move)

    def _cleared(self, block: str) -> None:
        """`block_vacated` of a move's origin ends the move once its arrival
        block reads occupied (ADR-0077).

        **Before the arrival it only marks the move's origin cleared**: no
        release, no grant, and no drain. The layout publishes a vacate when the
        origin's own detectors go clear, and a train shorter than the gap to
        the next block's entry detector reads clear behind before it reads
        occupied ahead, which is normal running. The train may be standing on
        the connection's points, so the origin and the transit stay locked,
        and the arrival ends the move.

        A clear reading on a block nobody holds is explained too: a stray or
        a stuck detector clearing, which gives back a block a train may be
        waiting on, so it sweeps rather than draining the railroad.
        """
        state = self._state
        found = self._explained(block)
        if found is None or found[2].from_block != block:
            if block not in state.locks:
                self._sweep()
            elif not self._lifted(block):
                self._unexplained()
            return
        train, active, move = found
        if state.block_of.get(train) == move.into:
            self._ended(train, active, move)
        else:
            active.origin_cleared = True

    def _ended(self, train: str, active: Active, move: Move) -> None:
        """A move over, on both its readings — origin clear, arrival
        occupied, in either order (ADR-0077): it releases the origin block
        and the transit and completes the request, and what it released is
        why a sweep runs here (ADR-0047).

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
        active.outstanding = None
        del state.crossing[train]
        if active.request.cancelled:
            self._retire(train, active, Cancellation.REVOKED)
        else:
            del state.locks[move.from_block]
            del state.locks[move.transit]
            self._publish(
                "lock_released",
                {"train": train, "resources": [move.from_block, move.transit]},
            )
            if active.cur_index == len(active.route.blocks) - 1:
                del state.active[train]
                self._requests.remove(active.request)
                self._publish("request_completed", {"id": active.request.id})
                self._ending(active.request, opposite_end(self._entered(active.route)))
        self._sweep()

    def _lifted(self, block: str) -> bool:
        """A clear reading on a block a removed train still holds: the hand
        has lifted the loco, and the block opens (ADR-0069). Answers whether
        the reading was that.

        The reading is explained, so the railroad does not drain. It releases the
        block, and the transit kept for it once neither of that transit's
        blocks is still residue, in one `lock_released` — and what it frees is
        why a sweep runs here, as at the end of any move. A clear reading
        under a train that stands in its block is still unexplained
        (ADR-0048): a detector dropping out under a dirty wheel reads the
        same, and only a removal says it was a lift.
        """
        state = self._state
        if block not in state.residue:
            return False
        train = state.locks[block]
        state.residue.discard(block)
        self._open(train, [block, *self._spent(train)])
        self._sweep()
        return True

    def _on_power(self, payload: Payload) -> None:
        """What the layout says about the one switch a person turns: `on`,
        `draining` or `off` (ADR-0078).

        Anything but `on` **routes nothing**: no route is chosen, no move
        granted and no lock taken, and every signalled end shows `stop`
        rather than going on showing `clear` over a train that will not be
        let past it (ADR-0041). Which of the others it is changes nothing here
        but the disputed set, compared only under `off` — `layout` switches a
        drain off once `state/moving` reads false, and the panel is where the
        person is told which it is.

        "Anything but `on`" is read literally, so a payload that cannot be
        read at all is one of those cases rather than an exception: the value
        comes through `payload.power`, which answers `off` where a
        subscript would have raised (#175).

        Power **returning** to `on` runs a sweep (ADR-0078, decision 6): a
        person turning the power on is the whole of the go, after a drain, a
        cut or a fault alike, and every train carries on with what it was
        granted while the waiting requests are routed.

        What it cannot do is undo the cut. A train granted a move that no
        sensor will ever answer keeps its locks and its `crossing` entry, and
        every train waiting on those resources waits with it, until somebody
        takes that train off or places it again, which cancels its request
        (ADR-0049) — nothing on the bus retracts a `move` already sent.
        """
        was = self._state.power
        self._state.power = power(payload)
        if self._state.power != ON:
            self._drain_asked = False
        if self._state.power == was:
            return
        if self._state.power == ON:
            self._sweep()
        else:
            self._publish_aspects()
            self._publish_disputed()

    def _sweep(self) -> None:
        """One grant pass, run where the lock table or the waiting set
        changed: a request admitted, cancelled or moved in the list, a vacated
        block releasing what a move held, the power coming back `on`. A sweep
        covers the whole list, so a refused request is reconsidered exactly
        when the resource it waited on frees (ADR-0047).

        While power reads anything but `on` nothing commits (ADR-0078): a move
        already sent is not retractable, so a sensor still applies where it
        lands, and what is withheld is everything that would commit something
        new — a drain grants no train its next move, and each stops in the
        block it is entering. `_phases` keeps counting whatever the power is
        doing: the count is what stamps an admission with the grant order it
        joined at.
        """
        self._phases += 1
        # Before the grant pass, so a table that has stopped agreeing with
        # itself grants nothing in this sweep (ADR-0076), however long the
        # drain it asked for takes to come back on `state/power`.
        faulted = self._check()
        if self._state.power == ON and not faulted and not self._drain_asked:
            self._grant()
        self._publish_aspects()
        self._publish_allocation()
        self._publish_disputed()
        # And `moving`: a grant puts a train in `crossing`, and a sweep
        # follows each place that takes one out, so it is where the boolean
        # moves (ADR-0062).
        self._publish_moving()

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
        # The list in its order (ADR-0080): each waiting request is offered
        # the first claim in turn, and one that cannot start is skipped, so a
        # later one still starts where an earlier one cannot. A train's own
        # requests run in list order: once one of them is left waiting —
        # refused, or launched and now active — the rest of that train's wait.
        # Letting a later request overtake a refused one would run a train's
        # work out of order and from the wrong origin.
        waiting: set[str] = set(state.active)
        for req in self.pending:
            if req.train in waiting or req not in self._requests:
                # The second: a request chained after one this sweep has just
                # rejected, and cancelled with it.
                continue
            if req.depart is None:
                # Chained, and the request it follows has not arrived.
                waiting.add(req.train)
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
                self._requests.remove(req)
                self._reject(req.id, Reason.WRONG_ORIGIN)
                self._ending(req, None)
                continue
            if any(block_of(end) == origin for end in req.arrivals):
                # Degenerate: already standing in an arrival block, whichever
                # end that arrival names. Empty route, complete in this phase.
                # The train did not move, so the request chained after it
                # leaves the way this one would have.
                self._requests.remove(req)
                self._publish(
                    "route_chosen", {"id": req.id, "route": [origin], "k_tried": 0}
                )
                self._publish("request_completed", {"id": req.id})
                self._ending(req, depart)
                continue
            result = self._strategy.launch(req, origin, depart, state)
            if result is None:
                self._requests.remove(req)
                self._reject(req.id, Reason.UNREACHABLE)
                self._ending(req, None)
            elif isinstance(result, Refused):
                waiting.add(req.train)
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
        # The request stays where it is in the list, started (ADR-0080).
        # The strategy says what to lock and the dispatcher locks it (#761),
        # before the grant below, which reads the launch's locks to tell what
        # it newly locks.
        for resource in launched.locked:
            self._state.locks[resource] = req.train
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
        self._state.departure[req.train] = departure_end(
            self._state.layout, self._entered(launched.route)
        )
        move = self._strategy.grant(req.train, self._state)
        assert isinstance(move, Move)  # the launch just granted the first increment
        self._apply_move(self._state.active[req.train], move)

    def _stopped(self, active: Active) -> str:
        """The end a train whose request is cancelled underway carries on by:
        the end of the block it stands in opposite the one it came in
        through, or, where it never left its origin, the end its route
        departed by (#836)."""
        route, at = active.route, active.cur_index
        if at == 0:
            ends = transit_ends(self._state.layout, route.blocks[0], route.transits[0])
            assert ends is not None  # a route's transits reach its blocks
            return ends[0]
        ends = transit_ends(
            self._state.layout, route.blocks[at], route.transits[at - 1]
        )
        assert ends is not None
        return opposite_end(ends[0])

    def _entered(self, route: Route) -> str:
        """The end of its arrival block a route comes in through."""
        ends = transit_ends(self._state.layout, route.arrival_block, route.transits[-1])
        assert ends is not None  # a route's transits reach its blocks
        return ends[0]

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
        for resource in (*result.locked, *result.ahead):
            self._state.locks[resource] = active.request.train
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
                # Read off the locks the move has just taken, from where
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
        active.origin_cleared = False
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
        where nothing needs throwing, and always `reported` on each, `false`
        where the address is not (ADR-0097): the document is quiet, the wire
        explicit.
        """
        connection, _, transit = transit_id.partition(".")
        needed = self._state.layout.connections[connection].points.get(transit, ())
        self._bus.publish(
            "tc49/layout/align",
            {
                "connection": connection,
                "transit": transit,
                "points": [
                    {
                        "addr": point.addr,
                        "position": point.position,
                        "reported": point.reported,
                    }
                    for point in needed
                ],
            },
        )

    def _throw(self, payload: Payload) -> None:
        """A person throwing a point by hand, passed on unless the point is
        **lit** (ADR-0068).

        Dropped in silence and to the trace, as every gesture the dispatcher
        cannot act on is (ADR-0034), where the address is one no point on
        this railroad wears — the one a signal wears would change its aspect
        instead — and where **any** point wearing it lies on the way of a
        transit that is locked, a crossing train's included, or committed
        ahead of an active train. Points sharing an address move together,
        so one of them on a lit road is the whole address on it.

        Otherwise it goes out as an `align` naming no transit, carrying the
        one point as asked, `reported` where any point wearing the address is
        (ADR-0097): on `align` and not a topic of its own so that it
        keeps its order against a route's (ADR-0008). The dispatcher keeps no
        record of where it left the point. Every `align` sends all the points
        its transit needs, so the next route over this one sets it again.

        The power does not stop it. Throwing a point on a road nothing is lit
        over commits nothing, which is all power not `on` refuses; with the
        power off the layout stores the row and the point moves
        when power returns (ADR-0054).
        """
        point = wanted_point(payload)
        if point is None:
            return
        connections = self._state.layout.connections
        wearing = [
            (f"{name}.{transit}", each)
            for name, connection in connections.items()
            for transit, needed in connection.points.items()
            for each in needed
            if each.addr == point.addr
        ]
        worn = {transit for transit, _ in wearing}
        if not worn:
            return
        lit = set(self._state.locks)
        for active in self._state.active.values():
            lit.update(active.route.transits[active.cur_index :])
        if worn & lit:
            return
        self._bus.publish(
            "tc49/layout/align",
            {
                "connection": None,
                "transit": None,
                "points": [
                    {
                        "addr": point.addr,
                        "position": point.position,
                        "reported": any(each.reported for _, each in wearing),
                    }
                ],
            },
        )

    def _moving(self) -> bool:
        """Whether a power cut now would strand something: any train crossing
        (GLOSSARY.md, **Moving**, #844). A train standing in a block loses
        nothing when the supply goes, whether or not it is active: one a drain
        stopped at a signal partway along its route keeps that route and its
        locks, and carries on once power reads `on` again (ADR-0078). A
        **crossing** train counts with no request behind it: a restored hint
        is a train the dispatcher believes is between two blocks, and a drain
        that ended over one would have `layout` cut the supply under it.
        """
        return bool(self._state.crossing)

    def _publish_moving(self) -> None:
        """Whether anything is moving, on `state/moving`: what `layout` reads
        to end a drain by switching the supply off (ADR-0078, ADR-0062).

        A boolean of its own and beside power rather than a value of it: power
        says what a person asked the railroad for, and this says whether the
        railroad has got there. A value that changes nothing publishes
        nothing, as it does for every other state topic here, which is what
        lets this be called wherever `moving` can have moved without a caller
        working out whether it did.
        """
        moving = self._moving()
        if moving == self._published_moving:
            return
        self._published_moving = moving
        self._publish("state/moving", {"moving": moving})

    def _publish_aspects(self) -> None:
        """The signalled ends, on a last-value topic, when any of them has
        changed. Every end each time rather than the ones that moved: a late
        subscriber wants the whole picture on connect, not the first change
        after it arrives (BUS.md)."""
        shown = aspects(self._state)
        if shown != self._aspects:
            self._aspects = shown
            self._bus.publish(ASPECTS, {"aspects": shown})

    def _publish_allocation(self) -> None:
        """The run's picture, on a last-value topic, when any of what it
        carries has moved. Published from the two places that move it: a
        request joining the queue, and the grant phase that runs it."""
        picture = allocation(self._state, self._requests)
        if picture != self._allocation:
            self._allocation = picture
            self._bus.publish(ALLOCATION, picture)

    def _publish_disputed(self) -> None:
        """What the detectors make of the placement, on a last-value topic,
        when it moves — the panel points a person at it, and a panel joining
        later must find it there (ADR-0032). Published from every place that
        moves either side of the comparison: a reading arriving, a placement,
        and the power reading `off` or leaving it."""
        found = disputed(self._state)
        if found != self._disputed:
            self._disputed = found
            self._publish("state/disputed", found)

    def _publish_unfit(self) -> None:
        """The trains the last rebuild under the same name took off the
        layout, each with the block it stood in and why (#709). Published
        from the constructor whatever it holds, so a joining client is served
        a value and the last build's list does not stand (ADR-0032), and
        again each time a person places one of them."""
        self._bus.publish(
            UNFIT,
            {
                "trains": [
                    {"train": train, "block": block, "why": why}
                    for train, (block, why) in self._unfit.items()
                ]
            },
        )

    def _publish(self, leaf: str, payload: Payload) -> None:
        self._bus.publish(f"tc49/dispatch/{leaf}", payload)
