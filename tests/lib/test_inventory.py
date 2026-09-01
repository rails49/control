"""The inventory's own rules: what marks a state topic, and the device rows
the layout writes under an address (SYSTEM.md, rules 1 and 2; ADR-0043)."""

import pytest

from tc49.lib.inventory import (
    DEVICE_PREFIX,
    DEVICE_TOPICS,
    INBOUND,
    TOPICS,
    device_topic,
    is_state_topic,
    leaf,
    split_device,
)

POINT = "tc49/layout/state/wanted/point"
TRACK = "tc49/layout/state/wanted/track"
MODE_WANTED = "tc49/layout/mode_wanted"
THROTTLE_WANTED = "tc49/layout/throttle_wanted"
MODE = "tc49/layout/state/mode"


@pytest.mark.parametrize("topic", sorted(TOPICS))
def test_every_declared_row_keeps_the_answer_it_has_today(topic: str) -> None:
    """The rule moved from the second level from the end to the third from
    the start, and no row in the inventory notices: none of them carries a
    level past its own name."""
    assert is_state_topic(topic) == (topic.split("/")[-2] == "state")


def test_an_addressed_device_topic_is_a_state_topic() -> None:
    """Read backwards it would not be, `dccex` standing where `state` has to
    stand — and its retained value would be dropped on the way out of the
    state file, which is the whole of what a translator finds on connect."""
    assert is_state_topic("tc49/layout/state/wanted/point/dccex/5")


def test_a_command_is_not_a_state_topic() -> None:
    assert not is_state_topic("tc49/layout/move")
    assert not is_state_topic("tc49/layout/state")


def test_a_device_address_round_trips() -> None:
    """What a translator does with a topic it hears: name the row, then read
    the address off it and see whether it answers to that one (ADR-0043)."""
    assert split_device(device_topic(POINT, "dccex", "5")) == (POINT, "dccex/5")


def test_a_bare_address_is_one_level_and_still_round_trips() -> None:
    """Traction takes no system prefix — a decoder answers to the number it
    was programmed with whoever sends the packet (ADR-0045)."""
    traction = "tc49/layout/state/wanted/traction"
    assert split_device(device_topic(traction, "460")) == (traction, "460")


def test_the_track_row_carries_no_address() -> None:
    """One railroad-wide desired power: the districts are hardware and do not
    reach the bus (#217). So the row is the whole topic, and splits to an
    empty address rather than to nothing — it is a device row."""
    assert device_topic(TRACK) == TRACK
    assert split_device(TRACK) == (TRACK, "")


def test_an_addressed_row_naming_no_device_is_not_a_device_topic() -> None:
    assert split_device(POINT) is None


def test_a_topic_outside_the_vocabulary_does_not_split() -> None:
    """Both of these start where a device row starts or under a component that
    writes one, and neither is one."""
    assert split_device("tc49/layout/state/power") is None
    assert split_device("tc49/dispatch/state/aspects") is None


def test_every_device_row_is_the_layouts_and_repeats_its_address() -> None:
    for key, row in DEVICE_TOPICS.items():
        assert key.startswith(DEVICE_PREFIX)
        assert row.fields[0] == "addr" or key == TRACK


def test_the_two_manual_driving_gestures_are_a_pages_to_write() -> None:
    """Taking a train in a throttle and turning that throttle are gestures
    (#284): a throttle is any number of writers — two tabs are two of them —
    and the row names `layout`, which answers them, rather than whoever sent
    one. The mode the two settle is `layout`'s own state topic and no page
    writes it."""
    assert {MODE_WANTED, THROTTLE_WANTED} <= INBOUND
    assert MODE not in INBOUND
    assert TOPICS[MODE_WANTED].fields == ("train", "mode")
    assert TOPICS[THROTTLE_WANTED].fields == ("train", "speed")
    assert TOPICS[MODE].fields == ("modes",)


def test_no_state_row_is_browser_writable() -> None:
    """A page has concurrent instances, and concurrent writers may not write
    a state topic at all (ADR-0035). So a gesture may be marked and the state
    it settles never is, however many throttles ask for one."""
    assert not [
        topic for topic, row in TOPICS.items() if row.browser and is_state_topic(topic)
    ]


def test_no_device_row_is_browser_writable() -> None:
    """Every one of them is a state topic, and concurrent writers may not
    write one (ADR-0035)."""
    assert all(is_state_topic(key) for key in DEVICE_TOPICS)
    assert not any(row.browser for row in DEVICE_TOPICS.values())


def test_names_are_unique_across_both_mappings() -> None:
    """The trace records one name per row in its `event` field, so two rows
    sharing one could not be told apart there — and the device rows are named
    by their key past `tc49/layout/state/`."""
    names = [leaf(topic) for topic in TOPICS] + [
        key.removeprefix(DEVICE_PREFIX) for key in DEVICE_TOPICS
    ]
    assert len(names) == len(set(names))
