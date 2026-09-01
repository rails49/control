"""The state leaves the browser knows, against the inventory's state rows.

The panel guards a state topic's ordering as the dispatcher does (#240), and
it has to name the state leaves to do it: the relay hands a page `{topic,
payload}` and the model keeps the leaf alone, so `ui/src/model/trace.ts`
carries its own list. A second copy of a contract drifts unless something
fails when it does, and this is that something — the list is read out of the
TypeScript and compared with `tc49.lib.inventory`.

A test rather than a generated file, unlike the rejection reasons: the list
is eight names that move when the contract does, and what is worth pinning is
that the two agree, not who typed them.
"""

import re
from pathlib import Path

from tc49.lib.inventory import TOPICS, is_state_topic, leaf
from tests.harness import ROOT

TRACE_TS = Path("ui/src/model/trace.ts")

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
    """The device rows are not among them and are not missing either: a
    device topic is named by its row and the address under it rather than by
    a leaf, and no view reads one (ADR-0043)."""
    assert declared() == {
        leaf(topic) for topic in TOPICS if is_state_topic(topic)
    }, f"{TRACE_TS} and tc49.lib.inventory disagree about the state topics"
