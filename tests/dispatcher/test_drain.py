"""The drain: `draining` is the third value of the run, and it stops
launching rather than admitting (#294, ADR-0037).

Turning a railroad off has to be something other than an abrupt cut, because
an abrupt cut leaves no point position trustworthy and can strand a train
mid-transit. The drain is that something: the dispatcher launches nothing
more, lets what is already moving run to where it was going, and writes
`held` itself at the first moment no train is active and none is crossing.
That transition is the drain's completion, and it is what the panel watches
for before cutting power (ADR-0051).

Manual trains count by the same rule and need no mention: every train moves
on a route the dispatcher allocated, and *manual* names only who turns the
throttle (#207).

Driven at the bus, which is where a person's press arrives: `run_wanted` in,
`state/run` and the trace out.
"""

from typing import cast

from tc49.bench.runner import Assembly
from tc49.lib.bus import Payload
from tests.harness import (
    RUN_WANTED,
    build,
    events,
    leaves,
    live,
    load,
    press,
    runs,
    ticks,
)

REQUEST_WANTED = "tc49/schedule/request_wanted"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
POWER = "tc49/layout/state/power"


def ids(assembly: Assembly, leaf: str) -> list[str]:
    return [str(line["id"]) for line in leaves(assembly, leaf)]


def draining() -> Assembly:
    """The timetabled meet, drained the moment it opens: freight_1 is
    crossing on the route its launch took at time zero, and the two requests
    behind it are admitted and waiting."""
    assembly = build(*load("crossover-yard/meet"))
    press(assembly, RUN_WANTED, {"run": "draining"})
    return assembly


def test_a_drain_admits_and_never_launches() -> None:
    """The gate is on launching, not on admission: a request minted into a
    draining run is admitted like any other and no route is chosen for it.
    Admission is cheap and reversible; launching is the commitment."""
    assembly = draining()
    press(assembly, REQUEST_WANTED, {"train": "express_2", "dest": ["dn_w.A"]})
    ticks(assembly, 4)

    assert "express_2-2" in ids(assembly, "request_admitted")
    assert ids(assembly, "route_chosen") == ["freight_1-1"]


def test_a_crossing_train_is_granted_its_next_move_and_completes() -> None:
    """What the drain is for: the train under way runs to where it was
    going. It takes grant after grant while the run drains, and its request
    completes — anything else would strand it mid-transit, which is the very
    thing an abrupt cut does."""
    assembly = draining()
    ticks(assembly, 20)

    granted = leaves(assembly, "move_granted")
    assert len(granted) > 1
    assert {str(line["train"]) for line in granted} == {"freight_1"}
    assert ids(assembly, "request_completed") == ["freight_1-1"]


def test_the_drain_ends_at_held_when_nothing_is_under_way_and_not_before() -> None:
    """The dispatcher writes `held` itself, and the moment it writes it is
    the first at which no train is active and none is crossing. While
    freight_1 is still running its route the run reads `draining`."""
    assembly = draining()
    ticks(assembly, 3)
    assert runs(assembly) == ["running", "draining"]
    assert assembly.dispatcher.state.crossing

    ticks(assembly, 20)
    assert runs(assembly) == ["running", "draining", "held"]
    assert not assembly.dispatcher.state.active
    assert not assembly.dispatcher.state.crossing
    # And it is that request ending that ends the drain: the `held` frame
    # follows the completion on the trace rather than preceding it.
    order = [line["event"] for line in events(assembly.trace)]
    assert order.index("run", order.index("request_completed")) > order.index(
        "request_completed"
    )


def test_a_drain_over_a_railroad_with_nothing_under_way_is_done_at_once() -> None:
    """No train is active and none is crossing already, so the first moment
    the rule names is the press itself. The panel's OFF waits for `held`, and
    a drain that had nothing to wait for would otherwise never answer it."""
    assembly = live("crossover-yard/meet")
    press(assembly, RUN_WANTED, {"run": "draining"})

    assert runs(assembly) == ["running", "draining", "held"]


def test_a_hold_during_a_drain_reaches_held_without_waiting() -> None:
    """`held` published while a drain is in progress abandons it. The hold
    asks for less than the drain does and is honoured at once — a person who
    wants the railroad still now does not wait out a train's route."""
    assembly = draining()
    press(assembly, RUN_WANTED, {"run": "held"})

    assert runs(assembly) == ["running", "draining", "held"]
    # Abandoned, not completed: the train is still crossing, and the move
    # already sent still runs to its sensors (ADR-0037).
    assert assembly.dispatcher.state.crossing


def test_a_release_during_a_drain_resumes_launching() -> None:
    """The drain is a gate and not a one-way door: GO re-opens it, and the
    sweep the release runs launches what the drain had left waiting."""
    assembly = draining()
    press(assembly, RUN_WANTED, {"run": "running"})
    ticks(assembly, 20)

    assert runs(assembly) == ["running", "draining", "running"]
    assert set(ids(assembly, "route_chosen")) == {
        "freight_1-1",
        "express_2-1",
        "freight_1-2",
    }


def test_a_dropped_request_no_longer_holds_the_drain_open() -> None:
    """A drain a train holds open forever is escaped by ending what that
    train is doing (#237): the request goes, the train is no longer active,
    and the drain finds its first moment in the sweep that follows."""
    assembly = draining()
    # The move outstanding at the press ends, and freight_1 stands in a block
    # with its route still ahead of it.
    ticks(assembly, 1)
    assert runs(assembly) == ["running", "draining"]

    press(assembly, CANCEL_WANTED, {"train": "freight_1"})
    ticks(assembly, 4)

    assert runs(assembly) == ["running", "draining", "held"]
    # The gesture names a train and ends everything that train has, and the
    # active one waits for the move it was already making (ADR-0049): the
    # drain ends where that request does and not at the press.
    assert set(ids(assembly, "request_cancelled")) == {"freight_1-1", "freight_1-2"}


def test_a_removed_train_no_longer_holds_a_drain_open() -> None:
    """The wedged train's own case: a person holds the run, lifts the train
    off the layout — which is where a placement is honoured (ADR-0037) — and
    drains a railroad that no longer has it. Removing drops the request, so
    there is nothing left for the drain to wait on."""
    assembly = draining()
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, PLACEMENT_WANTED, {"train": "freight_1", "block": None})
    assert set(ids(assembly, "request_cancelled")) == {"freight_1-1", "freight_1-2"}

    press(assembly, RUN_WANTED, {"run": "draining"})
    assert runs(assembly) == ["running", "draining", "held", "draining", "held"]


def test_power_leaving_on_ends_a_drain_at_held() -> None:
    """`stopped` power is always honoured and is not a drain: it holds the
    run by the path it always takes, and the drain it lands in the middle of
    is abandoned like any other (ADR-0041)."""
    assembly = draining()
    ticks(assembly, 2, at={0: (POWER, cast(Payload, {"power": "stopped"}))})

    assert runs(assembly) == ["running", "draining", "held"]


def test_a_drain_is_refused_while_the_track_has_no_power() -> None:
    """A drain grants moves to trains already under way, so asking for one
    over dead rails asks for exactly what a release does and is dropped the
    same way (ADR-0041). A hold is honoured whatever the power is doing."""
    assembly = build(*load("crossover-yard/meet"))
    ticks(assembly, 2, at={0: (POWER, cast(Payload, {"power": "off"}))})
    press(assembly, RUN_WANTED, {"run": "draining"})

    assert runs(assembly) == ["running", "held"]


def test_an_unreadable_run_wanted_leaves_a_drain_where_it_was() -> None:
    """A fourth value is not a fourth state, and neither is a frame that
    states nothing: the gesture is dropped in silence and to the trace, and
    the drain goes on draining (ADR-0034)."""
    assembly = draining()
    press(assembly, RUN_WANTED, {"run": "drained"})
    press(assembly, RUN_WANTED, {"held": True})
    press(assembly, RUN_WANTED, cast(Payload, "off with it"))

    assert runs(assembly) == ["running", "draining"]
    assert assembly.dispatcher.state.run == "draining"


def test_a_draining_run_still_signals_the_train_it_is_granting() -> None:
    """A held run puts every end to stop, because while held the answer to
    "may this train leave" is no. A drain answers yes to the train already
    moving, so its end shows what the locks say — a lineside signal at stop
    over a train that has just been granted its next move would be the lie
    the other way about."""
    assembly = draining()
    ticks(assembly, 3)

    shown = cast(dict[str, str], leaves(assembly, "aspects")[-1]["aspects"])
    assert {aspect for aspect in shown.values() if aspect != "stop"}
