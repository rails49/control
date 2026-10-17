"""The two bindings of the layout interface, held to one contract (#753).

`layout` drives steel and `simulator` stands in for it, and a client on the
bus is not to tell which is running (ADR-0030, ADR-0070). Every case here runs
against both, and reads what both expose: where each train stands
(`position`), and what each says on `state/railroad` and `state/power`. What
only one binding does — the layout's fold, align hold and traction writes, the
simulator's sensor timing — stays in that binding's own suite.

Both run on the bench railroad `tests/layout/railroad.py` draws. The layout is
given a station that reports the supply it is told to have, live under `on`
and under a stop and dead under `off`, so a press reaches `state/power` on
both the way it would on a railroad. The bus stamps nothing, so a case can
hand a run row the stamp it wants (#240).
"""

from collections.abc import Callable
from typing import Protocol

import pytest

from tc49.layout import LayoutInterface
from tc49.lib.bus import Payload
from tc49.lib.clock import Clock
from tc49.simulator import Simulator
from tests.layout.railroad import (
    DEVICE_TRACK,
    MOVE,
    POWER,
    POWER_WANTED,
    RAILROAD,
    REMOVED,
    RUN,
    WANTED_TRACK,
    Unstamped,
    align,
    move,
    railroad,
    stand,
    stock,
)


class Binding(Protocol):
    bus: Unstamped

    @property
    def position(self) -> dict[str, str]: ...

    def settle(self) -> None: ...


class OnSteel:
    """The layout binding, and a station answering for its supply."""

    def __init__(self, position: dict[str, str] | None = None) -> None:
        clock = Clock()
        self.bus = Unstamped(clock)
        self.bus.subscribe(WANTED_TRACK, self._station)
        self._app = LayoutInterface(
            self.bus, railroad(), stock(), clock, position=position
        )
        self.bus.drain()

    def _station(self, topic: str, payload: Payload) -> None:
        live = "off" if payload.get("power") == "off" else "on"
        self.bus.publish(DEVICE_TRACK, {"power": live})

    @property
    def position(self) -> dict[str, str]:
        return self._app.position

    def settle(self) -> None:
        """A move this binding acts on, it acts on at once."""


class Simulated:
    """The simulator binding, run to quiescence after each command."""

    def __init__(self, position: dict[str, str] | None = None) -> None:
        clock = Clock()
        self.bus = Unstamped(clock)
        self._app = Simulator(self.bus, railroad(), clock, position)
        self.bus.drain()

    @property
    def position(self) -> dict[str, str]:
        return self._app.position

    def settle(self) -> None:
        """The head reaching the far detector is when the train stands
        there, so the scheduled readings are fired."""
        self._app.run()


Build = Callable[..., Binding]


@pytest.fixture(params=[OnSteel, Simulated], ids=["layout", "simulator"])
def build(request: pytest.FixtureRequest) -> Build:
    return request.param


def press(binding: Binding, word: str) -> None:
    binding.bus.publish(POWER_WANTED, {"power": word})
    binding.bus.drain()


def power(binding: Binding) -> str:
    return str(binding.bus.last_values[POWER]["power"])


def runs(binding: Binding, row: Payload) -> None:
    binding.bus.publish(RUN, row)
    binding.bus.drain()


def crosses(binding: Binding, train: str, transit: str, into: str) -> None:
    """The dispatcher's `align` and the driver's `move`, as they are sent."""
    align(binding.bus, "crossover", transit)
    move(binding.bus, train, "crossover", transit, into)
    binding.settle()


def live(build: Build) -> Binding:
    """A binding with the power on and freight_1 standing in up_w."""
    binding = build()
    press(binding, "on")
    stand(binding.bus, "freight_1", "up_w")
    return binding


# -- what it says as it comes up ---------------------------------------------


def test_it_comes_up_naming_its_railroad_with_the_power_off(build: Build) -> None:
    binding = build()
    assert binding.bus.last_values[RAILROAD]["name"] == "bench"
    assert power(binding) == "off"


# -- the near-end check and the rails ----------------------------------------


def test_a_train_crosses_from_where_it_was_placed(build: Build) -> None:
    binding = live(build)
    crosses(binding, "freight_1", "to_dn", "dn_e")
    assert binding.position == {"freight_1": "dn_e"}


@pytest.mark.parametrize("words", [[], ["on", "off"], ["on", "stopped"]])
def test_no_move_while_the_power_is_not_on(build: Build, words: list[str]) -> None:
    binding = build()
    for word in words:
        press(binding, word)
    stand(binding.bus, "freight_1", "up_w")
    crosses(binding, "freight_1", "to_dn", "dn_e")
    assert binding.position == {"freight_1": "up_w"}


def test_a_move_redelivered_after_arrival_changes_nothing(build: Build) -> None:
    binding = live(build)
    crosses(binding, "freight_1", "to_dn", "dn_e")
    crosses(binding, "freight_1", "to_dn", "dn_e")
    assert binding.position == {"freight_1": "dn_e"}


def test_a_move_overtaken_by_a_hand_changes_nothing(build: Build) -> None:
    binding = live(build)
    stand(binding.bus, "freight_1", "up_e")
    crosses(binding, "freight_1", "to_dn", "dn_e")
    assert binding.position == {"freight_1": "up_e"}


def test_a_train_taken_off_the_layout_is_moved_nowhere(build: Build) -> None:
    binding = live(build)
    binding.bus.publish(REMOVED, {"train": "freight_1"})
    binding.bus.drain()
    crosses(binding, "freight_1", "to_dn", "dn_e")
    assert binding.position == {}


@pytest.mark.parametrize(
    ("transit", "into"),
    [("nowhere", "dn_e"), ("straight", "dn_e")],
    ids=["no-such-transit", "transit-misses-block"],
)
def test_a_move_over_track_that_is_not_there_changes_nothing(
    build: Build, transit: str, into: str
) -> None:
    binding = live(build)
    crosses(binding, "freight_1", transit, into)
    assert binding.position == {"freight_1": "up_w"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"train": "freight_1"},
        {"train": 1, "connection": "crossover", "transit": "to_dn", "into": "dn_e"},
    ],
)
def test_a_move_that_cannot_be_read_changes_nothing(
    build: Build, payload: Payload
) -> None:
    binding = live(build)
    align(binding.bus, "crossover", "to_dn")
    binding.bus.publish(MOVE, payload)
    binding.bus.drain()
    binding.settle()
    assert binding.position == {"freight_1": "up_w"}


# -- where the trains stand as it comes up -----------------------------------


def test_it_comes_up_with_the_trains_it_is_given(build: Build) -> None:
    """What a rebuild under the same name hands the next build (ADR-0071)."""
    binding = build({"freight_1": "up_w"})
    binding.position["freight_1"] = "up_e"
    press(binding, "on")
    crosses(binding, "freight_1", "to_dn", "dn_e")
    assert binding.position == {"freight_1": "dn_e"}


# -- power -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("row", "after"),
    [
        (None, "off"),
        ({"run": "held", "moving": False}, "off"),
        ({"run": "held"}, "off"),
        ({"run": "held", "moving": True}, "on"),
        ({"run": "running", "moving": False}, "on"),
        ({"run": "draining", "moving": True}, "on"),
    ],
)
def test_off_is_applied_only_where_nothing_moves(
    build: Build, row: Payload | None, after: str
) -> None:
    """No run row is no evidence, and neither is a row without `moving`
    (ADR-0062, #406)."""
    binding = build()
    press(binding, "on")
    if row is not None:
        runs(binding, row)
    press(binding, "off")
    assert power(binding) == after


def test_a_refused_off_is_not_kept_for_later(build: Build) -> None:
    binding = build()
    press(binding, "on")
    runs(binding, {"run": "draining", "moving": True})
    press(binding, "off")
    runs(binding, {"run": "held", "moving": False})
    assert power(binding) == "on"


@pytest.mark.parametrize("run", ["running", "draining", "held"])
@pytest.mark.parametrize("moving", [True, False])
def test_on_and_stopped_are_answered_in_every_run_state(
    build: Build, run: str, moving: bool
) -> None:
    binding = build()
    runs(binding, {"run": run, "moving": moving})
    press(binding, "stopped")
    assert power(binding) == "stopped"
    press(binding, "on")
    assert power(binding) == "on"


def test_the_run_row_judged_by_is_the_last_one_stated(build: Build) -> None:
    binding = build()
    press(binding, "on")
    runs(binding, {"run": "running", "moving": True})
    press(binding, "off")
    assert power(binding) == "on"
    runs(binding, {"run": "held", "moving": False})
    press(binding, "off")
    assert power(binding) == "off"


def test_a_run_row_stamped_earlier_is_ignored(build: Build) -> None:
    binding = build()
    press(binding, "on")
    runs(binding, {"at": 2.0, "run": "held", "moving": False})
    runs(binding, {"at": 1.0, "run": "running", "moving": True})
    press(binding, "off")
    assert power(binding) == "off"


def test_a_run_row_that_cannot_be_read_keeps_the_last(build: Build) -> None:
    binding = build()
    press(binding, "on")
    runs(binding, {"run": "held", "moving": True})
    runs(binding, {"run": "drained"})
    runs(binding, {"run": "held", "moving": "no"})
    press(binding, "off")
    assert power(binding) == "on"


@pytest.mark.parametrize("payload", [{"power": "sideways"}, {"power": 1}, {}])
def test_a_press_that_cannot_be_read_changes_nothing(
    build: Build, payload: Payload
) -> None:
    binding = build()
    press(binding, "on")
    binding.bus.publish(POWER_WANTED, payload)
    binding.bus.drain()
    assert power(binding) == "on"


def test_a_stop_stands_over_an_off_until_on(build: Build) -> None:
    """`stopped` stands until `on` (ADR-0070, #752)."""
    binding = build()
    press(binding, "on")
    press(binding, "stopped")
    press(binding, "off")
    assert power(binding) == "stopped"
    press(binding, "on")
    assert power(binding) == "on"
