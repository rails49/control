"""One train that cannot finish stops only itself (#1150, SAFETY.md).

The grants are asked of `Incremental` directly, on hand-built states: the
blocks are named for the part they play, the railroad under them has no say in
a grant that locks no transit, and the deadlock of the third case cannot be
reached by grants at all. Only a person placing the trains gets there.
"""

from collections.abc import Iterable, Mapping
from itertools import pairwise

from tc49.dispatcher import Incremental
from tc49.dispatcher.dispatch import Active, Request, State
from tc49.dispatcher.locking import Move, Refused, safety_view
from tc49.dispatcher.routing import Route
from tc49.dispatcher.safety import safe
from tc49.lib.inventory import Refusal
from tests.harness import load

STUCK = ("X", "Y", "STILL", "Z")
"""T's route: its next block is free, and STILL further on reads occupied with
nobody in it (ADR-0077)."""

FREE = ("M", "N", "O")
"""A route on track nobody else wants."""


def railroad(
    routes: Mapping[str, tuple[str, ...]],
    holding: Mapping[str, Iterable[str]] | None = None,
    reading: Iterable[str] = (),
) -> State:
    """Each train active at the start of its route and holding the block it
    stands in, plus what `holding` says it holds ahead."""
    layout, _roster, _ = load("crossover-yard/meet")
    locks = {blocks[0]: train for train, blocks in routes.items()}
    for train, blocks in (holding or {}).items():
        locks.update({block: train for block in blocks})
    return State(
        layout,
        {train: 500 for train in routes},
        locks,
        {train: blocks[0] for train, blocks in routes.items()},
        {
            train: Active(
                Request(f"{train}-1", train, f"{blocks[0]}.B", (f"{blocks[-1]}.A",), 0),
                Route(blocks, tuple(f"c.{a}_{b}" for a, b in pairwise(blocks))),
                0,
                None,
            )
            for train, blocks in routes.items()
        },
        reported={block: True for block in reading},
    )


def asks(train: str, state: State) -> Move | Refused:
    return Incremental(state.layout, 2).grant(train, state)


def refused_unsafe(answer: Move | Refused, resource: str, holder: str) -> bool:
    return answer == Refused(Refusal.UNSAFE, [{"resource": resource, "holder": holder}])


def test_a_train_on_free_track_runs_past_one_that_cannot_finish() -> None:
    state = railroad({"T": STUCK, "U": FREE}, reading=["STILL"])
    assert isinstance(asks("U", state), Move)
    assert refused_unsafe(asks("T", state), "STILL", "")


def test_a_train_needing_what_a_stuck_train_holds_waits_and_the_rest_run() -> None:
    state = railroad(
        {"T": STUCK, "U": ("P", "Q", "Y", "R"), "V": FREE},
        holding={"T": ["Y"]},
        reading=["STILL"],
    )
    assert refused_unsafe(asks("U", state), "Y", "T")
    assert isinstance(asks("V", state), Move)
    assert refused_unsafe(asks("T", state), "STILL", "")


def test_a_train_needing_the_block_a_stuck_train_stands_in_waits() -> None:
    state = railroad(
        {"T": STUCK, "U": ("P", "Q", "X", "R"), "V": FREE}, reading=["STILL"]
    )
    assert refused_unsafe(asks("U", state), "X", "T")
    assert isinstance(asks("V", state), Move)


def test_two_trains_placed_in_a_deadlock_leave_the_third_running() -> None:
    state = railroad({"T": ("A", "C", "B", "D"), "U": ("B", "E", "A", "F"), "V": FREE})
    assert refused_unsafe(asks("T", state), "B", "U")
    assert refused_unsafe(asks("U", state), "A", "T")
    assert isinstance(asks("V", state), Move)


def test_with_no_failure_a_grant_that_would_deadlock_is_still_refused() -> None:
    """Either can finish first as they stand, but T stepping into M leaves
    each needing where the other stands. U going first is fine."""
    state = railroad({"T": ("A", "M", "Q", "Z"), "U": ("Q", "M", "R")})
    assert safe(*safety_view(state))
    assert refused_unsafe(asks("T", state), "Q", "U")
    assert isinstance(asks("U", state), Move)


def test_a_train_outside_the_set_leaves_the_view_and_its_blocks_are_idle() -> None:
    state = railroad({"T": STUCK, "U": FREE}, holding={"T": ["Y"]}, reading=["STILL"])
    cur, rem, idle, held = safety_view(state)
    assert cur == {"U": "M"}
    assert rem == {"U": ["N", "O"]}
    assert held == {"U": []}
    assert sorted(idle) == ["STILL", "X", "Y"]


def test_the_train_asking_is_left_for_the_caller_to_supply() -> None:
    """The set is judged with T in it, so asking for T does not change who
    leaves. T's own blocks are not idle: it is the train being moved."""
    state = railroad({"T": STUCK, "U": FREE}, reading=["STILL"])
    cur, _rem, idle, _held = safety_view(state, skip="T")
    assert cur == {"U": "M"}
    assert idle == ["STILL"]


def test_a_train_inside_the_set_is_not_given_up_for_the_one_asking() -> None:
    """T and U both end on D, and only one can. The tie goes to T, so U asks
    against T still running and is refused, naming T."""
    state = railroad({"T": ("A", "C", "D"), "U": ("B", "E", "D")})
    assert isinstance(asks("T", state), Move)
    assert refused_unsafe(asks("U", state), "D", "T")
