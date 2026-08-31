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


def test_hardware_protocols_stay_in_hardware_docs() -> None:
    leaks: list[str] = []
    for page in sorted(DOCS.rglob("*.md")):
        rel = page.relative_to(DOCS)
        if rel.parts[0] in ALLOWED_DIRS or str(rel) in ALLOWED_FILES:
            continue
        for number, line in enumerate(page.read_text().splitlines(), 1):
            found = PROTOCOLS.search(line)
            if found:
                leaks.append(f"docs/{rel}:{number}: {found.group(0)}")
    assert not leaks, "hardware protocol names outside hardware docs:\n" + "\n".join(
        leaks
    )
