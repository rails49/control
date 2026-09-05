"""Every topic the glossary names, against the inventory (#433).

`CONTEXT.md` is the canonical glossary and names topics to explain the words
that ride on them; `tc49.lib.inventory` is the list the apps publish and
subscribe. Nothing compared the two, so the glossary could describe a topic
that does not exist. It named `tc49/layout/railroad_wanted` two batches
before the topic reached the inventory — right in advance rather than wrong,
and nothing would have caught it had the topic never arrived.

The shape is `test_state_leaves.py`'s and `test_store_routes_are_proxied.py`'s:
both sides are read at run time and this file carries no copy of either list.
One direction only — a topic the prose names is a topic that exists — and not
the reverse, which would be a much larger claim and a wrong one: the glossary
is about words and not about every row.
"""

import re
from pathlib import Path

from tc49.lib.inventory import DEVICE_TOPICS, TOPICS

GLOSSARY = Path(__file__).resolve().parents[2] / "CONTEXT.md"

INVENTORIED = frozenset(TOPICS) | frozenset(DEVICE_TOPICS)
"""Both mappings, because a topic is named two ways: `TOPICS` holds a whole
topic per row and `DEVICE_TOPICS` holds the fixed part of a device row, the
address under it being a railroad's wiring (ADR-0043)."""

NAMED = re.compile(r"(?<![\w/.])tc49/(?:[a-z0-9_]+/?)*")
"""What a topic looks like in the prose, from the first level on. The
lookbehind keeps a path that merely contains the package — `src/tc49/lib` —
from reading as one, and the levels stop at the `<` of a placeholder, so
`tc49/<component>/<leaf>` reads as the bare namespace it is talking about."""


def inventoried(name: str) -> bool:
    """Whether the inventory holds `name` as the prose writes it.

    Three ways, all three in `CONTEXT.md` today. A whole topic —
    `tc49/dispatch/state/allocation` — is a row. A **prefix**, written with a
    trailing slash where the prose means everything under it, holds where the
    inventory has a topic under it or is that topic itself: the device halves
    `tc49/layout/state/wanted/` and `tc49/layout/state/device/` name no row of
    their own, and an addressed row's own key sits at the prefix a `<block>.
    <end>` hangs off. The bare namespace `tc49/` is the widest prefix of all
    and names no topic, so it holds by the same reading rather than by an
    exception."""
    if name.endswith("/"):
        return any(
            topic == name.removesuffix("/") or topic.startswith(name)
            for topic in INVENTORIED
        )
    return name in INVENTORIED


def test_every_topic_the_glossary_names_is_in_the_inventory() -> None:
    """Reported with line and name, so whoever trips it reads neither file end
    to end to find out which topic it was."""
    missing = [
        f"CONTEXT.md:{number}: {found.group(0)}"
        for number, line in enumerate(GLOSSARY.read_text().splitlines(), 1)
        for found in NAMED.finditer(line)
        if not inventoried(found.group(0))
    ]
    assert not missing, "topics named in the glossary and not in " + (
        "tc49.lib.inventory:\n" + "\n".join(missing)
    )


def test_the_glossary_names_topics_at_all() -> None:
    """The check is worth nothing if the reading stops matching the prose."""
    assert NAMED.findall(GLOSSARY.read_text())


def test_a_prefix_holds_where_the_inventory_has_a_topic_under_it() -> None:
    assert inventoried("tc49/layout/state/wanted/")
    assert inventoried("tc49/layout/state/device/")
    assert inventoried("tc49/layout/state/device/sensor/")
    assert inventoried("tc49/")
    assert not inventoried("tc49/layout/state/nowhere/")


def test_a_whole_topic_holds_only_where_it_is_a_row() -> None:
    assert inventoried("tc49/dispatch/state/allocation")
    assert inventoried("tc49/layout/state/device/sensor")
    assert not inventoried("tc49/dispatch/state/alloc")
    assert not inventoried("tc49/layout/state/device")
