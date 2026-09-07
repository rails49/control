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

import pytest

from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.lib.loading import (
    POWER,
    RAILROAD,
    RAILROAD_WANTED,
    Answering,
    Loaded,
    taken,
)

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


def test_a_power_value_outside_the_set_is_not_news_about_the_rails() -> None:
    """Rule 4 is that anything at all can arrive on a topic, and power is a
    closed set of three. A frame naming a fourth value said nothing, so the
    rails are still dark and the gesture is still answered.

    Adopting it instead wedged the picker: the stored value was not `off`, so
    every railroad a person picked was refused until a true frame landed
    (#492)."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)
    bus.publish(POWER, {"power": "banana"})

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (NOW, True)


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


# -- the documents a moved railroad is rebuilt on --------------------------


class Reading:
    """What an app reads, as `taken` sees it: a railroad's name to that app's
    documents, and nothing else about which documents they are. It records
    what it was asked for, so that the railroad the documents came back for
    is visible."""

    def __init__(self, refuses: Exception | None = None, of: str = "") -> None:
        # Which railroad the store cannot give, and what it says about it.
        self.refuses = refuses
        self.of = of
        self.asked: list[str] = []

    def __call__(self, railroad: str) -> str:
        self.asked.append(railroad)
        if self.refuses is not None and railroad == self.of:
            raise self.refuses
        return f"the documents of {railroad}"


def moved() -> Loaded:
    """A follower whose row has just named another railroad, which is where
    an app's loop calls `taken`."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": NOW})
    bus.drain()
    return loaded


def test_the_railroad_just_named_is_read() -> None:
    """The ordinary case, which is the store having the railroad a person
    picked: what comes back is that railroad's documents, nothing is said,
    and the app stays on the name it moved to."""
    loaded = moved()
    reading = Reading()
    said: list[str] = []

    documents = taken(loaded, WAS, said.append, reading)

    assert documents == f"the documents of {NOW}"
    assert (loaded.name, said) == (NOW, [])
    assert reading.asked == [NOW]


@pytest.mark.parametrize(
    "refused",
    [
        OSError("the store is not answering"),
        ValueError("no such railroad"),
        TypeError("the drawing does not derive"),
    ],
    ids=["os", "value", "type"],
)
def test_a_railroad_the_store_cannot_give_is_said_and_not_taken(
    refused: Exception,
) -> None:
    """An app with nothing to run on is worse than one still running the
    railroad it had (ADR-0050): the refusal is said against the railroad
    still built, that one is kept, and its documents are what the app is
    rebuilt on."""
    loaded = moved()
    reading = Reading(refuses=refused, of=NOW)
    said: list[str] = []

    documents = taken(loaded, WAS, said.append, reading)

    assert said == [f"'{NOW}': {refused} — staying on '{WAS}'"]
    assert (loaded.name, loaded.moved) == (WAS, False)
    assert documents == f"the documents of {WAS}"
    assert reading.asked == [NOW, WAS]


def test_what_an_app_reads_is_the_only_thing_it_says() -> None:
    """One document or two is the whole of the difference between the four
    apps that load a railroad, and it comes back as the app wrote it — the
    scheduler and the simulator with a layout, the dispatcher and the layout
    interface with a layout and a roster."""
    loaded = moved()

    pair = taken(loaded, WAS, lambda _line: None, lambda name: (name, len(name)))

    assert pair == (NOW, len(NOW))
