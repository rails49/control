"""Scheduler: the one writer of requests, and the holder of facing.

Its sources are configuration rather than a rule (ADR-0036): a timetable
submitted whole at the start of a run, in the file's order, and a person
gesturing on the two topics the scheduler declares,
`tc49/schedule/request_wanted` and `tc49/schedule/reversal_wanted`. Time is
the scheduler's responsibility, and a timetable released against a clock is
a milestone-2 feature nothing needs yet (ADR-0047); the queue does the
staggering, there never being enough tracks to satisfy every request at
once. A gesture is not a request — it names a train and
where to put it, and the id and the departure end are what the scheduler
adds. A timetable's ids are minted deterministically in its order
(`<train>-1`, `<train>-2`, ...) from one undivided counter and a drag's carry
a **per-process nonce** in between (`<train>-<nonce>-<n>`), which is
ADR-0033's split moved inside this app: a document's requests read in the
document's order, and a restart of this process alone — ordinary now the apps
are separate ones (ADR-0059) — would otherwise re-mint a drag's id the
dispatcher already holds and has dropped unanswered. The harness states the
nonce rather than taking the minted one, which is what keeps a replayed run
reproducible now that a replay feeds its document as drags. The arrival-end expansion is purely mechanical (a bare
block becomes both of its ends), and `exhausted` is set as soon as the last
timetable request is out.

It **holds facing** (ADR-0019), seeded where a run was built from a document
and carried forward from the bus: a train that left nose-first faces away from
the end it entered through, and a **propelled** one — pushed out of the end its
nose points away from — faces the end it entered through. Committing to a route
changes nothing, facing being a fact about the stock and not about the plan
(#295). That is what the layout read is for — `move_granted` names a transit
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
"""

import secrets
from collections import Counter
from collections.abc import Sequence

from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import (
    FACINGS,
    Layout,
    connected_end,
    connected_facing,
    departure_end,
    end_across,
    end_crossed,
    end_letter,
    facing_ends,
    facing_towards,
)
from tc49.lib.payload import (
    gesture,
    grant,
    kept_facing,
    named_train,
    placement,
    readable_id,
)
from tc49.lib.scenario import RequestSpec

FACING = "tc49/schedule/state/facing"


class Scheduler:
    def __init__(
        self,
        bus: Bus,
        layout: Layout,
        facing: dict[str, str] | None = None,
        timetable: Sequence[RequestSpec] = (),
        nonce: str | None = None,
    ) -> None:
        """`facing` is where a run built from a document says its trains point,
        train to the run it would make across its block, and `timetable` is
        that document's request list. Both are the harness's: a run an
        operator drives is given neither, and its facing arrives with the
        placements a person makes (ADR-0036 — which sources a run has is
        configuration, not a rule).
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
        self._train_of: dict[str, str] = {}  # request id -> the train it moves
        self._counters: Counter[str] = Counter()  # one undivided minter
        # What makes a drag's id unique across a restart of this process
        # alone: the counter above starts empty in every process, so without
        # it the first drag after a restart mints an id the dispatcher is
        # still holding and drops before any check runs (ADR-0033). Four
        # bytes of `secrets`, not the clock, which SYSTEM.md forbids of the
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
        self._publish_facing()
        for request in timetable:
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
        self._bus.publish("tc49/dispatch/request_submitted", event)

    # -- gestures ----------------------------------------------------------

    def _on_gesture(self, topic: str, payload: Payload) -> None:
        """A person's action on a page: which of the two leaves it came on.

        The filter is the whole of `tc49/schedule`, as rule 3 asks, so the
        scheduler's own two state topics come back through here and are
        ignored on the way past. Nothing in the topic or the payload says who
        sent a gesture, and nothing here asks: a page sends these today, and
        anything else that composes one is served the same (SYSTEM.md,
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
        # a throttle is a third leaf under this role, later

    def _compose(self, payload: Payload) -> None:
        """A drag, composed into the request it asks for.

        A gesture names a train and where to put it; the two fields it omits
        are the two the scheduler owns — the id it mints and the departure
        end it reads off the facing it holds (ADR-0036). A facing is the run
        the train would make across its block, so the departure end is the
        end that run comes out at, said as an end (#241).

        The id carries this process's nonce, `<train>-<nonce>-<n>`, where the
        timetable's is `<train>-<n>`: nothing a person drags is reproducible,
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

        It judges nothing else: a train that is not idle is composed and
        submitted like any other, and answered `wrong_origin` or queued.
        """
        wanted = gesture(payload)
        if wanted is None:
            return
        facing = self._facing.get(wanted.train)
        if facing is None:  # a train this session does not hold
            return
        _, depart = facing_ends(facing)
        self._counters[wanted.train] += 1
        self._submit(
            {
                "id": f"{wanted.train}-{self._nonce}-{self._counters[wanted.train]}",
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
        any number of writers (SYSTEM.md, rule 1), so a page may submit for a
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
        wall and is rejected `unreachable` for the rest of the session.
        """
        train = named_train(payload)
        if train is None:
            return
        facing = self._facing.get(train)
        if facing is None:  # a train this session does not hold
            return
        if train in self._train_of.values():  # a request in flight
            return
        tail, _ = facing_ends(facing)
        self._facing[train] = facing_towards(connected_end(self._layout, tail))
        self._publish_facing()

    # -- facing ------------------------------------------------------------

    def _on_dispatch(self, topic: str, payload: Payload) -> None:
        """Facing, carried forward from what the dispatcher announces.

        A route is a strict pass-through, so a train that left nose-first
        faces away from the end it entered through, and a propelled one faces
        the end it entered through. Both are answers to a move that actually
        happened: `route_chosen` is not one, and is ignored here like every
        other leaf the scheduler does not act on. Committing to a route is a
        plan, and facing is a fact about the stock — where the request departs
        the end the train's tail stands at, which ADR-0019 allows, recording
        the departure would say the train had turned around while nothing
        touched it (#295).

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
        one (SYSTEM.md, rule 1 — one responder, any number of writers). The
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
        down by whoever published it (SYSTEM.md, rule 4). What cannot be read
        is dropped, silently and to the trace, as a gesture is: the scheduler
        answers nothing on the bus, so there is nothing to address a refusal
        to even where the frame carries an id (ADR-0034).
        """
        leaf = topic.rsplit("/", 1)[-1]
        if leaf == "move_granted":
            self._granted(payload)
        elif leaf == "train_placed":
            placed = placement(payload)
            # A null block is `train_removed`'s statement and not this
            # leaf's, so the fact that carries one is read as unreadable.
            if placed is not None and placed.block is not None:
                self._placed(placed.train, placed.block)
        elif leaf == "train_removed":
            # An unplaced train has no facing: facing is the end of *its
            # block* a parked train would depart through, and there is no
            # block for it to be an end of (ADR-0019, ADR-0039).
            removed = named_train(payload)
            if removed is not None:
                self._facing.pop(removed, None)
        elif leaf == "request_submitted":
            # A request in flight, whoever submitted it. Either half
            # unreadable and there is nothing to remember by: a frame with no
            # id could never be answered and so never dropped again, and one
            # with no train says nothing about the train the guard asks
            # about.
            submitted, mover = readable_id(payload), named_train(payload)
            if submitted is not None and mover is not None:
                self._train_of[submitted] = mover
        elif leaf in ("request_completed", "request_rejected", "request_cancelled"):
            answered = readable_id(payload)
            if answered is not None:
                self._train_of.pop(answered, None)
        self._publish_facing()

    def _granted(self, payload: Payload) -> None:
        """Facing after a move the dispatcher authorised: away from the end
        the train came in through where it left nose-first, and **at** that
        end where it was propelled.

        Neither end is on the bus — the grant names the transit and the block
        entered — so both are read off the layout, and read there through
        `end_crossed` and `end_across`. Dropping a transit no connection here
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
        entered = end_crossed(self._layout, granted.into, granted.transit)
        if entered is None:  # not a transit into that block on this railroad
            return
        left_by = end_across(self._layout, granted.into, granted.transit)
        facing = self._facing.get(granted.train)
        propelled = facing is not None and left_by == facing_ends(facing)[0]
        self._facing[granted.train] = facing_towards(
            entered if propelled else departure_end(self._layout, entered)
        )

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


def _kept(retained: object) -> dict[str, str]:
    """The facing a previous session left on the state topic, **read** rather
    than adopted whole (#123).

    The reading is `lib.payload`'s, as every payload the scheduler takes off
    the bus is: a retained value is a payload like any other, and rule 4 does
    not exempt the moment one is read at construction (#277). Where it states
    no facing map at all the reader answers nothing and the scheduler starts
    as a cold start does.

    What is left here is the vocabulary, which is the layout's question: this
    value may have been written by an older build, so a value outside it is
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
