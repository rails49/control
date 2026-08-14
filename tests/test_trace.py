"""Tests at the trace-tap seam: JSONL bytes per SYSTEM.md "The trace"."""

import io

import pytest

from tc49.bus import Bus
from tc49.inventory import TOPICS, leaf
from tc49.trace import TraceTap


def test_line_is_flat_with_canonical_key_order() -> None:
    bus = Bus()
    out = io.StringIO()
    TraceTap(bus, out)

    # Payload built in non-canonical key order; the tap must reorder.
    bus.publish(
        "tc49/schedule/request_submitted",
        {"dest": ["yard_e.A"], "id": "re460-1", "depart": "main_w.A", "train": "re460"},
    )
    bus.drain()

    assert out.getvalue() == (
        '{"tick":0,"event":"request_submitted",'
        '"id":"re460-1","train":"re460","depart":"main_w.A","dest":["yard_e.A"]}\n'
    )


def test_tick_stamp_follows_the_last_tick_event_observed() -> None:
    bus = Bus()
    out = io.StringIO()
    TraceTap(bus, out)

    # Before the first tick (e.g. startup standing locks): stamped 0.
    bus.publish("tc49/dispatch/lock_granted", {"train": "re460", "resources": ["a"]})
    bus.publish("tc49/layout/tick", {"tick": 1})
    bus.publish("tc49/layout/block_occupied", {"block": "b"})
    bus.publish("tc49/layout/tick", {"tick": 2})
    bus.publish("tc49/dispatch/request_completed", {"id": "re460-1"})
    bus.drain()

    assert out.getvalue().splitlines() == [
        '{"tick":0,"event":"lock_granted","train":"re460","resources":["a"]}',
        '{"tick":1,"event":"tick"}',
        '{"tick":1,"event":"block_occupied","block":"b"}',
        '{"tick":2,"event":"tick"}',
        '{"tick":2,"event":"request_completed","id":"re460-1"}',
    ]


def test_scripted_sequence_traced_twice_is_byte_identical() -> None:
    def run() -> bytes:
        bus = Bus()
        out = io.StringIO()
        TraceTap(bus, out)

        def complete(topic: str, payload: dict[str, object]) -> None:
            bus.publish("tc49/dispatch/request_completed", {"id": payload["id"]})

        bus.subscribe("tc49/schedule/request_submitted", complete)
        bus.publish(
            "tc49/dispatch/lock_granted", {"train": "re460", "resources": ["a"]}
        )
        bus.publish("tc49/layout/tick", {"tick": 1})
        bus.publish(
            "tc49/schedule/request_submitted",
            {"id": "re460-1", "train": "re460", "depart": "a.A", "dest": ["b.A"]},
        )
        bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
        bus.publish("tc49/layout/tick", {"tick": 2})
        bus.drain()
        return out.getvalue().encode()

    first, second = run(), run()
    assert first == second


def test_payload_field_outside_the_inventory_fails_loudly() -> None:
    bus = Bus()
    TraceTap(bus, io.StringIO())
    bus.publish("tc49/layout/block_occupied", {"blokc": "a"})

    with pytest.raises(ValueError):
        bus.drain()


def test_leaf_names_are_globally_unique_across_the_inventory() -> None:
    leaves = [leaf(topic) for topic in TOPICS]
    assert len(leaves) == len(set(leaves))
