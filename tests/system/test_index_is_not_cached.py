"""The built UI's `index.html` is sent with `Cache-Control: no-cache` (#1123).

Stock nginx sends it with `etag` and `last-modified` and nothing else, and a
browser may then reuse its copy without asking. That copy names the bundle of
the build before, so a phone kept drawing the Run view of the deploy before
#1108 after a reload. The bundle's files under `assets/` carry a hash in
their names and need no header: a new build gives them new names.

Read off the files rather than a running nginx: `web` mounts its own config,
and that config adds the header to `index.html`, which is also what nginx
serves for `/`.
"""

import re
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]

COMPOSE = ROOT / "deploy/compose.yaml"

CONFIG = "deploy/nginx.conf"

MOUNT = "./nginx.conf:/etc/nginx/conf.d/default.conf:ro"
"""Where stock nginx reads its one server block, which the file replaces."""

INDEX = re.compile(
    r"location\s*=\s*/index\.html\s*\{[^}]*add_header\s+Cache-Control\s+no-cache;"
)


def test_web_mounts_its_config() -> None:
    """Without the mount nginx serves its default config, which adds no
    header."""
    document = cast(dict[str, Any], yaml.safe_load(COMPOSE.read_text()))
    assert MOUNT in document["services"]["web"]["volumes"]


def test_index_is_sent_with_no_cache() -> None:
    assert INDEX.search(
        (ROOT / CONFIG).read_text()
    ), f"{CONFIG} does not add Cache-Control: no-cache to /index.html"
