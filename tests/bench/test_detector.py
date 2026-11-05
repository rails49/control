"""The hand-fed detector: a person's typed readings where a camera's will be
(#315).

Nothing publishes `tc49/layout/sensor` on a physical railroad, so a `move` on
the steel has nothing to complete it. A line a person types is published as the
report a detector would write — and what these assert is that it is *that*
report, indistinguishable downstream: `layout` settles a typed level and passes
it on exactly as it does a camera's, debounce and all.

The reader itself is a client of the broker, `tc49 readings`, and what it does
against a real one is `test_readings.py`'s. What is read here is the reading
and the row it comes to.

The railroad is whichever the checkout has and the crossing is read off it, the
library railroads being renamed and moved under #319: a name spelled here would
go red for a reason that is not this suite's.
"""

import io
import time
from dataclasses import dataclass

import pytest

from tc49.bench.detector import ENDS, LEVELS, SENSOR, SHAPE, HandFed
from tc49.layout import LayoutInterface
from tc49.layout.interface import SETTLING_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import TOPICS, is_state_topic
from tc49.lib.layout import Layout, block_of, opposite_end
from tests.harness import a_railroad

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
PLACED = "tc49/dispatch/train_placed"
DEVICE_TRACK = "tc49/layout/state/device/track"


def a_block(layout: Layout) -> str:
    """Some block of this railroad, which is what a sensor is addressed by:
    whichever comes first by name, since these ask what a typed line is worth
    and not what stands where."""
    return min(layout.blocks)


def hand_fed(
    layout: Layout, typed: str = ""
) -> tuple[HandFed, InProcessBus, io.StringIO]:
    """A detector on a bare bus, what it publishes readable off the bus, and
    where it says a line that is no reading."""
    bus = InProcessBus(Clock())
    out = io.StringIO()
    return HandFed(bus, layout, io.StringIO(typed), out), bus, out


def sensed(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every sensor report published from here on, in order. Drained here rather
    than by the detector: publishing is all it does, and the loop that owns
    the run is what carries a report to whoever reads it."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe(SENSOR, lambda topic, payload: seen.append((topic, payload)))
    return seen


# -- what a line is ----------------------------------------------------------


def test_the_topic_a_reading_goes_on_is_the_one_the_inventory_declares() -> None:
    """This publishes a detector's report and invents nothing: the topic is a
    `TOPICS` key and an event, so a contract change here would be caught as one."""
    assert SENSOR in TOPICS
    assert not is_state_topic(SENSOR)


def test_a_typed_line_reaches_the_sensor_topic_with_the_level_on_it() -> None:
    """The whole of what this is for: `<block>.<end> <level>` published as the
    report a camera would write, the payload naming the block end."""
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    end = f"{a_block(layout)}.A"
    published = sensed(bus)

    assert detector.reads(f"{end} occupied") is None
    bus.drain()

    assert len(published) == 1
    assert published[0] == (SENSOR, {"addr": end, "occupancy": "occupied"})


@pytest.mark.parametrize("level", LEVELS)
def test_every_level_a_detector_may_report_may_be_typed(level: str) -> None:
    """The three values of `occupancy` and no others — `unknown` among them,
    which is a value and not an absence (BUS.md)."""
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    end = f"{a_block(layout)}.B"
    published = sensed(bus)

    assert detector.reads(f"{end} {level}") is None
    bus.drain()
    assert published[0][1]["occupancy"] == level


def test_the_closed_words_are_taken_in_either_case_and_the_block_is_not() -> None:
    """A block is spelled the way the drawing spells it. The two ends and the
    three levels are a closed vocabulary this reads back to the person anyway,
    so a shift key is not what stands between a train and its arrival."""
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    block = a_block(layout)
    published = sensed(bus)

    assert detector.reads(f"{block}.a OCCUPIED") is None
    bus.drain()
    assert published[0] == (
        SENSOR,
        {"addr": f"{block}.A", "occupancy": "occupied"},
    )
    assert detector.reads(f"{block.upper() + block}.A clear") is not None


def test_a_typed_level_is_published_again_after_each_second() -> None:
    """A sensor is reported at least once a second, changed or not, and a
    person types once: this says it again until they type something else."""
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    end = f"{a_block(layout)}.A"
    published = sensed(bus)
    detector.repeats(100.0)
    assert detector.reads(f"{end} occupied") is None
    bus.drain()
    assert len(published) == 1

    detector.repeats(100.9)
    bus.drain()
    assert len(published) == 1

    for count, now in enumerate((101.0, 102.0, 103.0), start=2):
        detector.repeats(now)
        bus.drain()
        assert len(published) == count
    assert published[-1] == (SENSOR, {"addr": end, "occupancy": "occupied"})


def test_what_is_repeated_is_the_level_typed_last() -> None:
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    end = f"{a_block(layout)}.A"
    published = sensed(bus)

    assert detector.reads(f"{end} occupied") is None
    assert detector.reads(f"{end} clear") is None
    detector.repeats(1.0)
    bus.drain()

    assert [payload["occupancy"] for _topic, payload in published] == [
        "occupied",
        "clear",
        "clear",
    ]


def test_a_sensor_nobody_typed_is_never_reported() -> None:
    """Only what a person said: this knows nothing about any other sensor."""
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    block = a_block(layout)
    published = sensed(bus)

    detector.repeats(1.0)
    bus.drain()
    assert published == []

    assert detector.reads(f"{block}.A occupied") is None
    assert detector.reads(f"{block}.C occupied") is not None
    for now in (2.0, 3.0, 4.0):
        detector.repeats(now)
    bus.drain()
    assert {payload["addr"] for _topic, payload in published} == {f"{block}.A"}


def test_a_blank_line_is_a_person_pressing_return_and_is_nothing() -> None:
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    published = sensed(bus)

    assert detector.reads("\n") is None
    assert detector.reads("   ") is None
    bus.drain()
    assert published == []


# -- a typo at the bench must not look like a detector -----------------------


@dataclass(frozen=True)
class Typo:
    """A line that is no reading, and a word the report has to carry."""

    line: str
    said: str


def typos(layout: Layout) -> list[Typo]:
    """Every way a typed line is not a reading, on this railroad."""
    block = a_block(layout)
    return [
        Typo(f"{block}.A", SHAPE),  # a sensor and no level
        Typo(f"{block}.A occupied please", SHAPE),  # a word too many
        Typo(f"{block} occupied", "<block>.<end>"),  # a block and no end
        Typo(".A occupied", "<block>.<end>"),  # an end and no block
        Typo(f"{block}.C occupied", " and ".join(ENDS)),  # no such end
        Typo("nonesuch.A occupied", "nonesuch"),  # no such block
        Typo(f"{block}.A occupado", "occupied, clear or unknown"),  # no such level
    ]


def test_a_line_that_is_not_a_reading_is_reported_and_published_nowhere() -> None:
    """A typo at the bench must not look like a detector: a reading for a
    block end this railroad has not is one nothing above can explain, and an
    unexplained reading goes in front of a person as a dispute (#1154). So it is answered in words
    naming what was wrong, and nothing goes on the bus."""
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    published = sensed(bus)

    for typo in typos(layout):
        refused = detector.reads(typo.line)
        assert refused is not None, typo.line
        assert typo.said in refused, refused
    bus.drain()
    assert published == []


def test_a_malformed_line_is_said_where_the_person_typed_it() -> None:
    """Printed and never raised, and the session runs on: this is a person
    typing beside a running railroad, and a typo is not a reason to stop one.
    """
    layout, _roster = a_railroad()
    block = a_block(layout)
    detector, bus, out = hand_fed(layout, f"nonesuch.A occupied\n{block}.A occupied\n")
    published = sensed(bus)

    detector.opens()
    assert waits_for(detector, bus, published)

    assert "nonesuch" in out.getvalue()
    assert published[0][1]["addr"] == f"{block}.A"


def waits_for(
    detector: HandFed, bus: InProcessBus, published: list[tuple[str, Payload]]
) -> bool:
    """Turn after turn of what the pacer does with it — take what was typed,
    then drain — until the reader thread has caught up. The read is on a
    thread of its own, so a line's arrival is a wait and never a given."""
    for _turn in range(500):
        detector.typed()
        bus.drain()
        if published:
            return True
        time.sleep(0.01)
    return False


def test_an_input_that_cannot_be_read_is_said_and_the_run_goes_on() -> None:
    """A session whose input is closed is one nobody is typing at. It is said
    once — a person who meant to type would otherwise watch a railroad ignore
    them — and the run drives on, blind as it was before there was a keyboard.
    """
    layout, _roster = a_railroad()
    lines = io.StringIO()
    lines.close()
    bus = InProcessBus(Clock())
    out = io.StringIO()
    detector = HandFed(bus, layout, lines, out)

    detector.opens()
    for _turn in range(500):
        detector.typed()
        if out.getvalue():
            break
        time.sleep(0.01)

    assert "nothing can be read" in out.getvalue()
    said = out.getvalue()
    detector.typed()
    assert out.getvalue() == said  # once, and not once a turn


# -- the pair that follows a real crossing -----------------------------------


@dataclass(frozen=True)
class Crossing:
    """Some way across this railroad: the connection and transit a `move`
    names, the block a train stands in, the block it is sent to, and the two
    ends of that block a real crossing trips, head first."""

    connection: str
    transit: str
    origin: str
    into: str
    head: str
    tail: str


def a_crossing(layout: Layout) -> Crossing:
    """One read off the layout, rather than a railroad's names spelled here.

    A transit joins two block ends: the train stands at one and comes in
    through the other, which is the entered block's near end — the head — and
    its opposite is the second sensor the train trips once it is fully in.
    """
    for name, connection in sorted(layout.connections.items()):
        for transit, (one, other) in sorted(connection.transits.items()):
            if block_of(one) != block_of(other):
                return Crossing(
                    connection=name,
                    transit=transit,
                    origin=block_of(one),
                    into=block_of(other),
                    head=other,
                    tail=opposite_end(other),
                )
    raise AssertionError(f"no transit between two blocks on {layout.name}")


def points_for(layout: Layout, crossing: Crossing) -> list[Payload]:
    """The points that way needs, as the dispatcher reads them off the layout
    and puts them on the command (ADR-0031). Always present, `[]` where the
    way needs nothing thrown: an absent list is a frame that lost a field."""
    points = layout.connections[crossing.connection].points.get(crossing.transit, ())
    return [
        {"addr": point.addr, "position": point.position, "reported": point.reported}
        for point in points
    ]


def test_a_typed_pair_completes_a_move_the_way_a_detectors_would() -> None:
    """The acceptance: a train is sent across a transit, a person types the
    two levels the entered block's detectors would have reported, and each goes
    out on its sensor's row, in the order typed.

    On the app the physical binding is built from and nothing else, with the
    clock driven rather than slept on: what is being asked is whether a typed
    level is a detector's, and a suite that waited out the settling time
    would be asking it more slowly and no better.
    """
    layout, roster = a_railroad()
    crossing = a_crossing(layout)
    clock = Clock()
    bus = InProcessBus(clock)
    app = LayoutInterface(bus, layout, roster, clock)
    detector = HandFed(bus, layout, io.StringIO(), io.StringIO())
    # The railroad as it stands when the move is granted: the rails live, the
    # train standing where a hand put it, and the way set.
    train = min(roster.trains)
    bus.publish(DEVICE_TRACK, {"power": "on"})
    bus.publish(PLACED, {"train": train, "block": crossing.origin})
    bus.publish(
        ALIGN,
        {
            "connection": crossing.connection,
            "transit": crossing.transit,
            "points": points_for(layout, crossing),
        },
    )
    bus.publish(
        MOVE,
        {
            "train": train,
            "connection": crossing.connection,
            "transit": crossing.transit,
            "into": crossing.into,
            "speed": 1.0,
        },
    )
    bus.drain()
    rows: list[tuple[object, object]] = []
    bus.subscribe(
        "tc49/layout/state/settled/sensor/#",
        lambda _topic, row: rows.append((row["addr"], row["occupancy"])),
    )
    bus.drain()
    rows.clear()

    for typed in (f"{crossing.head} occupied", f"{crossing.tail} occupied"):
        assert detector.reads(typed) is None
        bus.drain()
        clock.advance(clock.now + SETTLING_S)
        app.settle()
        bus.drain()

    assert rows == [(crossing.head, "occupied"), (crossing.tail, "occupied")]
