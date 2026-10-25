"""A train placed by hand: one made since the last build, and one with a move.

A train made in the stock view since the last build is on the store's roster
and nowhere else. The dispatcher's accept, `train_placed`, is the first this
app hears of it, so a placement naming a train the roster lacks reads the
roster again; a take keeps its own read, for a train placed while the store
did not answer (ADR-0092, decision 2).

The dispatcher cancels a train's requests to accept its placement, so any
move of the train's this app holds is forgotten, and a running train no
throttle holds is stopped (#1061).
"""

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.inventory import AUTOMATIC, MANUAL
from tc49.lib.roster import Coupled, Roster, Train
from tests.layout.railroad import (
    align,
    commanded,
    energised,
    faces,
    loco,
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


def test_a_placed_train_made_since_the_build_is_driven_in_automatic() -> None:
    """No throttle holds the train and nothing sends a take, so the placement
    is what reads the roster: the grant reaches the car's address."""
    asked: list[None] = []

    def reread() -> Roster | None:
        asked.append(None)
        return Roster("bench", {"railcar": Train((Coupled(loco("7")),))})

    bus, _app, _clock = wired(reread=reread)
    energised(bus)
    stand(bus, "railcar", "up_w")
    faces(bus, railcar="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "railcar", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written) == [("7", 0.6)]
    assert len(asked) == 1


def test_a_placement_of_a_train_it_has_reads_no_roster() -> None:
    """A train the interface was built with keeps its entry until the next
    build (ADR-0071), so its placement costs no store read."""
    asked: list[None] = []

    def reread() -> Roster | None:
        asked.append(None)
        return None

    bus, _app, _clock = wired(reread=reread)
    stand(bus, "single", "up_w")

    assert asked == []


def test_a_take_reads_again_for_a_train_placed_while_the_store_did_not_answer() -> None:
    """The placement's read finds nothing and the train stays unknown; the
    take reads again and the lever reaches the car."""
    answers: list[Roster | None] = [
        None,
        Roster("bench", {"railcar": Train((Coupled(loco("7")),))}),
    ]
    asked: list[None] = []

    def reread() -> Roster | None:
        asked.append(None)
        return answers.pop(0)

    bus, _app, _clock = wired(driving=MANUAL, reread=reread)
    energised(bus)
    stand(bus, "railcar", "up_w")
    faces(bus, railcar="up_w.A-to-B")
    assert len(asked) == 1
    written = commanded(bus)
    takes(bus, "railcar")
    turns(bus, "railcar", 0.4)

    assert speeds(written) == [("7", 0.4)]
    assert len(asked) == 2


def told(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every traction write from here on, and not the rows already standing."""
    written = commanded(bus)
    bus.drain()
    written.clear()
    return written


def test_a_train_placed_mid_move_is_stopped_and_its_move_forgotten() -> None:
    """The dispatcher cancelled the move to accept the placement (#1061). The
    decoder keeps its last speed, so `0.0` goes out, and the readings the move
    was waiting on write nothing for it afterwards."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    written = told(bus)

    stand(bus, "single", "up_e")
    assert speeds(written) == [("3", 0.0)]

    written.clear()
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == []
    assert app.position == {"single": "up_e"}


def test_a_move_granted_in_manual_is_not_driven_after_a_placement() -> None:
    """In `manual` the move is recorded and not driven. Placed elsewhere, the
    train has no move outstanding, so switching to `automatic` writes it
    nothing but the stand it already has (#1061)."""
    bus, _app, _clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    stand(bus, "single", "dn_e")
    faces(bus, single="dn_e.B-to-A")
    written = told(bus)

    switches(bus, AUTOMATIC)

    assert all(speed == 0.0 for _addr, speed in speeds(written))


def test_a_train_a_throttle_holds_keeps_its_speed_on_a_placement() -> None:
    """A person is driving it, so the speed stays theirs."""
    bus, _app, _clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    turns(bus, "single", 0.4)
    written = told(bus)

    stand(bus, "single", "up_e")

    assert speeds(written) == []


def test_a_standing_train_placed_is_written_nothing() -> None:
    """Nothing written has moved it, so there is nothing to stop."""
    bus, _app, _clock = wired()
    energised(bus)
    written = told(bus)

    stand(bus, "single", "up_w")
    stand(bus, "single", "up_e")

    assert speeds(written) == []


def test_a_move_held_for_its_align_is_dropped_by_a_placement() -> None:
    """Placed elsewhere and back, the train stands at the near end again, and
    the move the dispatcher cancelled would pass every rule on the `align`."""
    bus, _app, _clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    stand(bus, "single", "up_e")
    stand(bus, "single", "up_w")
    written = told(bus)

    align(bus, "crossover", "to_dn")

    assert speeds(written) == []
