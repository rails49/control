"""The inventory's own rules: what marks a state topic, and the device rows
addressed under the layout interface — what `layout` wants of the hardware and
what a detector or a translator reports back (SYSTEM.md, rules 1 and 2;
ADR-0043)."""

import pytest

from tc49.lib.inventory import (
    AT,
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
SENSOR = "tc49/layout/state/device/sensor"
OBSERVED_POINT = "tc49/layout/state/device/point"
OBSERVED_TRACK = "tc49/layout/state/device/track"
LINK = "tc49/layout/state/device/link"
MODE_WANTED = "tc49/layout/mode_wanted"
THROTTLE_WANTED = "tc49/layout/throttle_wanted"
MODE = "tc49/layout/state/mode"
POWER_WANTED = "tc49/layout/power_wanted"
POWER = "tc49/layout/state/power"


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


def test_the_track_rows_carry_no_address() -> None:
    """One railroad-wide power desired and one observed: the districts are
    hardware and do not reach the bus (#217). So the row is the whole topic,
    and splits to an empty address rather than to nothing — it is a device
    row."""
    for track in (TRACK, OBSERVED_TRACK):
        assert device_topic(track) == track
        assert split_device(track) == (track, "")


def test_an_addressed_row_naming_no_device_is_not_a_device_topic() -> None:
    assert split_device(POINT) is None


def test_a_topic_outside_the_vocabulary_does_not_split() -> None:
    """Both of these start where a device row starts or under a component that
    writes one, and neither is one."""
    assert split_device("tc49/layout/state/power") is None
    assert split_device("tc49/dispatch/state/aspects") is None


def test_every_device_row_repeats_the_address_it_names() -> None:
    """A row says which payload field its address comes back in, and that
    field leads the payload past the stamp, which is the binding's rather
    than the publisher's (#240). Two rows name none, and those are the two
    that carry none."""
    for key, row in DEVICE_TOPICS.items():
        assert key.startswith(DEVICE_PREFIX)
        if row.address:
            assert row.fields[1:2] == (row.address,), key
        else:
            assert key in (TRACK, OBSERVED_TRACK)


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
    assert TOPICS[MODE].fields == (AT, "modes")


def test_the_panel_commands_power_on_a_row_of_its_own() -> None:
    """The command direction of the one axis (#293, ADR-0051): an event row
    a page may write, carrying the one field `power` and the same closed set
    the observation carries. It is `layout`'s because `layout` answers it —
    a topic names the responder and never the sender — and the observation
    stays `layout`'s alone, so no page can say a railroad has power."""
    assert POWER_WANTED in INBOUND
    assert TOPICS[POWER_WANTED].fields == ("power",)
    assert TOPICS[POWER].fields == (AT, "power")
    assert POWER not in INBOUND


def test_no_state_row_is_browser_writable() -> None:
    """A page has concurrent instances, and concurrent writers may not write
    a state topic at all (ADR-0035). So a gesture may be marked and the state
    it settles never is, however many throttles ask for one."""
    assert not [
        topic for topic, row in TOPICS.items() if row.browser and is_state_topic(topic)
    ]


def test_the_observed_rows_state_their_fields_in_order() -> None:
    """What a detector and a translator write back (#282): the observed half
    of the device vocabulary, each row's fields in the order the contract
    gives them, past the stamp every state row leads with."""
    assert DEVICE_TOPICS[SENSOR].fields == (AT, "addr", "occupancy", "reason")
    assert DEVICE_TOPICS[OBSERVED_POINT].fields == (AT, "addr", "position")
    assert DEVICE_TOPICS[OBSERVED_TRACK].fields == (AT, "power")
    assert DEVICE_TOPICS[LINK].fields == (AT, "system", "link", "detail")


def test_a_sensor_is_addressed_by_the_block_end_it_watches() -> None:
    """`<block>.<end>` and never a camera's own identifier (#194), one topic
    per sensor and never a whole-railroad map: a map would make one camera the
    writer of every sensor on the railroad, and a second camera could then not
    join (ADR-0035)."""
    assert device_topic(SENSOR, "A1.b") == "tc49/layout/state/device/sensor/A1.b"
    assert split_device("tc49/layout/state/device/sensor/A1.b") == (SENSOR, "A1.b")


def test_a_link_is_addressed_by_the_system_whose_link_it_reports() -> None:
    """One translator per hardware system, each publishing its own link to
    the hardware as observed state like any other, so a UI can say the command
    station is unreachable rather than the railroad merely looking idle
    (ADR-0050). The address comes back as `system` rather than `addr`: it
    names a translator's system, not a device the translator drives."""
    assert split_device(device_topic(LINK, "dccex")) == (LINK, "dccex")
    assert DEVICE_TOPICS[LINK].address == "system"


def test_the_two_halves_of_the_vocabulary_are_named_apart() -> None:
    """The same turnout answers on both, and a trace line records the row
    rather than the leaf, so `wanted/point` and `device/point` are two names
    for two things and neither hides the other (ADR-0043)."""
    assert DEVICE_TOPICS[POINT].fields == DEVICE_TOPICS[OBSERVED_POINT].fields
    assert POINT != OBSERVED_POINT
    assert split_device(device_topic(OBSERVED_POINT, "dccex", "5")) == (
        OBSERVED_POINT,
        "dccex/5",
    )


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


def test_every_state_row_leads_with_the_stamp_and_no_event_row_carries_one() -> None:
    """The rule the ordering guard rests on (#240): a state payload states
    when it was published and an event payload states nothing of the kind, so
    a consumer can gate on the topic's own name rather than on whether a
    payload happens to carry a number. It **leads** the field order so the
    trace shows it in a fixed place."""
    for topic, row in {**TOPICS, **DEVICE_TOPICS}.items():
        if is_state_topic(topic):
            assert row.fields[0] == AT, topic
        else:
            assert AT not in row.fields, topic
