"""The page's copy of the widget contract, against the store and the inventory.

The editor and the run view name a widget's kinds, its text sizes and
alignments, its keys, the rule for its name and the rows it is on, and each of
those is a fact Python owns: `tc49.store.drawing` for the document,
`tc49.lib.inventory.WIDGET_TOPICS` for the rows (ADR-0087). A second copy of a
contract drifts unless something fails when it does, and this is that
something — the names are read out of the TypeScript with regular expressions
and compared with the Python, as `test_state_names` does for `STATE_NAMES`.
"""

import re
from pathlib import Path

from tc49.lib.inventory import WIDGET_TOPICS
from tc49.store import drawing
from tests.harness import ROOT

WIDGETS_TS = Path("ui/src/model/widgets.ts")
RULES_TS = Path("ui/src/model/rules.ts")
DRAWING_TS = Path("ui/src/model/drawing.ts")


def source(path: Path) -> str:
    """The TypeScript at `path`, line comments and block comments removed."""
    text = (ROOT / path).read_text()
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.DOTALL)


def find(path: Path, pattern: str, what: str) -> str:
    """The first group of `pattern` in `path`, which must be there."""
    found = re.search(pattern, source(path), re.DOTALL)
    assert found is not None, f"no {what} in {path}"
    return found.group(1)


def strings(text: str) -> list[str]:
    """The double-quoted strings in `text`, in order."""
    return re.findall(r'"([^"]*)"', text)


def widget_spec() -> str:
    """The body of `WidgetSpec` in `ui/src/model/drawing.ts`."""
    return find(
        DRAWING_TS, r"export interface WidgetSpec \{(.*?)\n\}", "WidgetSpec interface"
    )


def test_the_kinds_are_the_stores() -> None:
    kinds = strings(
        find(
            WIDGETS_TS, r"export const WIDGET_KINDS\b[^=]*=\s*\[(.*?)\]", "WIDGET_KINDS"
        )
    )
    assert set(kinds) == set(drawing.WIDGET_KINDS) and len(kinds) == len(
        drawing.WIDGET_KINDS
    ), f"{WIDGETS_TS} WIDGET_KINDS and tc49.store.drawing.WIDGET_KINDS disagree"


def test_the_text_sizes_and_alignments_are_the_stores() -> None:
    for name, owned in (
        ("WIDGET_TEXT", drawing.WIDGET_TEXT),
        ("WIDGET_ALIGN", drawing.WIDGET_ALIGN),
    ):
        declared = strings(
            find(WIDGETS_TS, rf"export const {name}\s*=\s*\[(.*?)\]", name)
        )
        assert (
            tuple(declared) == owned
        ), f"{WIDGETS_TS} {name} and tc49.store.drawing.{name} disagree"


def test_the_topics_are_the_inventorys_widget_rows() -> None:
    body = find(WIDGETS_TS, r"const TOPICS\b[^=]*=\s*\{(.*?)\}", "TOPICS")
    assert set(re.findall(r':\s*"([^"]*)"', body)) == set(
        WIDGET_TOPICS
    ), f"{WIDGETS_TS} TOPICS and tc49.lib.inventory.WIDGET_TOPICS disagree"


def test_every_widget_row_starts_with_the_prefix() -> None:
    prefix = find(
        WIDGETS_TS, r'export const WIDGET_PREFIX\s*=\s*"([^"]*)"', "WIDGET_PREFIX"
    )
    assert all(topic.startswith(prefix) for topic in WIDGET_TOPICS), (
        f"{WIDGETS_TS} WIDGET_PREFIX does not start every key of "
        "tc49.lib.inventory.WIDGET_TOPICS"
    )


def test_the_name_rule_is_the_stores() -> None:
    pattern = find(
        RULES_TS,
        r"export function isWidgetName\b.*?/\^(.*?)\$/\.test",
        "isWidgetName pattern",
    )
    owned = drawing._WIDGET_NAME.pattern  # pyright: ignore[reportPrivateUsage]
    assert (
        pattern == owned
    ), f"{RULES_TS} isWidgetName and tc49.store.drawing._WIDGET_NAME disagree"


def test_the_specs_text_and_align_are_the_stores() -> None:
    body = widget_spec()
    for field, name, owned in (
        ("text", "WIDGET_TEXT", drawing.WIDGET_TEXT),
        ("align", "WIDGET_ALIGN", drawing.WIDGET_ALIGN),
    ):
        found = re.search(rf"^\s*{field}\?:\s*([^;]*);", body, re.MULTILINE)
        assert found is not None, f"no {field}? in {DRAWING_TS} WidgetSpec"
        assert (
            tuple(strings(found.group(1))) == owned
        ), f"{DRAWING_TS} WidgetSpec {field}? and tc49.store.drawing.{name} disagree"


def test_the_specs_fields_are_the_keys_the_store_allows() -> None:
    fields = set(re.findall(r"^\s*(\w+)\??:", widget_spec(), re.MULTILINE))
    allowed = {"kind", "at"}.union(
        *(required | optional for required, optional in drawing.WIDGET_KINDS.values())
    )
    assert fields == allowed, (
        f"{DRAWING_TS} WidgetSpec and the keys tc49.store.drawing.WIDGET_KINDS "
        "allows disagree"
    )
