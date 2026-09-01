"""The inventory's own rules: what marks a state topic, and the device rows
the layout writes under an address (SYSTEM.md, rules 2 and 3; ADR-0043)."""

import pytest

from tc49.lib.inventory import TOPICS, is_state_topic


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
