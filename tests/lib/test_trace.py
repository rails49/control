"""Tests at the trace-tap seam: JSONL bytes per SYSTEM.md "The trace"."""

import io
from typing import cast

import pytest

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import TOPICS, leaf
from tc49.lib.trace import TraceTap

WANTED = "tc49/schedule/request_wanted"
REVERSAL = "tc49/schedule/reversal_wanted"


def test_line_is_flat_with_canonical_key_order() -> None:
    bus = InProcessBus(Clock())
    out = io.StringIO()
    TraceTap(bus, out, Clock())

    # Payload built in non-canonical key order; the tap must reorder.
    bus.publish(
        "tc49/dispatch/request_submitted",
        {"dest": ["yard_e.A"], "id": "re460-1", "depart": "main_w.A", "train": "re460"},
    )
    bus.drain()

    assert out.getvalue() == (
        '{"time":0.0,"event":"request_submitted",'
        '"id":"re460-1","train":"re460","depart":"main_w.A","dest":["yard_e.A"]}\n'
    )


def test_a_state_line_shows_the_payloads_stamp_ahead_of_its_fields() -> None:
    """`time` is the tap's observation and `at` is the payload's own (#240):
    the two agree here because the value was published on the same clock the
    tap reads, and the stamp leads the fields because the inventory puts it
    first."""
    clock = Clock()
    bus = InProcessBus(clock)
    out = io.StringIO()
    TraceTap(bus, out, clock)

    clock.advance(30.0)
    bus.publish("tc49/dispatch/state/run", {"run": "held"})
    bus.drain()

    assert out.getvalue() == '{"time":30.0,"event":"run","at":30.0,"run":"held"}\n'


def test_a_device_line_is_named_by_its_row_and_not_by_its_address() -> None:
    """The address is trailing levels a railroad's wiring decides, so the
    leaf of a device topic is an accessory number and names nothing
    (ADR-0043). The line carries the key past `tc49/layout/state/` instead,
    which says both the device and which half of the vocabulary it is —
    `wanted/point` here, `device/point` for what the hardware reports back.
    The address is in the payload beside it, which is what lets the line read
    on its own."""
    clock = Clock()
    bus = InProcessBus(clock)
    out = io.StringIO()
    TraceTap(bus, out, clock)

    bus.publish(
        "tc49/layout/state/wanted/point/5",
        {"addr": "5", "position": "thrown"},
    )
    bus.drain()

    assert out.getvalue() == (
        '{"time":0.0,"event":"wanted/point","at":0.0,'
        '"addr":"5","position":"thrown"}\n'
    )


def test_the_unaddressed_device_rows_are_named_the_same_way() -> None:
    """`track` carries no address — one railroad-wide power desired and one
    observed — so the whole topic is the row, and the line names it in the
    same two levels as every other device row rather than by its leaf, which
    the two halves would share."""
    clock = Clock()
    bus = InProcessBus(clock)
    out = io.StringIO()
    TraceTap(bus, out, clock)

    bus.publish("tc49/layout/state/wanted/track", {"power": "off"})
    bus.publish("tc49/layout/state/device/track", {"power": "on"})
    bus.drain()

    assert out.getvalue().splitlines() == [
        '{"time":0.0,"event":"wanted/track","at":0.0,"power":"off"}',
        '{"time":0.0,"event":"device/track","at":0.0,"power":"on"}',
    ]


def test_the_time_stamp_reads_the_run_clock_as_it_records() -> None:
    clock = Clock()
    bus = InProcessBus(clock)
    out = io.StringIO()
    TraceTap(bus, out, clock)

    # The startup cascade lands at 0.0; later events at the clock's reading.
    bus.publish("tc49/dispatch/lock_granted", {"train": "re460", "resources": ["a"]})
    bus.drain()
    clock.advance(30.0)
    bus.publish("tc49/layout/block_occupied", {"block": "b"})
    bus.drain()
    clock.advance(60.0)
    bus.publish("tc49/dispatch/request_completed", {"id": "re460-1"})
    bus.drain()

    assert out.getvalue().splitlines() == [
        '{"time":0.0,"event":"lock_granted","train":"re460","resources":["a"]}',
        '{"time":30.0,"event":"block_occupied","block":"b"}',
        '{"time":60.0,"event":"request_completed","id":"re460-1"}',
    ]


def test_scripted_sequence_traced_twice_is_byte_identical() -> None:
    def run() -> bytes:
        bus = InProcessBus(Clock())
        out = io.StringIO()
        TraceTap(bus, out, Clock())

        def complete(topic: str, payload: dict[str, object]) -> None:
            bus.publish("tc49/dispatch/request_completed", {"id": payload["id"]})

        bus.subscribe("tc49/dispatch/request_submitted", complete)
        bus.publish(
            "tc49/dispatch/lock_granted", {"train": "re460", "resources": ["a"]}
        )
        bus.publish(
            "tc49/dispatch/request_submitted",
            {"id": "re460-1", "train": "re460", "depart": "a.A", "dest": ["b.A"]},
        )
        bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
        bus.drain()
        return out.getvalue().encode()

    first, second = run(), run()
    assert first == second


def test_payload_field_outside_the_inventory_fails_loudly() -> None:
    bus = InProcessBus(Clock())
    TraceTap(bus, io.StringIO(), Clock())
    bus.publish("tc49/layout/block_occupied", {"blokc": "a"})

    with pytest.raises(ValueError):
        bus.drain()


def test_leaf_names_are_globally_unique_across_the_inventory() -> None:
    leaves = [leaf(topic) for topic in TOPICS]
    assert len(leaves) == len(set(leaves))


def test_a_client_frame_outside_the_inventory_is_recorded_rather_than_raised() -> None:
    """A browser may publish anything on the inbound topic (ADR-0034), and
    the frame's only record is its trace line — so the tap writes what it was
    given: the fields it knows in canonical order, then the rest."""
    bus = InProcessBus(Clock())
    out = io.StringIO()
    TraceTap(bus, out, Clock())
    bus.publish(WANTED, {"junk": 1, "train": "t1"})
    bus.drain()

    assert out.getvalue() == (
        '{"time":0.0,"event":"request_wanted","train":"t1","junk":1}\n'
    )


def test_every_inbound_topic_is_recorded_as_given() -> None:
    """A client's frame is recorded as-given whichever leaf it came on: both
    inbound topics carry whatever a browser published (#124, ADR-0034)."""
    bus = InProcessBus(Clock())
    out = io.StringIO()
    TraceTap(bus, out, Clock())
    bus.publish(REVERSAL, {"junk": 1, "train": "t1"})
    bus.drain()

    assert out.getvalue() == (
        '{"time":0.0,"event":"reversal_wanted","train":"t1","junk":1}\n'
    )


def test_a_client_frame_that_is_not_an_object_is_recorded_whole() -> None:
    """Nothing in it can be a field, so all of it is the record — which is
    what makes a dropped gesture verifiable in the trace (#107, ADR-0036)."""
    bus = InProcessBus(Clock())
    out = io.StringIO()
    TraceTap(bus, out, Clock())
    bus.publish(WANTED, cast(Payload, ["yard_e.A"]))
    bus.drain()

    assert out.getvalue() == (
        '{"time":0.0,"event":"request_wanted","payload":["yard_e.A"]}\n'
    )
