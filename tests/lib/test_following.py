"""What one more reading says about a move, given what was read before it
(#1333): every reading at each of the move's sensors and at one it does not
have, from every combination of what was read so far."""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

import pytest

from tc49.lib.following import Facts, Seen, follow

EXIT, ENTRY, FAR, OTHER = "x.B", "y.A", "y.B", "z.A"

# (sensor, occupied): the flags the reading sets, and the facts it gives as a
# function of what was read before it.
ROWS: dict[tuple[str, bool], tuple[set[str], Callable[[Seen], Facts]]] = {
    (EXIT, True): ({"exit_read"}, lambda seen: Facts()),
    (EXIT, False): (set(), lambda seen: Facts(tail_out=seen.exit_read)),
    (ENTRY, True): ({"head_in"}, lambda seen: Facts(head_in=not seen.head_in)),
    (ENTRY, False): (set(), lambda seen: Facts(whole_in=seen.head_in)),
    (FAR, True): (
        {"head_in", "at_far"},
        lambda seen: Facts(head_in=not seen.head_in, at_far=True),
    ),
    (FAR, False): (set(), lambda seen: Facts()),
    (OTHER, True): (set(), lambda seen: Facts()),
    (OTHER, False): (set(), lambda seen: Facts()),
}

SO_FAR = [
    Seen(exit_read=e, head_in=h, at_far=f)
    for e, h, f in product([False, True], repeat=3)
]


@pytest.mark.parametrize("sensor, occupied", list(ROWS))
@pytest.mark.parametrize("seen", SO_FAR)
def test_a_reading_sets_its_flags_and_gives_its_facts(
    seen: Seen, sensor: str, occupied: bool
) -> None:
    sets, facts = ROWS[sensor, occupied]

    new, given = follow(
        seen, exit=EXIT, entry=ENTRY, far=FAR, sensor=sensor, occupied=occupied
    )

    assert new == Seen(
        exit_read=seen.exit_read or "exit_read" in sets,
        head_in=seen.head_in or "head_in" in sets,
        at_far=seen.at_far or "at_far" in sets,
    )
    assert given == facts(seen)


def test_the_tail_out_after_the_grant_and_the_whole_train_in() -> None:
    """A train granted with its tail over the exit sensor, crossing into the
    entered block and stopping at its far sensor."""
    seen = Seen(exit_read=True)
    given: list[Facts] = []
    for sensor, occupied in [(ENTRY, True), (EXIT, False), (ENTRY, False), (FAR, True)]:
        seen, facts = follow(
            seen, exit=EXIT, entry=ENTRY, far=FAR, sensor=sensor, occupied=occupied
        )
        given.append(facts)

    assert given == [
        Facts(head_in=True),
        Facts(tail_out=True),
        Facts(whole_in=True),
        Facts(at_far=True),
    ]
    assert seen == Seen(exit_read=True, head_in=True, at_far=True)


@pytest.mark.parametrize("sensor, occupied", list(ROWS))
@pytest.mark.parametrize("seen", SO_FAR)
def test_a_move_with_no_exit_sensor_reads_its_exit_as_any_other_sensor(
    seen: Seen, sensor: str, occupied: bool
) -> None:
    """`layout`'s crossing follows only the entered block (#1334)."""
    other = OTHER if sensor == EXIT else sensor
    sets, facts = ROWS[other, occupied]

    new, given = follow(
        seen, exit=None, entry=ENTRY, far=FAR, sensor=sensor, occupied=occupied
    )

    assert new == Seen(
        exit_read=seen.exit_read or "exit_read" in sets,
        head_in=seen.head_in or "head_in" in sets,
        at_far=seen.at_far or "at_far" in sets,
    )
    assert given == facts(seen)


def test_a_subclass_comes_back_as_itself() -> None:
    """A record that extends `Seen` with fields of its own is returned updated,
    those fields kept."""

    @dataclass(frozen=True)
    class Move(Seen):
        train: str

    new, _ = follow(
        Move("t", exit_read=True),
        exit=EXIT,
        entry=ENTRY,
        far=FAR,
        sensor=ENTRY,
        occupied=True,
    )

    assert new == Move("t", exit_read=True, head_in=True)
