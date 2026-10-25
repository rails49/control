"""A train made in the stock view since the last build, placed and driven.

Such a train is on the store's roster and nowhere else. The dispatcher's
accept, `train_placed`, is the first this app hears of it, so a placement
naming a train the roster lacks reads the roster again; a take keeps its own
read, for a train placed while the store did not answer (ADR-0092,
decision 2).
"""

from tc49.lib.inventory import MANUAL
from tc49.lib.roster import Coupled, Roster, Train
from tests.layout.railroad import (
    align,
    commanded,
    energised,
    faces,
    loco,
    move,
    speeds,
    stand,
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
