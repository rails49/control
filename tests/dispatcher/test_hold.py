"""The run is held or running, and held blocks commitment (ADR-0037, #152).

A brake and not an emergency stop: a move already granted runs to its sensors
and releases its locks, and what the hold buys is that nothing new commits —
no route is chosen, no move granted, no lock taken — over a railroad that may
have come back live under it. Admission is untouched: requests queue up while
held and drain in the order they accumulated when the release sweeps them
(ADR-0047).

Driven at the bus, which is where a person's press arrives: `run_wanted` in,
`state/run` and the trace out. The held runs are built live — a batch run's
timetable mints and is granted in the opening drain, before any press could
land, so what queues into a held run arrives as gestures.
"""

from tc49.bench.runner import Assembly
from tests.harness import RUN_WANTED, leaves, live, press, run_wanted, runs, ticks

REQUEST_WANTED = "tc49/schedule/request_wanted"


def ids(assembly: Assembly, leaf: str) -> list[str]:
    return [str(line["id"]) for line in leaves(assembly, leaf)]


def held_with_three_requests() -> Assembly:
    """A live railroad held with three gestures queued into it: two of
    freight_1's in a chain around one of express_2's."""
    assembly = live("crossover-yard/meet")
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    press(assembly, REQUEST_WANTED, {"train": "express_2", "dest": ["yard_w.B"]})
    press(
        assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["dn_w.A", "dn_w.B"]}
    )
    return assembly


def test_a_cold_session_says_it_is_running_before_anything_moves(
    timetabled: Assembly,
) -> None:
    """The value is served rather than inferred from an absence (ADR-0032):
    the constructor states it, so a client joining an idle railroad reads a
    value instead of guessing one."""
    ticks(timetabled, 1)
    assert runs(timetabled) == ["running"]
    assert leaves(timetabled, "run")[0]["time"] == 0.0


def test_a_held_run_grants_nothing_while_requests_mint_into_it() -> None:
    """The whole of the guarantee, on the events that would move a train:
    the requests arrive and are admitted, and no route is committed."""
    assembly = held_with_three_requests()
    ticks(assembly, 3)

    assert len(ids(assembly, "request_admitted")) == 3
    assert leaves(assembly, "route_chosen") == []
    assert leaves(assembly, "move_granted") == []
    assert leaves(assembly, "grant_refused") == []
    # The startup standing locks and nothing since: no lock is taken on the
    # strength of a placement nobody has confirmed.
    assert {line["train"] for line in leaves(assembly, "lock_granted")} == {
        "freight_1",
        "express_2",
    }


def test_admissions_keep_their_order_while_held() -> None:
    """`_phases` stamps an admission with the sweep count it joined at, and a
    held run is still a run: the queue records the order a release will
    honour."""
    assembly = held_with_three_requests()
    assert ids(assembly, "request_admitted") == [
        "freight_1-1",
        "express_2-1",
        "freight_1-2",
    ]


def test_a_released_queue_drains_in_the_order_it_accumulated() -> None:
    """Nobody accrues refusals while held, so the aging key is admission
    order and the queue leaves as it arrived (#34)."""
    assembly = held_with_three_requests()
    press(assembly, RUN_WANTED, {"run": "running"})
    ticks(assembly, 40)

    assert runs(assembly) == ["running", "held", "running"]
    assert ids(assembly, "route_chosen") == [
        "freight_1-1",
        "express_2-1",
        "freight_1-2",
    ]
    assert set(ids(assembly, "request_completed")) == {
        "freight_1-1",
        "express_2-1",
        "freight_1-2",
    }


def test_release_grants_on_the_press_itself() -> None:
    """Releasing runs a sweep (ADR-0047): the press re-opens the gate the
    hold closed, so the first route commits with the gesture and no beat is
    waited out."""
    assembly = live("crossover-yard/meet")
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert leaves(assembly, "route_chosen") == []

    press(assembly, RUN_WANTED, {"run": "running"})
    assert ids(assembly, "route_chosen") == ["freight_1-1"]


def test_a_value_that_is_no_run_state_leaves_the_run_alone(
    timetabled: Assembly,
) -> None:
    """A gesture has no id to address an answer to, so a third value is
    dropped in silence and to the trace (ADR-0034)."""
    press(timetabled, RUN_WANTED, {"run": "draining"})
    press(timetabled, RUN_WANTED, {"held": True})
    ticks(timetabled, 2)

    assert runs(timetabled) == ["running"]


def test_the_same_value_twice_republishes_nothing(timetabled: Assembly) -> None:
    """A state topic moves when its value moves, as every other one here
    does; a press that changes nothing is not a change."""
    press(timetabled, RUN_WANTED, {"run": "held"})
    press(timetabled, RUN_WANTED, {"run": "held"})
    ticks(timetabled, 2)

    assert runs(timetabled) == ["running", "held"]


def test_a_request_wanted_is_still_admitted_while_held() -> None:
    """Held blocks commitment, not admission: a person can queue work
    against a railroad at rest and watch it leave when they release it."""
    assembly = live("crossover-yard/meet")
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 3)

    assert ids(assembly, "request_admitted") == ["freight_1-1"]
    assert leaves(assembly, "route_chosen") == []


def test_an_outstanding_move_completes_and_releases_its_locks(
    timetabled: Assembly,
) -> None:
    """The hold is a brake, not an emergency stop. Nothing on the bus can
    retract a `move` already sent, so a sensor applies where it lands, held
    or not — otherwise a train that arrived would hold the block behind it
    for as long as the operator stood there."""
    ticks(timetabled, 2, at={0: run_wanted("held")})

    # freight_1's opening launch went out before the press could land — its
    # sensors completed the move and gave yard_w back while held — and
    # nothing new committed after it: express_2, refused at the start while
    # freight_1 held yard_w, is not launched by the release that vacate
    # would otherwise have swept.
    assert len(leaves(timetabled, "move_granted")) == 1
    assert leaves(timetabled, "lock_released")
    assert ids(timetabled, "route_chosen") == ["freight_1-1"]


def test_a_degenerate_request_waits_for_the_release_too() -> None:
    """A request whose train already stands in one of its own arrival blocks
    completes without moving a wheel, and still waits: "no `route_chosen`" is
    read literally, and a sweep that answered one request would be a sweep
    that committed."""
    assembly = live("crossover-yard/meet")
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_w.B"]})
    ticks(assembly, 3)

    assert ids(assembly, "request_admitted") == ["freight_1-1"]
    assert leaves(assembly, "route_chosen") == []

    press(assembly, RUN_WANTED, {"run": "running"})
    assert leaves(assembly, "route_chosen")[0]["route"] == ["yard_w"]
    assert ids(assembly, "request_completed") == ["freight_1-1"]
