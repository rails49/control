"""The inventory's own rules: what marks a state topic, and the device rows
addressed under the layout interface — what `layout` wants of the hardware and
what a detector or a translator reports back (BUS.md, rules 1 and 2;
ADR-0043)."""

import pytest

from tc49.lib.inventory import (
    AT,
    DEVICE_PREFIX,
    DEVICE_TOPICS,
    INBOUND,
    TOPICS,
    WIDGET_TOPICS,
    device_topic,
    is_state_topic,
    leaf,
    split_device,
)

REQUEST_WANTED = "tc49/schedule/request_wanted"
REVERSAL_WANTED = "tc49/schedule/reversal_wanted"
RUN_WANTED = "tc49/dispatch/run_wanted"
RUN = "tc49/dispatch/state/run"
MOVING = "tc49/dispatch/state/moving"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
POINT_WANTED = "tc49/dispatch/point_wanted"
REORDER_WANTED = "tc49/dispatch/reorder_wanted"
ALLOCATION = "tc49/dispatch/state/allocation"
REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
POINT = "tc49/layout/state/wanted/point"
TRACK = "tc49/layout/state/wanted/track"
SENSOR = "tc49/layout/state/device/sensor"
OBSERVED_POINT = "tc49/layout/state/device/point"
OBSERVED_TRACK = "tc49/layout/state/device/track"
LINK = "tc49/layout/state/device/link"
REFUSED = "tc49/layout/state/device/refused"
MODE_WANTED = "tc49/layout/mode_wanted"
THROTTLE_WANTED = "tc49/layout/throttle_wanted"
MODE = "tc49/layout/state/mode"
TAKE_WANTED = "tc49/layout/take_wanted"
THROTTLE_ALIVE = "tc49/layout/throttle_alive"
TAKEN = "tc49/layout/state/taken"
FUNCTION_WANTED = "tc49/layout/function_wanted"
FUNCTIONS = "tc49/layout/state/functions"
DRIVING_WANTED = "tc49/layout/driving_wanted"
DRIVING = "tc49/layout/state/driving"
POWER_WANTED = "tc49/layout/power_wanted"
POWER = "tc49/layout/state/power"
RAILROAD_WANTED = "tc49/layout/railroad_wanted"
RAILROAD = "tc49/layout/state/railroad"
CLOCK = "tc49/layout/state/clock"
CLOCK_WANTED = "tc49/layout/clock_wanted"
SETTINGS = "tc49/layout/state/settings"
SETTINGS_WANTED = "tc49/layout/settings_wanted"
TEXT = "tc49/ui/state/text"
TOGGLE = "tc49/ui/state/toggle"
BUTTON = "tc49/ui/button"


@pytest.mark.parametrize("topic", sorted(TOPICS))
def test_every_declared_row_keeps_the_answer_it_has_today(topic: str) -> None:
    """The rule moved from the second level from the end to the third from
    the start, and no row in the inventory notices: none of them carries a
    level past its own name."""
    assert is_state_topic(topic) == (topic.split("/")[-2] == "state")


def test_an_addressed_device_topic_is_a_state_topic() -> None:
    """Read backwards it would not be, `point` standing where `state` has to
    stand — and its retained value would be dropped on the way out of the
    state file, which is the whole of what a translator finds on connect."""
    assert is_state_topic("tc49/layout/state/wanted/point/5")


def test_a_command_is_not_a_state_topic() -> None:
    assert not is_state_topic("tc49/layout/move")
    assert not is_state_topic("tc49/layout/state")


def test_a_device_address_round_trips() -> None:
    """What a translator does with a topic it hears: name the row, then read
    the address off it and see whether it answers to that one (ADR-0043)."""
    assert split_device(device_topic(POINT, "5")) == (POINT, "5")


def test_an_address_of_several_levels_still_round_trips() -> None:
    """A function is addressed by the decoder and the function number, two
    levels, and the address is what lies under the row however many levels it
    runs to (ADR-0043)."""
    function = "tc49/layout/state/wanted/function"
    assert split_device(device_topic(function, "460", "2")) == (function, "460/2")


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


def test_turning_a_throttle_is_a_pages_to_write() -> None:
    """Turning a throttle is a gesture (#284): a throttle is any number of
    writers — two tabs are two of them — and the row names `layout`, which
    answers them, rather than whoever sent one."""
    assert THROTTLE_WANTED in INBOUND
    assert TOPICS[THROTTLE_WANTED].fields == ("train", "speed", "throttle")


@pytest.mark.parametrize("topic", [RUN_WANTED, RUN, MODE_WANTED, MODE])
def test_the_run_and_a_trains_mode_have_left_the_contract(topic: str) -> None:
    """Power's three values replace the run, and the railroad's one driving
    mode with a throttle's take replaces a train's mode (ADR-0078, ADR-0079),
    so neither the gestures nor the state rows they settled remain (#834)."""
    assert topic not in TOPICS


def test_one_throttle_holds_a_train_and_layout_states_which() -> None:
    """A throttle takes a train, says it is still there, and turns it, each
    naming itself by the id its page minted (ADR-0079): gestures any page
    may write. Which throttle holds which train is `layout`'s state and no
    page writes it."""
    assert {TAKE_WANTED, THROTTLE_ALIVE} <= INBOUND
    assert TOPICS[TAKE_WANTED].fields == ("train", "throttle")
    assert TOPICS[THROTTLE_ALIVE].fields == ("throttle",)
    assert TOPICS[TAKEN].fields == (AT, "taken")
    assert TAKEN not in INBOUND


def test_a_throttle_switches_a_function_and_layout_states_which_are_on() -> None:
    """A throttle switches one of its train's functions by the name the
    catalogue gives it (#849): a gesture any page may write. Which of each
    train's functions are on is `layout`'s state and no page writes it."""
    assert FUNCTION_WANTED in INBOUND
    assert TOPICS[FUNCTION_WANTED].fields == ("train", "throttle", "function", "on")
    assert is_state_topic(FUNCTIONS)
    assert FUNCTIONS.startswith("tc49/layout/")
    assert TOPICS[FUNCTIONS].fields == (AT, "functions")
    assert FUNCTIONS not in INBOUND


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


def test_the_driving_mode_is_a_gesture_and_layouts_state() -> None:
    """The railroad's one driving mode (ADR-0079): a page asks for it on an
    event row carrying the one field `driving`, and `layout`, which answers,
    states it on a row no page writes."""
    assert DRIVING_WANTED in INBOUND
    assert TOPICS[DRIVING_WANTED].fields == ("driving",)
    assert TOPICS[DRIVING].fields == (AT, "driving")
    assert DRIVING not in INBOUND


def test_whether_anything_is_moving_is_the_dispatchers_state() -> None:
    """`layout` ends a drain once nothing is moving, and the dispatcher, which
    knows what is crossing, states it on a row of its own that no
    page writes (ADR-0078)."""
    assert TOPICS[MOVING].fields == (AT, "moving")
    assert is_state_topic(MOVING)
    assert MOVING not in INBOUND


def test_the_railroad_a_person_loads_is_a_gesture_of_its_own() -> None:
    """Which railroad the apps run is chosen while they run (ADR-0060): an
    event row a page may write, carrying the one field `railroad`. It is
    `layout`'s because the binding of the layout interface that is running
    answers it — the one app bound to a railroad — and the state row it
    settles stays that app's alone, so no page can say which railroad is
    loaded."""
    assert RAILROAD_WANTED in INBOUND
    assert TOPICS[RAILROAD_WANTED].fields == ("railroad",)
    assert TOPICS[RAILROAD].fields == (AT, "name", "built")
    assert RAILROAD not in INBOUND


def test_a_person_cancels_and_reorders_one_request_by_id() -> None:
    """The waiting requests are a list a person orders (ADR-0080): a page
    cancels one request by its id, and moves one in front of another, or to
    the end with `null`. The list itself is the dispatcher's state and no
    page writes it."""
    assert {CANCEL_WANTED, REORDER_WANTED} <= INBOUND
    assert TOPICS[CANCEL_WANTED].fields == ("id",)
    assert TOPICS[REORDER_WANTED].fields == ("id", "before")
    assert ALLOCATION not in INBOUND


def test_a_request_may_follow_an_earlier_one_of_its_train() -> None:
    """A train's later request starts where its earlier one ends (#820):
    `after` names the request it follows, and the request then carries no
    departure end of its own. The scheduler composes it, so no page writes
    it."""
    assert TOPICS[REQUEST_SUBMITTED].fields == (
        "id",
        "train",
        "depart",
        "dest",
        "after",
    )
    assert REQUEST_SUBMITTED not in INBOUND


def test_the_inbound_topics_are_the_inventorys_marked_rows() -> None:
    """What a broker's ACL would grant a page is the inventory's
    browser-writable rows (#263): the set is read off the rows' marks rather
    than off a prefix, a topic naming the component that responds to it.

    The equality below is where widening stops being silent (#158). Marking a
    row grants every page the write — with anonymous clients a broker cannot
    tell a page from an app (ADR-0059, decision 4) — so pinning the set
    exactly means a new mark fails here instead, and whoever adds it grants
    the write deliberately by naming it. Do not relax this to a subset check.

    Gestures, never requests: `tc49/dispatch/request_submitted` carries no
    mark, which is what leaves the scheduler the single minter of ids
    (ADR-0036)."""
    assert INBOUND == {
        REQUEST_WANTED,
        REVERSAL_WANTED,
        PLACEMENT_WANTED,
        CANCEL_WANTED,
        REORDER_WANTED,
        POINT_WANTED,
        THROTTLE_WANTED,
        POWER_WANTED,
        RAILROAD_WANTED,
        DRIVING_WANTED,
        CLOCK_WANTED,
        TAKE_WANTED,
        THROTTLE_ALIVE,
        FUNCTION_WANTED,
        SETTINGS_WANTED,
    }
    assert not any(is_state_topic(topic) for topic in INBOUND)


def test_layout_states_the_fast_clock() -> None:
    """The time of day and the speed-up, `layout`'s state and no page's
    (ADR-0090)."""
    assert TOPICS[CLOCK].fields == (AT, "time", "speed_up")
    assert CLOCK not in INBOUND


def test_a_person_sets_the_fast_clock_from_any_page() -> None:
    """A time of day, a speed-up, or both: a gesture, so a page may write it
    (ADR-0090, decision 2)."""
    assert TOPICS[CLOCK_WANTED].fields == ("time", "speed_up")
    assert CLOCK_WANTED in INBOUND


def test_the_settings_row_says_the_gap_the_speeds_and_the_throttle_silence() -> None:
    """Every field always present: the railroad's point gap and speeds, and
    the installation's throttle silence (#1125, #1130)."""
    assert TOPICS[SETTINGS].fields == (AT, "point_gap", "speeds", "throttle_silence")
    assert SETTINGS not in INBOUND


def test_a_person_sets_the_railroads_settings_from_any_page() -> None:
    """The point gap, the speeds, the throttle silence, any of them: a
    gesture, so a page may write it (#1126, #1131)."""
    assert TOPICS[SETTINGS_WANTED].fields == ("point_gap", "speeds", "throttle_silence")
    assert SETTINGS_WANTED in INBOUND


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
    assert DEVICE_TOPICS[OBSERVED_TRACK].fields == (AT, "power", "reason")
    assert DEVICE_TOPICS[LINK].fields == (AT, "id", "link", "detail")
    assert DEVICE_TOPICS[REFUSED].fields == (AT, "id", "addr", "detail")


def test_a_sensor_is_addressed_by_the_block_end_it_watches() -> None:
    """`<block>.<end>` and never a camera's own identifier (#194), one topic
    per sensor and never a whole-railroad map: a map would make one camera the
    writer of every sensor on the railroad, and a second camera could then not
    join (ADR-0035)."""
    assert device_topic(SENSOR, "A1.b") == "tc49/layout/state/device/sensor/A1.b"
    assert split_device("tc49/layout/state/device/sensor/A1.b") == (SENSOR, "A1.b")


def test_a_link_is_keyed_by_whatever_the_publisher_calls_itself() -> None:
    """A participant that knows it cannot reach its hardware says so
    (ADR-0050), and the row is keyed so that a second participant's `up` does
    not erase the first's `down`. The key is the publisher's own id — it
    appears in no drawing, no configuration and no list of ours — and comes
    back as `id` rather than `addr`, there being no device at the far end of
    it (ADR-0059)."""
    assert split_device(device_topic(LINK, "the shed")) == (LINK, "the shed")
    assert DEVICE_TOPICS[LINK].address == "id"


def test_a_refusal_is_keyed_by_the_publisher_and_not_by_the_device() -> None:
    """The row `device/link` is keyed the same way and for a reason of its
    own: a refusal is the publisher's report on its own last exchange rather
    than a state of the thing addressed, so keying it by device address would
    ask a translator to remember which addresses are refusing and when they
    stop — the table no translator holds (ADR-0063). The address the refused
    command named rides in the payload as ``addr`` and is optional, a refusal
    that had no address having none to give."""
    assert split_device(device_topic(REFUSED, "the shed")) == (REFUSED, "the shed")
    assert DEVICE_TOPICS[REFUSED].address == "id"


def test_the_two_halves_of_the_vocabulary_are_named_apart() -> None:
    """The same turnout answers on both, and a trace line records the row
    rather than the leaf, so `wanted/point` and `device/point` are two names
    for two things and neither hides the other (ADR-0043)."""
    assert DEVICE_TOPICS[POINT].fields == DEVICE_TOPICS[OBSERVED_POINT].fields
    assert POINT != OBSERVED_POINT
    assert split_device(device_topic(OBSERVED_POINT, "5")) == (OBSERVED_POINT, "5")


def test_no_device_row_is_browser_writable() -> None:
    """Every one of them is a state topic, and concurrent writers may not
    write one (ADR-0035)."""
    assert all(is_state_topic(key) for key in DEVICE_TOPICS)
    assert not any(row.browser for row in DEVICE_TOPICS.values())


def test_names_are_unique_across_the_three_mappings() -> None:
    """The trace records one name per row in its `event` field, so two rows
    sharing one could not be told apart there — and the device rows are named
    by their key past `tc49/layout/state/`. A widget row is named by its key
    past `tc49/ui/`, which is the namespace the widget's own name hangs off."""
    names = (
        [leaf(topic) for topic in TOPICS]
        + [key.removeprefix(DEVICE_PREFIX) for key in DEVICE_TOPICS]
        + [key.removeprefix("tc49/ui/") for key in WIDGET_TOPICS]
    )
    assert len(names) == len(set(names))


def test_a_text_widgets_row_is_state_any_writer_with_no_fields() -> None:
    """The text a widget shows is retained, so a page opened later shows it,
    and is raw text control defines no field of (ADR-0087 decisions 3 and 4).
    It carries no browser mark: no page writes a text row."""
    assert WIDGET_TOPICS[TEXT].fields == ()
    assert not WIDGET_TOPICS[TEXT].browser
    assert is_state_topic(TEXT)


def test_a_text_widgets_topic_ends_in_its_name() -> None:
    """The name is a level past the row's key, as an address is past a device
    row's, and the topic stays a state topic (ADR-0087 decision 2)."""
    assert is_state_topic(TEXT + "/current")


def test_a_toggles_row_is_state_browser_writable_with_no_fields() -> None:
    """A toggle's position is retained, so a page opened later and a listener
    that restarts both find it, and a page writes it when a person presses the
    toggle: the one state row with the browser mark (ADR-0087 decision 3). Its
    payload is the toggle's on or off payload, raw (decision 4)."""
    assert WIDGET_TOPICS[TOGGLE].fields == ()
    assert WIDGET_TOPICS[TOGGLE].browser
    assert is_state_topic(TOGGLE + "/lights")


def test_the_toggle_row_stays_out_of_inbound() -> None:
    """`INBOUND` is the whole topics a page writes, read off `TOPICS`; the
    toggle and button rows are patterns the drawing completes, so their marks
    are read off `WIDGET_TOPICS` instead."""
    assert not [topic for topic in INBOUND if topic.startswith("tc49/ui/")]


def test_a_buttons_row_is_an_event_browser_writable_with_no_fields() -> None:
    """A press is an event and is not kept, and a page writes it when a person
    presses the button (ADR-0087 decisions 2 and 3). Its payload is the one
    typed for the button, raw (decision 4)."""
    assert WIDGET_TOPICS[BUTTON].fields == ()
    assert WIDGET_TOPICS[BUTTON].browser
    assert not is_state_topic(BUTTON + "/horn")


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


def test_layout_is_asked_to_take_a_move_back_and_says_when_it_has() -> None:
    """A cancel landing on a move nothing has driven ends at once (#1068): the
    dispatcher asks, `layout` answers. Neither is a page's to write."""
    for topic in ("tc49/layout/withdraw_wanted", "tc49/layout/move_withdrawn"):
        assert TOPICS[topic].fields == ("train", "transit", "into")
        assert topic not in INBOUND
        assert not is_state_topic(topic)
