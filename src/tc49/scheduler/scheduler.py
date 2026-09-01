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
adds. Ids are minted deterministically in the timetable's order
(`<train>-1`, `<train>-2`, ...) from one undivided counter, the arrival-end
expansion is purely mechanical (a bare block becomes both of its ends), and
`exhausted` is set as soon as the last timetable request is out.

It **holds facing** (ADR-0019), seeded where a run was built from a document
and carried forward from the bus: a train faces away from the end it entered
through, and a committed route's departure end is the end it will leave by.
That is what the layout read is for — `move_granted` names a transit and the
block entered, not the end entered through — and why the scheduler subscribes
`tc49/dispatch/#` (ADR-0028's growth, spent on facing). What it holds per
train is `lib`'s facing: the run the train would make across its block,
`<block>.A-to-B` or `<block>.B-to-A`, out of which a drag's departure end is
read (#241). Into a terminal block there is no end to face away towards, so
arrival goes through `departure_end` and seeding through `connected_facing`,
which turns a candidate off a wall (#145). The last-value topic it publishes
is what every view reads to draw a direction arrow, a train that has never
moved having no other source for one. Where the bus binding has kept that
topic across a restart the scheduler adopts what it finds there instead of
the placement, which is what a broker that outlived it would have delivered
(#123).
Deliberate reversal at rest is the one change routes do not account for, and
it arrives as its own gesture on `tc49/schedule/reversal_wanted` (#124).
"""

from collections import Counter
from collections.abc import Sequence
from typing import cast

from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import (
    FACINGS,
    Layout,
    connected_end,
    connected_facing,
    departure_end,
    end_crossed,
    end_letter,
    facing_ends,
    facing_towards,
)
from tc49.lib.payload import (
    chosen,
    gesture,
    grant,
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
        self._published: Payload = {}  # the facing last sent, so only changes go
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
        bus.subscribe("tc49/dispatch/#", self._on_dispatch)
        bus.subscribe("tc49/schedule/#", self._on_gesture)

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
                "id": f"{wanted.train}-{self._counters[wanted.train]}",
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
        request still departs the old end, and `route_chosen` flips the arrow
        back when it launches, undoing the operator's gesture minutes later.
        A **rejected** request leaves the train idle — `_train_of` has dropped
        it — and that is precisely when you want to turn around.

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

        A route is a strict pass-through, so a train faces away from the end
        it entered through; and a committed route's departure end is the end
        it will leave by, which a request departing against facing is allowed
        to state (ADR-0019 makes facing a discipline, not an invariant).

        The first of those is `lib`'s `departure_end`: into a terminal block
        there is no end to face away towards, and it gives back the one end a
        connection holds (#145). The second needs no correction — a route's
        departure end is a transit's end and so always connected.

        `request_submitted` is on this filter too, the scheduler's own
        included, because the topic names the dispatcher that responds to it.
        It is ignored here like every other leaf the scheduler does not act
        on.

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
        elif leaf == "route_chosen":
            self._launched(payload)
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
        elif leaf in ("request_completed", "request_rejected"):
            answered = readable_id(payload)
            if answered is not None:
                self._train_of.pop(answered, None)
        self._publish_facing()

    def _granted(self, payload: Payload) -> None:
        """Facing after a move the dispatcher authorised: away from the end
        the train came in through.

        The end is not on the bus — the grant names the transit and the block
        entered — so it is read off the layout, and read there through
        `end_crossed`: a transit no connection here holds, or one that
        crosses neither end of the block named, leaves nothing to face away
        from and the frame is dropped. The layout the scheduler holds is what
        makes that a real question rather than a guess.
        """
        move = grant(payload)
        if move is None:
            return
        entered = end_crossed(self._layout, move.into, move.transit)
        if entered is None:  # not a transit into that block on this railroad
            return
        self._facing[move.train] = facing_towards(departure_end(self._layout, entered))

    def _launched(self, payload: Payload) -> None:
        """Facing after a route was committed: the end it will leave by.

        Which train that is, is the scheduler's own record of the request it
        submitted, so a route chosen for an id it never minted moves nothing
        — as one for a request that has since been answered does not. The
        degenerate already-there route is a single block and has no transit
        to read an end off, and needs none: nothing moves.

        No correction for a terminal block here, unlike an arrival: a route's
        departure end is a transit's end and so always connected.
        """
        launch = chosen(payload)
        if launch is None:
            return
        train = self._train_of.get(launch.id)
        if train is None or len(launch.route) < 2:
            return
        departure = end_crossed(self._layout, launch.route[0], launch.route[1])
        if departure is None:  # not a transit off that block on this railroad
            return
        self._facing[train] = facing_towards(departure)

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


def _kept(retained: Payload | None) -> dict[str, str]:
    """The facing a previous session left on the state topic, **read** rather
    than adopted whole (#123).

    A retained value is a payload like any other and this one may have been
    written by an older build, so a value outside the vocabulary is dropped
    and the train falls back to what its placement gives — the seed under it
    where a document places it, and no facing at all until a person places it
    where none does (#241). Guessing which way round an `A` meant is the one
    thing that must not happen: it would be the reading turned around.
    """
    values = retained.get("facing") if isinstance(retained, dict) else None
    if not isinstance(values, dict):
        return {}
    held: dict[str, str] = {}
    for train, facing in sorted(cast(dict[str, object], values).items()):
        if isinstance(facing, str) and end_letter(facing) in FACINGS:
            held[train] = facing
    return held


def _expand(arrivals: tuple[str, ...]) -> list[str]:
    """Mechanical arrival-end expansion: a bare block means both its ends."""
    ends: list[str] = []
    for entry in arrivals:
        if "." in entry:
            ends.append(entry)
        else:
            ends += [f"{entry}.A", f"{entry}.B"]
    return ends
