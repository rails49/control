"""Reading a payload from outside, in the one place both apps read one (#127)."""

from tc49.lib.payload import Gesture, gesture, reversal


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
    assert reversal({"train": "freight_1"}) == "freight_1"
    assert reversal({"train": "freight_1", "dest": ["yard_e.A"]}) == "freight_1"


def test_a_payload_naming_no_reversal_reads_as_none() -> None:
    refused: list[object] = [
        "freight_1",  # not an object at all
        ["freight_1"],  # nor a list of its fields
        {},  # no train
        {"train": None},  # a train that is not a name
        {"train": 7},
    ]
    for payload in refused:
        assert reversal(payload) is None, payload
