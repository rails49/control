"""The committed railroads, and the two conveniences the store tests share.

`RAILROADS` is every railroad in `layouts/`, so a test that must hold for all
of them says so by parametrising over it rather than by listing names again. It
is read off the directory rather than typed, since a list typed once is a list
that stops being every railroad: `gotthard`, the one that is being built,
was missing from it for as long as it had been drawn.
"""

from typing import Any

import yaml

from tc49.store.drawing import Drawing
from tests.harness import ROOT

_SUFFIX = ".drawing.yaml"
RAILROADS = sorted(
    path.name.removesuffix(_SUFFIX) for path in (ROOT / "layouts").glob(f"*{_SUFFIX}")
)


def read(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load((ROOT / "layouts" / name).read_text())
    return doc


def derive(doc: dict[str, Any]) -> dict[str, Any]:
    return Drawing.from_document(doc).derive()
