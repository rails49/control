"""`moving` beside the run word on `state/run` (ADR-0062, #406).

`held` does not say the railroad is still. The dispatcher writes that word
when a drain completes, and a person's HOLD writes the same word with trains
still rolling, so a reader waiting to cut track power was answered by the
wrong event and could strand a train mid-transit. The row carries a boolean
beside the three values instead: true while any train is **active** or
**crossing** (CONTEXT.md, **Moving**), which is the test the drain's
completion already makes.

It is orthogonal to the run and not a fourth value of it, and the row goes out
whenever either of the two moves — a running run whose last train arrives says
`running` again with `moving` false.

Driven at the bus, which is where a person's press arrives: the gestures in,
`state/run` and the trace out.
"""

import json
from pathlib import Path

from tc49.bench.runner import Assembly
from tests.harness import live, press, run_rows, runs, ticks

REQUEST_WANTED = "tc49/schedule/request_wanted"
RUN_WANTED = "tc49/dispatch/run_wanted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
ALLOCATION = "tc49/dispatch/state/allocation"


def under_way() -> Assembly:
    """A live railroad with freight_1 one boundary into a route it was just
    launched on: a train the dispatcher has granted a move to and no sensor
    has yet finished with."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 1)
    return assembly


def test_a_granted_move_is_moving_and_the_arrival_is_not() -> None:
    """The whole of the field on a running run: nothing is granted, so
    nothing is moving; the launch grants and it is; the train arrives and it
    is not again — with the run word standing at `running` throughout, which
    is what makes this a value of its own and not a fourth run state."""
    assembly = live("crossover-yard/meet")
    assert run_rows(assembly) == []  # nothing said until the bus is turned

    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert run_rows(assembly) == [("running", False), ("running", True)]

    ticks(assembly, 40)
    assert run_rows(assembly)[-1] == ("running", False)
    assert runs(assembly) == ["running"]


def test_a_hold_over_a_train_under_way_is_moving() -> None:
    """The failure ADR-0062 exists for: the hold is a brake and not an
    emergency stop, so the move already granted runs to its sensor. `held`
    goes out with `moving` true, and a reader that cut power on the word
    alone would strand the train the hold did not stop."""
    assembly = under_way()
    press(assembly, RUN_WANTED, {"run": "held"})

    assert run_rows(assembly)[-1] == ("held", True)
    assert assembly.dispatcher.state.crossing


def test_a_held_train_goes_on_moving_until_its_request_ends() -> None:
    """A train whose sensors have caught up with it is still **active**: it
    has a committed route it has not finished, and a hold commits nothing
    further rather than retiring what is committed. So the row does not go
    quiet at the boundary the move ended on."""
    assembly = under_way()
    press(assembly, RUN_WANTED, {"run": "held"})
    ticks(assembly, 10)

    assert not assembly.dispatcher.state.crossing
    assert assembly.dispatcher.state.active
    assert run_rows(assembly)[-1] == ("held", True)


def test_the_drains_completion_is_held_and_not_moving() -> None:
    """The two the panel has to tell apart, said in one row: the drain ends
    at `held` with `moving` false, where the hold above ends at `held` with
    `moving` true. That row is what a reader waits for before cutting
    power."""
    assembly = under_way()
    press(assembly, RUN_WANTED, {"run": "draining"})
    assert run_rows(assembly)[-1] == ("draining", True)

    ticks(assembly, 40)
    assert run_rows(assembly)[-1] == ("held", False)


def test_a_restored_crossing_hint_with_no_request_is_moving(tmp_path: Path) -> None:
    """A hint the last session left is a train the dispatcher believes is
    between two blocks, and nothing but a person clears it (#123, #154).
    There is no request behind it — the queue comes back empty — so `active`
    is empty and the hint alone is what says the railroad is not still."""
    state = tmp_path / "session.json"
    state.write_text(
        json.dumps(
            {
                ALLOCATION: {
                    "trains": {"express_2": "up_w", "freight_1": "dn_e"},
                    "crossing": {"freight_1": "crossover.dn_straight"},
                    "locks": {},
                    "requests": [],
                }
            }
        )
    )
    assembly = live("crossover-yard/meet", state=state)
    ticks(assembly, 1)

    assert not assembly.dispatcher.state.active
    assert run_rows(assembly) == [("held", True)]


def test_lifting_the_wedged_train_off_stops_the_moving(tmp_path: Path) -> None:
    """The documented way out of a drain a train holds open forever: hold,
    and take the train off the layout (ADR-0039, #294). The gesture drops the
    hint and the request together, and it is not a sweep — so the row is
    published where the placement settles, or the reader waiting to cut power
    would wait on a railroad that has nothing left on it."""
    assembly = under_way()
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, PLACEMENT_WANTED, {"train": "freight_1", "block": None})

    assert run_rows(assembly)[-1] == ("held", False)
    assert not assembly.dispatcher.state.crossing
    assert not assembly.dispatcher.state.active
