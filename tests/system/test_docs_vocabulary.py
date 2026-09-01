"""Hardware protocol names stay in hardware docs (#255).

Components meet over the bus and the store's contract, and hardware exists
only behind the layout interface (ADR-0030, ADR-0043). Stated in prose the
rule kept being broken, so like the import rule it is a test: a protocol
name on a page about anything else is a leak, reported with file, line and
word so the fix is legible to whoever tripped it.
"""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"

PROTOCOLS = re.compile(r"\b(dcc(?:-?ex)?|jmri)\b", re.IGNORECASE)

ALLOWED_DIRS = frozenset(
    {
        "adr",  # a decision may name what it decides about
        "research",  # research notes about hardware are about hardware
        # The hardware apps' own docs, once they exist (ADR-0043).
        "layout",
        "dccex",
        "jmri",
        "station",
    }
)

ALLOWED_FILES = frozenset(
    {
        "DEPLOY.md",  # the physical deployment is hardware
        "store/DRAWING.md",  # the drawing carries hardware addresses (ADR-0022)
    }
)

PACKAGES = frozenset({"dccex", "jmri"})
"""The package names a translator's app and docs folder carry: a translator
is named for the system it speaks to (ADR-0043), so a page that inventories
what is on disk cannot list one without spelling it."""

NAMES_PACKAGES = frozenset({"ARCHITECTURE.md"})
"""Where a **package name** is not a leak, in that exact spelling and no
other. The repository's own map lists every package, every docs folder and
every test package, and a directory listing knows nothing about a protocol.
`DCC-EX`, `DCC` and `JMRI` are still leaks on these pages, which is the
difference between naming a directory and writing about hardware (#289)."""


def test_hardware_protocols_stay_in_hardware_docs() -> None:
    leaks: list[str] = []
    for page in sorted(DOCS.rglob("*.md")):
        rel = page.relative_to(DOCS)
        if rel.parts[0] in ALLOWED_DIRS or str(rel) in ALLOWED_FILES:
            continue
        packages = str(rel) in NAMES_PACKAGES
        for number, line in enumerate(page.read_text().splitlines(), 1):
            for found in PROTOCOLS.finditer(line):
                if packages and found.group(0) in PACKAGES:
                    continue
                leaks.append(f"docs/{rel}:{number}: {found.group(0)}")
                break
    assert not leaks, "hardware protocol names outside hardware docs:\n" + "\n".join(
        leaks
    )


def test_a_page_that_may_name_a_package_may_not_write_about_hardware() -> None:
    """The narrow allowance is narrow: the exact directory name passes and
    every other spelling of the same hardware does not, so the map can list
    what is on disk without becoming a page about a command station."""
    passes = "  dccex/       test_commands  test_replies  test_translator"
    leaks = "the dccex translator speaks DCC-EX over 2560"
    assert all(found.group(0) in PACKAGES for found in PROTOCOLS.finditer(passes))
    assert not all(found.group(0) in PACKAGES for found in PROTOCOLS.finditer(leaks))
