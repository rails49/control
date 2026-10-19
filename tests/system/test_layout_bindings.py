"""The two bindings of the layout interface, held to one contract (#753).

`layout` drives steel and `simulator` stands in for it, and a client on the
bus is not to tell which is running (ADR-0030, ADR-0070). Every case here runs
against both, and reads what both expose: where each train stands
(`position`), and what each says on `state/railroad` and `state/power`. What
only one binding does — the layout's fold, align hold and traction writes, the
simulator's sensor timing — stays in that binding's own suite.

Both run on the bench railroad `tests/layout/railroad.py` draws. The layout is
given a station that reports the supply it is told to have, live under `on`
and dead under `off`, so a press reaches `state/power` on both the way it
would on a railroad. The bus stamps nothing, so a case can hand a moving row
the stamp it wants (#240).
"""

import logging
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
    MOVING,
    POWER,
    POWER_WANTED,
    RAILROAD,
    REMOVED,
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


def moves(binding: Binding, row: Payload) -> None:
    binding.bus.publish(MOVING, row)
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


@pytest.mark.parametrize("words", [[], ["on", "off"]])
def test_no_move_while_the_power_is_off(build: Build, words: list[str]) -> None:
    binding = build()
    for word in words:
        press(binding, word)
    stand(binding.bus, "freight_1", "up_w")
    crosses(binding, "freight_1", "to_dn", "dn_e")
    assert binding.position == {"freight_1": "up_w"}


def test_a_move_granted_while_draining_is_carried_out(build: Build) -> None:
    """The supply is on through a drain and the move was granted, so the
    train runs into the next block and stops at its sensor (#862, #863)."""
    binding = live(build)
    press(binding, "draining")
    crosses(binding, "freight_1", "to_dn", "dn_e")
    binding.settle()
    assert binding.position == {"freight_1": "dn_e"}


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
    "row", [None, {"moving": False}, {"moving": True}, {"moving": "no"}]
)
def test_off_is_applied_at_once_whatever_moves(
    build: Build, row: Payload | None
) -> None:
    """The emergency stop, with no guard (ADR-0078, decision 5)."""
    binding = build()
    press(binding, "on")
    if row is not None:
        moves(binding, row)
    press(binding, "off")
    assert power(binding) == "off"


def test_a_drain_ends_off_once_nothing_moves(build: Build) -> None:
    binding = build()
    press(binding, "on")
    moves(binding, {"moving": True})
    press(binding, "draining")
    assert power(binding) == "draining"
    moves(binding, {"moving": True})
    assert power(binding) == "draining"
    moves(binding, {"moving": False})
    assert power(binding) == "off"


def test_a_drain_with_nothing_moving_ends_at_the_press(build: Build) -> None:
    binding = build()
    press(binding, "on")
    moves(binding, {"moving": False})
    press(binding, "draining")
    assert power(binding) == "off"


@pytest.mark.parametrize("row", [None, {}, {"moving": "no"}, {"at": 1.0}])
def test_a_moving_row_absent_or_unreadable_is_a_train_moving(
    build: Build, row: Payload | None
) -> None:
    binding = build()
    press(binding, "on")
    if row is not None:
        moves(binding, row)
    press(binding, "draining")
    assert power(binding) == "draining"


def test_on_during_a_drain_ends_it(build: Build) -> None:
    binding = build()
    press(binding, "on")
    moves(binding, {"moving": True})
    press(binding, "draining")
    press(binding, "on")
    assert power(binding) == "on"
    moves(binding, {"moving": False})
    assert power(binding) == "on"


@pytest.mark.parametrize("words", [[], ["on", "off"], ["on", "draining"]])
def test_a_drain_from_anything_but_on_is_dropped(
    build: Build, words: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """A refusal goes to the log with its reason, for the person reading the
    trace (ADR-0034)."""
    binding = build()
    for word in words:
        press(binding, word)
    before = power(binding)
    with caplog.at_level(logging.INFO, logger="tc49.lib.power"):
        press(binding, "draining")
    assert power(binding) == before
    assert caplog.messages == [f"power draining dropped: the power reads {before}"]


def test_a_moving_row_stamped_earlier_is_ignored(build: Build) -> None:
    binding = build()
    press(binding, "on")
    moves(binding, {"at": 2.0, "moving": True})
    moves(binding, {"at": 1.0, "moving": False})
    press(binding, "draining")
    assert power(binding) == "draining"


@pytest.mark.parametrize(
    "payload", [{"power": "sideways"}, {"power": "stopped"}, {"power": 1}, {}]
)
def test_a_press_that_cannot_be_read_changes_nothing(
    build: Build, payload: Payload
) -> None:
    binding = build()
    press(binding, "on")
    binding.bus.publish(POWER_WANTED, payload)
    binding.bus.drain()
    assert power(binding) == "on"
