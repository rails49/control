"""Every relative link between the pages resolves, target and anchor (#549).

Carving `BUS.md` out of `SYSTEM.md` moved four sections and the anchors that
named them, and nothing would have said so had one been missed. The same rot
had already happened twice unnoticed: a heading renamed under a link that
still named the old one, and an ADR renamed under a sibling that still named
the old file.

Both sides are read at run time and this file carries no list of pages, no
list of headings and no allowlist. A link is checked where both ends are
rails49's: a relative target inside the repository, and a link into another
rails49 repository, read through GitHub's REST API (org ADR-0017). Every other
`http://` and `https://` link goes unread, and so do `mailto:` and a bare
`#fragment`, which names a heading on the page it sits in and is the one case
a reader cannot follow wrong. `docs/research/` is not read for rails49 links:
a research note is never edited, so a link in one that broke stays broken.

`.implement-loop/` is excluded with the rest of the tree by reading only
`docs/` and the four pages at the root: those records quote the paths a batch
saw at the time, and correcting them would be rewriting what happened.
"""

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PAGES = sorted(
    [ROOT / name for name in ("README.md", "CLAUDE.md", "GLOSSARY.md")]
    + list((ROOT / "docs").rglob("*.md"))
)

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
"""An inline markdown link's target. Titles and whitespace inside the
parentheses are not used here and would not parse as a path anyway."""

HEADING = re.compile(r"^#{1,6} +(.+?)\s*$", re.MULTILINE)

EXTERNAL = ("http://", "https://", "mailto:", "#")

RAILS49 = "https://github.com/rails49/"


def anchors(page: str) -> set[str]:
    """The fragment each heading answers to, as GitHub derives it: lowercased,
    anything but a letter, a digit, a space or a hyphen dropped, and spaces
    hyphenated. Inline code and emphasis leave their markers behind as
    characters that drop, so `## `layout`` answers to `#layout` either way."""
    return {
        re.sub(r"[^a-z0-9 -]", "", text.lower()).replace(" ", "-")
        for text in HEADING.findall(page)
    }


@cache
def github(path: str) -> str | None:
    """What GitHub's REST API answers at `path`, a file as its text, or None
    where it answers 404. Any other failure, a rate limit among them, raises:
    it says nothing about the link."""
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github.raw"},
    )
    if token := os.environ.get("GITHUB_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def rails49_problem(target: str) -> str | None:
    """Why a link into a rails49 repository goes nowhere, or None where it
    lands. A ref may hold a slash, so a `blob` or `tree` link is tried at each
    split of ref from path until one answers. Links of any other shape, an
    issue's among them, are not read."""
    address, _, anchor = target.removeprefix(RAILS49).partition("#")
    repo, *rest = address.rstrip("/").split("/")
    if not rest:
        found = github(f"/repos/rails49/{repo}") is not None
        return None if found else "no such repository"
    kind, *segments = rest
    if kind not in ("blob", "tree") or not segments:
        return None
    for split in range(1, len(segments) + 1):
        ref = urllib.parse.quote("/".join(segments[:split]), safe="")
        path = "/".join(segments[split:])
        text = github(f"/repos/rails49/{repo}/contents/{path}?ref={ref}")
        if text is not None:
            break
    else:
        return "no such file"
    if anchor and path.endswith(".md") and anchor not in anchors(text):
        return "no such heading"
    return None


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
                    anchor
                    and landed.suffix == ".md"
                    and anchor not in anchors(landed.read_text())
                ):
                    broken.append(f"{rel}:{number}: no such heading: {target}")
    assert not broken, "links that go nowhere:\n" + "\n".join(broken)


def test_every_rails49_link_resolves() -> None:
    """Reported the way the relative links are."""
    research = ROOT / "docs" / "research"
    broken: list[str] = []
    for page in PAGES:
        if page.is_relative_to(research):
            continue
        rel = page.relative_to(ROOT)
        for number, line in enumerate(page.read_text().splitlines(), 1):
            for target in LINK.findall(line):
                if target.startswith(RAILS49) and (problem := rails49_problem(target)):
                    broken.append(f"{rel}:{number}: {problem}: {target}")
    assert not broken, "links that go nowhere:\n" + "\n".join(broken)


def test_the_pages_carry_links_at_all() -> None:
    """The check is worth nothing if the reading stops matching the prose."""
    assert sum(len(LINK.findall(page.read_text())) for page in PAGES) > 100


def test_an_anchor_is_derived_the_way_a_heading_renders() -> None:
    bus = (ROOT / "docs" / "BUS.md").read_text()
    assert {"the-bus", "event-inventory", "time", "device-vocabulary"} <= anchors(bus)
    assert "layout" in anchors(bus), "a `code` heading keeps its word"
