"""Tests of `InterleavingBus`: the order BUS.md promises, and no more (#1043)."""

from collections.abc import Iterator

from tc49.lib.bus import Payload
from tc49.lib.clock import Clock
from tests.interleaving import InterleavingBus


class Listener:
    """A subscriber, as an app is: an object its handlers are bound to."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def on(self, topic: str, payload: Payload) -> None:
        self.seen.append(f"{topic} {payload.get('n')}")


def replaying(indices: list[int]) -> tuple[list[int], InterleavingBus]:
    """A bus choosing `indices` in turn and 0 once they run out, with the
    channel counts it was offered."""
    offered: list[int] = []
    picks: Iterator[int] = iter(indices)

    def choose(n: int) -> int:
        offered.append(n)
        return min(next(picks, 0), n - 1)

    return offered, InterleavingBus(Clock(), choose)


def test_one_publisher_on_one_topic_arrives_in_publish_order() -> None:
    # Whatever is chosen, a channel has one head and it is the oldest.
    _, bus = replaying([5, 5, 5])
    listener = Listener()
    bus.subscribe("tc49/layout/boundary", listener.on)

    for n in range(3):
        bus.publish("tc49/layout/boundary", {"n": n})
    bus.drain()

    assert listener.seen == [f"tc49/layout/boundary {n}" for n in range(3)]


def test_one_publisher_on_two_topics_can_arrive_in_either_order() -> None:
    def run(indices: list[int]) -> list[str]:
        _, bus = replaying(indices)
        listener = Listener()
        bus.subscribe("tc49/layout/#", listener.on)
        bus.publish("tc49/layout/boundary", {"n": 1})
        bus.publish("tc49/layout/block_vacated", {"n": 2})
        bus.drain()
        return listener.seen

    assert run([0]) == ["tc49/layout/boundary 1", "tc49/layout/block_vacated 2"]
    assert run([1]) == ["tc49/layout/block_vacated 2", "tc49/layout/boundary 1"]


def test_choose_picks_between_channels_ordered_by_their_head() -> None:
    offered, bus = replaying([2, 0, 0])
    first, second = Listener(), Listener()
    bus.subscribe("tc49/layout/boundary", first.on)
    bus.subscribe("tc49/layout/boundary", second.on)
    bus.subscribe("tc49/layout/block_vacated", first.on)

    bus.publish("tc49/layout/boundary", {"n": 1})  # to first, then second
    bus.publish("tc49/layout/block_vacated", {"n": 2})  # to first
    bus.drain()

    assert offered == [3, 2, 1]
    assert first.seen == ["tc49/layout/block_vacated 2", "tc49/layout/boundary 1"]
    assert second.seen == ["tc49/layout/boundary 1"]


def test_choosing_zero_delivers_each_copy_in_the_order_it_was_queued() -> None:
    # Unlike `InProcessBus`, which hands one message to every subscriber
    # before the next: here a copy published inside a handler can overtake
    # an older message's copy to another subscriber only by being older.
    bus = InterleavingBus(Clock(), lambda n: 0)
    seen: list[str] = []

    class Answerer:
        def on(self, topic: str, payload: Payload) -> None:
            seen.append(f"answerer {topic}")
            bus.publish("tc49/dispatch/move_granted", {})

    answerer = Answerer()
    bus.subscribe("tc49/layout/boundary", answerer.on)
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(f"tap {topic}"))

    bus.publish("tc49/layout/boundary", {})
    bus.drain()

    assert seen == [
        "answerer tc49/layout/boundary",
        "tap tc49/layout/boundary",
        "tap tc49/dispatch/move_granted",
    ]


def test_a_handler_publishes_on_its_own_channel() -> None:
    # The answer is the answerer's, not the outside's: it may overtake a
    # message the outside published on the same topic before it.
    _, bus = replaying([0, 1])
    seen: list[str] = []

    class Answerer:
        def on(self, topic: str, payload: Payload) -> None:
            bus.publish("tc49/dispatch/move_granted", {"n": "answer"})

    bus.subscribe("tc49/layout/boundary", Answerer().on)
    bus.subscribe(
        "tc49/dispatch/move_granted",
        lambda topic, payload: seen.append(str(payload["n"])),
    )

    bus.publish("tc49/layout/boundary", {})
    bus.publish("tc49/dispatch/move_granted", {"n": "outside"})
    bus.drain()

    assert seen == ["answer", "outside"]


def test_a_retained_value_reaches_a_late_subscriber() -> None:
    bus = InterleavingBus(Clock(), lambda n: 0)
    bus.publish("tc49/layout/state/power", {"power": "on"})
    bus.drain()

    listener = Listener()
    bus.subscribe("tc49/layout/state/#", listener.on)
    bus.publish("tc49/layout/boundary", {"n": 9})
    bus.drain()

    assert listener.seen == ["tc49/layout/state/power None"]
    assert bus.last_values["tc49/layout/state/power"]["power"] == "on"


def test_forget_empties_every_channel() -> None:
    bus = InterleavingBus(Clock(), lambda n: 0)
    listener = Listener()
    bus.subscribe("tc49/#", listener.on)
    bus.publish("tc49/layout/boundary", {"n": 1})
    bus.publish("tc49/dispatch/move_granted", {"n": 2})

    bus.forget()
    bus.drain()
    bus.publish("tc49/layout/boundary", {"n": 3})
    bus.drain()

    assert listener.seen == []


def test_after_sees_each_delivery_with_its_subscriber() -> None:
    delivered: list[tuple[object, str]] = []
    bus = InterleavingBus(
        Clock(), lambda n: 0, after=lambda who, topic, _: delivered.append((who, topic))
    )
    listener = Listener()
    bus.subscribe("tc49/layout/boundary", listener.on)

    bus.publish("tc49/layout/boundary", {"n": 1})
    bus.drain()

    assert delivered == [(listener, "tc49/layout/boundary")]
