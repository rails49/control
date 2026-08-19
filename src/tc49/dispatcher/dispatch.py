"""Dispatcher: admission, queue, lock table, buffered sensors, grant phase.

Fully asynchronous at the bus boundary (SYSTEM.md, dispatcher footprint):
requests arrive as events, every fate is announced as an event, and the
request id is both correlation and idempotency key. Sensor events are
buffered until the tick and treated as a set, so grants are a pure
function of the buffered set, never of delivery order (DISPATCH.md, time
model). Standing locks are seeded from the scenario and published at
startup. The locking discipline is the pluggable strategy of locking.py.
"""

from dataclasses import dataclass

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
        self._buffered: list[tuple[str, str]] = []  # (leaf, block) since last tick
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
        rid = payload["id"]
        if rid in self._seen_ids:  # idempotency: duplicates are dropped
            return
        self._seen_ids.add(rid)
        train = payload["train"]
        expected = self._expected_block(train)
        if self._departs_elsewhere(payload["depart"], expected):
            self._bus.publish(
                "tc49/dispatch/request_rejected", {"id": rid, "reason": "wrong_origin"}
            )
            return

        surviving: list[str] = []
        pruned: list[dict[str, str]] = []
        for end in payload["dest"]:
            block = end.rpartition(".")[0]
            if block == expected:
                # Possibly degenerate — the request names the block the train
                # stands in, accepted whichever end it names (DISPATCH.md);
                # the first launch attempt decides.
                surviving.append(end)
            elif self._state.train_lengths[train] > self._state.layout.blocks[block]:
                pruned.append({"end": end, "reason": "no_fit"})
            elif end not in self._state.layout.end_connection:
                pruned.append({"end": end, "reason": "no_entry"})
            else:
                surviving.append(end)
        if not surviving:
            reason = (
                "no_fit" if any(p["reason"] == "no_fit" for p in pruned) else "no_entry"
            )
            self._bus.publish(
                "tc49/dispatch/request_rejected", {"id": rid, "reason": reason}
            )
            return
        self._pending.append(
            Request(
                rid,
                train,
                payload["depart"],
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
        if leaf == "tick":
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
        if result.locked:
            self._publish(
                "lock_granted",
                {"train": active.request.train, "resources": result.locked},
            )
        self._publish(
            "move_granted",
            {
                "id": active.request.id,
                "train": active.request.train,
                "transit": result.transit,
                "into": result.into,
            },
        )
        active.outstanding = result
        active.cur_index += 1

    def _publish(self, leaf: str, payload: Payload) -> None:
        self._bus.publish(f"tc49/dispatch/{leaf}", payload)
