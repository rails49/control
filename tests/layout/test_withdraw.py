"""A move taken back where nothing has driven the train since (#1068).

A cancel landing on a move outstanding cannot end on the dispatcher's word: a
turnout usually has no detector, and a train stopped halfway across the
points looks to it like one that never left. `layout` knows the difference,
every speed a train is given passing through it, so the dispatcher asks it on
`withdraw_wanted` and it answers `move_withdrawn` where no non-zero speed has
been written for the train since it acted on the move. Otherwise it says
nothing, and the cancel waits for the sensors.
"""

from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC, MANUAL
from tests.layout.railroad import (
    align,
    commanded,
    energised,
    faces,
    gives,
    heard,
    move,
    reads,
    settle,
    speeds,
    stand,
    switches,
    takes,
    turns,
    wired,
)

WITHDRAW_WANTED = "tc49/layout/withdraw_wanted"
MOVE_WITHDRAWN = "tc49/layout/move_withdrawn"
TO_DN = "crossover.to_dn"


def withdraws(
    bus: InProcessBus, train: str, transit: str = TO_DN, into: str = "dn_e"
) -> None:
    """The dispatcher asking for a cancelled request's move back."""
    bus.publish(WITHDRAW_WANTED, {"train": train, "transit": transit, "into": into})
    bus.drain()


def answers(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every `move_withdrawn` from here on."""
    return heard(bus, MOVE_WITHDRAWN)


def asked(
    answered: list[tuple[str, Payload]],
) -> list[tuple[object, object, object]]:
    """Those answers as the train, the transit and the block each names."""
    return [
        (payload["train"], payload["transit"], payload["into"])
        for _topic, payload in answered
    ]


def told(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every traction write from here on, and not the rows already standing."""
    written = commanded(bus)
    bus.drain()
    written.clear()
    return written


def granted(driving: str = MANUAL) -> InProcessBus:
    """`single` standing in `up_w`, facing the crossover, and the move over
    it granted and acted on."""
    bus, _app, _clock = wired(driving=driving)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    return bus


def test_a_granted_move_nothing_drove_is_withdrawn_and_answered() -> None:
    """`manual`, no throttle: the train stood at its signal the whole time,
    so it is back where it was and the answer goes out once."""
    bus, app, _clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    answered = answers(bus)
    written = told(bus)

    withdraws(bus, "single")

    assert asked(answered) == [("single", TO_DN, "dn_e")]
    assert app.position == {"single": "up_w"}
    assert speeds(written) == [("3", 0.0)]


def test_after_a_withdrawal_switching_to_automatic_writes_no_speed() -> None:
    """The move is gone, so there is nothing for `automatic` to take up: the
    #1061 case reached by a cancel rather than a placement."""
    bus = granted()
    withdraws(bus, "single")
    written = told(bus)

    switches(bus, AUTOMATIC)

    assert speeds(written) == []


def test_a_move_a_throttle_drove_and_stopped_is_not_withdrawn() -> None:
    """It reads 0.0 now, but it was given a speed after the move was acted
    on, so it may be standing on the points."""
    bus = granted()
    takes(bus, "single")
    turns(bus, "single", 0.4)
    turns(bus, "single", 0.0)
    answered = answers(bus)
    written = told(bus)

    withdraws(bus, "single")

    assert answered == []
    assert speeds(written) == []


def test_a_throttle_before_the_move_was_acted_on_does_not_count() -> None:
    """Driven means since the move was acted on: a person shunting the train
    in its block beforehand moved it nowhere the move goes."""
    bus, _app, _clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    turns(bus, "single", 0.4)
    turns(bus, "single", 0.0)
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    answered = answers(bus)
    written = told(bus)

    withdraws(bus, "single")

    assert len(answered) == 1
    # A throttle holds it, so the speed is the person's: nothing is written.
    assert speeds(written) == []


def test_a_move_held_for_its_align_is_withdrawn_and_never_acted_on() -> None:
    bus, app, _clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    answered = answers(bus)

    withdraws(bus, "single")
    written = told(bus)
    align(bus, "crossover", "to_dn")

    assert len(answered) == 1
    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_a_withdrawal_before_the_move_is_answered_and_the_move_dropped() -> None:
    """The driver's `move` and the dispatcher's `withdraw_wanted` come from
    two writers, so either may land first."""
    bus, app, _clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    answered = answers(bus)

    withdraws(bus, "single")
    written = told(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)

    assert len(answered) == 1
    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_a_placement_clears_a_withdrawal_waiting_for_its_move() -> None:
    bus, app, _clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    withdraws(bus, "single")
    stand(bus, "single", "up_w")
    written = told(bus)

    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)

    assert speeds(written) == [("3", 0.3)]
    assert app.position == {"single": "dn_e"}


def test_in_automatic_a_move_already_acted_on_is_not_withdrawn() -> None:
    """Acted on in `automatic`, the move was given its speed at once."""
    bus = granted(AUTOMATIC)
    answered = answers(bus)

    withdraws(bus, "single")

    assert answered == []


def test_a_withdrawal_naming_a_move_already_carried_out_is_not_answered() -> None:
    """The train has crossed and its tail cleared before the ask landed: the
    move is not coming, so nothing waits for it. A transit it has not been
    sent over is a move still to come, and is answered."""
    bus, app, clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    takes(bus, "single")
    turns(bus, "single", 0.4)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)
    answered = answers(bus)

    withdraws(bus, "single")
    withdraws(bus, "single", "crossover.straight", "up_e")

    assert asked(answered) == [("single", "crossover.straight", "up_e")]


def arrived(bus: InProcessBus, app: LayoutInterface, clock: Clock) -> None:
    """`single` has crossed `crossover.to_dn` from `up_w` into `dn_e` in
    `manual`, driven by a throttle that let it go once it stood."""
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    takes(bus, "single")
    turns(bus, "single", 0.4)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)
    turns(bus, "single", 0.0)
    gives(bus, "single")


def test_a_withdrawal_of_the_way_back_over_a_transit_just_crossed_is_answered() -> None:
    """A transit names the way and not the direction: the move back over
    `crossover.to_dn` into `up_w` is told from the one just carried out into
    `dn_e` by the block it enters, so it is answered and its late `move`
    dropped (#1080)."""
    bus, app, clock = wired(driving=MANUAL)
    arrived(bus, app, clock)
    faces(bus, single="dn_e.A-to-B")
    align(bus, "crossover", "to_dn")
    answered = answers(bus)

    withdraws(bus, "single", TO_DN, "up_w")
    written = told(bus)
    move(bus, "single", "crossover", "to_dn", "up_w", 0.3)

    assert asked(answered) == [("single", TO_DN, "up_w")]
    assert speeds(written) == []
    assert app.position == {"single": "dn_e"}


def test_a_withdrawal_into_another_block_leaves_a_held_move_held() -> None:
    bus, app, _clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    answered = answers(bus)

    withdraws(bus, "single", TO_DN, "up_w")
    align(bus, "crossover", "to_dn")

    assert answered == []
    assert app.position == {"single": "dn_e"}


def test_a_withdrawal_that_cannot_be_read_is_dropped() -> None:
    bus = granted()
    answered = answers(bus)

    for payload in (
        {},
        {"train": "single"},
        {"transit": TO_DN},
        {"train": "single", "transit": TO_DN},
        {"train": "single", "transit": TO_DN, "into": 3},
        "single",
    ):
        bus.publish(WITHDRAW_WANTED, payload)  # type: ignore[arg-type]
        bus.drain()

    assert answered == []


def running(bus: InProcessBus) -> None:
    """`single` standing in `up_w`, facing the crossover, held in a throttle
    at 0.4 in `manual`: a person driving it, the lever left there."""
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    turns(bus, "single", 0.4)


def test_a_train_running_when_its_move_was_acted_on_is_not_withdrawn() -> None:
    """The decoder keeps the last speed it was given, so a lever left at 0.4
    drives the train over the points with nothing written since (#1076)."""
    bus, _app, _clock = wired(driving=MANUAL)
    running(bus)
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    answered = answers(bus)
    written = told(bus)

    withdraws(bus, "single")

    assert answered == []
    assert speeds(written) == []


def test_a_running_train_s_move_held_for_its_align_is_not_withdrawn() -> None:
    bus, app, _clock = wired(driving=MANUAL)
    running(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    answered = answers(bus)

    withdraws(bus, "single")
    align(bus, "crossover", "to_dn")

    assert answered == []
    assert app.position == {"single": "dn_e"}


def test_a_running_train_s_withdrawal_before_its_move_is_not_answered() -> None:
    bus, app, _clock = wired(driving=MANUAL)
    running(bus)
    align(bus, "crossover", "to_dn")
    answered = answers(bus)

    withdraws(bus, "single")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)

    assert answered == []
    assert app.position == {"single": "dn_e"}
