"""The rejection reason set both sides answer to (#126)."""

import json

from tc49.lib.rejection import GENERATED, Reason, render
from tests.harness import ROOT


def test_a_reason_crosses_the_bus_as_its_plain_name() -> None:
    """What the dispatcher publishes is read by a browser, so the value on
    the wire has to be the name itself and not a Python repr of it. The
    trace tap and the bridge both go through `json.dumps`."""
    assert json.dumps({"reason": Reason.NO_FIT}) == '{"reason": "no_fit"}'


def test_a_reason_compares_equal_to_the_name_a_payload_carries() -> None:
    """A payload that came back from JSON holds a plain string, and every
    reader compares it against the set without converting first."""
    assert json.loads('"wrong_origin"') == Reason.WRONG_ORIGIN


def test_the_committed_file_is_current() -> None:
    """The whole point of generating it: the panel's wording table is keyed
    by what this file says, so a stale one is a reason nobody worded."""
    assert (ROOT / GENERATED).read_text() == render(), "run `tc49 generate`"


def test_every_reason_is_rendered_as_a_member_of_the_union() -> None:
    generated = render()
    for reason in Reason:
        assert f'\n  | "{reason}"' in generated
