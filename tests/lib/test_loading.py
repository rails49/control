"""Which railroad an app is running, and what moves it (ADR-0060).

Two followers of one shape. `Loaded` watches `tc49/layout/state/railroad`,
which is the apps that are told (the scheduler, the dispatcher and the
driver); `Answering` watches `tc49/layout/railroad_wanted`, which is the
binding of the layout interface that is running — the one app bound to a
railroad, the writer of that row, and so the one that answers the gesture
rather than following the row.

Under both of them, the railroad an app is **built on**: the one it was
started on where the store has it, and otherwise whatever the bus names next,
the app standing with no railroad until then (#564).

At the bus seam and in one process, because what is under test is the rules
each applies to a payload and not the containers around them:
`tests/system/test_reload.py` is where the apps are started and a railroad
is loaded under them for real.
"""

import threading
from collections.abc import Callable, Sequence
from dataclasses import replace

import pytest

from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.lib.documents import Documents
from tc49.lib.inventory import AT
from tc49.lib.layout import Layout
from tc49.lib.loading import (
    BUILT,
    NO_RAILROAD,
    POWER,
    RAILROAD,
    RAILROAD_WANTED,
    Answering,
    Loaded,
    Running,
    dropped,
    named,
    rebuilding,
    standing,
    taken,
)
from tc49.simulator import Simulator
from tests.harness import load

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
    """An app started on a railroad knows no stamp for it, and the first row
    naming it is the build it runs: it has just read the store."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)

    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()

    assert loaded.moved is False


def test_a_follower_rebuilds_its_railroad_built_again() -> None:
    """A new stamp on the same name is that railroad built again from the
    store, as after a restore: an app that kept what it read before would
    route over a drawing the store no longer holds (#688)."""
    clock = Clock()
    bus = InProcessBus(clock)
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()

    clock.advance(1.0)
    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()

    assert (loaded.name, loaded.moved) == (WAS, True)


def test_a_follower_does_not_rebuild_on_the_build_handed_over_again() -> None:
    """Subscribing is what a rebuild does, and the broker hands the retained
    row over again with the stamp it had: the same build, not a move. An app
    that rebuilt on it would rebuild for ever."""
    clock = Clock()
    bus = InProcessBus(clock)
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()
    clock.advance(1.0)
    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()
    assert loaded.moved

    loaded.follow(bus)  # rebuilt, and subscribed afresh
    bus.drain()

    assert loaded.moved is False


def test_a_row_on_the_same_name_with_no_stamp_is_not_a_build() -> None:
    """Anything at all can arrive on a topic (rule 4), and a row with no
    readable stamp says nothing about which build it is."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()

    loaded._said(RAILROAD, {"name": WAS})  # pyright: ignore[reportPrivateUsage]

    assert loaded.moved is False


def test_a_follower_builds_nothing_on_a_railroad_named_and_not_built() -> None:
    """A row saying nothing was built names a railroad whose drawing is not a
    valid drawing: there is nothing to build, so the app keeps what it holds
    (ADR-0085, decision 4)."""
    clock = Clock()
    bus = InProcessBus(clock)
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": WAS})
    bus.drain()

    clock.advance(1.0)
    bus.publish(RAILROAD, {"name": WAS, BUILT: False})
    bus.drain()
    assert (loaded.name, loaded.moved) == (WAS, False), "a save that is invalid"

    clock.advance(1.0)
    bus.publish(RAILROAD, {"name": NOW, BUILT: False})
    bus.drain()
    assert (loaded.name, loaded.moved) == (WAS, False), "a pick that is invalid"


def test_a_follower_takes_the_build_that_arrives_once_the_drawing_is_valid() -> None:
    """The same name with a new stamp and `built: true` is the build arriving,
    as any rebuild is (#688): the drawing has been fixed and saved."""
    clock = Clock()
    bus = InProcessBus(clock)
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": WAS, BUILT: True})
    bus.drain()
    clock.advance(1.0)
    bus.publish(RAILROAD, {"name": WAS, BUILT: False})
    bus.drain()

    clock.advance(1.0)
    bus.publish(RAILROAD, {"name": WAS, BUILT: True})
    bus.drain()

    assert (loaded.name, loaded.moved) == (WAS, True)


def test_a_standing_follower_keeps_standing_on_a_railroad_not_built() -> None:
    """After a restart on a railroad whose drawing is invalid, the binding
    names it and builds nothing, and neither does an app that follows it."""
    bus = bused()
    loaded = Loaded(NO_RAILROAD)
    loaded.follow(bus)

    bus.publish(RAILROAD, {"name": WAS, BUILT: False})
    bus.drain()

    assert (loaded.name, loaded.moved) == (NO_RAILROAD, False)


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

    Adopting it instead refused every railroad a person picked until a true
    frame landed, because the stored value was not `off` (#492)."""
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
    """Anything at all can arrive on a topic (BUS.md, rule 4), and none of
    it takes the railroad down."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)

    for payload in ({}, {"railroad": ""}, {"railroad": 7}, {"name": NOW}):
        bus.publish(RAILROAD_WANTED, payload)
    bus.drain()

    assert (answering.name, answering.moved) == (WAS, False)


def test_a_gesture_naming_the_running_railroad_builds_it_again() -> None:
    """Naming a railroad means "run what the store holds": after a restore the
    store holds something other than what the app was built from (#688)."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    dark(bus)

    picking(bus, WAS)
    bus.drain()

    assert (answering.name, answering.moved) == (WAS, True)


def test_the_running_railroad_waits_for_the_supply_like_any_other() -> None:
    """The same precondition as picking another railroad: the rails and the
    drawing are never changed under a moving train (#688)."""
    bus = bused()
    answering = Answering(WAS)
    answering.follow(bus)
    live(bus)

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


def simulated(bus: InProcessBus) -> Answering:
    """The answerer as `python -m tc49.simulator` builds it, following before
    the simulator states its rows, with that binding on the same bus."""
    answering = Answering(WAS)
    answering.follow(bus)
    layout, _roster, _scenario = load("crossover-yard/meet")
    Simulator(bus, layout, Clock())
    bus.drain()
    return answering


def test_the_simulator_powered_drops_the_gesture() -> None:
    """Every binding waits for `off` before loading a railroad (ADR-0070,
    decision 5): the simulator answers ON as the layout does, and once its
    rails read `on` the gesture is dropped like the layout's."""
    bus = bused()
    answering = simulated(bus)
    bus.publish("tc49/layout/power_wanted", {"power": "on"})
    bus.drain()

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (WAS, False)


def test_the_simulator_dark_answers_the_gesture() -> None:
    """It comes up `off`, as the layout interface does, so a railroad can be
    picked on a simulated box until somebody presses ON — and after OFF."""
    bus = bused()
    answering = simulated(bus)

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (NOW, True)


class Recording(Documents):
    """A store that records `railroad` as loaded and is asked nothing else,
    noting each railroad recorded since in `journal`."""

    def __init__(self, railroad: str, journal: list[str] | None = None) -> None:
        super().__init__("http://unused")
        self._railroad = railroad
        self.journal: list[str] = [] if journal is None else journal

    def loaded(self) -> str:
        return self._railroad

    def put_loaded(self, name: str) -> None:
        self.journal.append(f"recorded {name}")
        self._railroad = name


def test_the_answerer_starts_on_the_railroad_the_store_records() -> None:
    said: list[str] = []

    loaded = Answering.recorded(Recording(NOW), WAS, said.append)

    assert loaded.name == NOW
    assert said == [f"the store records '{NOW}' as loaded"]


def test_the_answerer_starts_on_its_own_railroad_where_the_store_records_none() -> None:
    said: list[str] = []

    loaded = Answering.recorded(Recording(""), WAS, said.append)

    assert loaded.name == WAS
    assert said == []


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


HELD = f"the documents {WAS} was built on"
"""What an app holds while it runs, which is not what the store holds once a
save or a restore has written over it."""


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

    documents = taken(loaded, WAS, HELD, said.append, reading)

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

    documents = taken(loaded, WAS, HELD, said.append, reading)

    assert said == [f"'{NOW}': {refused} — staying on '{WAS}'"]
    assert (loaded.name, loaded.moved) == (WAS, False)
    assert documents == HELD
    assert reading.asked == [NOW]


def test_a_saved_drawing_that_does_not_derive_keeps_the_railroad_running() -> None:
    """A save names the loaded railroad again (ADR-0071), and the store then
    holds a drawing that does not derive under the name still built. The
    documents the app already has are what it keeps: reading that name again
    is refused too, and an app that let it out exited, came back standing
    and named no railroad, and the page closed the drawing that needed the
    fix."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)
    bus.publish(RAILROAD, {"name": WAS, AT: 1.0})
    bus.publish(RAILROAD, {"name": WAS, AT: 2.0})
    bus.drain()
    reading = Reading(refuses=ValueError("pin 'yard_e.B' takes one wire"), of=WAS)
    said: list[str] = []

    documents = taken(loaded, WAS, HELD, said.append, reading)

    assert documents == HELD
    assert (loaded.name, loaded.moved) == (WAS, False)
    assert reading.asked == [WAS]


def test_what_an_app_reads_is_the_only_thing_it_says() -> None:
    """One document or two is the whole of the difference between the four
    apps that load a railroad, and it comes back as the app wrote it — the
    scheduler and the simulator with a layout, the dispatcher and the layout
    interface with a layout and a roster."""
    loaded = moved()

    pair = taken(
        loaded, WAS, (WAS, 0), lambda _line: None, lambda name: (name, len(name))
    )

    assert pair == (NOW, len(NOW))


# -- the documents an app comes up on --------------------------------------


def standing_on(
    loaded: Loaded, reading: Reading, said: list[str], bus: InProcessBus
) -> str | None:
    """`standing` as an app's `serve` calls it, on a bus a test has already
    published to: a period of nothing, because the retained row is in the
    queue before the wait begins and the drain in that loop is what hands it
    over."""
    return standing(bus, loaded, threading.Event(), said.append, reading, 0.0)


def test_the_railroad_a_box_named_is_what_the_app_comes_up_on() -> None:
    """The ordinary case: the store has the railroad the process was started
    on, and nothing waits for anything."""
    said: list[str] = []
    reading = Reading()

    documents = standing_on(Loaded(WAS), reading, said, bused())

    assert documents == f"the documents of {WAS}"
    assert (reading.asked, said) == ([WAS], [])


def test_an_app_that_was_named_no_railroad_waits_for_one() -> None:
    """Every app starts holding `NO_RAILROAD` — nothing on a command line
    names a railroad (ADR-0072, decision 5, #564) — so there is nothing to
    read and nothing to fail on: the app stands, and the row naming a
    railroad is what builds it."""
    bus = bused()
    bus.publish(RAILROAD, {"name": NOW})
    said: list[str] = []
    reading = Reading()
    loaded = Loaded(NO_RAILROAD)

    documents = standing_on(loaded, reading, said, bus)

    assert documents == f"the documents of {NOW}"
    assert reading.asked == [NOW]
    assert said == ["standing: no railroad to come up on, waiting for one to be named"]


def test_a_railroad_the_store_does_not_have_leaves_the_app_standing() -> None:
    """The defect (#564): four apps exited where the store had no such
    railroad, which on a box whose store is empty — an ordinary state, by
    decision — is a restart loop. It says what the store said and stands
    instead, and the railroad named next is what it comes up on."""
    bus = bused()
    bus.publish(RAILROAD, {"name": NOW})
    refused = FileNotFoundError(f"no drawing '{WAS}'")
    reading = Reading(refuses=refused, of=WAS)
    said: list[str] = []
    loaded = Loaded(WAS)

    documents = standing_on(loaded, reading, said, bus)

    assert said[0] == f"'{WAS}': {refused}"
    assert documents == f"the documents of {NOW}"
    assert (loaded.name, reading.asked) == (NOW, [WAS, NOW])


def test_a_stop_ends_the_wait_with_no_railroad() -> None:
    """A signal is what ends a container, and one arriving while an app is
    standing ends it there: nothing comes back, and the caller publishes
    nothing (`lib/startup.py`, `connected`)."""
    stopped = threading.Event()
    stopped.set()
    said: list[str] = []

    assert standing(bused(), Loaded(WAS), stopped, said.append, Reading(), 0.0) is None
    assert said == []


def test_an_app_that_is_standing_answers_railroad_wanted_with_the_rails_live() -> None:
    """The precondition binds a railroad that is loaded. An app standing has
    none: no turnout can throw under it and there is no drawing for the rails
    to disagree with, so the first railroad a box loads is answerable —
    otherwise a redeploy is the only way to name one, which is what ADR-0060
    says choosing a railroad is not."""
    bus = bused()
    answering = Answering(NO_RAILROAD)
    answering.follow(bus)
    live(bus)

    picking(bus, NOW)
    bus.drain()

    assert (answering.name, answering.moved) == (NOW, True)


def test_the_answerer_standing_says_so_on_the_row() -> None:
    """The binding of the layout interface writes the row, and while it
    stands the row names no railroad: a page can tell "no railroad loaded"
    from "layout not running" (#727)."""
    bus = bused()

    def said(line: str) -> None:
        # A person picks while it stands, which is what ends the wait.
        picking(bus, NOW)

    standing(bus, Answering(NO_RAILROAD), threading.Event(), said, Reading(), 0.0)

    assert bus.last_values[RAILROAD]["name"] == NO_RAILROAD


def test_a_follower_standing_publishes_nothing() -> None:
    """Only the binding owns the row (ADR-0035): a follower standing on it
    leaves it as the binding left it."""
    bus = bused()
    bus.publish(RAILROAD, {"name": NOW})
    bus.drain()

    standing_on(Loaded(NO_RAILROAD), Reading(), [], bus)

    assert bus.last_values[RAILROAD]["name"] == NOW


def test_a_follower_built_on_a_railroad_keeps_it_when_the_row_names_none() -> None:
    """The row names no railroad while the binding stands (#727), and an app
    built on one keeps running it: there is nothing to be rebuilt on."""
    bus = bused()
    loaded = Loaded(WAS)
    loaded.follow(bus)

    bus.publish(RAILROAD, {"name": NO_RAILROAD})
    bus.drain()

    assert (loaded.name, loaded.moved) == (WAS, False)


def test_a_follower_standing_keeps_standing_when_the_row_names_none() -> None:
    """The other half: an app with no railroad is not handed one by a row
    that names none."""
    bus = bused()
    loaded = Loaded(NO_RAILROAD)
    loaded.follow(bus)

    bus.publish(RAILROAD, {"name": NO_RAILROAD})
    bus.drain()

    assert (loaded.name, loaded.moved) == (NO_RAILROAD, False)


def test_a_railroad_is_named_in_a_log_line_or_said_to_be_absent() -> None:
    """One spelling of the sentence an app prints when it is up, the driver
    being the one that prints it with no railroad: it reads no documents, so
    it never stands."""
    assert (named(WAS), named(NO_RAILROAD)) == (f"'{WAS}'", "no railroad")


# -- what a rebuild drops ----------------------------------------------------


def test_a_rebuild_drops_its_rows_but_the_ones_it_keeps() -> None:
    """A rebuild under the same name keeps what a person told the apps about
    the steel (ADR-0071): the topic handed as `keep` stays on the broker, and
    every other row under the app's filters goes."""
    bus = bused()
    bus.publish("tc49/dispatch/state/allocation", {"trains": {"t": "b"}})
    bus.publish("tc49/dispatch/state/moving", {"moving": False})
    bus.publish("tc49/schedule/state/facing", {"facing": {}})

    gone = dropped(
        bus,
        ("tc49/dispatch/state/#",),
        threading.Event(),
        0.0,
        keep=("tc49/dispatch/state/allocation",),
    )

    assert gone == ["tc49/dispatch/state/moving"]
    assert set(bus.last_values) == {
        "tc49/dispatch/state/allocation",
        "tc49/schedule/state/facing",
    }


# -- the rebuild loop the two layout bindings run --------------------------


GONE = "nowhere"
"""A name the store lists no railroad under."""


class Scripted(threading.Event):
    """A stop whose every wait runs the next step of a script, and which is
    set once the script is done: the loop and the person at the page in one
    thread, a step being what that person does between two turns."""

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[Callable[[], None]] = []

    def wait(self, timeout: float | None = None) -> bool:
        if self.steps:
            self.steps.pop(0)()
        else:
            self.set()
        return self.is_set()


def idle() -> None:
    """A turn in which nobody does anything: what `dropped` spends its wait
    for the retained rows on, and what `standing` drains in."""


class Run:
    """A binding built on a railroad: it drains between two waits until it is
    told to stop, with a position a step can put trains in."""

    def __init__(self, bus: InProcessBus, stop: Scripted) -> None:
        self.position: dict[str, str] = {}
        self._bus = bus
        self._stop = stop

    def run(self, until: Callable[[], bool]) -> None:
        while not until():
            self._stop.wait(0.0)
            self._bus.drain()


class Binding:
    """A layout binding reading the fixture drawings, as `rebuilding` sees
    one. Each build publishes the opening rows a constructor does — the
    railroad, `built` on it, and the power `off` — and is noted, with what it
    was handed."""

    owned: Sequence[str] = (RAILROAD, POWER)

    def __init__(self, bus: InProcessBus, stop: Scripted, journal: list[str]) -> None:
        layout, _roster, _scenario = load("crossover-yard/meet")
        self.drawings = {WAS: layout, NOW: replace(layout, name=NOW)}
        self.broken: set[str] = set()
        self.builds: list[tuple[Layout, dict[str, str], bool]] = []
        self.runs: list[Run] = []
        self.during_build: Callable[[], None] = lambda: None
        self._bus = bus
        self._stop = stop
        self._journal = journal

    def read(self, railroad: str) -> Layout:
        if railroad in self.broken:
            raise ValueError("pin 'yard_e.B' takes one wire")
        if railroad not in self.drawings:
            raise FileNotFoundError(f"no railroad '{railroad}'")
        return self.drawings[railroad]

    def nothing(self, railroad: str) -> Layout:
        return Layout(railroad, {}, {}, frozenset(), {})

    def layout(self, read: Layout) -> Layout:
        return read

    def build(self, read: Layout, position: dict[str, str], built: bool) -> Running:
        self._journal.append(f"built {read.name}")
        self.builds.append((read, position, built))
        self._bus.publish(RAILROAD, {"name": read.name, BUILT: built})
        self._bus.publish(POWER, {"power": "off"})
        self.during_build()
        run = Run(self._bus, self._stop)
        self.runs.append(run)
        return run


class Rebuilding:
    """`rebuilding` on the in-process bus, the store recording `recorded`:
    started by `go` once a test has written the script on `stop`."""

    def __init__(self, recorded: str) -> None:
        self.bus = bused()
        self.stop = Scripted()
        self.journal: list[str] = []
        self.documents = Recording(recorded, self.journal)
        self.binding = Binding(self.bus, self.stop, self.journal)
        self.said: list[str] = []

    def go(self) -> None:
        rebuilding(
            self.bus,
            self.documents,
            NO_RAILROAD,
            self.stop,
            self.binding,
            self.said.append,
            0.0,
            0.0,
        )

    def built(self) -> list[str]:
        return [read.name for read, _position, _built in self.binding.builds]

    def row(self) -> dict[str, object]:
        return {
            key: value
            for key, value in self.bus.last_values[RAILROAD].items()
            if key != AT
        }


def test_it_starts_on_the_railroad_the_store_records() -> None:
    """A box comes back on the railroad its rails were built to (ADR-0072,
    decision 5), and says so."""
    rebuilt = Rebuilding(WAS)

    rebuilt.go()

    assert rebuilt.built() == [WAS]
    assert f"up on '{WAS}'" in rebuilt.said


def test_it_records_each_railroad_it_is_built_on_before_the_build() -> None:
    """The record is written on the way up and on each answered pick, before
    the build, so the next start finds the one loaded last."""
    rebuilt = Rebuilding(WAS)
    rebuilt.stop.steps = [lambda: picking(rebuilt.bus, NOW), idle]

    rebuilt.go()

    assert rebuilt.journal == [
        f"recorded {WAS}",
        f"built {WAS}",
        f"recorded {NOW}",
        f"built {NOW}",
    ]
    assert f"loading '{NOW}': 2 rows of '{WAS}' cleared" in rebuilt.said


def test_a_recorded_railroad_the_store_does_not_have_leaves_it_standing() -> None:
    """The record is a starting point and not a binding: one the store
    cannot give leaves the binding standing, naming no railroad on the row
    (#727), and the next pick is what builds it."""
    rebuilt = Rebuilding(GONE)
    rows: list[dict[str, object]] = []

    def pick() -> None:
        rows.append(rebuilt.row())
        picking(rebuilt.bus, NOW)

    rebuilt.stop.steps = [pick, idle]

    rebuilt.go()

    assert rows == [{"name": NO_RAILROAD}]
    assert rebuilt.built() == [NOW]


def test_a_rebuild_under_the_same_name_keeps_the_trains_whose_blocks_remain() -> None:
    """With track power off a saved edit changes the drawing and not the
    track, so a train stands where it stood (ADR-0071). The edit here drops
    `yard_e`: the train standing in it has no block left to stand in, and the
    one in `yard_w` is kept."""
    rebuilt = Rebuilding(WAS)
    binding = rebuilt.binding

    def edit() -> None:
        binding.runs[-1].position = {"freight_1": "yard_w", "express_2": "yard_e"}
        blocks = dict(binding.drawings[WAS].blocks)
        del blocks["yard_e"]
        binding.drawings[WAS] = replace(binding.drawings[WAS], blocks=blocks)
        picking(rebuilt.bus, WAS)

    rebuilt.stop.steps = [edit, idle]

    rebuilt.go()

    assert rebuilt.built() == [WAS, WAS]
    assert binding.builds[1][1] == {"freight_1": "yard_w"}


def test_a_rebuild_under_another_name_carries_no_train() -> None:
    """A block's name in one railroad says nothing about the steel of
    another."""
    rebuilt = Rebuilding(WAS)
    binding = rebuilt.binding

    def pick() -> None:
        binding.runs[-1].position = {"freight_1": "yard_w"}
        picking(rebuilt.bus, NOW)

    rebuilt.stop.steps = [pick, idle]

    rebuilt.go()

    assert binding.builds[1][1] == {}


def test_a_pick_whose_drawing_is_not_valid_is_named_and_the_build_runs_on() -> None:
    """A railroad picked whose drawing is not a valid drawing stays named:
    the store records it and the row says nothing was built. The build it
    runs goes on, and none of its rows go (ADR-0085, decision 4)."""
    rebuilt = Rebuilding(WAS)
    rebuilt.binding.broken = {NOW}
    rebuilt.stop.steps = [lambda: picking(rebuilt.bus, NOW)]

    rebuilt.go()

    assert rebuilt.journal == [f"recorded {WAS}", f"built {WAS}", f"recorded {NOW}"]
    assert rebuilt.row() == {"name": NOW, BUILT: False}
    assert POWER in rebuilt.bus.last_values, "its rows were cleared"
    assert not any(line.startswith("loading") for line in rebuilt.said)


def test_a_restart_on_a_drawing_that_is_not_valid_builds_on_nothing() -> None:
    """After a restart the record names a railroad whose drawing is not a
    valid drawing: the binding is built on `nothing` under its name, and says
    `built: false`, rather than standing on none (#885)."""
    rebuilt = Rebuilding(NOW)
    rebuilt.binding.broken = {NOW}

    rebuilt.go()

    [(read, _position, built)] = rebuilt.binding.builds
    assert (read, built) == (rebuilt.binding.nothing(NOW), False)
    assert rebuilt.row() == {"name": NOW, BUILT: False}


def test_a_pick_made_during_the_build_is_heard() -> None:
    """The gesture is followed before the build: an event is not retained,
    so a press landing while the app states its opening rows would otherwise
    be gone (ADR-0059, decision 5). The broker hands it over as it comes."""
    rebuilt = Rebuilding(WAS)

    def press() -> None:
        rebuilt.binding.during_build = lambda: None
        picking(rebuilt.bus, NOW)
        rebuilt.bus.drain()

    rebuilt.binding.during_build = press
    rebuilt.stop.steps = [idle]

    rebuilt.go()

    assert rebuilt.built() == [WAS, NOW]
