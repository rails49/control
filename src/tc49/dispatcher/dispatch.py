"""Dispatcher: admission, queue, lock table, sensor roles, grant sweep.

Fully asynchronous at the bus boundary (SYSTEM.md, dispatcher footprint):
requests arrive as events, every fate is announced as an event, and the
request id is both correlation and idempotency key. The dispatcher grants on
the events that arrive (ADR-0047): a sensor reading is applied where it
lands, and a **sweep** — one grant pass over the active trains and the whole
pending queue — runs wherever the lock table or the waiting set changes: a
request admitted, a reading releasing what a move held, the power
coming back `on`, the sensors not reporting changing. Every grant is `safe()`-checked before it commits, so arrival
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
`cancel_wanted`, `arrival_wanted`, `reorder_wanted` and `point_wanted`, from the ui, the scheduler, or a second scheduler introduced
later — and what
the layout interface observes, on a filter that also carries the `align` and
`move` commands, which name the layout and are passed by unread. Every leaf
goes through a reader in `lib.payload` and nothing subscripts a frame it has
not read. The one thing left that could take the app off the bus was a sensor
reading no granted move accounts for; it is named on `state/disputed` instead
and the rest keeps running (#1154).

While `state/settings` says `without_sensors` the railroad runs without
sensors (#1314, DISPATCH.md, *Without sensors*): readings are recorded and
ignored, a launch locks the whole route by the `FullRoute` rule whatever the
strategy, sets every point of it in one `align` naming no transit, and grants
no move. A person drives the train, and the run ends by "arrived"
(`arrival_wanted`), a cancel, a placement or a removal.
"""

import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from tc49.dispatcher.locking import (
    FullRoute,
    Launched,
    LockingStrategy,
    Refused,
)
from tc49.dispatcher.routing import candidates
from tc49.dispatcher.table import (
    Active,
    Disputed,
    Effect,
    Following,
    Granted,
    HeadIn,
    Move,
    MoveEnded,
    Opened,
    Placed,
    Released,
    Removed,
    Route,
    RunsEnded,
    Table,
    adopting,
    arriving,
    broken,
    cancelling,
    committing,
    committing_whole,
    completing,
    entered,
    granting,
    locked_ahead,
    not_reporting,
    opening,
    placing,
    reading,
    removing,
    retiring,
    setting_without_sensors,
    transit_blocks,
    withdrawing,
)
from tc49.lib.bus import Bus, Payload
from tc49.lib.cancellation import Reason as Cancellation
from tc49.lib.inventory import DRAINING, OFF, ON, Aspect, split_device
from tc49.lib.layout import (
    Layout,
    Point,
    block_of,
    opposite_end,
    transit_ends,
)
from tc49.lib.payload import (
    Ordering,
    gesture,
    kept_allocation,
    overdue,
    placement,
    power,
    readable_id,
    said_short_blocks,
    said_without_sensors,
    settled_reading,
    taken,
    unknown_sensors,
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
UNKNOWN_SENSORS = "tc49/layout/state/unknown_sensors"
OVERDUE = "tc49/layout/state/overdue"
TAKEN = "tc49/layout/state/taken"
SETTINGS = "tc49/layout/state/settings"
SETTLED_SENSOR = "tc49/layout/state/settled/sensor"
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
    # The block its newest move enters, where the request has been cancelled
    # before that move ended: nothing further is granted for it, and it retires
    # as `request_cancelled` at that move's end, the end of a request (ADR-0049,
    # #1171). On `state/allocation` as `cancelling` (#1117).
    cancelling: str | None = None
    # The latest `grant_refused` for it since its last grant, at a launch or
    # for its next move: on `state/allocation` as `refused`, so a page that
    # connects later is told why it waits (#1117).
    refused: Refused | None = None
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

    @property
    def cancelled(self) -> bool:
        return self.cancelling is not None


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
class State:
    """The dispatcher's state: the lock table and what else it reads. Each
    read of the table is handed to `table`, and `State` satisfies
    `locking.ReadOnlyState`, which the strategies read it through."""

    layout: Layout
    # train -> its length: the railroad's **roster**, and the whole of what
    # the dispatcher knows about stock. Being in it is what makes a train
    # **known**, which is separate from being **placed** — a request naming a
    # train that is not here is answered `unknown_train`, and one naming a
    # train that is here and not in `block_of` is answered `no_origin`
    # (ADR-0039).
    roster: dict[str, int]
    table: Table
    # `on`, `draining` or `off`: what the layout last said about the one
    # switch a person turns (ADR-0078). The dispatcher routes, grants and
    # locks only while it reads `on`; `draining` and `off` commit nothing, and
    # requests wait. Not an emergency stop for what is already granted — a
    # move already sent is not retractable and runs to its sensor whatever
    # the power — so it gates the sweep's grant pass and the aspects, and
    # admission goes on: it is cheap and reversible, and launching is the
    # commitment. State rather than a flag on the dispatcher because
    # `aspects()` answers off it.
    #
    # `off` until the layout says otherwise, because the railroad comes up
    # `off` and nothing is routed over rails nobody has heard from.
    power: str = OFF
    # The trains `layout` last listed on `state/overdue`: stopped for not
    # arriving within the allowance (#1191). No row means none. `Table.moving`
    # is its only reader.
    overdue: frozenset[str] = frozenset()
    # The trains `layout` last named on `state/taken`: held by a throttle
    # (#1187). No row means none. `Table.moving` is its only reader: a held train
    # is not left out for both its sensors being unknown, since `layout`
    # stops such a train only where no throttle holds it.
    held: frozenset[str] = frozenset()
    # Whether `layout` last said the railroad's settings let a route end in or
    # pass through a block shorter than the train (`state/settings`, #1287).
    # Routing and admission read it; placing and restoring do not, since a
    # placed or restored train holds only its block and a tail over points
    # would be unprotected. `False` until a row says otherwise, so a railroad
    # just loaded routes on fit until its own row is heard.
    short_blocks: bool = False

    @property
    def locks(self) -> Mapping[str, str]:
        return self.table.locks

    @property
    def block_of(self) -> Mapping[str, str]:
        return self.table.block_of

    @property
    def active(self) -> Mapping[str, Active]:
        return self.table.active

    @property
    def departure(self) -> Mapping[str, str]:
        return self.table.departure

    @property
    def crossing(self) -> Mapping[str, str]:
        return self.table.crossing

    @property
    def readings(self) -> Mapping[str, bool]:
        return self.table.readings

    @property
    def occupied(self) -> Mapping[str, Sequence[str]]:
        return self.table.occupied

    @property
    def following(self) -> Mapping[str, Sequence[Following]]:
        return self.table.following

    @property
    def residue(self) -> AbstractSet[str]:
        return self.table.residue

    @property
    def unknown_sensors(self) -> frozenset[str]:
        return self.table.unknown_sensors

    @property
    def without_sensors(self) -> bool:
        return self.table.without_sensors

    @property
    def out_of_use(self) -> frozenset[str]:
        return self.table.out_of_use

    @property
    def disputed_blocks(self) -> frozenset[str]:
        return self.table.disputed_blocks

    def reads_occupied(self, block: str) -> bool:
        return self.table.reads_occupied(block)

    def obstacle(self, resource: str, train: str) -> tuple[str, str, str] | None:
        return self.table.obstacle(resource, train)

    def free(self, block: str, train: str | None = None) -> bool:
        return self.table.free(block, train)

    def standing_still(self) -> list[str]:
        return self.table.standing_still()


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


def _aligned(point: Point) -> Payload:
    """A point as `tc49/layout/align` lists it: its address, the position the
    way needs and whether the address reports (ADR-0097)."""
    return {"addr": point.addr, "position": point.position, "reported": point.reported}


def aspect_of(depth: int) -> str:
    """The aspect a signal shows for a locked-ahead depth (ADR-0025)."""
    if depth >= 2:
        return Aspect.CLEAR
    return Aspect.CAUTION if depth else Aspect.STOP


def aspects(state: State, refused: AbstractSet[str]) -> dict[str, str]:
    """Every signalled block end's aspect. An end nothing ever leaves carries
    no signal and does not appear; an end no train is authorised to leave by
    shows `stop`, which falls out of there being nothing locked beyond it
    rather than being a rule of its own.

    **An aspect answers "may a train that reaches this end leave by it"**
    (ADR-0093). For each train, the exit of every block on its route from the
    one the dispatcher records it in (`block_of`) through its last locked
    block shows the depth counted from that block, so a train holding two
    ahead shows `clear`, then `caution`, then `stop`. The block it is recorded
    in is the origin of an outstanding move until the tail has left it or the
    head is in the entered block, whichever is first, and the entered block
    from then on: the signal it has passed shows `stop` from that moment, not
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

    **Nor is a train let into or out of a block out of use**, so a signal over
    such a move shows `stop` and depth counts only up to that block
    (`locked_ahead`, #1152).

    **A reading that refuses the next move shows the same** (#1160). A train
    refused its next move has just been told so, so every end along its route
    shows `stop`, and it keeps its locks. `refused` names the trains whose
    request was last refused. Its signals return in the sweep that
    grants it. A disputed block is not entered (ADR-0077), so depth counts only
    up to it (#1164).
    """
    shown: dict[str, str] = {
        end: Aspect.STOP for end in sorted(state.layout.end_connection)
    }
    if state.power != ON:
        return shown
    for train, active in state.active.items():
        if train in refused:
            continue
        route = active.route
        # `cur_index` advances at the grant, so with a move outstanding the
        # train is recorded one back until its tail has left or its head is in.
        standing = active.cur_index
        if active.outstanding and state.block_of.get(train) != route.blocks[standing]:
            standing -= 1
        last = standing + locked_ahead(state.table, train, route, standing)
        for i in range(standing, min(last + 1, len(route.transits))):
            ends = transit_ends(state.layout, route.blocks[i], route.transits[i])
            assert ends is not None  # a route's transits reach its blocks
            shown[ends[0]] = aspect_of(locked_ahead(state.table, train, route, i))
    return shown


def allocation(state: State, requests: Sequence[Request]) -> Payload:
    """The run's picture: where every train stands and which of them are
    crossing a transit, the lock table with its holders, what each train
    occupies tail to head (a lock on no list being held ahead), and every request
    still alive — carrying the route a committed one is running, why one
    waits where it was last refused, and the block a held cancel waits for
    its move to enter (#1117).

    A crossing train appears in both maps: `trains` names the block it is
    recorded in, and `crossing` names the transit it has not yet got its head
    across. The transit is the whole of the mark — there
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
    routes = {active.request_id: active.route for active in state.active.values()}
    return {
        "trains": dict(sorted(state.block_of.items())),
        "crossing": dict(sorted(state.crossing.items())),
        "locks": dict(sorted(state.locks.items())),
        "occupied": {
            train: list(listed) for train, listed in sorted(state.occupied.items())
        },
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
                **(
                    {}
                    if request.refused is None
                    else {
                        "refused": {
                            "reason": request.refused.reason,
                            "obstacles": request.refused.obstacles,
                        }
                    }
                ),
                **(
                    {}
                    if request.cancelling is None
                    else {"cancelling": request.cancelling}
                ),
            }
            for request in requests
        ],
    }


def disputed(blocks: AbstractSet[str]) -> Payload:
    """The blocks with a sensor reading occupied and no train explaining the
    reading (#153, #1164, #1171). Either of a block's sensors is enough. A train
    explains the reading when any of these holds:

    1. the block is on its `occupied` list;
    2. the block is the arrival block of its outstanding move;
    3. the block is residue of its removal (ADR-0069);
    4. the block is at either end of the transit a restored crossing names
       (`crossing` with no move behind it).

    **A lock held ahead explains nothing.** A hand can put a locomotive on a
    block a train holds on its way, so the block is named, and nothing is
    granted into it, the holder's own move included.

    **A clear reading disputes nothing.** A short train stands between its
    block's two sensors and both read clear, so the reading says nothing about
    where the train is, and it is granted as any other.

    On power-up the detectors assert straight away — anonymously, so no
    reading names a train — at exactly the moment the placement is least
    trustworthy: it is where the last session *believed* the railroad was,
    and the steel has stood unwatched since (GLOSSARY.md, recovery). Naming
    the blocks turns walking the whole railroad into checking a handful. It
    **resolves** nothing: the check points, and a person ends every entry with
    a `placement_wanted`, or the block's sensors read clear.

    **At every power value** (#1154): a hand or a throttle can make one with
    the power on, the others run, and the person has to be told while they do.

    Only sensors `readings` carries take part: one the layout has said
    nothing about is unknown, and its block is not on the list for it.

    `blocks` is the table's `disputed_blocks`.
    """
    return {"blocks": sorted(blocks)}


@dataclass(frozen=True)
class Adopted:
    """What a restart takes from the last picture (`restored`)."""

    standing: dict[str, str]  # train -> the block it comes up in
    crossing: dict[str, str]  # train -> the transit it was crossing
    # train -> what it comes up occupying, tail to head, its own block on it
    occupied: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
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

    Adoption is **selective**: `trains`, `crossing` and `occupied` are taken,
    `locks` and `requests` left behind. The lock table is rebuilt from what each
    train occupies, one block per train where the picture says no more, the
    queue comes back empty, and no request id resumes (ADR-0033). So what a
    train occupies stays locked with no move behind it, until its next move or a
    placement (#1171). Stock
    stays the **roster**'s, so the picture's word
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
    listed = stated.occupied if stated is not None else {}
    return Adopted(
        standing,
        {train: transit for train, transit in hinted.items() if train in kept},
        adopted_occupied(
            layout,
            standing,
            {train: listed[train] for train in listed if train in kept},
        ),
        {train: misfit[train] for train in sorted(misfit) if train not in standing},
    )


def adopted_occupied(
    layout: Layout,
    standing: dict[str, str],
    listed: dict[str, tuple[str, ...]],
) -> dict[str, list[str]]:
    """What each train comes up occupying: each entry `listed` for it that this
    railroad has and no other train has already taken, and its own block,
    appended where the list lacks it (#1171)."""
    taken = {block: train for train, block in standing.items()}
    adopted: dict[str, list[str]] = {}
    for train, block in standing.items():
        entries: list[str] = []
        for entry in listed.get(train, ()):
            on_railroad = entry in layout.blocks or transit_blocks(layout, entry)
            if (
                on_railroad
                and entry not in entries
                and taken.setdefault(entry, train) == train
            ):
                entries.append(entry)
        adopted[train] = entries if block in entries else [*entries, block]
    return adopted


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
        # What launches a request while the railroad runs without sensors,
        # whatever `strategy` is: the whole route or nothing (#1314).
        self._whole = FullRoute(layout, strategy.k)
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
            Table(layout, {}, {}, {}),
            # The railroad comes up `off` (`State.power`), restored or cold,
            # so nothing is routed until a person turns the power on
            # (ADR-0078): a restored picture is wherever the last session
            # left the steel, and the person turning it on is the one who has
            # looked.
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
        self._take(
            adopting(
                self._state.table, adopted.standing, adopted.occupied, adopted.crossing
            )
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
        # are `state/power`, `state/unknown_sensors`, `state/overdue` and
        # `state/taken` (#240). Two power
        # values delivered backwards would otherwise leave the dispatcher
        # believing the track is dead while it is live, or the other way about,
        # with nothing to notice.
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
        # And the sensors not reporting, for the same reason: a request admitted
        # before that drain is not to be sent into a block out of use.
        stated = bus.last_values.get(UNKNOWN_SENSORS)
        if stated is not None and self._ordering.accepts(UNKNOWN_SENSORS, stated):
            self._take(
                not_reporting(self._state.table, unknown_sensors(stated) or frozenset())
            )
        # And the trains stopped for not arriving, so the first `moving` leaves
        # them out.
        stated = bus.last_values.get(OVERDUE)
        if stated is not None and self._ordering.accepts(OVERDUE, stated):
            self._state.overdue = overdue(stated) or frozenset()
        # And the trains a throttle holds, so the first `moving` counts them.
        stated = bus.last_values.get(TAKEN)
        if stated is not None and self._ordering.accepts(TAKEN, stated):
            self._state.held = frozenset(taken(stated))
        # And whether a route may use a block shorter than the train, and
        # whether the railroad runs without sensors, so the first request is
        # admitted and launched under the railroad's own settings. No sweep:
        # the opening rows below follow it.
        stated = bus.last_values.get(SETTINGS)
        if stated is not None and self._ordering.accepts(SETTINGS, stated):
            self._on_settings(stated)
        # The last `state/moving` value published, so the topic moves only
        # when what it says moves.
        self._published_moving: bool | None = None
        # The trains the rebuild left off, until a person places each one.
        self._unfit = dict(adopted.unfit)
        # The lock table's rules broken at the last check (`_check`), so only
        # a rule newly broken drains the railroad, and `state/broken` moves
        # only when the list does. `None` until the first check publishes it.
        self._broken: list[str] | None = None
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
        # session left standing on that topic. The check that ends it says
        # which of the lock table's rules are broken, `[]` where none is, for
        # the same reason (#1118).
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
        return active is not None and active.request_id == req.id

    def _listed(self, rid: str) -> Request | None:
        return next((req for req in self._requests if req.id == rid), None)

    def _request(self, active: Active) -> Request:
        """The request an active train runs, which stays listed until it
        ends."""
        req = self._listed(active.request_id)
        assert req is not None
        return req

    def _refused(self) -> frozenset[str]:
        """The active trains whose request was last refused."""
        return frozenset(
            train
            for train, active in self._state.active.items()
            if self._request(active).refused is not None
        )

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
            elif (
                not self._state.short_blocks
                and self._state.roster[request.train] > self._state.layout.blocks[block]
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

        A pure function of layout, origin, departure end, arrival end, train
        length and `short_blocks`: asked with no block out of use, `candidates`
        prunes only on fit, which that setting lifts, and on the simple-path
        rule, congestion enters solely as a sort key and `k` only caps the
        list, so one route is all this has to find. `short_blocks` changes at
        run time: turned off between admission and the launch, it can leave
        the request with no route to any end admitted, and the launch rejects
        it `unreachable`.
        """
        return bool(
            candidates(
                self._state.layout,
                origin,
                depart,
                (end,),
                self._state.roster[train],
                1,
                short_blocks=self._state.short_blocks,
            )
        )

    # -- what is addressed to the dispatcher --------------------------------

    def _on_dispatch(self, topic: str, payload: Payload) -> None:
        """The six topics the dispatcher responds to, on one filter.

        A request, and the five gestures a person makes on a page: all six
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
        elif leaf == "arrival_wanted":
            self._arrive(payload)
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
        a block `_judged` accepted: the table takes it (`table.placing`).
        What it occupied behind it is released, `train_placed` follows, and
        then any residue the placement opened.
        """
        self._take(placing(self._state.table, train, block))

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
        first, `removed`, so `train_removed` describes a train with none. The
        cancellation keeps what the removal keeps (`Table.kept`), and the
        table then takes the removal (`table.removing`). Track a removal frees
        is what a cancellation frees, so it sweeps for it, and the sweep
        grants only while power reads `on`.

        A train that is already off the layout is left alone. The gesture
        asks for a state it is in, and there is no fact to announce.
        """
        self._cancel(train, Cancellation.REMOVED, keep=self._state.table.kept(train))
        self._take(removing(self._state.table, train))
        self._sweep()

    def _take(self, result: tuple[Table, list[Effect]]) -> None:
        """The table a transition returned, held, and its effects published."""
        self._state.table, effects = result
        self._published(effects)

    def _revoke(self, payload: Payload) -> None:
        """A person ending one request without it arriving (ADR-0049,
        ADR-0080), named by its id.

        A request waiting is cancelled at once. One underway gives up what it
        holds ahead and nothing its train is on, unless its newest move has not
        ended: nothing on the bus retracts a `move` already sent, so the request
        is marked instead, granted nothing further, and retires at the end of
        that move (`_request_over`, #1171). The requests chained after it by
        then are cancelled `revoked` as it ends; one chained after it once the
        cancel was asked departs from where the train stops (`_follow`, #836).
        Where the head is not yet in, the deferral asks `layout` to take the
        move back, and ends at once where it does (`_withdrawn`, #1068); with
        the head in there is nothing left to take back, so it asks nothing.
        While the railroad runs without sensors there is no move: the train has
        not left its block, which it is left occupying alone, and the request
        retires at once, asking `layout` nothing (#1314). An id the
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
        if active is not None and active.request_id == req.id:
            if req.cancelled:
                return
            req.revoking = frozenset(each.id for each in self._followers(req))
            # While the railroad runs without sensors there is no move, and
            # the cancel takes effect at once (`table.cancelling`, #1314).
            if not self._state.without_sensors and active.outstanding is not None:
                # Deferred: it frees nothing yet and dequeues nothing, so
                # there is nothing for a sweep to hand anybody. `layout` is
                # asked to take the move back, which it does where nothing
                # has driven the train since (`_withdrawn`, #1068). The
                # picture is republished all the same, so a page that
                # connects later is told the cancel is held (#1117).
                req.cancelling = active.outstanding.into
                self._bus.publish(
                    WITHDRAW_WANTED,
                    {
                        "train": req.train,
                        "transit": active.outstanding.transit,
                        "into": active.outstanding.into,
                    },
                )
                self._publish_allocation()
                return
            newest = self._state.table.newest(req.train)
            if newest is not None and newest.head_in and not newest.at_far:
                req.cancelling = newest.move.into
                self._publish_allocation()
                return
            self._retire(
                active,
                Cancellation.REVOKED,
                cancelling(self._state.table, req.train),
            )
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

    def _arrive(self, payload: Payload) -> None:
        """A person saying the train of an underway request is in its
        destination block, on a railroad run without sensors (#1314), where
        nothing else says so. Accepted at any power.

        Everything the train holds but the route's last block is released as
        one `lock_released`, the request completes, and `train_placed` says
        the train stands in that block. The requests chained after it depart
        by the end opposite the one the route came in by, as after an arrival
        followed by sensors (`_request_over`), and a sweep hands the released
        track on. A payload with no readable id, an id the dispatcher does not
        hold, a request still waiting, and any request while the railroad runs
        by its sensors are dropped in silence and to the trace (ADR-0034).
        """
        state = self._state
        rid = readable_id(payload)
        req = None if rid is None else self._listed(rid)
        if not state.without_sensors or req is None:
            return
        active = state.active.get(req.train)
        if active is None or active.request_id != req.id:
            return
        train = req.train
        block = active.route.arrival_block
        self._take(arriving(state.table, train))
        self._requests.remove(req)
        self._publish("request_completed", {"id": req.id})
        self._publish("train_placed", {"train": train, "block": block})
        self._ending(req, opposite_end(self._entered(active.route)))
        self._sweep()

    def _withdrawn(self, payload: Payload) -> None:
        """`layout` took back the move a cancelled request had outstanding:
        nothing had driven the train since it acted on the move, so the train
        never left its block (#1068).

        The request retires as the move's end would have retired it
        (`_request_over`), `revoked`, keeping what the train is on, the move's
        transit no longer among it: the train is put back where it was before
        the grant, so a request chained after it departs from there. Anything
        else is dropped — a request not cancelled, a move not outstanding, a
        transit other than the one it crosses or a block other than the one
        it enters (#1080) — the answer being about a move this dispatcher no
        longer holds."""
        withdrawn = withdrawal(payload)
        if withdrawn is None:
            return
        active = self._state.active.get(withdrawn.train)
        if active is None or not self._request(active).cancelled:
            return
        move = active.outstanding
        if (
            move is None
            or move.transit != withdrawn.transit
            or move.into != withdrawn.into
        ):
            return
        self._take(withdrawing(self._state.table, withdrawn.train))
        self._retire(
            self._state.active[withdrawn.train],
            Cancellation.REVOKED,
            retiring(self._state.table, withdrawn.train),
        )
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
        nothing and is named on `state/disputed`, which is the
        right answer to a detector firing under a train somebody has just moved
        by hand. A clear
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
            self._retire(active, reason, retiring(self._state.table, train, keep))
        for req in waiting:
            self._publish("request_cancelled", {"id": req.id, "reason": reason})
            self._ending(req, None)

    def _retire(
        self,
        active: Active,
        reason: Cancellation,
        retired: tuple[Table, list[Effect]],
    ) -> None:
        """The active request ended: the table takes `retired`, what
        `table.retiring` or `table.cancelling` returned for it, and the one
        event that says so follows. A person's cancel leaves the requests
        chained after it once it was asked departing from where the train
        stopped (#836); a placement or a removal leaves none.

        `_seen_ids` is not pruned. A cancelled id stays used for the session,
        because an id is unique and not meaningful (ADR-0033) and a resubmit
        of it is the duplicate it looks like.
        """
        req = self._request(active)
        self._take(retired)
        self._requests.remove(req)
        self._publish("request_cancelled", {"id": req.id, "reason": reason})
        if reason is Cancellation.REVOKED:
            self._ending(req, self._stopped(active), req.revoking)
        else:
            self._ending(req, None)

    # -- the sensors, and the sweep they trigger ----------------------------

    def _on_layout(self, topic: str, payload: Payload) -> None:
        """What the layout interface says, and the two commands sent to it.

        `align` and `move` are on this filter because they name the component
        that responds to them, and the dispatcher is not that component: the
        `state/settled/sensor` row is named here so a command passes by unread
        rather than being taken for a reading with no sensor in it. So is its own
        `withdraw_wanted`, and `layout`'s answer to it, `move_withdrawn`, is
        read (#1068). So is `power_wanted`, for a person's `on` (#1087).
        """
        leaf = topic.rsplit("/", 1)[-1]
        device = split_device(topic)
        if device is not None and device[0] == SETTLED_SENSOR:
            # An older value than the one held is ignored as `state/power`'s is,
            # and an unreadable one dropped, the last value standing (#1168).
            settled = settled_reading(payload)
            if self._ordering.accepts(topic, payload) and settled is not None:
                self._on_reading(*settled)
        elif leaf == "move_withdrawn":
            self._withdrawn(payload)
        elif leaf == "power_wanted":
            # A person's `on` ends a hold `layout` has not answered (`_drain`).
            if wanted_power(payload) == ON and self._drain_asked:
                self._drain_asked = False
                self._sweep()
        elif leaf == "power":
            # An older value of the supply than the one already held means
            # the wire handed the pair over backwards: it is ignored, and
            # quietly — the trace has it, as it has every frame.
            if self._ordering.accepts(topic, payload):
                self._on_power(payload)
        elif leaf == "unknown_sensors":
            if self._ordering.accepts(topic, payload):
                self._on_unknown_sensors(payload)
        elif leaf == "overdue":
            if self._ordering.accepts(topic, payload):
                self._on_overdue(payload)
        elif leaf == "taken":
            if self._ordering.accepts(topic, payload):
                self._on_taken(payload)
        elif leaf == "settings":
            if self._ordering.accepts(topic, payload) and self._on_settings(payload):
                self._sweep()
        self._check()

    def _on_reading(self, sensor: str, occupied: bool) -> None:
        """One sensor's settled reading, applied where it lands (ADR-0047):
        the table takes it against every move still expecting that sensor
        (`table.reading`), and a repeat changes nothing.

        A sensor reading occupied that no train explains is named on
        `state/disputed` and **a person is told and the rest keeps running**
        (#1154, which supersedes ADR-0048's drain). A hand putting a locomotive
        on a detected block, a train pushed while the supply was off, a cut of
        cars a broken coupling left standing, a detector asserting on dirt —
        they differ for the person recovering and not here. What each leaves is
        held apart without stopping anything: a block with a sensor reading
        occupied is an obstacle no train is sent into (ADR-0077). It does not
        raise: the frame is well formed and a handler that raised would take
        the app off the bus for an ordinary act of a person's hand (BUS.md,
        rule 4). Nothing is placed: occupancy is anonymous, so there is no
        train to place, and a person walks to what the set names and places
        what they find.

        Every changed reading ends in a sweep, for whatever it released or
        disputed.
        """
        self._sensed(reading(self._state.table, sensor, occupied))

    def _sensed(self, result: tuple[Table, list[Effect]]) -> None:
        """What a reading or a list of sensors not reporting came to, where it
        changed the table: taken, then residue opened, then a sweep."""
        if result[0] is self._state.table:
            return
        self._take(result)
        self._take(opening(self._state.table))
        self._sweep()

    def _published(self, effects: list[Effect]) -> None:
        """What a transition returned, published in the order returned."""
        for effect in effects:
            match effect:
                case Disputed(blocks):
                    self._publish_disputed(blocks)
                case Granted(train, resources):
                    self._publish(
                        "lock_granted", {"train": train, "resources": list(resources)}
                    )
                case Released(train, resources) | Opened(train, resources):
                    self._publish(
                        "lock_released", {"train": train, "resources": list(resources)}
                    )
                case HeadIn():
                    self._publish_aspects()
                    self._publish_allocation()
                case MoveEnded(train):
                    self._request_over(train)
                case Placed(train, block):
                    self._publish("train_placed", {"train": train, "block": block})
                    if self._unfit.pop(train, None) is not None:
                        self._publish_unfit()
                case Removed(train):
                    self._publish("train_removed", {"train": train})
                case RunsEnded():
                    self._end_every_request()

    def _request_over(self, train: str) -> None:
        """The newest move of the train has ended, at its `entry` clearing or
        its `far` reading occupied. Its request ends with it: **a cancelled one
        retires**, wherever along its route it had got to, the person's gesture
        having landed before this move ended (ADR-0049), and gives up what it
        holds ahead and nothing it is on; otherwise, at its route's last block,
        it completes. Otherwise nothing: its next move has been or will be
        granted."""
        state = self._state
        active = state.active.get(train)
        if active is None or active.outstanding is not None:
            return
        req = self._request(active)
        if req.cancelled:
            self._retire(active, Cancellation.REVOKED, retiring(state.table, train))
        elif active.cur_index == len(active.route.blocks) - 1:
            self._take(completing(state.table, train))
            self._requests.remove(req)
            self._publish("request_completed", {"id": req.id})
            self._ending(req, opposite_end(self._entered(active.route)))

    def _check(self) -> bool:
        """The lock table's rules, checked (`broken`): a rule broken now and
        not at the last check **drains the railroad** and is written to stderr
        (ADR-0076, ADR-0078). That is a bug in the software rather than a
        failure on the railroad, so it stops everything where a reading does
        not (#1154). Answers whether one was.

        The list goes on `state/broken` whenever it differs from the last
        one, back to `[]` once the tables agree again, so the run view can
        say why the railroad drained when nobody pressed for it (#1118).

        A rule still broken from the last check does nothing, so a person who
        has looked and turned the power on again is not overruled by the next
        sweep (#811); one that clears and breaks again drains again. It does
        not raise: an exception out of a handler takes the app off the bus.

        Called at the end of each event and before each grant pass, never
        after a single write: a handler changes several maps in steps, and
        the steps are not meant to agree with each other in between.
        """
        lines = broken(self._state.table)
        new = [line for line in lines if line not in (self._broken or [])]
        if lines != self._broken:
            self._publish("state/broken", {"rules": lines})
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
        goes on reading `on` until `layout` answers, and a request or a reading
        arriving in between would otherwise be granted from the table the
        fault just said is wrong. The hold ends on the first `state/power`
        that does not read `on`, after which power holds the grants itself,
        or on a person pressing `on`, which acknowledges the fault
        (ADR-0078, decision 7) and covers a `layout` that never answers.
        """
        if self._state.power == ON:
            self._drain_asked = True
            self._bus.publish(POWER_WANTED, {"power": DRAINING})

    def _on_power(self, payload: Payload) -> None:
        """What the layout says about the one switch a person turns: `on`,
        `draining` or `off` (ADR-0078).

        Anything but `on` **routes nothing**: no route is chosen, no move
        granted and no lock taken, and every signalled end shows `stop`
        rather than going on showing `clear` over a train that will not be
        let past it (ADR-0041). Which of the others it is changes nothing here:
        `layout` switches a drain off once `state/moving` reads false, and the
        panel is where the person is told which it is.

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

    def _on_unknown_sensors(self, payload: Payload) -> None:
        """Which sensors `layout` says are not reporting. A block with one is out
        of use (`State.out_of_use`).

        An unreadable row is dropped and the last value stands, and a row that
        changes nothing sweeps nothing, so a binding saying `sensors: []` runs as
        one saying nothing. A change sweeps: a sensor returning routes at once
        with no press, opens a block a removal left that reads clear, and
        `state/moving` follows the list, since `layout` has stopped a train both
        of whose sensors are on it.
        """
        listed = unknown_sensors(payload)
        if listed is None:
            return
        self._sensed(not_reporting(self._state.table, listed))

    def _on_overdue(self, payload: Payload) -> None:
        """Which trains `layout` has stopped for not arriving within the
        allowance (#1191). Read for `state/moving` alone: it sweeps nothing,
        takes and releases no lock and asks for no drain, and a listed train
        keeps its request, its route, its locks and its crossing.

        An unreadable row is dropped and the last value stands, and a row that
        changes nothing publishes nothing.
        """
        listed = overdue(payload)
        if listed is None or listed == self._state.overdue:
            return
        self._state.overdue = listed
        self._publish_moving()

    def _on_settings(self, payload: Payload) -> bool:
        """What the railroad's settings say the dispatcher runs on: whether a
        route may end in or pass through a block shorter than the train
        (#1287), and whether the railroad runs without sensors (#1314). A row
        whose field does not read leaves that value held.

        `short_blocks` is read for routing and admission alone: what is
        already routed keeps its route. `without_sensors` changing, either
        way, ends every train's run (`table.setting_without_sensors`) and
        every request (`_end_every_request`, #1321); turning `true` it also
        releases every train's residue, one `lock_released` per train.
        Turning `false` it brings back the
        readings and the sensors not reporting recorded meanwhile, at the
        caller's sweep. Answers whether `without_sensors` changed, for the
        caller to sweep. The seeding in the constructor finds no request to
        end.
        """
        state = self._state
        said = said_short_blocks(payload)
        if said is not None:
            state.short_blocks = said
        without = said_without_sensors(payload)
        if without is None or without == state.without_sensors:
            return False
        self._take(setting_without_sensors(state.table, without))
        return True

    def _end_every_request(self) -> None:
        """`without_sensors` changed and every run has ended (`RunsEnded`):
        every request ends `revoked`, in list order, each with no onward end,
        so one submitted `after` it later is cancelled too (#1321). Nothing is
        asked of `layout`."""
        ended, self._requests = self._requests, []
        for req in ended:
            self._publish(
                "request_cancelled", {"id": req.id, "reason": Cancellation.REVOKED}
            )
            self._finished[req.id] = (req.train, None)

    def _on_taken(self, payload: Payload) -> None:
        """Which trains a throttle holds (#1187). Read for `state/moving`
        alone, as `state/overdue` is: a held train between two sensors both
        unknown is one a person is driving, which `layout` does not stop
        (ADR-0081), so it counts.

        Read an entry at a time (`lib.payload.taken`): an unreadable entry
        leaves its train held by nobody, an unreadable payload holds nothing.
        A row that changes nothing publishes nothing.
        """
        held = frozenset(taken(payload))
        if held == self._state.held:
            return
        self._state.held = held
        self._publish_moving()

    def _sweep(self) -> None:
        """One grant pass, run where the lock table or the waiting set
        changed: a request admitted, cancelled or moved in the list, a reading
        releasing what a move held, the power coming back `on`, the
        sensors not reporting changing. A sweep
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
        # And `moving`: a grant starts a move being followed, and a sweep
        # follows each place that ends one, so it is where the boolean moves
        # (ADR-0062).
        self._publish_moving()

    def _grant(self) -> None:
        state = self._state
        # Active trains first, by request arrival then train id (DISPATCH.md).
        # None is offered a move while the railroad runs without sensors: a
        # person drives it (#1314).
        if not state.without_sensors:
            for train in sorted(
                state.active,
                key=lambda t: (self._request(state.active[t]).phase, t),
            ):
                active = state.active[train]
                if (
                    active.outstanding is not None
                    or self._request(active).cancelled
                    or active.cur_index == len(active.route.blocks) - 1
                ):
                    # A cancelled request is waiting for the move it was
                    # already making to end, and takes no other (ADR-0049). A
                    # train at its route's last block has no next move: its
                    # tail is what it waits for (#1171).
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
            strategy = self._whole if state.without_sensors else self._strategy
            result = strategy.launch(req, origin, depart, state)
            if result is None:
                self._requests.remove(req)
                self._reject(req.id, Reason.UNREACHABLE)
                self._ending(req, None)
            elif isinstance(result, Refused):
                waiting.add(req.train)
                req.refused = result
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
        """A route taken: its locks, `route_chosen` and `lock_granted`, and
        the first move at once. While the railroad runs without sensors there
        is no move: the train occupies the whole route and one `align` sets
        all its points (#1314)."""
        req.refused = None
        # The request stays where it is in the list, started (ADR-0080).
        self._publish(
            "route_chosen",
            {
                "id": req.id,
                "route": launched.route.interleaved(),
                "k_tried": launched.k_tried,
            },
        )
        # The strategy says what to lock and the table locks it (#761),
        # before the grant below, which reads the launch's locks to tell what
        # it newly locks. The end the route leaves the train facing is settled
        # with it, which is what lets a request dragged in mid-route be
        # answered while it is asked.
        if self._state.without_sensors:
            # The train occupies all of its route, and every point is set at
            # once (`table.committing_whole`).
            self._take(
                committing_whole(
                    self._state.table,
                    req.train,
                    req.id,
                    launched.route,
                    launched.locked,
                )
            )
            self._align_route(launched.route)
            return
        self._take(
            committing(
                self._state.table, req.train, req.id, launched.route, launched.locked
            )
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
        return entered(self._state.layout, route)

    def _apply_move(self, active: Active, result: Move | Refused) -> None:
        req = self._request(active)
        if isinstance(result, Refused):
            req.refused = result
            self._publish(
                "grant_refused",
                {
                    "id": req.id,
                    "reason": result.reason,
                    "obstacles": result.obstacles,
                },
            )
            return
        req.refused = None
        self._take(granting(self._state.table, req.train, result))
        self._align(result.transit)
        self._publish(
            "move_granted",
            {
                "id": req.id,
                "train": req.train,
                "transit": result.transit,
                "into": result.into,
                # Read off the locks the move has just taken, from where
                # the train stood: `active` is its record before the grant.
                "aspect": aspect_of(
                    locked_ahead(
                        self._state.table,
                        req.train,
                        active.route,
                        active.cur_index,
                    )
                ),
            },
        )

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
                "points": [_aligned(point) for point in needed],
            },
        )

    def _align_route(self, route: Route) -> None:
        """Set every point a route needs, for a launch while the railroad runs
        without sensors (#1314): one `align` naming no transit, as a hand
        throw's does (ADR-0068), so it authorises no crossing. The points of
        each transit in route order, each as `_align` writes it, an address
        already listed not repeated."""
        connections = self._state.layout.connections
        points: list[Payload] = []
        listed: set[str] = set()
        for transit_id in route.transits:
            connection, _, transit = transit_id.partition(".")
            for point in connections[connection].points.get(transit, ()):
                if point.addr not in listed:
                    listed.add(point.addr)
                    points.append(_aligned(point))
        self._bus.publish(
            "tc49/layout/align",
            {"connection": None, "transit": None, "points": points},
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
        moving = self._state.table.moving(self._state.overdue, self._state.held)
        if moving == self._published_moving:
            return
        self._published_moving = moving
        self._publish("state/moving", {"moving": moving})

    def _publish_aspects(self) -> None:
        """The signalled ends, on a last-value topic, when any of them has
        changed. Every end each time rather than the ones that moved: a late
        subscriber wants the whole picture on connect, not the first change
        after it arrives (BUS.md)."""
        shown = aspects(self._state, self._refused())
        if shown != self._aspects:
            self._aspects = shown
            self._bus.publish(ASPECTS, {"aspects": shown})

    def _publish_allocation(self) -> None:
        """The run's picture, on a last-value topic, when any of what it
        carries has moved. Published from the places that move it: a
        request joining the queue, the grant phase that runs it, and a
        cancel held for an outstanding move, which sweeps nothing (#1117)."""
        picture = allocation(self._state, self._requests)
        if picture != self._allocation:
            self._allocation = picture
            self._bus.publish(ALLOCATION, picture)

    def _publish_disputed(self, blocks: frozenset[str] | None = None) -> None:
        """The blocks the sensors dispute, on a last-value topic, when they
        change — the panel points a person at them, and a panel joining later
        must find them there (ADR-0032). Published from every place that moves
        either side of the comparison: a reading arriving, a placement, and
        whatever starts or ends a move, each of which sweeps. It reads no
        power: the set holds at every value (#1154). `blocks`, where given,
        is the set a transition returned (`Disputed`), and otherwise the
        current table's."""
        found = disputed(self._state.disputed_blocks if blocks is None else blocks)
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
