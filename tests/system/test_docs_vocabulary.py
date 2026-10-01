"""Hardware protocol names stay in hardware docs and out of the source (#255, #466).

Components meet over the bus and the store's contract, and hardware exists
only behind the layout interface (ADR-0030, ADR-0043). Stated in prose the
rule kept being broken, so like the import rule it is a test: a protocol
name on a page about anything else is a leak, reported with file, line and
word so the fix is legible to whoever tripped it.

The rule reads `src/` on the same terms as `docs/`. A docstring is prose and
leaks exactly as a page does, and the leaks it found were in prose: `lib`
naming the protocol a function number belongs to, where the number said it.
Every module under `src/tc49/` is read and none is exempt: no translator is
an app of this repository (#595), so no package here is a hardware app.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
SRC = ROOT / "src" / "tc49"

PROTOCOLS = re.compile(r"\b(dcc(?:-?ex)?|jmri)\b", re.IGNORECASE)

ALLOWED_DIRS = frozenset(
    {
        "adr",  # a decision may name what it decides about
        "research",  # research notes about hardware are about hardware
        # The layout interface's docs describe the device vocabulary, which
        # is where the hardware systems behind it are named (ADR-0043).
        "layout",
    }
)

ALLOWED_FILES = frozenset(
    {
        "DEPLOY.md",  # the physical deployment is hardware
        "store/DRAWING.md",  # the drawing carries hardware addresses (ADR-0022)
    }
)

PACKAGES = frozenset({"dccex", "jmri", "DccEx", "Jmri"})
"""Names, and never a leak wherever they appear. A translator is named for
the system it speaks to (ADR-0043), so nothing can say which one does the
work without spelling it — and none of them is an app of this repository
(#595), so these are the names of other repositories, of the address
prefixes that reach them (`dccex/12`, `jmri/LS3`), and of classes there that
prose here still names, `DccEx` among them. `DCC-EX`, `DCC` and `JMRI` — the
product and protocol names the rule exists to keep out — still leak
everywhere they leak today. The difference is naming a repository, an
address or a class versus writing about hardware, and it does not depend on
which file you are in: listing the pages that may name one was a per-file
allowlist that every new mention had to be added to, for no gain."""


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


def test_no_module_names_a_hardware_protocol() -> None:
    leaks: list[str] = []
    for module in sorted(SRC.rglob("*.py")):
        rel = module.relative_to(SRC)
        for number, line in enumerate(module.read_text().splitlines(), 1):
            for found in PROTOCOLS.finditer(line):
                if found.group(0) in PACKAGES:
                    continue
                leaks.append(f"src/tc49/{rel}:{number}: {found.group(0)}")
                break
    assert not leaks, "hardware protocol names in src/tc49:\n" + "\n".join(leaks)


def test_a_package_name_passes_and_the_product_name_does_not() -> None:
    """The allowance is on the spelling, not the page. `dccex` is a name and
    passes anywhere; `DCC-EX` is a command station and leaks anywhere."""
    matched = [
        m.group(0)
        for m in PROTOCOLS.finditer("the dccex translator speaks DCC-EX over 2560")
    ]
    assert matched == ["dccex", "DCC-EX"]
    assert [m for m in matched if m not in PACKAGES] == ["DCC-EX"]
