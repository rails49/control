"""Scheduler: the one writer of requests, and the holder of facing.

Its sources are configuration rather than a rule (ADR-0036): the scenario's
requests, submitted whole at the start of a run in the file's order, and a
person gesturing on the two topics the scheduler declares,
`tc49/schedule/request_wanted` and `tc49/schedule/reversal_wanted`. Time is
the scheduler's responsibility (ADR-0047): a timetable it was asked to load
is released against the fast clock (#1353, below). Among requests that are
out the queue does the
staggering, there never being enough tracks to satisfy every request at
once. A gesture is not a request — it names a train and
where to put it, and the id and the departure end are what the scheduler
adds. The ids of the scenario's requests are minted deterministically in
their order (`<train>-1`, `<train>-2`, ...) from one undivided counter and a
drag's carry
a **per-process nonce** in between (`<train>-<nonce>-<n>`), which is
ADR-0033's split moved inside this app: a document's requests read in the
document's order, and a restart of this process alone — ordinary now the apps
are separate ones (ADR-0059) — would otherwise re-mint a drag's id the
dispatcher already holds and has dropped unanswered. The harness states the
nonce rather than taking the minted one, which is what keeps a replayed run
reproducible now that a replay feeds its document as drags. The arrival-end expansion is purely mechanical (a bare
block becomes both of its ends), and `exhausted` is set as soon as the last
of the scenario's requests is out.

It **holds facing** (ADR-0019), seeded where a run was built from a document
and carried forward from the bus: a train that left nose-first faces away from
the end it entered through, and a **propelled** one — pushed out of the end its
nose points away from — faces the end it entered through. Committing to a route
changes nothing, facing being a fact about the stock and not about the plan
(#295), and nor does a grant: the facing a move gives is worked out on
`move_granted` and kept, and taken up when `tc49/dispatch/state/allocation`
names the train in the block entered — until then the nose is still at the
signal the grant cleared, which is what a throttle shows (#1025). A restart
reads what it would have kept off the retained allocation's `crossing`. On a
railroad run without sensors no move is granted, so the scheduler also keeps
the route each `route_chosen` names, by request id, until the request ends. At
`request_completed`, where the train's facing does not yet name the route's
last block, the train takes the facing the same rule gives along the whole
route (#1317).
That is what the layout read is for — `move_granted` names a transit
and the block entered, not the end entered through — and why the scheduler
subscribes `tc49/dispatch/#` (ADR-0028's growth, spent on facing). What it
holds per train is `lib`'s facing: the run the train would make across its
block, `<block>.A-to-B` or `<block>.B-to-A`, out of which a drag's departure
end is read (#241). Into a terminal block there is no end to face away
towards, so arrival goes through `departure_end` and seeding through
`connected_facing`, which turns a candidate off a wall (#145). The last-value
topic it publishes is what every view reads to draw a direction arrow, a train
that has never moved having no other source for one. Where the bus binding has
kept that topic across a restart the scheduler adopts what it finds there
instead of the placement, which is what a broker that outlived it would have
delivered (#123). That retained value is **read**, through `lib.payload` like every
payload a subscription hands over, and one that cannot be read is a cold
start rather than a refusal to start: a value the scheduler cannot read tells
it nothing, and an app that will not come up tells a person even less (#277).
Deliberate reversal at rest is the one change routes do not account for, and
it arrives as its own gesture on `tc49/schedule/reversal_wanted` (#124).

It **records** a person's drags as a timetable (#1345, #1352), where it was
given a store client. The rule and its state are `tc49.scheduler.release`'s:
this module tells the rule what the bus said and does what it answers, in
`_settle`, after every message it takes.

- With power `on`, no timetable loaded, and a clock row and an allocation
  row read, it makes one named `untitled`, in place of a stored `untitled`.
  A person makes one by name on `tc49/schedule/timetable_wanted` with `new`,
  taken while power reads `off`.
- A new timetable starts at the clock's minute of the day, and repeats
  every day. The scheduler publishes `tc49/layout/clock_wanted` with the
  clock's time of day to the second, on day 0. Its `trains` are each train
  the allocation names in a block and the scheduler holds a facing for.
- While the timetable is `running` and Record is on, a drag composed from a
  gesture is added as an entry that is `out`, and a turn-round applied as one
  that has `ended`. The entry follows its request to `ended`, `rejected` or
  `cancelled`. `tc49/schedule/timetable_record_wanted` switches Record.
  While a drag adds an entry, a train on the layout that the timetable's
  `trains` does not name is added to them at its block and facing (#1370).
- `tc49/schedule/entry_wanted` changes or deletes the first entry equal to
  the one it names, in every phase. The entry keeps its state and its
  request, and a request that has gone out is left alone (#1354).
- `tc49/schedule/timetable_rename_wanted` renames the loaded timetable: the
  document is written under the new name and the old one deleted. Dropped
  where the store has a timetable of that name (#1354).
- `tc49/schedule/timetable_repeat_wanted` sets the loaded timetable's
  `repeat`, while power reads `off`. Dropped where an entry would fall at
  or after `start` plus `repeat`. In `running`, every entry's round moves
  by the clock's round under the new repeat less its round under the old
  one, and where that would put an entry below round 0, by minus the
  lowest round. In `loaded` the rounds stay (#1368, #1373).
- The document is written through the store client at each change to it. A
  change of an entry's state alone is no change to it.
- The loaded timetable is on `tc49/schedule/state/timetable`, published when
  it changes.
- A restart adopts that row as it adopts facing, and reads the document from
  the store. The row's entries are kept where the document's differ. A row
  that cannot be read, or a name the store has no document for, leaves no
  timetable loaded. An entry that is `out` whose request the first
  allocation row read does not list has `ended`.

It **loads** a timetable and **releases** its entries on the fast clock
(#1345, #1353), by the same rule and in the same place.

- `tc49/schedule/timetable_wanted` without `new` loads the timetable of
  that name from the store, taken while power reads `off` and once an
  allocation row was read. Its phase is `loaded` and Record is off. A name
  the store has no document for, and a document that does not read, leave
  what was loaded.
- Each train its `trains` name that stands in another block is sent to its
  start block by one request, composed as a drag is: to `<block>.A` where
  it is recorded facing `A-to-B` and `<block>.B` for `B-to-A`. Where the
  dispatcher rejects that as `unreachable`, one more goes to both ends. A
  train in its start block, whatever its facing, and a train off the
  layout get none. The row's `positioning` lists these requests until each
  ends. They are not entries.
- It starts when the last of them has ended and power reads `on`, or when a
  person asks on `tc49/schedule/timetable_start_wanted`: the scheduler
  publishes `tc49/layout/clock_wanted` with the start time on day 0, and
  the phase is `running`.
- An entry the rule says is due is released: one with `to` as a drag of its
  train to those arrival ends, which chains after the train's latest
  request in flight as a person's drag does, and a turn-round as the
  reversal a person's gesture makes. A person's own drag is composed at
  once, whatever dwell an entry stated.
- The timetable repeats every `repeat` and never ends: each entry runs once
  in each round. It stays loaded until another is loaded or made.
- A restart adopts a `loaded` phase, the row's `positioning` and each
  entry's round and state. An id the first allocation row read does not
  list has ended. One rejected as `unreachable` after a restart gets no
  second request.
"""

import secrets
from collections import Counter
from collections.abc import Sequence

from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import (
    FACINGS,
    Layout,
    block_of,
    connected_end,
    connected_facing,
    departure_end,
    end_letter,
    facing_ends,
    facing_towards,
    transit_ends,
)
from tc49.lib.payload import (
    chosen,
    gesture,
    grant,
    kept_allocation,
    kept_facing,
    listed_requests,
    loaded_timetable,
    named_train,
    placement,
    power,
    readable_id,
    rejected_for,
    said_clock,
    wanted_entry,
    wanted_record,
    wanted_rename,
    wanted_repeat,
    wanted_start,
    wanted_timetable,
)
from tc49.lib.rejection import Reason
from tc49.lib.scenario import RequestSpec
from tc49.lib.timetable import Timetable, TrainStart
from tc49.scheduler import release
from tc49.scheduler.keeping import Timetables

FACING = "tc49/schedule/state/facing"
TIMETABLE = "tc49/schedule/state/timetable"
ALLOCATION = "tc49/dispatch/state/allocation"
CLOCK = "tc49/layout/state/clock"
CLOCK_WANTED = "tc49/layout/clock_wanted"
POWER = "tc49/layout/state/power"


class Scheduler:
    def __init__(
        self,
        bus: Bus,
        layout: Layout,
        facing: dict[str, str] | None = None,
        requests: Sequence[RequestSpec] = (),
        nonce: str | None = None,
        store: Timetables | None = None,
    ) -> None:
        """`facing` is where a run built from a document says its trains point,
        train to the run it would make across its block, and `requests` is
        that document's request list. Both are the harness's: a run an
        operator drives is given neither, and its facing arrives with the
        placements a person makes (ADR-0036 — which sources a run has is
        configuration, not a rule).

        `store` is where timetables are kept. Given none, as by the harness
        and the bench, the scheduler makes and loads no timetable, publishes
        no timetable row and does not subscribe the clock or the power.
        """
        self._bus = bus
        self._layout = layout
        # Facing as the last session left it, where the bus binding kept it
        # across the process: the scheduler's own state topic, found waiting
        # exactly as it would be against a broker that outlived the app
        # (#123). It comes first, and for every train `_kept` can read it for
        # — including one no document places, which a person put on the rails
        # by hand (ADR-0039); dropping that one would leave its drags
        # uncomposable for want of a departure end. The seed above it is a
        # cold start's, and a train the retained value does not name — one
        # added since, or one it names in a spelling this build refuses — is
        # a cold start of one.
        restored = _kept(bus.last_values.get(FACING))
        self._facing: dict[str, str] = dict(sorted((facing or {}).items())) | restored
        # Facing a grant has settled and the train has not yet taken up: the
        # block each move enters and the facing the train will hold there, in
        # grant order. Adopted when the allocation names the train in that
        # block (#1025). More than one only where the next grant overtakes
        # the allocation that records the arrival before it.
        self._kept: dict[str, list[tuple[str, str]]] = self._crossing(
            bus.last_values.get(ALLOCATION)
        )
        self._train_of: dict[str, str] = {}  # request id -> the train it moves
        self._routes: dict[str, tuple[str, ...]] = {}  # request id -> its route
        self._counters: Counter[str] = Counter()  # one undivided minter
        # What makes a drag's id unique across a restart of this process
        # alone: the counter above starts empty in every process, so without
        # it the first drag after a restart mints an id the dispatcher is
        # still holding and drops before any check runs (ADR-0033). Four
        # bytes of `secrets`, not the clock, which BUS.md forbids of the
        # bus.
        #
        # `nonce` is the harness's, and the only caller that passes one: the
        # bench replays a document as drags, so without a stated nonce two
        # runs of one document mint different ids and the run stops being
        # reproducible, which is what the harness is for. It costs nothing
        # to let it say one — the collision the nonce prevents needs two
        # scheduler processes, and a bench run is one from start to finish.
        self._nonce = secrets.token_hex(4) if nonce is None else nonce
        self._published: Payload = {}  # the facing last sent, so only changes go
        self._store = store
        # Train -> the block it stands in, as the last allocation row read
        # names it. None until one was read.
        self._standing: dict[str, str] | None = None
        # Whether an allocation row's request list was read: the first one
        # says which requests ended while this process was not up.
        self._listed = False
        self._written: Timetable | None = None  # the document the store has
        self._said: Payload | None = None  # the timetable row last sent
        # Request id -> the start block it sends its train to, for each
        # first request of a load not yet ended (#1353).
        self._to_start: dict[str, str] = {}
        self._state = self._restarted(bus.last_values.get(TIMETABLE))
        # Before the opening rows and not after. Over a broker a publish is
        # asynchronous where a subscribe waits for the broker to acknowledge,
        # so anything published first opens a window a round trip wide in which
        # a gesture addressed to this app is lost — `exhausted` is what a
        # client waits for to know the app is up, and an event is not retained,
        # so nothing replays it. In one process the window had no width and the
        # order did not show. Both handlers already ignore this app's own rows
        # coming back (`_on_gesture`), which is what makes this side safe.
        bus.subscribe("tc49/dispatch/#", self._on_dispatch)
        bus.subscribe("tc49/schedule/#", self._on_gesture)
        if store is not None:
            bus.subscribe(CLOCK, self._on_clock)
            bus.subscribe(POWER, self._on_power)
        self._publish_facing()
        self._settle()
        for request in requests:
            self._counters[request.train] += 1
            self._submit(
                {
                    "id": f"{request.train}-{self._counters[request.train]}",
                    "train": request.train,
                    "depart": request.depart,
                    "dest": _expand(request.arrivals),
                }
            )
        self._bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})

    def _submit(self, event: Payload) -> None:
        self._train_of[event["id"]] = event["train"]
        self._state = release.announced(self._state, event["id"], event["train"])
        self._bus.publish("tc49/dispatch/request_submitted", event)

    # -- gestures ----------------------------------------------------------

    def _on_gesture(self, topic: str, payload: Payload) -> None:
        """A person's action on a page: which leaf it came on.

        The filter is the whole of `tc49/schedule`, as rule 3 asks, so the
        scheduler's own state topics come back through here and are
        ignored on the way past. Nothing in the topic or the payload says who
        sent a gesture, and nothing here asks: a page sends these today, and
        anything else that composes one is served the same (BUS.md,
        rule 4).

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
        elif leaf == "timetable_wanted":
            self._wanted(payload)
        elif leaf == "timetable_record_wanted":
            record = wanted_record(payload)
            if record is not None:
                self._state = release.recording(self._state, record)
        elif leaf == "entry_wanted":
            change = wanted_entry(payload)
            if change is not None:
                self._state = release.changed(self._state, change.was, change.now)
        elif leaf == "timetable_rename_wanted":
            self._rename(payload)
        elif leaf == "timetable_repeat_wanted":
            repeat = wanted_repeat(payload)
            if repeat is not None:
                self._state = release.repeated(self._state, repeat)
        elif leaf == "timetable_start_wanted":
            self._start_wanted(payload)
        # a throttle is one more leaf under this role, later
        self._settle()

    def _compose(self, payload: Payload) -> None:
        """A `request_wanted` gesture: the drag it names, composed and
        submitted (`_drag`), and told to the release rule, which adds it to
        the loaded timetable as an entry where that records (#1352)."""
        wanted = gesture(payload)
        if wanted is None:
            return
        request = self._drag(wanted.train, wanted.arrivals)
        if request is not None:
            self._state = release.dragged(
                self._state, wanted.train, wanted.arrivals, request
            )

    def _drag(self, train: str, arrivals: tuple[str, ...]) -> str | None:
        """A drag of `train` to `arrivals`, composed into the request it asks
        for and submitted. The id it was given, or None where the scheduler
        holds no facing for the train and submitted nothing.

        A gesture names a train and where to put it; the two fields it omits
        are the two the scheduler owns — the id it mints and the departure
        end it reads off the facing it holds (ADR-0036). A facing is the run
        the train would make across its block, so the departure end is the
        end that run comes out at, said as an end (#241).

        `arrivals` are block ends or bare blocks, as a gesture's `dest` and
        an entry's `to` write them. The request's `dest` is block ends only,
        so a bare block is submitted as both of its ends (`_expand`).

        The id carries this process's nonce, `<train>-<nonce>-<n>`, where the
        id of one of the scenario's requests is `<train>-<n>`: nothing a person
        drags is reproducible,
        and a restart that re-minted `<train>-1` for a drag would have it
        dropped as a duplicate and never answered (ADR-0033).

        Read and **not corrected**: the end the facing names is the end the
        request states, wall or not. Every site that settles a facing has
        already turned it off a terminal block's wall (#145), so correcting
        again here would only ever fire on a facing that arrived broken —
        and it would fire silently, composing a request that departs by one
        end while the published facing goes on naming the other. A facing
        that names a wall is a fault to see, not to paper over: the store
        refuses such a placement at load, and a drag on one is rejected
        `unreachable`, exactly as it was before the value was rewritten.

        Where the train has a request **in flight** the drag **chains**: it
        is submitted `after` the latest of them, with `depart` `null`, and the
        dispatcher departs it from where that one arrives (ADR-0080). The
        facing says where the train stands now, not where it will stand once
        the requests ahead of it have arrived, so it has no departure end to
        offer. In flight is what `_train_of` holds — every request the
        dispatcher has announced for the train, whoever wrote it (#439) —
        and latest is the order they were announced in, which is the order
        `_train_of` keeps; a person reorders the list on the dispatcher, not
        here. A train with nothing in flight composes off its facing (#827).
        """
        facing = self._facing.get(train)
        if facing is None:  # a train this session does not hold
            return None
        self._counters[train] += 1
        event: Payload = {
            "id": f"{train}-{self._nonce}-{self._counters[train]}",
            "train": train,
        }
        latest = self._latest_in_flight(train)
        event["depart"] = facing_ends(facing)[1] if latest is None else None
        event["dest"] = _expand(arrivals)
        if latest is not None:
            event["after"] = latest
        self._submit(event)
        return event["id"]

    def _latest_in_flight(self, train: str) -> str | None:
        """The id of the train's request in flight announced last, or `None`
        where it has none: what a drag chains after (ADR-0080)."""
        ids = [request for request, mover in self._train_of.items() if mover == train]
        return ids[-1] if ids else None

    def _reverse(self, payload: Payload) -> None:
        """A `reversal_wanted` gesture: the train it names, turned around
        (`_turn`). One that was applied is told to the release rule, which
        adds it to the loaded timetable as an entry where that records
        (#1352)."""
        train = named_train(payload)
        if train is not None and self._turn(train):
            self._state = release.turned_round(self._state, train)

    def _wanted(self, payload: Payload) -> None:
        """A `timetable_wanted` gesture. With `new` it makes a timetable of
        that name in place of the one loaded, where the release rule takes
        it: power reads `off`, and a clock row and an allocation row were
        read. A name no timetable document takes is dropped. Without `new`
        it loads the timetable of that name (`_load`)."""
        wanted = wanted_timetable(payload)
        if wanted is None or self._store is None:
            return
        if not wanted.new:
            self._load(self._store, wanted.name)
            return
        if not release.new(self._state):
            return
        try:
            self._make(wanted.name)
        except ValueError:  # no name a timetable document takes
            return

    def _make(self, name: str) -> None:
        """A new timetable named `name` made (`release.made`), and the clock
        asked to be set to its time of day on day 0, to the second, on
        `tc49/layout/clock_wanted` with no `speed_up`. A `name` no timetable
        document takes is a `ValueError`, and nothing is made or asked."""
        self._state = release.made(self._state, name, self._layout.name, self._stands())
        self._bus.publish(CLOCK_WANTED, {"time": self._state.clock})

    def _rename(self, payload: Payload) -> None:
        """A `timetable_rename_wanted` gesture: the loaded timetable takes
        the name `to`. Its document is written under the new name, then the
        one under the old name is deleted, and the state row names the new
        one (#1354).

        Dropped where no timetable is loaded, where `to` is no name a
        timetable document takes, and where the store has a timetable of
        that name, one it cannot read included. The name the timetable has
        is such a name.
        """
        to = wanted_rename(payload)
        loaded = self._state.timetable
        if to is None or self._store is None or loaded is None:
            return
        try:
            renamed = release.renamed(self._state, to)
            if self._store.timetable(self._layout.name, to) is not None:
                return
        except (ValueError, TypeError):
            return
        self._state = renamed
        self._settle()  # the write of the new document, ahead of the delete
        self._store.delete_timetable(self._layout.name, loaded.name)

    def _load(self, store: Timetables, name: str) -> None:
        """A load of the timetable `name`, read from the store, in place of
        the one loaded (#1353). Its phase is `loaded` and Record is off.

        Dropped unless power reads `off` and an allocation row was read,
        where the store has no document of that name, and where the document
        does not read. What was loaded then stays loaded.

        Each train the timetable's `trains` name that stands in another
        block is sent to its start block by one request, composed as a drag
        is (`_drag`): to `<block>.A` where the train is recorded facing
        `A-to-B` and to `<block>.B` for `B-to-A`, the one arrival end a
        train run in nose-first is left facing as recorded by. A train in
        its start block gets none, whatever its facing, and nor does a
        train off the layout. The requests are listed in the row's
        `positioning` until each ends, and are not entries.

        The requests in flight are left alone, those the timetable loaded
        before sent to start blocks among them.
        """
        if not release.loads(self._state):
            return
        try:
            timetable = store.timetable(self._layout.name, name)
        except (ValueError, TypeError):
            return
        if timetable is None:
            return
        self._written = timetable
        self._state = release.loaded(self._state, timetable)
        stands = self._stands()
        for train, start in timetable.trains.items():
            if train not in stands or stands[train].at == start.at:
                continue
            end = facing_ends(f"{start.at}.{start.facing}")[0]
            request = self._drag(train, (end,))
            if request is not None:
                self._to_start[request] = start.at
                self._state = release.positioned(self._state, request)

    def _turn(self, train: str) -> bool:
        """Turning a train around at rest: the little arrow in the block it
        stands in, and nothing else (#124). Whether it was applied: false
        where it was dropped.

        Facing is fully determined once placed — routes are strict
        pass-throughs — with this one exception, which ADR-0019 named and
        parked for want of a scheduler to gesture at. No request is composed
        and the dispatcher learns nothing: nothing moves.

        Dropped where the train has a request in flight, from submit to
        completion, or a granted move it has not yet been recorded at the
        end of: the facing that move keeps would land over the flip (#1025).
        Flipping the arrow under one produces a lie: the queued
        request still departs the end the facing named when it was composed,
        so the train the arrow now points one way would leave the other — and
        the move that answers it would be read as a propelling one, turning
        the arrow again on arrival. Nothing takes the gesture back any more
        (#295): facing does not change under a queued request at all, which
        is what makes dropping it the whole of the protection. A **rejected**
        request leaves the train idle — `_train_of` has dropped it — and that
        is precisely when you want to turn around.

        In flight means **every request the dispatcher has announced**, not
        every request this app sent. A request topic has one responder and
        any number of writers (BUS.md, rule 1), so a page may submit for a
        train this scheduler holds the facing of, and a guard reading only
        what `_submit` minted would be blind to it and turn the arrow under
        somebody else's queued request (#439). `_on_dispatch` fills
        `_train_of` from the bus, which is where every submitter's requests
        land, and the answers empty it there whoever asked.

        A train turned around leaves by the end it had been standing with
        its tail at, and the flip goes through `lib`'s `connected_end` on the
        way: on a terminal block that end is the wall, so the gesture is a
        no-op rather than a train pointed at it (#145) — there is one end a
        stub can be left by either way, and facing never names an end that
        leads nowhere. Without that the gesture reaches the state
        `validate_scenario` refuses at load, and the next drag departs by the
        wall and is rejected `unreachable` for the rest of the session. That
        no-op counts as applied.
        """
        facing = self._facing.get(train)
        if facing is None:  # a train this session does not hold
            return False
        if train in self._train_of.values():  # a request in flight
            return False
        if train in self._kept:  # a move not yet taken up (#1025)
            return False
        tail, _ = facing_ends(facing)
        self._facing[train] = facing_towards(connected_end(self._layout, tail))
        self._publish_facing()
        return True

    # -- facing ------------------------------------------------------------

    def _on_dispatch(self, topic: str, payload: Payload) -> None:
        """Facing, carried forward from what the dispatcher announces.

        A route is a strict pass-through, so a train that left nose-first
        faces away from the end it entered through, and a propelled one faces
        the end it entered through. Both are answers to a move that actually
        happened: `route_chosen` is not one, and changes no facing. Committing
        to a route is a plan, and facing is a fact about the stock — where the
        request departs the end the train's tail stands at, which ADR-0019
        allows, recording the departure would say the train had turned around
        while nothing touched it (#295).

        The route `route_chosen` names is kept, by request id, and dropped
        when the request ends, whichever way. On a railroad run without
        sensors no move is granted and the request completes when a person
        says the train has arrived, so `request_completed` is the one answer
        to the run: where the facing does not yet name the route's last
        block, `_ran` carries it along the route (#1317). After a run
        followed by sensors it already names that block, and nothing changes.

        A request ends by arrival, by rejection, or by **cancellation**
        (ADR-0049), and the third leaves as little behind as the other two:
        the request and its destination are dropped and nothing is
        re-submitted. A destination that is still wanted is asked for again
        with `request_wanted` — the gesture that ended it was a person's, and
        re-asking on their behalf would compose work they just ended. Facing
        needs no case of its own either: `removed` is followed by
        `train_removed`, which already pops it, and `displaced` by
        `train_placed`, which already recomputes it.

        `request_submitted` is on this filter too, the scheduler's own
        included, because the topic names the dispatcher that responds to it,
        and it is **read** rather than ignored: it is what tells this app
        that a train has a request in flight when something else submitted
        one (BUS.md, rule 1 — one responder, any number of writers). The
        id and the train are recorded, and the answers below drop them again
        by id, so the removal side that was already whole gets an insertion
        side to match (#439). `_submit` writes the same key and the same
        value for this app's own requests, which keeps the guard immediate
        there: over a broker the frame comes back a round trip later, and a
        reversal arriving inside that window would slip past a guard that is
        about to be correct.

        Every payload is **read** and never trusted, exactly as a gesture is
        (#259). These leaves name the dispatcher because the dispatcher
        emits them, and a name is not a sender: the bus authenticates
        nobody, so a frame claiming to be an announcement is one more thing
        anyone can publish, and a consumer that raised on one would be taken
        down by whoever published it (BUS.md, rule 4). What cannot be read
        is dropped, silently and to the trace, as a gesture is: the scheduler
        answers nothing on the bus, so there is nothing to address a refusal
        to even where the frame carries an id (ADR-0034).
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "move_granted":
            self._granted(payload)
        elif leaf == "allocation":
            self._recorded(payload)
            self._stood(payload)
        elif leaf == "train_placed":
            placed = placement(payload)
            # A null block is `train_removed`'s statement and not this
            # leaf's, so the fact that carries one is read as unreadable.
            if placed is not None and placed.block is not None:
                self._kept.pop(placed.train, None)
                self._placed(placed.train, placed.block)
        elif leaf == "train_removed":
            # An unplaced train has no facing: facing is the end of *its
            # block* a parked train would depart through, and there is no
            # block for it to be an end of (ADR-0019, ADR-0039). Nor a kept
            # one: the move it was kept for is not going to be taken up.
            removed = named_train(payload)
            if removed is not None:
                self._facing.pop(removed, None)
                self._kept.pop(removed, None)
        elif leaf == "request_submitted":
            # A request in flight, whoever submitted it. Either half
            # unreadable and there is nothing to remember by: a frame with no
            # id could never be answered and so never dropped again, and one
            # with no train says nothing about the train the guard asks
            # about.
            submitted, mover = readable_id(payload), named_train(payload)
            if submitted is not None and mover is not None:
                self._train_of[submitted] = mover
                self._state = release.announced(self._state, submitted, mover)
        elif leaf == "route_chosen":
            picked = chosen(payload)
            if picked is not None:
                self._routes[picked.id] = picked.route
        elif leaf in ("request_completed", "request_rejected", "request_cancelled"):
            answered = readable_id(payload)
            if answered is not None:
                route = self._routes.pop(answered, None)
                train = self._train_of.pop(answered, None)
                if leaf == "request_completed" and route and train is not None:
                    self._ran(train, route)
                block = self._to_start.pop(answered, None)
                if (
                    block is not None
                    and train is not None
                    and answered in self._state.positioning
                    and rejected_for(payload) == Reason.UNREACHABLE
                ):
                    self._either_way(train, block)
                self._state = release.ended(
                    self._state, answered, leaf.removeprefix("request_")
                )
        self._publish_facing()
        self._settle()

    def _ran(self, train: str, route: tuple[str, ...]) -> None:
        """Facing after a request completed whose moves no grant described:
        `_across` applied to each transit of the route in turn, from the
        facing held (#1317).

        Only where that facing does not already name the route's last block.
        Where it does, the moves were granted and taken up one by one, and
        nothing is left to carry. A train with no facing held gets none, and
        a transit this layout does not hold leaves the facing as it was.
        """
        facing = self._facing.get(train)
        if facing is None or block_of(facing) == route[-1]:
            return
        for transit, into in zip(route[1::2], route[2::2]):
            ends = transit_ends(self._layout, into, transit)
            if ends is None:
                return
            entered, left_by = ends
            facing = self._across(facing, left_by, entered)
        self._facing[train] = facing

    def _granted(self, payload: Payload) -> None:
        """Facing after a move the dispatcher authorised, **kept** rather than
        held: away from the end the train came in through where it left
        nose-first, and **at** that end where it was propelled.

        A grant is permission, and the train is still in the block it is
        leaving: its nose is still at the signal the grant cleared. So the
        facing the move will give it is worked out here and kept against the
        block it enters, and `_recorded` adopts it once the dispatcher records
        the train there (ADR-0019: facing changes only by the geometry of a
        move the train actually made; #1025). Read against the facing the
        train will hold when the move begins — the last one kept, where the
        grant overtook the allocation recording the arrival before it, and the
        one held otherwise.

        Neither end is on the bus — the grant names the transit and the block
        entered — so both are read off the layout, and read there through
        `transit_ends`. Dropping a transit no connection here
        holds, or one that crosses neither end of the block named, is not this
        reader's own strictness but the rule every reader of a transit and a
        block that arrived together keeps (SYSTEM.md): the frame describes a
        run there is no track for, so the layout interface moves no train
        under it either. Here it leaves nothing to face away from. The layout
        the scheduler holds is what makes that a real question rather than a
        guess.

        A train is **propelled** where the end it left by is the end its nose
        points *away* from — the tail end of the facing held — which is what a
        request departing against facing asks for and ADR-0019 allows. It
        enters the next block tail-first, so its nose points at the end it
        came in by, and pushing it further along the same route keeps saying
        so: routes are strict pass-throughs (ADR-0001), so every move of one
        route gets the same answer and nothing has to be remembered between
        them (#295). Read against the facing rather than remembered, and a
        train the scheduler holds no facing for is the nose-first case, which
        is what an arrival alone can say.

        No correction for a terminal block in that case, unlike the
        nose-first one: the end entered is a transit's end and so always
        connected, and a stub's one connected end is exactly what a train
        pushed into it faces (#145).
        """
        granted = grant(payload)
        if granted is None:
            return
        ends = transit_ends(self._layout, granted.into, granted.transit)
        if ends is None:  # not a transit into that block on this railroad
            return
        entered, left_by = ends
        kept = self._kept.setdefault(granted.train, [])
        facing = kept[-1][1] if kept else self._facing.get(granted.train)
        kept.append((granted.into, self._across(facing, left_by, entered)))

    def _across(self, facing: str | None, left_by: str, entered: str) -> str:
        """The facing a train holding `facing` has once it has left by
        `left_by` and come in through `entered`: the pass-through rule
        `_granted` states, and the one a restart's crossing is read by."""
        propelled = facing is not None and left_by == facing_ends(facing)[0]
        return facing_towards(
            entered if propelled else departure_end(self._layout, entered)
        )

    def _recorded(self, payload: Payload) -> None:
        """The kept facing a train takes up when the dispatcher's allocation
        names it in the block the move entered — the entered block reading
        occupied, which is when the train's nose is past the signal it left
        by (ADR-0093) and the facing its throttle reads the signal ahead off
        has to move with it (#1025).

        Moves kept ahead of that one stay kept. A train the allocation has
        stopped naming as crossing, and not named in any block it was kept
        for, has had its move ended by something other than its arrival and
        keeps nothing. An allocation that cannot be read moves nothing.
        """
        stated = kept_allocation(payload)
        if stated is None:
            return
        for train in list(self._kept):
            kept = self._kept[train]
            entered = [into for into, _ in kept]
            standing = stated.trains.get(train)
            if standing in entered:
                arrived = entered.index(standing)
                self._facing[train] = kept[arrived][1]
                del kept[: arrived + 1]
            elif train not in stated.crossing:
                kept.clear()
            if not kept:
                del self._kept[train]

    def _crossing(self, retained: object) -> dict[str, list[tuple[str, str]]]:
        """The facing kept for each train a retained allocation says was
        crossing when the last session ended (#1025).

        A restart holds no kept facing — the grant it was worked out on went
        by before this process existed — so it is read off the allocation
        instead: the transit the train is crossing out of the block it is
        recorded in, against the facing adopted for it there, by the same
        rule a grant is read by. Only where that facing names that block: a
        train whose facing says it stands somewhere else has nothing here to
        carry forward. A train already recorded in the block the transit
        enters reads the same way, and is kept a facing for the block
        behind it that nothing will record it in; `_recorded` drops it once
        the crossing ends.
        """
        stated = kept_allocation(retained)
        if stated is None:
            return {}
        kept: dict[str, list[tuple[str, str]]] = {}
        for train, transit in stated.crossing.items():
            origin, facing = stated.trains.get(train), self._facing.get(train)
            if origin is None or facing is None or block_of(facing) != origin:
                continue
            ends = transit_ends(self._layout, origin, transit)
            if ends is None:
                continue
            left_by, entered = ends
            kept[train] = [(block_of(entered), self._across(facing, left_by, entered))]
        return kept

    def _placed(self, train: str, block: str) -> None:
        """Facing after a person has said where a train actually stands.

        The scheduler follows `train_placed` and never `placement_wanted`:
        whether the block was free is knowledge only the dispatcher has, and
        two apps reading one gesture would have to agree on every
        precondition (ADR-0037). The facing is carried into the new block,
        which is arbitrary — the layout is topological and there is nothing
        better to derive from — and `reversal_wanted` is the correction where
        it lands the wrong way round (ADR-0019).

        A train that was **off the layout** has none to carry, so it gets
        `B-to-A` and the same correction: it is one more arbitrary choice of
        the kind the carry already is, and the dispatcher accepting the
        placement is what says the train is known (ADR-0039).
        """
        facing = self._facing.get(train)
        run = "B-to-A" if facing is None else end_letter(facing)
        self._facing[train] = connected_facing(self._layout, f"{block}.{run}")

    def _publish_facing(self) -> None:
        facing = {"facing": dict(sorted(self._facing.items()))}
        if facing != self._published:
            self._published = facing
            self._bus.publish(FACING, facing)

    # -- the timetable -----------------------------------------------------

    def _restarted(self, retained: object) -> release.State:
        """The release rule's state as this process begins: the timetable a
        retained `tc49/schedule/state/timetable` value names, where the store
        has its document, and no timetable loaded otherwise (#1352).

        The row is adopted as facing is, and read as any payload is. A row
        that cannot be read, a name the store has no document for, and a
        document the store cannot read each leave no timetable loaded. Where
        the row's entries are not the document's, the row's are kept and
        `_settle` writes them.
        """
        name = loaded_timetable(retained)
        if self._store is None or name is None:
            return release.State()
        try:
            document = self._store.timetable(self._layout.name, name)
        except (ValueError, TypeError):
            return release.State()
        if document is None:
            return release.State()
        self._written = document
        return release.restarted(retained, document) or release.State()

    def _on_clock(self, topic: str, payload: Payload) -> None:
        """A `tc49/layout/state/clock` row: the release rule takes the
        clock's time from it. One that cannot be read is dropped.

        A row that moves a recording's start (#1371) and reads day 1 or later
        asks for the clock on day 0 at its time of day, on
        `tc49/layout/clock_wanted` with no `speed_up`, as `_make` does."""
        said = said_clock(payload)
        if said is None:
            return
        time, speed_up = said
        timetable = self._state.timetable
        self._state = release.clocked(self._state, time, speed_up)
        if self._state.timetable is not timetable and self._state.clock != time:
            self._bus.publish(CLOCK_WANTED, {"time": self._state.clock})
        self._settle()

    def _on_power(self, topic: str, payload: Payload) -> None:
        """`tc49/layout/state/power`. A row that cannot be read reads `off`,
        as `lib.payload.power` reads it for every reader."""
        self._state = release.powered(self._state, power(payload))
        self._settle()

    def _stood(self, payload: Payload) -> None:
        """An allocation row: where each train stands, which a new
        timetable's `trains` are read off. The first one whose request list
        can be read also says which requests are in flight, and an entry
        that is `out` whose request it does not list has ended
        (`release.listed`)."""
        stated = kept_allocation(payload)
        if stated is None:
            return
        self._standing = stated.trains
        requests = listed_requests(payload)
        if requests is not None and not self._listed:
            self._listed = True
            self._state = release.listed(self._state, requests)

    def _stands(self) -> dict[str, TrainStart]:
        """Where each train on the layout stands: its block, as the last
        allocation row read names it, and the facing held for it. A train
        with no block there or no facing here is off the layout."""
        standing = self._standing or {}
        return {
            train: TrainStart(standing[train], end_letter(facing))
            for train, facing in sorted(self._facing.items())
            if train in standing
        }

    def _either_way(self, train: str, block: str) -> None:
        """The second request that sends `train` to its start block
        `block`, after the dispatcher rejected the first as `unreachable`:
        to both ends of the block (#1353). It is listed in `positioning`
        before the first one is told ended, so the timetable does not start
        between the two. It is not in `_to_start`, so its own rejection is
        followed by nothing."""
        request = self._drag(train, (f"{block}.A", f"{block}.B"))
        if request is not None:
            self._state = release.positioned(self._state, request)

    def _start_wanted(self, payload: Payload) -> None:
        """A `timetable_start_wanted` gesture: a `loaded` timetable is
        started, whatever power reads and whichever requests to start blocks
        are still out. Dropped in any other phase and with none loaded."""
        if wanted_start(payload) and release.starts(self._state, asked=True):
            self._start()

    def _start(self) -> None:
        """The loaded timetable started (#1353): the clock is asked to be
        set to the timetable's start time, on `tc49/layout/clock_wanted`
        with no `speed_up`, and the phase is `running`. The caller asked
        `release.starts` first."""
        timetable = self._state.timetable
        assert timetable is not None
        self._bus.publish(CLOCK_WANTED, {"time": timetable.start})
        self._state = release.started(self._state)

    def _release(self) -> None:
        """Each entry the release rule says is due, released (#1353).

        An entry with `to` is a drag of its train to those arrival ends,
        composed and submitted by `_drag` as a person's is, so it has the
        same id form and departure end, and chains after the train's
        latest request in flight. The entry is then `out` as that request.
        A turn-round is applied by `_turn`, and the entry has `ended`. It
        is not recorded as a person's gesture is.

        An entry that could not be done is left as it is and is due again
        at the next message. The rule is asked again only after a
        turn-round was applied, which can make the train's next entry due.
        """
        again = True
        while again:
            again = False
            for due in release.due(self._state):
                train = due.entry.train
                if due.entry.turn:
                    if self._turn(train):
                        self._state = release.turned(self._state, due.index)
                        again = True
                    continue
                request = self._drag(train, due.entry.to)
                if request is not None:
                    self._state = release.released(self._state, due.index, request)

    def _settle(self) -> None:
        """What follows every message the scheduler takes, where it was
        given a store: the release rule is told the trains on the layout and
        where each stands (`release.located`) and asked what to do, the
        timetable's document is written where it changed, and the state row
        is published where it changed (#1352). What the rule answers is
        `untitled` made, the loaded timetable started (`_start`) and its due
        entries released (`_release`), in that order (#1353).

        The rule is told no trains until an allocation row was read, and
        makes no timetable until then. A change of an entry's state alone is
        no change to the document.
        """
        if self._store is None:
            return
        if self._standing is not None:
            stands = self._stands()
            on_layout = frozenset(stands)
            if on_layout != self._state.placed:
                self._state = release.placed(self._state, on_layout)
            self._state = release.located(self._state, stands)
        if release.untitled(self._state):
            self._make(release.UNTITLED)
        if release.starts(self._state):
            self._start()
        self._release()
        timetable = self._state.timetable
        if timetable is not None and timetable != self._written:
            self._written = timetable
            self._store.put_timetable(timetable)
        said = release.row(self._state)
        if said != self._said:
            self._said = said
            self._bus.publish(TIMETABLE, said)


def _kept(retained: object) -> dict[str, str]:
    """The facing a previous session left on the state topic, **read** rather
    than adopted whole (#123).

    The reading is `lib.payload`'s, as every payload the scheduler takes off
    the bus is: a retained value is a payload like any other, and rule 4 does
    not exempt the moment one is read at construction (#277). Where it states
    no facing map at all the reader answers nothing and the scheduler starts
    as a cold start does.

    What is left here is the vocabulary, which is the layout's question: this
    value may have been hand-edited on the broker, so a value outside it is
    dropped and the train falls back to what its placement gives — the seed
    under it where a document places it, and no facing at all until a person
    places it where none does (#241). Guessing which way round an `A` meant is
    the one thing that must not happen: it would be the reading turned around.
    """
    held = kept_facing(retained)
    if held is None:
        return {}
    return {
        train: lie for train, lie in sorted(held.items()) if end_letter(lie) in FACINGS
    }


def _expand(arrivals: tuple[str, ...]) -> list[str]:
    """Mechanical arrival-end expansion: a bare block means both its ends."""
    ends: list[str] = []
    for entry in arrivals:
        if "." in entry:
            ends.append(entry)
        else:
            ends += [f"{entry}.A", f"{entry}.B"]
    return ends
