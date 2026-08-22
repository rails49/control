"""The run is held or running, and held blocks commitment (ADR-0037, #152).

A brake and not an emergency stop: a move already granted runs to its sensor
and releases its locks, and what the hold buys is that nothing new commits —
no route is chosen, no move granted, no lock taken — over a railroad that may
have come back live under it. Admission is untouched: requests queue up while
held and drain in the order they accumulated.

Driven at the bus, which is where a person's press arrives: `run_wanted` in,
`state/run` and the trace out.
"""

from tc49.bench.runner import Assembly, assemble_live
from tests.harness import RUN_WANTED, leaves, load, press, run_wanted, runs, ticks

REQUEST_WANTED = "tc49/ui/request_wanted"


def ids(assembly: Assembly, leaf: str) -> list[str]:
    return [str(line["id"]) for line in leaves(assembly, leaf)]


def test_a_cold_session_says_it_is_running_before_anything_moves(
    timetabled: Assembly,
) -> None:
    """The value is served rather than inferred from an absence (ADR-0032):
    the constructor states it, so a client joining an idle railroad reads a
    word instead of guessing one."""
    ticks(timetabled, 1)
    assert runs(timetabled) == ["running"]
    assert leaves(timetabled, "run")[0]["boundary"] == 0


def test_a_held_run_grants_nothing_while_a_timetable_mints_into_it(
    timetabled: Assembly,
) -> None:
    """The whole of the guarantee, on the events that would move a train:
    the workings arrive and are admitted, and no route is committed."""
    ticks(timetabled, 14, at={0: run_wanted("held")})

    assert len(ids(timetabled, "request_admitted")) == 3
    assert leaves(timetabled, "route_chosen") == []
    assert leaves(timetabled, "move_granted") == []
    assert leaves(timetabled, "grant_refused") == []
    # The startup standing locks and nothing since: no lock is taken on the
    # strength of a placement nobody has confirmed.
    assert {line["train"] for line in leaves(timetabled, "lock_granted")} == {
        "freight_1",
        "express_2",
    }


def test_the_boundary_keeps_counting_while_held(timetabled: Assembly) -> None:
    """`_phases` stamps an admission with the grant order it joined at, and a
    held run is still a run: the return working, minted at boundary 12, must
    reach the queue at all."""
    ticks(timetabled, 14, at={0: run_wanted("held")})
    assert ids(timetabled, "request_admitted") == [
        "freight_1-1",
        "express_2-1",
        "freight_1-2",
    ]


def test_a_released_queue_drains_in_the_order_it_accumulated(
    timetabled: Assembly,
) -> None:
    """Nobody accrues refusals while held, so the aging key is admission
    order and the queue leaves as it arrived (#34)."""
    ticks(timetabled, 40, at={0: run_wanted("held"), 14: run_wanted("running")})

    assert runs(timetabled) == ["running", "held", "running"]
    assert ids(timetabled, "route_chosen") == [
        "freight_1-1",
        "express_2-1",
        "freight_1-2",
    ]
    assert ids(timetabled, "request_completed") == [
        "freight_1-1",
        "express_2-1",
        "freight_1-2",
    ]


def test_release_grants_at_the_next_boundary_and_not_on_the_gesture(
    timetabled: Assembly,
) -> None:
    """Releasing sets the flag and nothing else. Granting from the gesture
    handler would make the boundary no longer the sole trigger, and would
    grant against a sensor buffer filled over part of a period — the one
    thing the time model rules out (DISPATCH.md)."""
    ticks(timetabled, 3, at={0: run_wanted("held")})
    press(timetabled, RUN_WANTED, {"run": "running"})

    assert runs(timetabled)[-1] == "running"
    assert leaves(timetabled, "route_chosen") == []

    ticks(timetabled, 1)
    assert ids(timetabled, "route_chosen") == ["freight_1-1"]


def test_a_word_that_is_no_run_state_leaves_the_run_alone(
    timetabled: Assembly,
) -> None:
    """A gesture has no id to address an answer to, so a third word is
    dropped in silence and to the trace (ADR-0034)."""
    press(timetabled, RUN_WANTED, {"run": "draining"})
    press(timetabled, RUN_WANTED, {"held": True})
    ticks(timetabled, 2)

    assert runs(timetabled) == ["running"]
    assert ids(timetabled, "route_chosen") == ["freight_1-1"]


def test_the_same_word_twice_republishes_nothing(timetabled: Assembly) -> None:
    """A state topic moves when its value moves, as every other one here
    does; a press that changes nothing is not a change."""
    press(timetabled, RUN_WANTED, {"run": "held"})
    press(timetabled, RUN_WANTED, {"run": "held"})
    ticks(timetabled, 2)

    assert runs(timetabled) == ["running", "held"]


def test_a_request_wanted_is_still_admitted_while_held() -> None:
    """Held blocks commitment, not admission: a person can queue work
    against a railroad at rest and watch it leave when they release it."""
    assembly = assemble_live(*load("crossover-yard/meet"))
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 3)

    assert ids(assembly, "request_admitted") == ["freight_1-1"]
    assert leaves(assembly, "route_chosen") == []


def test_an_outstanding_move_completes_and_releases_its_locks(
    timetabled: Assembly,
) -> None:
    """The hold is a brake, not an emergency stop. Nothing on the bus can
    retract a `cross` already sent, so the buffered sensors are applied at
    every boundary held or not — otherwise a train that arrived would hold
    the block behind it for as long as the operator stood there."""
    ticks(timetabled, 3, at={2: run_wanted("held")})

    assert leaves(timetabled, "move_granted")  # one went out before the press
    assert leaves(timetabled, "lock_released")  # and its origin came back
    # and nothing committed at the boundary the press landed before
    assert [line["boundary"] for line in leaves(timetabled, "route_chosen")] == [1]


def test_a_degenerate_request_waits_for_the_release_too() -> None:
    """A request whose train already stands in one of its own arrival blocks
    completes without moving a wheel, and still waits: "no `route_chosen`" is
    read literally, and a phase that answered one working would be a phase
    that ran."""
    assembly = assemble_live(*load("crossover-yard/meet"))
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_w.B"]})
    ticks(assembly, 3)

    assert ids(assembly, "request_admitted") == ["freight_1-1"]
    assert leaves(assembly, "route_chosen") == []

    press(assembly, RUN_WANTED, {"run": "running"})
    ticks(assembly, 1)

    assert leaves(assembly, "route_chosen")[0]["route"] == ["yard_w"]
    assert ids(assembly, "request_completed") == ["freight_1-1"]
