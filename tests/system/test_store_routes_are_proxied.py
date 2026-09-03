"""Every route the store serves is reachable from the app (#392).

The app fetches the store on its own origin: through vite's proxy in
development and through the reverse proxy in front of a layout server. Both
list the store's path prefixes by hand, and so do the tables in DEPLOY.md.
`/catalogue` landed in the store with no entry in any of them, so the routes
worked in tests and nowhere else. This reads the prefixes off the store's own
route list and checks each is named where a request has to pass.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ROUTE = re.compile(r"^\s+(?:GET|PUT|POST|DELETE)\s+(/[a-z]+)", re.MULTILINE)


def store_prefixes() -> set[str]:
    server = (ROOT / "src/tc49/store/server.py").read_text()
    docstring = server.split('"""', 2)[1]
    found = set(ROUTE.findall(docstring))
    assert found, "the store's docstring lists its routes; none found"
    return found


@pytest.mark.parametrize(
    "path",
    [
        "ui/vite.config.ts",
        "deploy/routes/layout.yaml",
        "docs/DEPLOY.md",
    ],
)
def test_every_store_prefix_is_proxied(path: str) -> None:
    text = (ROOT / path).read_text()
    missing = sorted(p for p in store_prefixes() if p not in text)
    assert not missing, f"{path} does not name the store route(s) {missing}"
