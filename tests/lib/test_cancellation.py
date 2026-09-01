"""The cancellation reason set every reader answers to (#271)."""

import json

from tc49.lib.cancellation import Reason


def test_a_reason_crosses_the_bus_as_its_plain_name() -> None:
    """What the dispatcher publishes is read by a browser, so the value on
    the wire has to be the name itself and not a Python repr of it. The
    trace tap and the bridge both go through `json.dumps`."""
    assert json.dumps({"reason": Reason.REVOKED}) == '{"reason": "revoked"}'


def test_a_reason_compares_equal_to_the_name_a_payload_carries() -> None:
    """A payload that came back from JSON holds a plain string, and every
    reader compares it against the set without converting first."""
    assert json.loads('"displaced"') == Reason.DISPLACED


def test_the_three_reasons_are_the_whole_set() -> None:
    """One gesture revokes a request; the other two are the two directions
    of a placement (ADR-0039, ADR-0049)."""
    assert [reason.value for reason in Reason] == ["revoked", "removed", "displaced"]
