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
        "dccex_usb",
    }
)

ALLOWED_FILES = frozenset(
    {
        "DEPLOY.md",  # the physical deployment is hardware
        "store/DRAWING.md",  # the drawing carries hardware addresses (ADR-0022)
    }
)

PACKAGES = frozenset({"dccex", "jmri"})
"""Package names, and never a leak wherever they appear. A translator is
named for the system it speaks to (ADR-0043), so a page cannot say which app
does the work without spelling the directory. `DCC-EX`, `DCC` and `JMRI` —
the product and protocol names the rule exists to keep out — still leak
everywhere they leak today. The difference is naming a directory versus
writing about hardware, and it does not depend on which page you are on:
listing the pages that may name a package was a per-file allowlist that
every new mention had to be added to, for no gain."""


def test_hardware_protocols_stay_in_hardware_docs() -> None:
    leaks: list[str] = []
    for page in sorted(DOCS.rglob("*.md")):
        rel = page.relative_to(DOCS)
        if rel.parts[0] in ALLOWED_DIRS or str(rel) in ALLOWED_FILES:
            continue
        for number, line in enumerate(page.read_text().splitlines(), 1):
            for found in PROTOCOLS.finditer(line):
                if found.group(0) in PACKAGES:
                    continue
                leaks.append(f"docs/{rel}:{number}: {found.group(0)}")
                break
    assert not leaks, "hardware protocol names outside hardware docs:\n" + "\n".join(
        leaks
    )


def test_a_package_name_passes_and_the_product_name_does_not() -> None:
    """The allowance is on the spelling, not the page. `dccex` is a directory
    and passes anywhere; `DCC-EX` is a command station and leaks anywhere."""
    matched = [
        m.group(0)
        for m in PROTOCOLS.finditer("the dccex translator speaks DCC-EX over 2560")
    ]
    assert matched == ["dccex", "DCC-EX"]
    assert [m for m in matched if m not in PACKAGES] == ["DCC-EX"]
