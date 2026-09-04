"""Tests at the InProcessBus seam: publish/subscribe/drain per SYSTEM.md "The bus"."""

import json
from pathlib import Path

import pytest

from tc49.lib.bus import Handler, InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.payload import Ordering


def test_publish_queues_without_delivering() -> None:
    bus = InProcessBus(Clock())
    seen: list[str] = []
    bus.subscribe("tc49/layout/boundary", lambda topic, payload: seen.append(topic))

    bus.publish("tc49/layout/boundary", {"boundary": 1})

    assert seen == []


def test_drain_delivers_in_publish_order() -> None:
    bus = InProcessBus(Clock())
    seen: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(topic))

    bus.publish("tc49/layout/block_occupied", {"block": "a"})
    bus.publish("tc49/layout/block_vacated", {"block": "b"})
    bus.drain()

    assert seen == ["tc49/layout/block_occupied", "tc49/layout/block_vacated"]


def test_publish_inside_handler_joins_back_of_queue() -> None:
    bus = InProcessBus(Clock())
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
    bus = InProcessBus(Clock())
    seen: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append("first"))
    bus.subscribe("tc49/layout/+", lambda topic, payload: seen.append("second"))

    bus.publish("tc49/layout/boundary", {"boundary": 1})
    bus.drain()

    assert seen == ["first", "second"]


def test_filter_grammar() -> None:
    bus = InProcessBus(Clock())
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
    bus = InProcessBus(Clock())
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": False})
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    seen: list[tuple[str, dict[str, object]]] = []
    bus.subscribe(
        "tc49/schedule/#", lambda topic, payload: seen.append((topic, payload))
    )
    bus.drain()

    assert seen == [("tc49/schedule/state/exhausted", {"at": 0.0, "exhausted": True})]


def test_last_value_goes_only_to_the_new_subscriber() -> None:
    bus = InProcessBus(Clock())
    early: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: early.append(topic))

    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    bus.subscribe("tc49/#", lambda topic, payload: None)
    bus.drain()

    assert early == ["tc49/schedule/state/exhausted"]


def test_event_topics_never_replay() -> None:
    bus = InProcessBus(Clock())
    bus.publish("tc49/layout/block_occupied", {"block": "a"})
    bus.drain()

    seen: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(topic))
    bus.drain()

    assert seen == []


def test_plus_matches_exactly_one_level() -> None:
    bus = InProcessBus(Clock())
    seen: list[str] = []
    bus.subscribe("tc49/+", lambda topic, payload: seen.append(topic))

    bus.publish("tc49/layout/boundary", {"boundary": 1})
    bus.drain()

    assert seen == []


@pytest.mark.parametrize(
    "bad", ["tc49/#/boundary", "tc49/lay#", "tc49/ten+", "+tc49/x"]
)
def test_mqtt_invalid_filters_are_rejected(bad: str) -> None:
    bus = InProcessBus(Clock())
    with pytest.raises(ValueError):
        bus.subscribe(bad, lambda topic, payload: None)


def test_delivery_order_is_a_pure_function_of_publish_and_subscribe_order() -> None:
    def run() -> list[str]:
        bus = InProcessBus(Clock())
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
    bus = InProcessBus(Clock())
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    assert list(tmp_path.iterdir()) == []


def test_a_retained_value_outlives_the_bus_that_held_it(tmp_path: Path) -> None:
    """What a broker's retained message does: the value is waiting on the
    topic when a process that was not there comes up and subscribes."""
    path = tmp_path / "session.json"
    first = InProcessBus(Clock(), path)
    first.publish(
        "tc49/schedule/state/facing", {"facing": {"freight_1": "yard_w.A-to-B"}}
    )
    first.drain()

    seen: list[tuple[str, Payload]] = []
    restored = InProcessBus(Clock(), path)
    restored.subscribe("tc49/#", lambda topic, payload: seen.append((topic, payload)))
    restored.drain()

    assert seen == [
        (
            "tc49/schedule/state/facing",
            {"at": 0.0, "facing": {"freight_1": "yard_w.A-to-B"}},
        )
    ]


def test_an_event_topic_is_not_persisted(tmp_path: Path) -> None:
    """Only what is retained survives: an event topic is never replayed, and
    a file that held one would replay it."""
    path = tmp_path / "session.json"
    bus = InProcessBus(Clock(), path)
    bus.publish("tc49/layout/block_occupied", {"block": "yard_w"})
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    bus.drain()

    assert json.loads(path.read_text()) == {
        "tc49/schedule/state/exhausted": {"at": 0.0, "exhausted": True}
    }


def test_every_change_rewrites_the_whole_file(tmp_path: Path) -> None:
    """One value moving rewrites all of them, so the file is always a whole
    picture and never a log to replay."""
    path = tmp_path / "session.json"
    bus = InProcessBus(Clock(), path)
    bus.publish(
        "tc49/schedule/state/facing", {"facing": {"freight_1": "yard_w.B-to-A"}}
    )
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": False})
    bus.publish(
        "tc49/schedule/state/facing", {"facing": {"freight_1": "yard_w.A-to-B"}}
    )

    assert json.loads(path.read_text()) == {
        "tc49/schedule/state/facing": {
            "at": 0.0,
            "facing": {"freight_1": "yard_w.A-to-B"},
        },
        "tc49/schedule/state/exhausted": {"at": 0.0, "exhausted": False},
    }


def test_a_cut_mid_write_leaves_the_previous_copy_to_load(tmp_path: Path) -> None:
    """The write goes to a temporary file in the same directory and is
    renamed over the target, so a process cut mid-write leaves a partial file
    the loader never looks at and the last good copy in place."""
    path = tmp_path / "session.json"
    bus = InProcessBus(Clock(), path)
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})
    good = path.read_text()
    partial = path.with_name(path.name + ".tmp")
    partial.write_text('{"tc49/schedule/state/exha')

    assert path.read_text() == good
    seen: list[Payload] = []
    restored = InProcessBus(Clock(), path)
    restored.subscribe("tc49/#", lambda topic, payload: seen.append(payload))
    restored.drain()
    assert seen == [{"at": 0.0, "exhausted": True}]


def test_a_path_with_no_file_yet_starts_empty(tmp_path: Path) -> None:
    """The first session of all: a path names where the picture will go, not
    a file that has to be there."""
    seen: list[Payload] = []
    bus = InProcessBus(Clock(), tmp_path / "session.json")
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
    bus = InProcessBus(Clock(), path)
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(topic))
    bus.drain()

    assert seen == ["tc49/schedule/state/exhausted"]


def test_the_directory_the_session_named_is_made(tmp_path: Path) -> None:
    """`--state runs/today.json` is an ordinary thing to type, and the first
    write is what has to make the directory: dying there would kill a session
    that had already printed its banner."""
    bus = InProcessBus(Clock(), tmp_path / "runs" / "today" / "session.json")
    bus.publish("tc49/schedule/state/exhausted", {"exhausted": True})

    assert json.loads((tmp_path / "runs" / "today" / "session.json").read_text()) == {
        "tc49/schedule/state/exhausted": {"at": 0.0, "exhausted": True}
    }


# --- the stamp the binding puts on a state value (#240) ----------------------

EXHAUSTED = "tc49/schedule/state/exhausted"
OCCUPIED = "tc49/layout/block_occupied"


def test_a_state_value_is_stamped_from_the_run_clock() -> None:
    """The binding stamps, not the app: `at` is the clock's reading at the
    moment this bus published, so no app component reads a clock of its own
    (ADR-0009)."""
    clock = Clock()
    bus = InProcessBus(clock)
    seen: list[Payload] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(payload))

    bus.publish(EXHAUSTED, {"exhausted": False})
    clock.advance(30.0)
    bus.publish(EXHAUSTED, {"exhausted": True})
    bus.drain()

    assert seen == [
        {"at": 0.0, "exhausted": False},
        {"at": 30.0, "exhausted": True},
    ]


def test_the_stamp_leads_the_value_the_late_subscriber_is_served() -> None:
    """Retained with its stamp on it, which is what a consumer joining later
    compares the next value against."""
    clock = Clock()
    bus = InProcessBus(clock)
    clock.advance(12.0)
    bus.publish(EXHAUSTED, {"exhausted": True})
    bus.drain()

    assert bus.last_values[EXHAUSTED] == {"at": 12.0, "exhausted": True}
    assert list(bus.last_values[EXHAUSTED]) == ["at", "exhausted"]


def test_no_event_payload_is_stamped() -> None:
    """The stamp is a state topic's, and the ordering rule it serves is too:
    an event topic is never replayed, and a sensor level repeats."""
    clock = Clock()
    bus = InProcessBus(clock)
    clock.advance(5.0)
    seen: list[Payload] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append(payload))

    bus.publish(OCCUPIED, {"block": "yard_w"})
    bus.drain()

    assert seen == [{"block": "yard_w"}]


def test_a_stamp_the_caller_supplied_is_replaced() -> None:
    """One place stamps, and it is the one publishing. A caller cannot state
    when this bus published its value, however plausible the number."""
    clock = Clock()
    bus = InProcessBus(clock)
    clock.advance(7.0)
    bus.publish(EXHAUSTED, {"at": 900.0, "exhausted": True})

    assert bus.last_values[EXHAUSTED] == {"at": 7.0, "exhausted": True}


def test_the_file_keeps_the_stamp_beside_the_value(tmp_path: Path) -> None:
    """The durable file round-trips `at`: it is a field of the value, and the
    whole value is what is written."""
    path = tmp_path / "session.json"
    clock = Clock()
    bus = InProcessBus(clock, path)
    clock.advance(41.0)
    bus.publish(EXHAUSTED, {"exhausted": True})

    assert json.loads(path.read_text()) == {EXHAUSTED: {"at": 41.0, "exhausted": True}}


def test_a_restored_value_is_re_stamped_with_this_sessions_clock(
    tmp_path: Path,
) -> None:
    """The stamp is seconds since the session started, so one carried out of
    the last run sits on another timeline — and, being the larger number for
    as long as that run was long, would beat every genuine report this one
    makes. The restored value is the oldest thing known instead, and the
    first report of the new session supersedes it (ADR-0030).

    The file still holds the stamp it was written with; it is the read that
    re-stamps.
    """
    path = tmp_path / "session.json"
    first = Clock()
    bus = InProcessBus(first, path)
    first.advance(600.0)
    bus.publish(EXHAUSTED, {"exhausted": True})

    second = Clock()
    restored = InProcessBus(second, path)
    assert restored.last_values[EXHAUSTED] == {"at": 0.0, "exhausted": True}
    assert json.loads(path.read_text())[EXHAUSTED]["at"] == 600.0


def test_the_first_value_of_the_new_session_beats_the_restored_one(
    tmp_path: Path,
) -> None:
    """What the re-stamping is for, seen through the comparison a consumer
    makes: the picture a restart comes up holding is a starting assumption,
    and the first thing the layout says now outranks it."""
    path = tmp_path / "session.json"
    first = Clock()
    was = InProcessBus(first, path)
    first.advance(600.0)
    was.publish(EXHAUSTED, {"exhausted": True})

    clock = Clock()
    bus = InProcessBus(clock, path)
    ordering = Ordering()
    assert ordering.accepts(EXHAUSTED, bus.last_values[EXHAUSTED])
    clock.advance(2.0)
    bus.publish(EXHAUSTED, {"exhausted": False})
    assert ordering.accepts(EXHAUSTED, bus.last_values[EXHAUSTED])


def test_a_retained_value_that_is_not_an_object_is_left_as_it_came(
    tmp_path: Path,
) -> None:
    """Nothing in it can be a field, so there is nowhere to put a stamp — and
    a file can be hand-edited (rule 4). It is served as it was written and
    reads as unstamped, which is a case the comparison already has."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({EXHAUSTED: "nonsense"}))

    assert InProcessBus(Clock(), path).last_values[EXHAUSTED] == "nonsense"


def test_a_cleared_row_is_gone_rather_than_empty() -> None:
    """What a reload does to the rows the railroad that left owned: the row
    is not there, so a late subscriber is handed nothing and reads the
    absence rather than a stale value (ADR-0060)."""
    bus = InProcessBus(Clock())
    bus.publish(EXHAUSTED, {"exhausted": True})
    bus.drain()  # what was published is delivered; a clear is not a recall

    bus.clear(EXHAUSTED)

    assert EXHAUSTED not in bus.last_values
    heard: list[tuple[str, Payload]] = []
    bus.subscribe(EXHAUSTED, lambda topic, payload: heard.append((topic, payload)))
    bus.drain()
    assert heard == [], "a late subscriber was handed a cleared row"


def test_clearing_delivers_nothing_to_a_subscriber() -> None:
    """A handler is never told a row went. There is nothing for it to read —
    the app that owns the row is about to publish the new railroad's — and a
    binding that delivered an empty payload would be handing every consumer a
    shape none of them parses."""
    bus = InProcessBus(Clock())
    heard: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: heard.append(topic))
    bus.publish(EXHAUSTED, {"exhausted": True})
    bus.drain()

    bus.clear(EXHAUSTED)
    bus.drain()

    assert heard == [EXHAUSTED], "the clear was delivered as an event"


def test_an_event_topic_has_nothing_to_clear() -> None:
    """Only a state topic keeps a value, so asking for an event topic is a
    bug in the caller rather than a no-op to absorb."""
    with pytest.raises(ValueError):
        InProcessBus(Clock()).clear(OCCUPIED)


def test_forgetting_drops_every_subscription_and_what_was_in_flight() -> None:
    """What makes a reload a cold start: the app built on the railroad that
    left keeps its handlers until something takes them off, and one still
    answering beside its replacement would be a second dispatcher on one
    railroad. What was queued goes with them — it was published to the
    railroad that is gone (ADR-0054)."""
    bus = InProcessBus(Clock())
    heard: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: heard.append(topic))
    bus.publish(OCCUPIED, {"block": "yard_w"})

    bus.forget()
    bus.drain()
    assert heard == [], "a forgotten subscriber was still delivered to"

    # And the values themselves stay: they are the railroad's, not the
    # subscriber's, and what comes next reads them to know what to clear.
    bus.publish(EXHAUSTED, {"exhausted": True})
    assert EXHAUSTED in bus.last_values
    bus.drain()
    assert heard == []
