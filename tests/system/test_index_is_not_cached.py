"""The built UI's `index.html` is sent with `Cache-Control: no-cache` (#1123).

Stock nginx sends it with `etag` and `last-modified` and nothing else, and a
browser may then reuse its copy without asking. That copy names the bundle of
the build before, so a phone kept drawing the Run view of the deploy before
#1108 after a reload. The bundle's files under `assets/` carry a hash in
their names and need no header: a new build gives them new names.

Read off the files rather than a running nginx: the `control-web` image
carries its own config, and that config adds the header to `index.html`,
which is also what nginx serves for `/`. `test_images.py` asks a running one.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOCKERFILE = ROOT / "deploy/web.Dockerfile"

CONFIG = "deploy/nginx.conf"

COPY = "COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf"
"""Where stock nginx reads its one server block, which the file replaces."""

INDEX = re.compile(
    r"location\s*=\s*/index\.html\s*\{[^}]*add_header\s+Cache-Control\s+no-cache;"
)


def test_web_carries_its_config() -> None:
    """Without it nginx serves its default config, which adds no header."""
    assert COPY in DOCKERFILE.read_text()


def test_index_is_sent_with_no_cache() -> None:
    assert INDEX.search(
        (ROOT / CONFIG).read_text()
    ), f"{CONFIG} does not add Cache-Control: no-cache to /index.html"
