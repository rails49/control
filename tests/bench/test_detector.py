"""The hand-fed detector: a person's typed readings where a camera's will be
(#315).

Nothing publishes `tc49/layout/state/device/sensor` on a physical railroad, so
a `move` on the steel has nothing to complete it. A line typed at a session
running on the physical binding is published as the row a detector would write
— and what these assert is that it is *that* row, indistinguishable downstream:
`layout` folds a typed pair into `block_occupied` and `block_vacated` exactly
as it folds a camera's, debounce and all.

The railroad is whichever the checkout has and the crossing is read off it, the
library railroads being renamed and moved under #319: a name spelled here would
go red for a reason that is not this suite's.
"""

import io
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import pytest
from websockets.sync.client import ClientConnection, connect

from tc49.bench.detector import ENDS, LEVELS, SENSOR, SHAPE, HandFed
from tc49.bench.runner import assemble_live
from tc49.bench.session import Session
from tc49.layout import LayoutInterface
from tc49.layout.interface import SETTLING_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import DEVICE_TOPICS
from tc49.lib.layout import Layout, block_of, opposite_end
from tests.bench.physical import (
    HOST,
    PERIOD_S,
    TIMEOUT_S,
    Station,
    a_railroad,
    closed_port,
    until,
    waits_until,
)
from tests.harness import ASSETS, railroads

ALIGN = "tc49/layout/align"
MOVE = "tc49/layout/move"
PLACED = "tc49/dispatch/train_placed"
DEVICE_TRACK = "tc49/layout/state/device/track"
BLOCK_OCCUPIED = "tc49/layout/block_occupied"
BLOCK_VACATED = "tc49/layout/block_vacated"


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
    """Every sensor row published from here on, in order. Drained here rather
    than by the detector: publishing is all it does, and the loop that owns
    the run is what carries a row to whoever reads it."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe(SENSOR + "/#", lambda topic, payload: seen.append((topic, payload)))
    return seen


# -- what a line is ----------------------------------------------------------


def test_the_row_a_reading_goes_on_is_the_one_the_inventory_declares() -> None:
    """This publishes a detector's row and invents nothing: the topic is a
    `DEVICE_TOPICS` key, so a contract change here would be caught as one."""
    assert SENSOR in DEVICE_TOPICS


def test_a_typed_line_reaches_the_sensor_row_with_the_level_on_it() -> None:
    """The whole of what this is for: `<block>.<end> <level>` published as the
    row a camera would write, addressed by the block end and repeating the
    address in the payload as every device row does."""
    layout, _roster = a_railroad()
    detector, bus, _out = hand_fed(layout)
    end = f"{a_block(layout)}.A"
    published = sensed(bus)

    assert detector.reads(f"{end} occupied") is None
    bus.drain()

    assert len(published) == 1
    topic, payload = published[0]
    assert topic == f"{SENSOR}/{end}"
    assert payload["addr"] == end and payload["occupancy"] == "occupied"


@pytest.mark.parametrize("level", LEVELS)
def test_every_level_a_detector_may_report_may_be_typed(level: str) -> None:
    """The three values of `occupancy` and no others — `unknown` among them,
    which is a value and not an absence (SYSTEM.md)."""
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
        f"{SENSOR}/{block}.A",
        {"at": 0.0, "addr": f"{block}.A", "occupancy": "occupied"},
    )
    assert detector.reads(f"{block.upper() + block}.A clear") is not None


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
    unexplained reading holds the run (ADR-0048). So it is answered in words
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
    assert published[0][0] == f"{SENSOR}/{block}.A"


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


# -- only where the physical binding is --------------------------------------


def test_a_simulated_run_grows_no_second_source_of_sensors() -> None:
    """The simulator publishes its own, so a run on it is handed no reader at
    all — not even one nobody types at. Two things saying what one block end
    reads is the one thing a stand-in must not become."""
    layout, roster = a_railroad()
    simulated = assemble_live(layout, roster, readings=io.StringIO("what\n"))
    assert simulated.detector is None and simulated.simulator is not None


def test_a_physical_run_nobody_types_at_reads_nothing() -> None:
    """Every construction but a session's, the suite included: the input is
    the caller's to hand over, and a run given none is blind as it was."""
    layout, roster = a_railroad()
    driven = assemble_live(layout, roster, station=(HOST, closed_port()))
    assert driven.detector is None

    typed = assemble_live(
        layout,
        roster,
        station=(HOST, closed_port()),
        readings=io.StringIO(),
        reports=io.StringIO(),
    )
    assert typed.detector is not None


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
    return [{"addr": point.addr, "position": point.position} for point in points]


def test_a_typed_pair_completes_a_move_the_way_a_detectors_would() -> None:
    """The acceptance: a train is sent across a transit, a person types the
    two levels the entered block's detectors would have reported, and the fold
    publishes the arrival and the block behind — occupied then vacated, the
    only order the steel can produce (ADR-0047).

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
    folded: list[tuple[str, Payload]] = []
    for topic in (BLOCK_OCCUPIED, BLOCK_VACATED):
        bus.subscribe(topic, lambda seen, payload: folded.append((seen, payload)))

    for typed in (f"{crossing.head} occupied", f"{crossing.tail} occupied"):
        assert detector.reads(typed) is None
        bus.drain()
        clock.advance(clock.now + SETTLING_S)
        app.settle()
        bus.drain()

    assert folded == [
        (BLOCK_OCCUPIED, {"block": crossing.into}),
        (BLOCK_VACATED, {"block": crossing.origin}),
    ]


def test_the_loop_publishes_what_was_typed_at_a_run_that_is_up() -> None:
    """The wiring the acceptance rides on: a line typed at a physical session
    is taken on the pacer's turn and published, so a level reaches the row
    between one turn and the next exactly as a camera's would (#314)."""
    layout, roster = a_railroad()
    end = f"{a_block(layout)}.A"
    driven = assemble_live(
        layout,
        roster,
        station=(HOST, closed_port()),
        readings=io.StringIO(f"{end} occupied\n"),
        reports=io.StringIO(),
    )
    row = f"{SENSOR}/{end}"

    driven.run(PERIOD_S, stop=until(lambda: row in driven.bus.last_values))

    assert driven.bus.last_values[row]["occupancy"] == "occupied"


def sensor_frame(client: ClientConnection, end: str) -> dict[str, Any]:
    """The first frame that says what that block end reads, off the picture a
    joining client is served: a sensor row is retained state like any other, so
    a level typed before the panel joined is waiting for it (ADR-0032)."""
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        frame = json.loads(client.recv(timeout=TIMEOUT_S))
        if frame.get("topic") == f"{SENSOR}/{end}":
            payload: dict[str, Any] = frame["payload"]
            return payload
    raise AssertionError(f"the session never said what {end} reads")


def test_a_reading_typed_at_a_session_reaches_a_panel_as_the_row_it_is() -> None:
    """The whole way through: a session on the physical binding reads its own
    input, and what a person types there is relayed to a joined panel as the
    detector row it stands in for — the panel being told nothing about who
    typed it."""
    name = railroads()[0]
    layout, _roster = a_railroad()
    end = f"{a_block(layout)}.A"
    with Station() as station:
        live = Session(
            ASSETS,
            PERIOD_S,
            station=(HOST, station.port),
            readings=io.StringIO(f"{end} occupied\n"),
        )
        assert live.wants(name) is None
        log = io.StringIO()
        thread = threading.Thread(target=live.run, args=(log,), daemon=True)
        thread.start()
        try:
            assert waits_until(lambda: f"running {name}" in log.getvalue())
            with connect(f"ws://{HOST}:{live.bridge.port}/{name}") as client:
                assert sensor_frame(client, end)["occupancy"] == "occupied"
        finally:
            live.stop()
            thread.join(TIMEOUT_S)
            live.bridge.close()
