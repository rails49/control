"""Tests at the Bus seam: publish/subscribe/drain per SYSTEM.md "The bus"."""

import json
from pathlib import Path

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
    bus.publish("tc49/dispatch/request_submitted", {"id": "t-1"})
    bus.drain()

    # Breadth-first: the nested publish lands after everything already queued.
    assert seen == [
        "tc49/layout/boundary",
        "tap:tc49/layout/boundary",
        "tap:tc49/dispatch/request_submitted",
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


# --- durability: the retained values outlive the process (#151) --------------


def test_no_file_is_opened_without_a_path(tmp_path: Path) -> None:
    """The default bus persists nothing, so `bench` and `sweep` are untouched
    by construction rather than by a branch."""
    bus = Bus()
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    assert list(tmp_path.iterdir()) == []


def test_a_retained_value_outlives_the_bus_that_held_it(tmp_path: Path) -> None:
    """What a broker's retained message does: the value is waiting on the
    topic when a process that was not there comes up and subscribes."""
    path = tmp_path / "session.json"
    first = Bus(path)
    first.publish("tc49/schedule/state/facing", {"facing": {"freight_1": "yard_w.B"}})
    first.drain()

    seen: list[tuple[str, Payload]] = []
    restored = Bus(path)
    restored.subscribe("tc49/#", lambda topic, payload: seen.append((topic, payload)))
    restored.drain()

    assert seen == [
        ("tc49/schedule/state/facing", {"facing": {"freight_1": "yard_w.B"}})
    ]


def test_an_event_topic_is_not_persisted(tmp_path: Path) -> None:
    """Only what is retained survives: an event topic is never replayed, and
    a file that held one would replay it."""
    path = tmp_path / "session.json"
    bus = Bus(path)
    bus.publish("tc49/layout/block_occupied", {"block": "yard_w"})
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    assert json.loads(path.read_text()) == {
        "tc49/schedule/state/exhausted": {"exhausted": True}
    }


def test_every_change_rewrites_the_whole_file(tmp_path: Path) -> None:
    """One value moving rewrites all of them, so the file is always a whole
    picture and never a log to replay."""
    path = tmp_path / "session.json"
    bus = Bus(path)
    bus.publish("tc49/schedule/state/facing", {"facing": {"freight_1": "yard_w.A"}})
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": False})
    bus.publish("tc49/schedule/state/facing", {"facing": {"freight_1": "yard_w.B"}})

    assert json.loads(path.read_text()) == {
        "tc49/schedule/state/facing": {"facing": {"freight_1": "yard_w.B"}},
        "tc49/schedule/state/exhausted": {"exhausted": False},
    }


def test_a_cut_mid_write_leaves_the_previous_copy_to_load(tmp_path: Path) -> None:
    """The write goes to a temporary file in the same directory and is
    renamed over the target, so a process cut mid-write leaves a partial file
    the loader never looks at and the last good copy in place."""
    path = tmp_path / "session.json"
    bus = Bus(path)
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    good = path.read_text()
    partial = path.with_name(path.name + ".tmp")
    partial.write_text('{"tc49/schedule/state/exha')

    assert path.read_text() == good
    seen: list[Payload] = []
    restored = Bus(path)
    restored.subscribe("tc49/#", lambda topic, payload: seen.append(payload))
    restored.drain()
    assert seen == [{"exhausted": True}]


def test_a_path_with_no_file_yet_starts_empty(tmp_path: Path) -> None:
    """The first session of all: a path names where the picture will go, not
    a file that has to be there."""
    seen: list[Payload] = []
    bus = Bus(tmp_path / "session.json")
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(payload))
    bus.drain()

    assert seen == []


def test_a_file_naming_an_event_topic_replays_nothing(tmp_path: Path) -> None:
    """Filtered on the way out as `publish` filters on the way in: whatever
    wrote the file, an event topic is never replayed and keeping that promise
    is the bus's own business."""
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "tc49/layout/block_occupied": {"block": "yard_w"},
                "tc49/schedule/state/exhausted": {"exhausted": True},
            }
        )
    )
    seen: list[str] = []
    bus = Bus(path)
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(topic))
    bus.drain()

    assert seen == ["tc49/schedule/state/exhausted"]


def test_the_directory_the_session_named_is_made(tmp_path: Path) -> None:
    """`--state runs/today.json` is an ordinary thing to type, and the first
    write is what has to make the directory: dying there would kill a session
    that had already printed its banner."""
    bus = Bus(tmp_path / "runs" / "today" / "session.json")
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})

    assert json.loads((tmp_path / "runs" / "today" / "session.json").read_text()) == {
        "tc49/schedule/state/exhausted": {"exhausted": True}
    }
