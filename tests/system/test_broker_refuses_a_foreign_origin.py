"""A page on another origin gets no socket to the broker (#349, ADR-0056).

The origin rule has two faces. The store's is `lib/origin.py`, read in the
app. The broker's cannot be: Mosquitto has no `Origin` setting, so the rule is
stated in front of it, as a router and a middleware on `/mqtt` in each site's
route table (ADR-0059, decision 4). Prose in `docs/DEPLOY.md` is how #342 came
to be rediscovered, so the two tables are read here instead.

What cannot be checked without a running proxy is that Traefik refuses; what
can be, and is the part a person gets wrong, is that every site carrying
`/mqtt` carries the refusal too, that the refusal admits the router's own host
and nothing else, and that a handshake with no `Origin` — a native client — is
not what it catches.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "deploy/routes"
SITES = sorted(p.name for p in ROUTES.iterdir() if p.is_dir())

HOST = re.compile(r"Host\(`([^`]+)`\)")
ORIGIN = re.compile(r"!HeaderRegexp\(`Origin`, `([^`]+)`\)")

FOREIGN = "https://evil.example"
"""A page somebody's browser visits. Its origin is wherever it is served
from, which is never the router's own host."""


def table(site: str) -> dict[str, Any]:
    read: dict[str, Any] = yaml.safe_load((ROUTES / site / "site.yaml").read_text())
    return read["http"]


def routers(site: str, kind: str) -> dict[str, dict[str, Any]]:
    """The site's routers whose rule names `/mqtt`, split by whether they are
    the refusal — which is the one that reads `Origin`."""
    found: dict[str, dict[str, Any]] = {}
    for name, router in table(site)["routers"].items():
        rule = str(router["rule"])
        if "PathPrefix(`/mqtt`)" not in rule:
            continue
        if ("Origin" in rule) == (kind == "refusal"):
            found[name] = router
    return found


@pytest.mark.parametrize("site", SITES)
def test_the_broker_is_reachable_at_all(site: str) -> None:
    """The premise of everything below: each site proxies `/mqtt`, which is
    how the run view reaches the broker on the page's own origin."""
    assert routers(site, "served"), f"{site} does not proxy /mqtt"


@pytest.mark.parametrize("site", SITES)
def test_a_foreign_origin_is_refused_on_the_broker(site: str) -> None:
    """One refusing router per site, and it refuses rather than proxies: the
    middleware it carries answers before the service behind it, so a foreign
    page is given no socket to be told over."""
    [(name, router)] = routers(site, "refusal").items()
    middlewares = table(site)["middlewares"]
    refusals = [middlewares[one] for one in router["middlewares"] if one in middlewares]
    assert any("ipAllowList" in one for one in refusals), (
        f"{site}'s {name} routes a foreign handshake somewhere without" " refusing it"
    )
    for one in refusals:
        for allowed in one.get("ipAllowList", {}).get("sourceRange", []):
            assert allowed == "255.255.255.255/32", (
                "the range is what makes this a refusal; a routable one lets a"
                f" foreign page through {site}"
            )


@pytest.mark.parametrize("site", SITES)
def test_the_refusal_admits_the_routers_own_host_and_nothing_else(site: str) -> None:
    """The rule itself, as `lib/origin.py` states it for the store: an origin
    whose host is the router's own is the app on its own origin and goes
    through; anything else is a page whose author is not in the room."""
    [router] = routers(site, "refusal").values()
    rule = str(router["rule"])
    [host] = HOST.findall(rule)
    [admitted] = ORIGIN.findall(rule)

    assert re.fullmatch(admitted, f"https://{host}")
    assert re.fullmatch(admitted, f"http://{host}")  # TLS terminates here
    assert not re.fullmatch(admitted, FOREIGN)
    assert not re.fullmatch(admitted, f"https://{host}.evil.example")
    assert not re.fullmatch(admitted, f"https://evil{host}")


@pytest.mark.parametrize("site", SITES)
def test_a_handshake_with_no_origin_is_not_what_is_refused(site: str) -> None:
    """No header means no page — a native throttle, `mosquitto_sub`, a test
    client — and those go through, as they do at the store's face (ADR-0042).
    Matching `Origin` at all is what selects the refusing router, so a
    handshake carrying none falls through to the one that proxies."""
    [router] = routers(site, "refusal").values()
    assert "HeaderRegexp(`Origin`, `.`)" in str(router["rule"])


@pytest.mark.parametrize("site", SITES)
def test_the_refusal_outranks_the_router_it_stands_in_front_of(site: str) -> None:
    """Traefik's default priority is the rule's length, and neither router
    states one: the refusal's rule is the other's plus the two `Origin`
    clauses, so it is longer and wins wherever both match. Stated as a test
    because a rule shortened by hand would silently stop refusing."""
    [served] = routers(site, "served").values()
    [refused] = routers(site, "refusal").values()
    assert "priority" not in served and "priority" not in refused
    assert len(str(refused["rule"])) > len(str(served["rule"]))
