"""Every relative link between the pages resolves, target and anchor (#549).

Carving `BUS.md` out of `SYSTEM.md` moved four sections and the anchors that
named them, and nothing would have said so had one been missed. The same rot
had already happened twice unnoticed: a heading renamed under a link that
still named the old one, and an ADR renamed under a sibling that still named
the old file.

Both sides are read at run time and this file carries no list of pages, no
list of headings and no allowlist. A link is checked only where both ends are
ours: a relative target inside the repository. `http://`, `https://` and
`mailto:` go unread — a test that reaches the network is a test that fails
when somebody else's server is down — and so does a bare `#fragment`, which
names a heading on the page it sits in and is the one case a reader cannot
follow wrong.

`.implement-loop/` is excluded with the rest of the tree by reading only
`docs/` and the four pages at the root: those records quote the paths a batch
saw at the time, and correcting them would be rewriting what happened.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PAGES = sorted(
    [ROOT / name for name in ("README.md", "CLAUDE.md", "CONTEXT.md")]
    + list((ROOT / "docs").rglob("*.md"))
)

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
"""An inline markdown link's target. Titles and whitespace inside the
parentheses are not used here and would not parse as a path anyway."""

HEADING = re.compile(r"^#{1,6} +(.+?)\s*$", re.MULTILINE)

EXTERNAL = ("http://", "https://", "mailto:", "#")


def anchors(page: Path) -> set[str]:
    """The fragment each heading answers to, as GitHub derives it: lowercased,
    anything but a letter, a digit, a space or a hyphen dropped, and spaces
    hyphenated. Inline code and emphasis leave their markers behind as
    characters that drop, so `## `layout`` answers to `#layout` either way."""
    return {
        re.sub(r"[^a-z0-9 -]", "", text.lower()).replace(" ", "-")
        for text in HEADING.findall(page.read_text())
    }


def test_every_relative_link_between_the_pages_resolves() -> None:
    """Reported with file, line and the target as written, so whoever trips it
    reads neither page end to end to find out which link it was."""
    broken: list[str] = []
    for page in PAGES:
        rel = page.relative_to(ROOT)
        for number, line in enumerate(page.read_text().splitlines(), 1):
            for target in LINK.findall(line):
                if target.startswith(EXTERNAL):
                    continue
                path, _, anchor = target.partition("#")
                landed = (page.parent / path).resolve()
                if not landed.exists():
                    broken.append(f"{rel}:{number}: no such file: {target}")
                elif (
                    anchor and landed.suffix == ".md" and anchor not in anchors(landed)
                ):
                    broken.append(f"{rel}:{number}: no such heading: {target}")
    assert not broken, "links that go nowhere:\n" + "\n".join(broken)


def test_the_pages_carry_links_at_all() -> None:
    """The check is worth nothing if the reading stops matching the prose."""
    assert sum(len(LINK.findall(page.read_text())) for page in PAGES) > 100


def test_an_anchor_is_derived_the_way_a_heading_renders() -> None:
    bus = ROOT / "docs" / "BUS.md"
    assert {"the-bus", "event-inventory", "time", "device-vocabulary"} <= anchors(bus)
    assert "layout" in anchors(bus), "a `code` heading keeps its word"
