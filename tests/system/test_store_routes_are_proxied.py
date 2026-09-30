"""Every route the store serves is reachable from the app (#392).

The app fetches the store on its own origin: through vite's proxy in
development, and on a box through the installation's door, which reads the
store's own router off its container (#556, #557). Both list the store's path
prefixes by hand, and so does the table in DEPLOY.md. `/catalogue` landed in
the store with no entry in any of them, so the routes worked in tests and
nowhere else. This reads the prefixes off the store's own route list and
checks each is named where a request has to pass.

A route no page fetches is named here instead. A prefix the browser never
reaches has nothing to proxy, and adding it to a door's path list would publish
it to the LAN for no caller — so the rule holds for every prefix but the ones
listed below, and a new route is proxied or is written down as server-side, one
or the other.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ROUTE = re.compile(r"^\s+(?:GET|PUT|POST|DELETE)\s+(/[a-z]+)", re.MULTILINE)

SERVER_SIDE = frozenset({"/scripts"})
"""The prefixes whose callers are apps rather than pages, and which are
therefore on no proxy. A railroad's translator script is fetched by the
translator that loads it and written by the face that edits it, each over the
stack's own network, so the door in front of the app never sees one
([#586](https://github.com/rails49/control/issues/586), ADR-0055)."""


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
        "deploy/compose.yaml",
        "docs/DEPLOY.md",
    ],
)
def test_every_store_prefix_is_proxied(path: str) -> None:
    text = (ROOT / path).read_text()
    missing = sorted(p for p in store_prefixes() - SERVER_SIDE if p not in text)
    assert not missing, f"{path} does not name the store route(s) {missing}"


def test_a_server_side_prefix_is_one_the_store_serves() -> None:
    """The exception is spelled the way the route list spells it. A prefix
    listed here that the store does not serve is a proxy entry silently
    excused, which is the fault this file exists to catch."""
    assert SERVER_SIDE <= store_prefixes()
