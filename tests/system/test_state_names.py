"""The state topics the browser knows, against the inventory's state rows.

The panel guards a state topic's ordering as the dispatcher does (#240), and
it has to name the state topics to do it: the relay hands a page `{topic,
payload}` and the model keeps the topic's name alone, so
`ui/src/model/trace.ts` carries its own list. A second copy of a contract
drifts unless something fails when it does, and this is that something — the
list is read out of the TypeScript and compared with `tc49.lib.inventory`.

A test rather than a generated file, unlike the rejection reasons: the list is
a handful of names that move when the contract does, and what is worth pinning
is that the two agree, not who typed them.
"""

import re
from pathlib import Path

from tc49.lib.inventory import (
    DEVICE_PREFIX,
    DEVICE_TOPICS,
    TOPICS,
    is_state_topic,
    leaf,
)
from tests.harness import ROOT

TRACE_TS = Path("ui/src/model/trace.ts")

READ = {"device/track"}
"""The device rows a view reads, named past ``DEVICE_PREFIX`` the way
``lib.trace`` names one: the observed supply, whose free-text ``reason`` is the
only place a tripped district is said, so the band can show it as a fault
(#602). Device rows are not leaves — the address is trailing levels — so each
is here under the name `Live` gives it, and the rest of the vocabulary is
absent because no view reads it (ADR-0043)."""

DECLARATION = re.compile(
    r"export const STATE_LEAVES: ReadonlySet<string> = new Set\(\[(.*?)\]\)", re.DOTALL
)


def declared() -> set[str]:
    """The leaves `ui/src/model/trace.ts` names."""
    source = (ROOT / TRACE_TS).read_text()
    found = DECLARATION.search(source)
    assert found is not None, f"no STATE_LEAVES declaration in {TRACE_TS}"
    return set(re.findall(r'"([^"]+)"', found.group(1)))


def test_the_browsers_state_leaves_are_the_inventorys_state_rows() -> None:
    """Every transit-level state row, and the device rows a view reads. The
    rest of the device vocabulary is absent and is not missing either: a
    device topic is named by its row and the address under it rather than by
    a leaf, and nothing above the layout interface reads one (ADR-0043)."""
    assert (
        declared() == {leaf(topic) for topic in TOPICS if is_state_topic(topic)} | READ
    ), f"{TRACE_TS} and tc49.lib.inventory disagree about the state topics"


def test_the_device_rows_a_view_reads_are_device_rows() -> None:
    """A name a view reads is a row the inventory declares, so a row that is
    renamed takes this with it rather than leaving the browser ordering a
    topic nothing publishes."""
    assert {DEVICE_PREFIX + name for name in READ} <= set(DEVICE_TOPICS)
