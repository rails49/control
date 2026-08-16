"""The committed railroads, and the two conveniences the store tests share.

`RAILROADS` is every railroad in `layouts/`, so a test that must hold for all
of them says so by parametrising over it rather than by listing names again.
"""

from typing import Any

import yaml

from tc49.store.drawing import Drawing
from tests.harness import ROOT

RAILROADS = ["crossover-yard", "facing-pair", "gotthard", "single-track-meet"]


def read(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load((ROOT / "layouts" / name).read_text())
    return doc


def derive(doc: dict[str, Any]) -> dict[str, Any]:
    return Drawing.from_document(doc).derive()
