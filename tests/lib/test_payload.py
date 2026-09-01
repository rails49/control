"""Reading a payload from outside, in the one place both apps read one (#127)."""

from tc49.lib.inventory import HELD, OFF, ON, RUNNING, STOPPED
from tc49.lib.payload import (
    Chosen,
    Gesture,
    Grant,
    Placement,
    chosen,
    gesture,
    grant,
    named_train,
    occupancy,
    placement,
    power,
    run_state,
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
    """The whole payload is which of the two the operator pressed for: a
    hold takes the brake off granting, a release puts it back (#152)."""
    assert run_state({"run": "held"}) == HELD
    assert run_state({"run": "running"}) == RUNNING


def test_a_payload_naming_no_run_state_reads_as_none() -> None:
    """A third value is not a third state. The topic carries an enum rather
    than a boolean so the drain can add `draining` later, and until it does
    anything else is dropped — a gesture has no id to answer to (ADR-0034)."""
    refused: list[object] = [
        "held",  # not an object at all
        ["held"],  # nor a list of its fields
        {},  # no run
        {"run": None},
        {"run": "draining"},  # the third value, not this issue's (#123)
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
