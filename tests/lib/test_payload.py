"""Reading a payload from outside, in the one place both apps read one (#127)."""

from tc49.lib.inventory import (
    AUTOMATIC,
    DRAINING,
    HELD,
    MANUAL,
    OFF,
    ON,
    RUNNING,
    STOPPED,
)
from tc49.lib.layout import Point
from tc49.lib.payload import (
    Alignment,
    Chosen,
    Command,
    Gesture,
    Grant,
    Mode,
    Ordering,
    Picture,
    Placement,
    Throttle,
    alignment,
    chosen,
    command,
    commanded_power,
    desired_aspect,
    desired_function,
    desired_position,
    desired_speed,
    detected,
    gesture,
    grant,
    granted_aspect,
    kept_allocation,
    kept_facing,
    link_up,
    named_train,
    occupancy,
    placement,
    power,
    reported_reason,
    run_state,
    shown_aspects,
    stamp,
    wanted_mode,
    wanted_throttle,
)


def test_a_well_formed_payload_reads_as_the_gesture_it_names() -> None:
    """The two fields a gesture is: which train, and the arrival ends it is
    wanted at. A request carries them too, alongside what the scheduler adds."""
    assert gesture({"train": "freight_1", "dest": ["dn_e.A", "dn_e.B"]}) == Gesture(
        "freight_1", ("dn_e.A", "dn_e.B")
    )


def test_a_payload_naming_no_gesture_reads_as_none() -> None:
    """Every shape either app refuses today, refused in the one place both
    now read: the answer is None and never an exception (ADR-0034)."""
    refused: list[object] = [
        "freight_1 to yard_e",  # not an object at all
        ["freight_1", ["yard_e.A"]],  # nor a list of its fields
        {"dest": ["yard_e.A"]},  # no train
        {"train": "freight_1"},  # no arrival ends
        {"train": None, "dest": ["yard_e.A"]},  # a train that is not a name
        {"train": "freight_1", "dest": "yard_e.A"},  # one end, not a set of them
        {"train": "freight_1", "dest": ["yard_e.A", 7]},  # not all ends
    ]
    for payload in refused:
        assert gesture(payload) is None, payload


def test_a_reversal_reads_as_the_train_it_names() -> None:
    """A train is the whole payload: turning around at rest moves nothing, so
    there is no destination and no departure end to state (#124)."""
    assert named_train({"train": "freight_1"}) == "freight_1"
    assert named_train({"train": "freight_1", "dest": ["yard_e.A"]}) == "freight_1"


def test_a_payload_naming_no_reversal_reads_as_none() -> None:
    refused: list[object] = [
        "freight_1",  # not an object at all
        ["freight_1"],  # nor a list of its fields
        {},  # no train
        {"train": None},  # a train that is not a name
        {"train": 7},
    ]
    for payload in refused:
        assert named_train(payload) is None, payload


def test_a_granted_move_reads_as_the_train_the_transit_and_the_block() -> None:
    """The three fields a consumer of the grant acts on. The transit stays
    qualified: splitting it is the driver's and reading the end it crosses is
    the layout's, and neither is a question about the payload."""
    assert grant(
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "transit": "west_ladder.to_dn",
            "into": "dn_w",
            "aspect": "clear",
        }
    ) == Grant("freight_1", "west_ladder.to_dn", "dn_w")


def test_a_payload_naming_no_granted_move_reads_as_none() -> None:
    """An announcement is read exactly as a gesture is: the bus does not
    authenticate a publisher, so a frame claiming to be the dispatcher's is
    read and never trusted (SYSTEM.md, rule 4)."""
    refused: list[object] = [
        "freight_1 into dn_w",  # not an object at all
        ["freight_1", "west_ladder.to_dn", "dn_w"],  # nor a list of its fields
        {"transit": "west_ladder.to_dn", "into": "dn_w"},  # no train
        {"train": "freight_1", "into": "dn_w"},  # no transit
        {"train": "freight_1", "transit": "west_ladder.to_dn"},  # no block entered
        {"train": "freight_1", "transit": None, "into": "dn_w"},
        {"train": "freight_1", "transit": "west_ladder.to_dn", "into": 7},
    ]
    for payload in refused:
        assert grant(payload) is None, payload


def test_the_aspect_a_grant_shows_reads_beside_the_move_it_authorises() -> None:
    """The field the driver adds to the three, read on its own so that a
    scheduler wanting only the facing is not made to care about it (#283).

    Every aspect reads, `stop` included: what a name is worth is the driver's
    mapping and not this reading, and a payload holds names.
    """
    granted = {
        "id": "freight_1-1",
        "train": "freight_1",
        "transit": "west_ladder.to_dn",
        "into": "dn_w",
    }
    for aspect in ("clear", "caution", "stop", "unheard_of"):
        assert granted_aspect({**granted, "aspect": aspect}) == aspect


def test_a_payload_showing_no_aspect_reads_as_none() -> None:
    """A grant is still a grant with an unreadable aspect — `grant` reads the
    three names off the last of these — and it is the driver, which has no
    speed to command, that turns the None into a dropped frame."""
    refused: list[object] = [
        "clear",  # not an object at all
        ["clear"],
        {},
        {"aspect": None},
        {"aspect": 1.0},
        {"aspect": ["clear"]},
        {"train": "freight_1", "transit": "west_ladder.to_dn", "into": "dn_w"},
    ]
    for payload in refused:
        assert granted_aspect(payload) is None, payload


def test_a_chosen_route_reads_as_the_id_and_the_names_in_order() -> None:
    """The alternating sequence, whole and unexamined: which of it a consumer
    needs is its own, and a single block is the degenerate already-there
    case."""
    assert chosen(
        {
            "id": "freight_1-1",
            "route": ["yard_w", "west_ladder.to_dn", "dn_w"],
            "k_tried": 2,
        }
    ) == Chosen("freight_1-1", ("yard_w", "west_ladder.to_dn", "dn_w"))
    assert chosen({"id": "freight_1-1", "route": ["yard_w"], "k_tried": 0}) == Chosen(
        "freight_1-1", ("yard_w",)
    )


def test_a_payload_naming_no_chosen_route_reads_as_none() -> None:
    """Whether the names name anything, and whether they alternate, are the
    layout's questions and the chooser's: a reader that asked them would be
    re-deriving the route rather than reading it."""
    refused: list[object] = [
        "yard_w",  # not an object at all
        {"route": ["yard_w"]},  # no id to correlate by
        {"id": "", "route": ["yard_w"]},  # nor an id that says anything
        {"id": "freight_1-1"},  # no route
        {"id": "freight_1-1", "route": "yard_w"},  # one name, not a sequence
        {"id": "freight_1-1", "route": ["yard_w", 7]},  # not all names
    ]
    for payload in refused:
        assert chosen(payload) is None, payload


def test_a_run_gesture_reads_as_the_state_it_asks_for() -> None:
    """The whole payload is which of the three the operator pressed for: a
    hold takes the brake off granting, a release puts it back (#152), and the
    drain asks for neither — launch nothing more and settle at `held` when
    what is moving has finished (#294)."""
    assert run_state({"run": "held"}) == HELD
    assert run_state({"run": "running"}) == RUNNING
    assert run_state({"run": "draining"}) == DRAINING


def test_a_payload_naming_no_run_state_reads_as_none() -> None:
    """A fourth value is not a fourth state. The topic carries an enum rather
    than a boolean, which is what let the drain add a third word to it, and
    anything outside the three is dropped — a gesture has no id to answer to
    (ADR-0034)."""
    refused: list[object] = [
        "held",  # not an object at all
        ["held"],  # nor a list of its fields
        {},  # no run
        {"run": None},
        {"run": "drained"},  # the drain's own word misspelt is not the drain
        {"run": True},  # the boolean the topic deliberately is not
    ]
    for payload in refused:
        assert run_state(payload) is None, payload


def test_a_power_payload_reads_as_the_value_the_layout_states() -> None:
    """The three values of the topic, each read as itself: the dispatcher
    branches on "not `on`", and the panel is where `stopped` and `off` are
    told apart (ADR-0041)."""
    assert power({"power": "on"}) == ON
    assert power({"power": "stopped"}) == STOPPED
    assert power({"power": "off"}) == OFF


def test_a_power_payload_that_cannot_be_read_reads_as_off() -> None:
    """The opposite direction from every other reader here, and that is the
    point. A dropped hold-or-release gesture means doing nothing; a dropped
    power value would mean **not holding**, leaving the run committing over
    track whose state could not be read. So an unreadable payload is one of
    the "anything but `on`" cases the contract already has (DISPATCH.md),
    and `off` is which of them because the dispatcher does not tell them
    apart (#175)."""
    unreadable: list[object] = [
        "off",  # not an object at all
        ["off"],  # nor a list of its fields
        {},  # no power
        {"power": None},
        {"power": 42},  # not a string
        {"power": "sideways"},  # a value outside the closed set
    ]
    for payload in unreadable:
        assert power(payload) == OFF, payload


def test_a_power_gesture_reads_as_the_value_it_asks_for() -> None:
    """The same closed set in the command direction (ADR-0051): a page asks
    for one of the three and `layout` writes the word it was given."""
    assert commanded_power({"power": "on"}) == ON
    assert commanded_power({"power": "stopped"}) == STOPPED
    assert commanded_power({"power": "off"}) == OFF


def test_a_power_gesture_that_cannot_be_read_is_dropped() -> None:
    """The other direction from the reading of the same axis, and the reason
    is which way a failure falls: an unreadable *reading* must hold the run,
    so it answers `off`, while an unreadable *command* answering `off` would
    cut the supply on a malformed frame — `layout` writing `off` of its own
    accord, which it never does (#287)."""
    refused: list[object] = [
        "on",  # not an object at all
        ["on"],  # nor a list of its fields
        {},  # no power
        {"power": None},
        {"power": 1},  # not a string
        {"power": "ON"},  # a value outside the closed set
    ]
    for payload in refused:
        assert commanded_power(payload) is None, payload


def test_a_mode_gesture_reads_as_the_train_and_the_word_it_names() -> None:
    """Taking a train in a throttle and giving it back: one gesture that names
    where the mode should stand rather than asking for a change (#284)."""
    assert wanted_mode({"train": "freight_1", "mode": "manual"}) == Mode(
        "freight_1", MANUAL
    )
    assert wanted_mode({"train": "freight_1", "mode": "automatic"}) == Mode(
        "freight_1", AUTOMATIC
    )


def test_a_null_train_is_every_train_at_once() -> None:
    """The gesture a person makes to a railroad rather than to the train they
    have picked, and an explicit `null` is how a page says it."""
    assert wanted_mode({"train": None, "mode": "manual"}) == Mode(None, MANUAL)


def test_a_payload_naming_no_mode_reads_as_none() -> None:
    """A third word is dropped whole and the train's mode stays where it was:
    falling to `manual` hands a train to a person who is not there, and
    falling to `automatic` takes one out of the hands of a person who is."""
    refused: list[object] = [
        None,  # no payload at all
        "manual",  # not an object
        {"mode": "manual"},  # no train, where a null one is a statement
        {"train": "freight_1"},  # no mode
        {"train": 1, "mode": "manual"},  # not a name
        {"train": "freight_1", "mode": None},
        {"train": "freight_1", "mode": "Manual"},  # outside the closed set
        {"train": "freight_1", "mode": "held"},  # the run's word, not this one
    ]
    for payload in refused:
        assert wanted_mode(payload) is None, payload


def test_a_throttle_gesture_reads_as_the_train_and_the_signed_speed() -> None:
    """Signed for the train and not for a locomotive: positive is the way the
    train points, and which decoder that reaches is `layout`'s."""
    assert wanted_throttle({"train": "freight_1", "speed": 0.4}) == Throttle(
        "freight_1", 0.4
    )
    assert wanted_throttle({"train": "freight_1", "speed": -1}) == Throttle(
        "freight_1", -1.0
    )


def test_a_payload_turning_no_throttle_reads_as_none() -> None:
    """A throttle is a speed, so a frame that states none turns nothing and
    there is nothing left to act on."""
    refused: list[object] = [
        None,
        0.4,  # not an object
        {"speed": 0.4},  # no train
        {"train": "freight_1"},  # no speed
        {"train": "freight_1", "speed": None},
        {"train": "freight_1", "speed": True},  # a boolean is not a speed
        {"train": "freight_1", "speed": "0.4"},  # nor a string
    ]
    for payload in refused:
        assert wanted_throttle(payload) is None, payload


def test_an_occupancy_frame_reads_as_the_block_it_names() -> None:
    """A block is the whole payload: which of the two readings it is, is the
    leaf it arrived on and not a field (SYSTEM.md, event inventory)."""
    assert occupancy({"block": "up_w"}) == "up_w"


def test_a_payload_naming_no_block_reads_as_none() -> None:
    """The opposite direction from `power` on the same role, which is why
    both are read here rather than one: a power value that cannot be read must
    still hold the run, a reading that cannot be read is dropped. Why the two
    fail in opposite directions is SYSTEM.md, sole payload authority."""
    refused: list[object] = [
        None,  # no payload at all
        "up_w",  # not an object either
        ["up_w"],  # nor a list of its fields
        {},  # no block
        {"block": None},
        # The shape that raised nothing and poisoned `reported` with a key
        # that is not a block name (#181).
        {"block": 42},
    ]
    for payload in refused:
        assert occupancy(payload) is None, payload


def test_a_sensor_row_reads_as_the_level_the_detector_states() -> None:
    """Presence is a level and the row states one of three words for it. What
    a block's two of them become is `layout`'s fold (#288)."""
    for level in ("occupied", "clear", "unknown"):
        assert detected({"addr": "up_w.B", "occupancy": level}) == level


def test_a_sensor_row_that_cannot_be_read_is_no_information_about_that_end() -> None:
    """The third reader that answers a value rather than None, falling the way
    its own axis does: `unknown` is what the contract calls no information, and
    a frame that cannot be read carries none (#181, #288)."""
    refused: list[object] = [
        None,  # no payload at all
        "occupied",  # not an object either
        ["occupied"],  # nor a list of its fields
        {},  # no occupancy
        {"addr": "up_w.B"},  # addressed and silent
        {"addr": "up_w.B", "occupancy": None},
        {"addr": "up_w.B", "occupancy": "OCCUPIED"},  # not the contract's word
        {"addr": "up_w.B", "occupancy": True},
    ]
    for payload in refused:
        assert detected(payload) == "unknown", payload


def test_a_reason_is_read_where_one_is_given_and_never_demanded() -> None:
    """Free text for a person, optional, and only ever beside `unknown`:
    nothing branches on it, so a reason that is not a string is no reason."""
    assert reported_reason({"occupancy": "unknown", "reason": "not calibrated"}) == (
        "not calibrated"
    )
    for payload in (None, "why", {}, {"occupancy": "unknown"}, {"reason": 7}):
        assert reported_reason(payload) is None, payload


def test_a_placement_reads_as_the_train_and_the_block_it_names() -> None:
    """Where a train actually stands, said by the person who can see it. No
    facing: the gesture names a train and a block, and `reversal_wanted` is
    the correction if it lands the wrong way round (#152)."""
    assert placement({"train": "freight_1", "block": "up_w"}) == Placement(
        "freight_1", "up_w"
    )


def test_a_null_block_is_a_train_off_the_layout() -> None:
    """One gesture in two directions: nowhere is one of the places a train can
    be said to be, and an explicit `null` is how a page says it (ADR-0039)."""
    assert placement({"train": "freight_1", "block": None}) == Placement(
        "freight_1", None
    )


def test_a_payload_naming_no_placement_reads_as_none() -> None:
    refused: list[object] = [
        "freight_1 in up_w",  # not an object at all
        ["freight_1", "up_w"],  # nor a list of its fields
        {"block": "up_w"},  # no train
        # A frame that lost the key: not a train taken off the layout, which
        # is what makes the key's presence load-bearing here.
        {"train": "freight_1"},
        {"train": 7, "block": "up_w"},
        {"train": "freight_1", "block": ["up_w"]},
    ]
    for payload in refused:
        assert placement(payload) is None, payload


def test_a_command_reads_as_the_train_the_transit_and_the_block_entered() -> None:
    """The command's own shape, which is the grant's with the transit split:
    the connection stands beside a bare transit, and whether the two name
    anything on this railroad is the layout's question and not this one."""
    assert command(
        {
            "train": "freight_1",
            "connection": "west_ladder",
            "transit": "to_dn",
            "into": "dn_w",
        }
    ) == Command("freight_1", "west_ladder", "to_dn", "dn_w")


def test_a_command_carries_the_speed_it_states_and_none_where_it_states_one_badly() -> (
    None
):
    """The speed rides beside the names rather than with them (#283): a frame
    stating none, or stating something that is no number, still commands a
    move, and what a move with no speed is worth is the binding's. A boolean
    is not a speed — JSON `true` is an `int` in Python and would otherwise be
    read as full speed."""
    named = {
        "train": "freight_1",
        "connection": "west_ladder",
        "transit": "to_dn",
        "into": "dn_w",
    }
    assert command(named | {"speed": 0.4}) == Command(
        "freight_1", "west_ladder", "to_dn", "dn_w", 0.4
    )
    for stated in ({}, {"speed": True}, {"speed": "fast"}, {"speed": None}):
        read = command(named | stated)
        assert read is not None and read.speed is None, stated


def test_a_payload_commanding_no_move_reads_as_none() -> None:
    """A command is read exactly as an announcement is: `tc49/layout/move`
    names the layout interface because the interface responds to it, and
    anyone at all can publish a frame claiming to be the driver's (SYSTEM.md,
    rule 4)."""
    refused: list[object] = [
        "freight_1 into dn_w",  # not an object at all
        ["freight_1", "west_ladder", "to_dn", "dn_w"],  # nor a list of its fields
        {"connection": "west_ladder", "transit": "to_dn", "into": "dn_w"},  # no train
        {"train": "freight_1", "transit": "to_dn", "into": "dn_w"},  # no connection
        {"train": "freight_1", "connection": "west_ladder", "into": "dn_w"},
        {"train": "freight_1", "connection": "west_ladder", "transit": "to_dn"},
        {"train": None, "connection": "west_ladder", "transit": "to_dn", "into": "d"},
        {"train": "f", "connection": ["west_ladder"], "transit": "to_dn", "into": "d"},
        {"train": "f", "connection": "west_ladder", "transit": 7, "into": "dn_w"},
        {"train": "f", "connection": "west_ladder", "transit": "to_dn", "into": None},
    ]
    for payload in refused:
        assert command(payload) is None, payload


def test_an_alignment_reads_as_the_transit_it_names_and_the_points_it_carries() -> None:
    """The command that sets the route: a connection, a bare transit and the
    address-and-position pairs the transit's way needs (ADR-0031). The pairs
    are what was read off the layout, so they read back as what the layout
    holds."""
    assert alignment(
        {
            "connection": "crossover",
            "transit": "up_to_dn",
            "points": [
                {"addr": "dccex/12", "position": "thrown"},
                {"addr": "dccex/13", "position": "closed"},
            ],
        }
    ) == Alignment(
        "crossover",
        "up_to_dn",
        (Point("dccex/12", "thrown"), Point("dccex/13", "closed")),
    )


def test_an_alignment_needing_nothing_thrown_carries_an_empty_list() -> None:
    """`points` is always stated, `[]` where the way crosses no point: the
    document is quiet and the wire explicit, so an absent list is a frame that
    lost a field rather than a way with nothing to throw."""
    assert alignment({"connection": "j", "transit": "ab", "points": []}) == Alignment(
        "j", "ab", ()
    )


def test_a_pair_that_cannot_be_read_fails_the_whole_alignment() -> None:
    """Unlike a retained map, which is read an entry at a time: an alignment
    is one route, and throwing the points that read while dropping the ones
    that did not would set a way half over and let a `move` onto it."""
    half = {
        "connection": "crossover",
        "transit": "up_to_dn",
        "points": [{"addr": "dccex/12", "position": "thrown"}, {"addr": "dccex/13"}],
    }
    assert alignment(half) is None


def test_a_payload_setting_no_route_reads_as_none() -> None:
    refused: list[object] = [
        "crossover.up_to_dn",  # not an object at all
        ["crossover", "up_to_dn"],  # nor a list of its fields
        {"transit": "up_to_dn", "points": []},  # no connection
        {"connection": "crossover", "points": []},  # no transit
        {"connection": "crossover", "transit": "up_to_dn"},  # no points
        {"connection": "crossover", "transit": "up_to_dn", "points": {}},
        {"connection": "crossover", "transit": 7, "points": []},
        {"connection": "crossover", "transit": "up_to_dn", "points": ["dccex/12"]},
        {
            "connection": "crossover",
            "transit": "up_to_dn",
            "points": [{"addr": 12, "position": "thrown"}],
        },
        {
            "connection": "crossover",
            "transit": "up_to_dn",
            "points": [{"addr": "dccex/12", "position": None}],
        },
    ]
    for payload in refused:
        assert alignment(payload) is None, payload


def test_an_aspects_value_reads_as_the_ends_it_shows() -> None:
    """Every signalled end and what stands at it, the whole picture in one
    value: what a late subscriber is owed on connect."""
    assert shown_aspects(
        {"at": 0.0, "aspects": {"up_w.B": "clear", "dn_w.B": "stop"}}
    ) == {"up_w.B": "clear", "dn_w.B": "stop"}


def test_an_aspect_entry_that_cannot_be_read_loses_that_end_and_no_other() -> None:
    """Read an entry at a time, as a retained facing is: the value is one
    session's whole picture of the signals, so an unreadable entry costs that
    end its aspect and leaves the rest standing."""
    assert shown_aspects({"aspects": {"up_w.B": "clear", "dn_w.B": 3}}) == {
        "up_w.B": "clear"
    }


def test_a_value_showing_no_aspects_at_all_reads_as_none() -> None:
    refused: list[object] = [
        "clear",  # not an object at all
        {},  # no aspects
        {"aspects": None},
        {"aspects": ["up_w.B"]},  # not a map
    ]
    for payload in refused:
        assert shown_aspects(payload) is None, payload


def test_a_link_reads_as_up_only_when_it_says_so() -> None:
    """One question, so a boolean: the railroad has power only while every
    link ever seen is up (#287)."""
    assert link_up({"system": "dccex", "link": "up"})
    assert not link_up({"system": "dccex", "link": "down"})


def test_a_link_that_cannot_be_read_is_not_up() -> None:
    """`power`'s direction on the row beside it (#181): a link a consumer
    cannot read is not one it may call good."""
    unreadable: list[object] = [
        "up",  # not an object at all
        {},  # no link
        {"link": None},
        {"link": "UP"},  # a word from outside the pair
        {"system": "dccex"},
    ]
    for payload in unreadable:
        assert not link_up(payload), payload


def test_a_desired_speed_reads_as_the_fraction_it_states() -> None:
    """A fraction of that locomotive's maximum, signed for direction along
    the track, and an integer is a fraction like any other (#289)."""
    assert desired_speed({"addr": "3", "speed": 0.5}) == 0.5
    assert desired_speed({"addr": "3", "speed": -1.0}) == -1.0
    assert desired_speed({"addr": "3", "speed": 0}) == 0.0


def test_a_desired_speed_past_the_range_is_still_read() -> None:
    """The contract states −1.0 … 1.0 and this reader is about shape: what a
    fraction past a locomotive's maximum is worth is the translator's, there
    being nothing above a maximum to ask for."""
    assert desired_speed({"addr": "3", "speed": 4.0}) == 4.0


def test_a_boolean_is_not_a_speed() -> None:
    """Refused ahead of the numeric read, as a stamp is: JSON `true` is an
    `int` here and would otherwise be full speed forward."""
    assert desired_speed({"addr": "3", "speed": True}) is None
    assert desired_speed({"addr": "3", "speed": False}) is None


def test_a_desired_value_that_cannot_be_read_reads_as_none() -> None:
    """A translator answers nothing — it reports observations — so a frame it
    cannot read is dropped, and one that raised would be taken down by
    whatever published it (rule 4)."""
    unreadable: list[object] = [
        "0.5",  # not an object at all
        {},  # no field
        {"speed": None},
        {"speed": "fast"},
    ]
    for payload in unreadable:
        assert desired_speed(payload) is None, payload


def test_the_three_named_desired_values_read_as_the_names_they_carry() -> None:
    """A position, an aspect and a function's value are read as names and
    nothing more: which names mean anything is the contract's for a position,
    a head's wiring for an aspect, and the model's for a function."""
    assert desired_position({"addr": "dccex/5", "position": "thrown"}) == "thrown"
    assert desired_aspect({"addr": "dccex/40", "aspect": "caution"}) == "caution"
    assert desired_function({"addr": "3", "function": "2", "value": "on"}) == "on"


def test_a_named_desired_value_that_is_no_name_reads_as_none() -> None:
    unreadable: list[object] = ["thrown", {}, {"position": None}, {"position": 5}]
    for payload in unreadable:
        assert desired_position(payload) is None, payload
    assert desired_aspect({"addr": "dccex/40"}) is None
    assert desired_function({"addr": "3", "value": 1}) is None


def test_a_retained_facing_reads_as_the_map_it_states() -> None:
    """The scheduler's own last value, handed back at construction by a bus
    binding that outlived it: train to the run it would make across its
    block (#277)."""
    assert kept_facing(
        {"facing": {"freight_1": "yard_w.A-to-B", "express_2": "up_e.B-to-A"}}
    ) == {"freight_1": "yard_w.A-to-B", "express_2": "up_e.B-to-A"}


def test_a_retained_value_stating_no_map_reads_as_none() -> None:
    """Rule 4 exempts no payload for having once been the reader's own: what
    is waiting on a broker can be hand-edited or written by another build, and
    every one of these carrying a value at all was an `AttributeError` out of
    the scheduler's constructor while it subscripted rather than read (#277)."""
    refused: list[object] = [
        None,  # nothing retained under the key
        "yard_w.A-to-B",  # not an object at all
        ["yard_w.A-to-B"],  # nor a list of its entries
        {},  # no facing
        {"facing": None},
        {"facing": "yard_w.A-to-B"},  # a value where a map belongs
        {"facing": ["freight_1"]},  # the trains without their facings
    ]
    for payload in refused:
        assert kept_facing(payload) is None, payload


def test_an_entry_that_cannot_be_read_loses_that_train_and_no_other() -> None:
    """A map is read one train at a time: the whole of a session's facing is
    in this one value, and dropping all of it for one bad entry would lose
    every train a good entry names. Whether a string spells a facing this
    build knows is the layout's question and not asked here — `dn_e.A` is a
    string and reads as one."""
    assert kept_facing(
        {"facing": {"freight_1": 7, "express_2": "up_e.B-to-A", "shunter": None}}
    ) == {"express_2": "up_e.B-to-A"}


def test_a_retained_picture_reads_as_the_two_maps_a_restart_takes() -> None:
    """The dispatcher's own last value, handed back at construction by a bus
    binding that outlived it: where each train stood, and which transit was
    taking it out of there (#278). `locks` and `requests` are in the payload
    and not in the answer — a restart rebuilds the table and comes up with an
    empty queue, so nothing adopts them."""
    assert kept_allocation(
        {
            "trains": {"express_2": "up_w", "freight_1": "dn_e"},
            "crossing": {"freight_1": "crossover.dn_straight"},
            "locks": {"up_w": "express_2"},
            "requests": [{"id": "freight_1-1"}],
        }
    ) == Picture(
        {"express_2": "up_w", "freight_1": "dn_e"},
        {"freight_1": "crossover.dn_straight"},
    )


def test_a_picture_that_states_two_empty_maps_is_still_a_picture() -> None:
    """An idle railroad nothing has placed a train on: the picture states two
    maps and both are empty, which is a picture and not the absence of one.
    The dispatcher does the same with it either way, and the reader still has
    to tell them apart — a value that says nothing about where the trains are
    is not the same claim as one that says nowhere."""
    assert kept_allocation(
        {"trains": {}, "crossing": {}, "locks": {}, "requests": []}
    ) == Picture({}, {})


def test_a_value_stating_no_picture_reads_as_none() -> None:
    """Rule 4 exempts no payload for having once been the reader's own, and
    the moment this one is read is the recovery after a power cut. Every one
    of these was an `AttributeError` out of the dispatcher's constructor
    while it subscripted rather than read (#278) — an app that does not start
    at all, which is worse than a dropped frame.

    Both maps have to be a map: the two are one statement about where the
    railroad stood, and a value carrying half of it was written by something
    other than the contract."""
    refused: list[object] = [
        None,  # nothing retained under the topic
        "up_w",  # not an object at all
        [{"express_2": "up_w"}],  # nor a list of its entries
        {},  # nothing said about anything
        {"crossing": {}},  # no trains
        {"trains": {"express_2": "up_w"}},  # no crossing
        {"trains": None, "crossing": {}},
        {"trains": "up_w", "crossing": {}},  # a value where a map belongs
        {"trains": ["express_2"], "crossing": {}},  # trains without blocks
        {"trains": {}, "crossing": ["freight_1"]},  # trains without transits
    ]
    for payload in refused:
        assert kept_allocation(payload) is None, payload


def test_a_train_a_picture_names_unreadably_loses_itself_and_no_other() -> None:
    """Each map is read one train at a time, as a retained facing is: the
    whole of a session's placement is in this one value, and dropping all of
    it for one bad entry would cold-start every train a good entry names.
    Whether `station_c_2` is a block on this railroad is not asked here — it is a
    string and reads as one, and the dispatcher answers that of its own
    roster and layout."""
    assert kept_allocation(
        {
            "trains": {"express_2": "up_w", "freight_1": 7, "local_3": "station_c_2"},
            "crossing": {"express_2": None, "local_3": "crossover.up_straight"},
        }
    ) == Picture(
        {"express_2": "up_w", "local_3": "station_c_2"},
        {"local_3": "crossover.up_straight"},
    )


# --- the stamp, and the order two values of one topic are kept in (#240) -----

POWER = "tc49/layout/state/power"
OCCUPIED = "tc49/layout/block_occupied"


def test_a_state_payload_states_the_instant_it_was_published_at() -> None:
    """Seconds since the session started, the run clock's own reading. An
    integer reads as one: JSON has one number type and a stamp at a whole
    second is a whole number on the wire."""
    assert stamp({"at": 12.5, "power": ON}) == 12.5
    assert stamp({"at": 3, "power": ON}) == 3.0


def test_a_payload_stating_no_readable_stamp_reads_as_unstamped() -> None:
    """None and never an exception, as every other reader here: the value
    arrives from another process and a reader that subscripted it would be
    taken down by whatever wrote it (rule 4)."""
    refused: list[object] = [
        "on",  # not an object at all
        {"power": ON},  # no stamp
        {"at": None, "power": ON},
        {"at": "12.5", "power": ON},  # a number said in words
        {"at": [12.5], "power": ON},
        {"at": True, "power": ON},  # a boolean is not a stamp
    ]
    for payload in refused:
        assert stamp(payload) is None, payload


def test_a_boolean_stamp_is_unreadable_rather_than_one_second() -> None:
    """The one shape refused ahead of the numeric read. JSON `true` is an
    `int` in Python, so it would otherwise be taken for `1.0` — a real
    instant in a session's first second, and one that would go on refusing
    everything published before it."""
    ordering = Ordering()
    assert ordering.accepts(POWER, {"at": 4.0, "power": ON})
    assert ordering.accepts(POWER, {"at": True, "power": OFF})
    # Unreadable, so unstamped: the value is taken and the held stamp goes
    # with it, rather than `1.0` sitting there refusing the next report.
    assert ordering.accepts(POWER, {"at": 2.0, "power": ON})


def test_the_later_of_two_values_is_the_one_kept() -> None:
    """Whichever order they arrive in, which is the whole point: MQTT
    promises no more than order from one publisher on one topic, and not
    across a reconnect or a retransmission (ADR-0008)."""
    ordering = Ordering()
    assert ordering.accepts(POWER, {"at": 9.0, "power": OFF})
    assert not ordering.accepts(POWER, {"at": 4.0, "power": ON})


def test_an_equal_stamp_replaces() -> None:
    """Two values of one instant are the publisher's own order, which the bus
    has already kept: the second is the later statement and is taken."""
    ordering = Ordering()
    assert ordering.accepts(POWER, {"at": 4.0, "power": ON})
    assert ordering.accepts(POWER, {"at": 4.0, "power": OFF})


def test_an_earlier_stamp_is_ignored_and_nothing_is_raised() -> None:
    """The case the guard exists for is not a fault to report: a value the
    wire handed over late is refused quietly, and the topic goes on."""
    ordering = Ordering()
    assert ordering.accepts(POWER, {"at": 9.0, "power": OFF})
    for _ in range(3):
        assert not ordering.accepts(POWER, {"at": 1.0, "power": ON})
    assert ordering.accepts(POWER, {"at": 9.5, "power": ON})


def test_an_unstamped_value_is_accepted_and_clears_the_held_stamp() -> None:
    """The publisher owns the value, so one carrying no stamp — an older
    build, or a hand-edited file — is taken. Ordering then restarts from the
    next stamped value: keeping the old stamp would leave it refusing values
    whose own stamp is gone."""
    ordering = Ordering()
    assert ordering.accepts(POWER, {"at": 9.0, "power": OFF})
    assert ordering.accepts(POWER, {"power": ON})
    assert ordering.accepts(POWER, {"at": 1.0, "power": OFF})


def test_each_state_topic_is_ordered_against_itself_alone() -> None:
    """The bus promises no ordering between one topic and another, so there
    is a stamp held per topic and never one for the consumer."""
    ordering = Ordering()
    assert ordering.accepts(POWER, {"at": 9.0, "power": OFF})
    assert ordering.accepts("tc49/dispatch/state/run", {"at": 1.0, "run": HELD})


def test_an_event_topic_is_not_ordered_at_all() -> None:
    """Gated on the topic being a state topic and never on what a payload
    happens to carry (SYSTEM.md, rule 2). An event topic reports something
    that happened and is never replayed, so there is no held value for a late
    one to lose to — and a repeated sensor reading must go on arriving."""
    ordering = Ordering()
    for _ in range(3):
        assert ordering.accepts(OCCUPIED, {"block": "up_w"})
    # Even one carrying something that would read as a stamp.
    assert ordering.accepts(OCCUPIED, {"at": 9.0, "block": "up_w"})
    assert ordering.accepts(OCCUPIED, {"at": 1.0, "block": "up_w"})
