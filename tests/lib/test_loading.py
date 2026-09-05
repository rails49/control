"""Which railroad an app is running, and what moves it (ADR-0060).

Two followers of one shape. `Loaded` watches `tc49/layout/state/railroad`,
which is the five apps that are told; `Answering` watches
`tc49/layout/railroad_wanted`, which is the binding of the layout interface
that is running — the one app bound to a railroad, the writer of that row,
and so the one that answers the picker rather than following it.

At the bus seam and in one process, because what is under test is the rules
each applies to a payload and not the containers around them:
`tests/system/test_reload.py` is where the six of them are started and a
railroad is loaded under them for real.
"""

from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.lib.loading import POWER, RAILROAD, RAILROAD_WANTED, Answering, Loaded

WAS = "crossover-yard"
NOW = "single-track-meet"


def bused() -> InProcessBus:
    return InProcessBus(Clock())


def dark(bus: InProcessBus) -> None:
    """The rails as the layout interface states them at its own start: the
    railroad comes up dark, and a person turns it on (ADR-0051)."""
    bus.publish(POWER, {"power": "off"})


def live(bus: InProcessBus) -> None:
    bus.publish(POWER, {"power": "on"})


def picking(bus: InProcessBus, railroad: str) -> None:
    bus.publish(RAILROAD_WANTED, {"railroad": railroad})


# -- the followers ---------------------------------------------------------


def test_a_follower_takes_another_name_on_the_row() -> None:
    """The whole of what an app that is told does: a name other than the one
    it is running is a railroad being loaded under it."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)

    bus.publish(RAILROAD, {"name": NOW})
    bus.drain()

    assert (loaded.name, loaded.moved) == (NOW, True)


def test_a_follower_does_not_move_on_its_own_railroad() -> None:
    """The binding that owns the row republishes it every time it is built,
    and an app that rebuilt on that would rebuild on its neighbour's
    heartbeat."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)

    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()

    assert loaded.moved is False


# -- the answerer ----------------------------------------------------------


def test_the_gesture_is_answered_where_the_rails_are_dead() -> None:
    """Track power off is the precondition, and it is the whole of it: with
    the power off nothing moves and no turnout throws, and the person who
    turns it back on is confirming the rails match the drawing just loaded
    (ADR-0060, ADR-0051)."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (NOW, True)


def test_the_gesture_changes_nothing_while_the_rails_have_power() -> None:
    """A train already under a committed route keeps rolling whatever the
    software forgets (ADR-0037 as amended, ADR-0060), so the gesture is
    dropped and the railroad is unmoved. Nothing here commands a shutdown:
    this app never writes `off` of its own accord."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    live(bus)

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (WAS, False)


def test_a_gesture_before_the_supply_has_said_anything_is_dropped() -> None:
    """No evidence that the rails are dead is not evidence that they are: an
    app that has heard nothing waits rather than answering on a guess."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)

    picking(bus, NOW)
    bus.drain()

    assert answering.moved is False


def test_the_rails_going_dead_makes_the_next_gesture_answerable() -> None:
    """The precondition is read at the moment of answering and not once: a
    person turns the power off and picks, which is the ordinary order."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    live(bus)
    picking(bus, NOW)
    bus.drain()

    dark(bus)
    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (NOW, True)


def test_the_answerer_ignores_the_state_row_it_writes() -> None:
    """It is the row's one writer (ADR-0035). An app that followed its own
    row would take a value a page or a stray client left there as a railroad
    to load, and there would be two things deciding which railroad is
    running."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)

    bus.publish(RAILROAD, {"name": NOW})
    bus.drain()

    assert (answering.name, answering.moved) == (WAS, False)


def test_a_gesture_naming_nothing_readable_is_dropped() -> None:
    """Anything at all can arrive on a topic (SYSTEM.md, rule 4), and none of
    it takes the railroad down."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)

    for payload in ({}, {"railroad": ""}, {"railroad": 7}, {"name": NOW}):
        bus.publish(RAILROAD_WANTED, payload)
    bus.drain()

    assert (answering.name, answering.moved) == (WAS, False)


def test_a_gesture_naming_the_running_railroad_is_not_a_move() -> None:
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)

    picking(bus, WAS)
    bus.drain()

    assert answering.moved is False


def test_a_refused_railroad_is_tried_again_when_it_is_picked_again() -> None:
    """Where the follower must remember a refusal — a retained row is handed
    over afresh on every rebuild, and an app would spend its life refusing it
    — the answerer must not. A gesture is an event: nothing hands it over
    again, so the next press is a person pressing again."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)
    picking(bus, NOW)
    bus.drain()
    answering.keep(WAS)

    answering.follow(bus)
    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (NOW, True)


def test_a_refused_row_is_not_tried_again_by_a_follower() -> None:
    """The other half of the rule, on the class that needs it: the row still
    stands, and subscribing is what has the bus hand it over."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": NOW})
    bus.drain()
    loaded.keep(WAS)

    loaded.follow(bus)
    bus.drain()

    assert (loaded.name, loaded.moved) == (WAS, False)


def test_a_binding_with_no_hardware_answers_with_the_rails_live() -> None:
    """The precondition guards a person confirming that the steel matches the
    drawing just loaded, so a binding with no steel has nothing to confirm and
    no precondition (ADR-0060 as amended).

    Written the other way, a deployed simulator could never answer the picker
    at all: it is the only writer of its own supply and that supply is the
    constant `on`, a power cut being a physical act ADR-0030 keeps out of the
    simulation.
    """
    bus = bused()
    answering = Answering(WAS, precondition=None)
    answering.follow(bus)
    live(bus)

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (NOW, True)


def test_a_binding_with_hardware_still_waits_for_the_supply() -> None:
    """The exemption is the absence of a precondition, not a looser one: the
    default is unchanged, so the binding that drives steel refuses exactly as
    before."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    live(bus)

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (WAS, False)
