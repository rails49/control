"""The layout says whether a train may move, and the run holds when it may
not (ADR-0041, #159).

Track power is an observation before it is anything else, and the dispatcher
branches on one thing: whether it is `on`. Anything else holds the run, so
nothing more is committed and no signalled end goes on showing `clear` over
track with no volts in it. Power returning releases nothing — the operator
presses GO — and a GO pressed while the rails are dead is dropped, releasing
into them being how the next train is stranded like the first.

Driven at the bus, which is where both arrive: `tc49/layout/state/power` from
the layout binding, `tc49/ui/run_wanted` from a page.

The cut itself is driven with the boundary published by hand and the
simulator left standing: a layout binding keeps its beat while the supply is
off, and the steel does not move. That is the whole failure — the crosses
already sent are never executed, and no sensor ever answers them.
"""

import pytest

from tc49.bench.runner import Assembly, assemble
from tc49.lib.bus import Payload
from tests.harness import events, load, press, ticks

BOUNDARY = "tc49/layout/boundary"
POWER = "tc49/layout/state/power"
RUN_WANTED = "tc49/ui/run_wanted"


@pytest.fixture
def timetabled() -> Assembly:
    """`crossover-yard/meet` with its timetable on, as the hold's tests use
    it: two workings minted at boundary 0 and freight_1's return at 12."""
    return assemble(*load("crossover-yard/meet"))


def power(word: str) -> tuple[str, Payload]:
    """The layout reporting its supply, as `ticks` plans an event."""
    return (POWER, {"power": word})


def run_wanted(word: str) -> tuple[str, Payload]:
    """A press of the run's one button."""
    return (RUN_WANTED, {"run": word})


def leaves(assembly: Assembly, leaf: str) -> list[Payload]:
    return events(assembly.trace, leaf)


def runs(assembly: Assembly) -> list[str]:
    return [str(line["run"]) for line in leaves(assembly, "run")]


def dead(assembly: Assembly, first: int, last: int) -> None:
    """The boundaries `first` to `last` with the steel standing still: the
    beat goes on and the buffered crosses are never executed, so no sensor
    answers them. The count carries on from wherever the ticks left it — the
    timetable mints against it, and a beat that went backwards would be a
    railroad no binding publishes."""
    for now in range(first, last + 1):
        assembly.bus.publish(BOUNDARY, {"boundary": now})
        assembly.bus.drain()


def test_power_leaving_on_holds_a_running_run() -> None:
    """Either word: the dispatcher branches on "not `on`" and nothing else."""
    for word in ("off", "stopped"):
        assembly = assemble(*load("crossover-yard/meet"))
        ticks(assembly, 3, at={2: power(word)})
        assert runs(assembly) == ["running", "held"], word
        # And no end goes on showing `clear` over track with no volts in it,
        # which is the lie the hold refuses to tell (ADR-0037).
        shown = leaves(assembly, "aspects")[-1]["aspects"]
        assert set(shown.values()) == {"stop"}, word


def test_the_same_word_twice_republishes_nothing(timetabled: Assembly) -> None:
    """A binding that restates its supply on a timer says nothing new, and an
    already-held run is not held again."""
    ticks(timetabled, 5, at={1: power("off"), 2: power("off"), 3: power("off")})
    assert runs(timetabled) == ["running", "held"]


def test_power_holds_a_run_that_is_already_held(timetabled: Assembly) -> None:
    """Nothing moves: the person held it, and the layout agrees."""
    ticks(timetabled, 5, at={1: run_wanted("held"), 3: power("off")})
    assert runs(timetabled) == ["running", "held"]


def test_a_stranded_train_keeps_its_locks_and_its_crossing_entry(
    timetabled: Assembly,
) -> None:
    """The failure this issue exists for, made honest rather than fixed.

    A move granted one boundary before the cut is a train between two blocks
    with no sensor coming. Its locks and its `crossing` entry stand — nothing
    on the bus retracts a `cross` already sent, and the dispatcher must not
    guess where the train ended up — so it is drawn on its connection and
    cannot be freed short of a restart (Not this issue). What the hold buys
    is that no *other* train is granted anything over the top of it.

    Admission goes on answering, as the hold's own rule has it (ADR-0037),
    and what it answers says how far the strandedness reaches: the return
    working the timetable mints at boundary 12 departs from a block its train
    never reached, so it is refused `wrong_origin` rather than queued.
    """
    ticks(timetabled, 2)  # boundary 1: the grants go out, the crosses buffer
    state = timetabled.dispatcher.state
    crossing = dict(state.crossing)
    locks = dict(state.locks)
    granted = len(leaves(timetabled, "move_granted"))
    routed = len(leaves(timetabled, "route_chosen"))
    assert crossing  # a train is between two blocks

    press(timetabled, POWER, {"power": "off"})
    dead(timetabled, 2, 20)

    assert state.crossing == crossing
    assert state.locks == locks
    assert len(leaves(timetabled, "move_granted")) == granted
    assert len(leaves(timetabled, "route_chosen")) == routed
    assert leaves(timetabled, "lock_released") == []
    assert [line["reason"] for line in leaves(timetabled, "request_rejected")] == [
        "wrong_origin"
    ]


def test_power_returning_grants_nothing_until_a_go(timetabled: Assembly) -> None:
    """The bar the hold exists for: an explicit GO before anything moves,
    whatever the rails did in the meantime."""
    ticks(timetabled, 6, at={1: power("off"), 3: power("on")})
    assert runs(timetabled) == ["running", "held"]
    granted = len(leaves(timetabled, "move_granted"))

    ticks(timetabled, 4, at={0: run_wanted("running")})
    assert runs(timetabled) == ["running", "held", "running"]
    assert len(leaves(timetabled, "move_granted")) > granted


def test_a_go_is_dropped_while_the_rails_are_dead(timetabled: Assembly) -> None:
    """In silence and to the trace, as every refused gesture is (ADR-0034):
    nothing is published, and the press is on the trace where it landed."""
    ticks(timetabled, 4, at={1: power("off"), 2: run_wanted("running")})

    assert runs(timetabled) == ["running", "held"]
    assert len(leaves(timetabled, "run_wanted")) == 1


def test_a_go_is_honoured_once_the_power_is_back(timetabled: Assembly) -> None:
    """The same press, after the same supply returned: the word is the run's
    answer to the rails and not to how often it was asked."""
    ticks(
        timetabled,
        6,
        at={
            1: power("off"),
            2: run_wanted("running"),
            3: power("on"),
            4: run_wanted("running"),
        },
    )
    assert runs(timetabled) == ["running", "held", "running"]


def test_the_run_is_never_running_while_the_rails_are_dead(
    timetabled: Assembly,
) -> None:
    """The refusal is aimed at the release alone.

    A hold asks for less than the railroad is already doing, so there is no
    state of the rails it can be refused in — and with the power off the run
    is already where it asks for, which is exactly why the two presses cannot
    be told apart at the bus. What can be told apart is the release, dropped
    where the hold is not, and the invariant it buys: the run is held for as
    long as the supply is anything but `on`.
    """
    ticks(timetabled, 6, at={1: power("off"), 3: run_wanted("running")})
    assert runs(timetabled) == ["running", "held"]

    press(timetabled, RUN_WANTED, {"run": "held"})
    assert timetabled.dispatcher.state.run == "held"
    assert runs(timetabled) == ["running", "held"]
