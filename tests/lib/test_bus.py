"""Tests at the Bus seam: publish/subscribe/drain per SYSTEM.md "The bus"."""

import pytest

from tc49.lib.bus import Bus, Handler, Payload


def test_publish_queues_without_delivering() -> None:
    bus = Bus()
    seen: list[str] = []
    bus.subscribe("tc49/layout/boundary", lambda topic, payload: seen.append(topic))

    bus.publish("tc49/layout/boundary", {"boundary": 1})

    assert seen == []


def test_drain_delivers_in_publish_order() -> None:
    bus = Bus()
    seen: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(topic))

    bus.publish("tc49/layout/block_occupied", {"block": "a"})
    bus.publish("tc49/layout/block_vacated", {"block": "b"})
    bus.drain()

    assert seen == ["tc49/layout/block_occupied", "tc49/layout/block_vacated"]


def test_publish_inside_handler_joins_back_of_queue() -> None:
    bus = Bus()
    seen: list[str] = []

    def on_boundary(topic: str, payload: dict[str, object]) -> None:
        seen.append(topic)
        bus.publish("tc49/dispatch/move_granted", {"id": "t-1"})

    bus.subscribe("tc49/layout/boundary", on_boundary)
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(f"tap:{topic}"))

    bus.publish("tc49/layout/boundary", {"boundary": 1})
    bus.publish("tc49/schedule/request_submitted", {"id": "t-1"})
    bus.drain()

    # Breadth-first: the nested publish lands after everything already queued.
    assert seen == [
        "tc49/layout/boundary",
        "tap:tc49/layout/boundary",
        "tap:tc49/schedule/request_submitted",
        "tap:tc49/dispatch/move_granted",
    ]


def test_fan_out_in_subscription_order() -> None:
    bus = Bus()
    seen: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append("first"))
    bus.subscribe("tc49/layout/+", lambda topic, payload: seen.append("second"))

    bus.publish("tc49/layout/boundary", {"boundary": 1})
    bus.drain()

    assert seen == ["first", "second"]


def test_filter_grammar() -> None:
    bus = Bus()
    seen: dict[str, list[str]] = {"exact": [], "plus": [], "hash": []}
    bus.subscribe(
        "tc49/layout/boundary", lambda topic, payload: seen["exact"].append(topic)
    )
    bus.subscribe("tc49/layout/+", lambda topic, payload: seen["plus"].append(topic))
    bus.subscribe("tc49/dispatch/#", lambda topic, payload: seen["hash"].append(topic))

    bus.publish("tc49/layout/boundary", {"boundary": 1})
    bus.publish("tc49/layout/block_occupied", {"block": "a"})
    bus.publish("tc49/dispatch/lock_granted", {"train": "re460", "resources": []})
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    assert seen["exact"] == ["tc49/layout/boundary"]
    assert seen["plus"] == ["tc49/layout/boundary", "tc49/layout/block_occupied"]
    assert seen["hash"] == ["tc49/dispatch/lock_granted"]


def test_state_topic_delivers_last_value_to_late_subscriber() -> None:
    bus = Bus()
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": False})
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    seen: list[tuple[str, dict[str, object]]] = []
    bus.subscribe(
        "tc49/schedule/#", lambda topic, payload: seen.append((topic, payload))
    )
    bus.drain()

    assert seen == [("tc49/schedule/state/exhausted", {"exhausted": True})]


def test_last_value_goes_only_to_the_new_subscriber() -> None:
    bus = Bus()
    early: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: early.append(topic))

    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    bus.subscribe("tc49/#", lambda topic, payload: None)
    bus.drain()

    assert early == ["tc49/schedule/state/exhausted"]


def test_event_topics_never_replay() -> None:
    bus = Bus()
    bus.publish("tc49/layout/block_occupied", {"block": "a"})
    bus.drain()

    seen: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(topic))
    bus.drain()

    assert seen == []


def test_plus_matches_exactly_one_level() -> None:
    bus = Bus()
    seen: list[str] = []
    bus.subscribe("tc49/+", lambda topic, payload: seen.append(topic))

    bus.publish("tc49/layout/boundary", {"boundary": 1})
    bus.drain()

    assert seen == []


@pytest.mark.parametrize(
    "bad", ["tc49/#/boundary", "tc49/lay#", "tc49/ten+", "+tc49/x"]
)
def test_mqtt_invalid_filters_are_rejected(bad: str) -> None:
    bus = Bus()
    with pytest.raises(ValueError):
        bus.subscribe(bad, lambda topic, payload: None)


def test_delivery_order_is_a_pure_function_of_publish_and_subscribe_order() -> None:
    def run() -> list[str]:
        bus = Bus()
        log: list[str] = []

        def relay(name: str) -> Handler:
            def handler(topic: str, payload: Payload) -> None:
                log.append(f"{name}:{topic}")
                if topic == "tc49/layout/boundary":
                    bus.publish(f"tc49/dispatch/from_{name}", {})

            return handler

        bus.subscribe("tc49/layout/#", relay("a"))
        bus.subscribe("tc49/#", relay("b"))
        bus.publish("tc49/layout/boundary", {"boundary": 1})
        bus.publish("tc49/schedule/state/exhausted", {"exhausted": False})
        bus.drain()
        bus.subscribe("tc49/schedule/#", relay("late"))
        bus.drain()
        return log

    assert run() == run()
