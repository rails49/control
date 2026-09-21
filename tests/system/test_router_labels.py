"""`control` declares its own routers as labels on its own containers (#556).

The door in front of everything a browser reaches on a box is the
installation's, not this repository's, and it reads its routers off container
labels. So the three containers a browser reaches — the built ui, the store
and the broker — carry the rules for their own paths, and a UI's paths change
in the same commit as the UI.

What a running proxy does with these labels is not checked here: a wrong label
parses and asserts fine, and only a request on a real box says otherwise. What
is checked is what a reader cannot see is wrong — a hostname written out
instead of taken from the box's declaration, a router named for a site that is
about to stop existing, an app container on a network the door can reach it
from, and the refusal's precedence left to a rule length that no longer sits
beside the rule it has to beat.

`deploy/routes/*/site.yaml` is still mounted and still serving, and the
assertions over it in `test_route_mount.py` and
`test_broker_refuses_a_foreign_origin.py` still hold. This is the expand half
of an expand–contract pair (#556): both ways exist until the route file goes,
and `test_the_two_ways_agree_while_both_exist` is what keeps them from
drifting apart in between.
"""

import re
from typing import Any, cast

import pytest
import yaml

from tests.system.test_compose import COMPOSE, services

NETWORK = "rails49"
"""The one network every stack on the box shares, created by the installation
and joined by every container the door reaches (rails49/installation ADR-0001).
The name is a contract in four repositories."""

REACHED = frozenset({"web", "store", "broker"})
"""The containers a browser reaches: the built ui, the store's HTTP face and
the broker's WebSocket listener. Everything else here talks to the bus rather
than to browsers, and stays off the shared network — the door has no route to
any of them."""

LABEL = "control"
"""What this UI is called under the box's name. The box declares which labels
it serves; which one is ours is ours to say."""

HOST = f"Host(`{LABEL}.${{BOX_DOMAIN}}`)"
"""Every rule begins with this: the box's own name, by compose substitution
out of `/etc/rails49/box.env`, so no template is rendered and no file is
copied."""

DOMAIN = "gleis49.org"
"""A stand-in for what the declaration holds, for the rules that are read as
patterns below. The file is read as written, with `${BOX_DOMAIN}` still in
it — what is asserted is that the declaration is where the name comes from."""

FOREIGN = "https://evil.example"
"""A page somebody's browser visits. Its origin is wherever it is served from,
which is never the app's own name."""

ORIGIN = re.compile(r"!Header\(`Origin`, `([^`]+)`\)")


def document() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(COMPOSE.read_text()))


def stack() -> str:
    """The compose project's name, which is what the routers are keyed to."""
    return str(document()["name"])


def labels(service: dict[str, Any]) -> dict[str, str]:
    """A service's labels, as a map. The file declares them as a list."""
    declared: list[str] = service.get("labels") or []
    pairs = (str(one).split("=", 1) for one in declared)
    return {key: value for key, value in pairs}


def declared(kind: str) -> dict[str, dict[str, str]]:
    """Every router, middleware or service the labels declare, by name, with
    its settings — wherever in the file the container carrying it sits."""
    pattern = re.compile(rf"^traefik\.http\.{kind}\.([^.]+)\.(.+)$")
    found: dict[str, dict[str, str]] = {}
    for service in services().values():
        for key, value in labels(service).items():
            said = pattern.match(key)
            if said:
                found.setdefault(said[1], {})[said[2]] = value
    return found


def routers() -> dict[str, dict[str, str]]:
    return declared("routers")


def router(name: str) -> dict[str, str]:
    """One router by its unprefixed name: `app` is `tc49-app`."""
    return routers()[f"{stack()}-{name}"]


def rule(name: str) -> str:
    """A router's rule with the box's name substituted, as compose would."""
    return router(name)["rule"].replace("${BOX_DOMAIN}", DOMAIN)


def priority(name: str) -> int:
    return int(router(name)["priority"])


def prefixes(text: str) -> set[str]:
    return set(re.findall(r"PathPrefix\(`([^`]+)`\)", text))


def test_the_shared_network_is_the_installations_to_create() -> None:
    """The installation creates it under a fixed name; every other stack
    declares it external. A stack that creates it when it is absent is a
    stack that silently decides its options (rails49/installation ADR-0001)."""
    network: dict[str, Any] = document()["networks"][NETWORK]
    assert network["external"] is True
    assert str(network.get("name", NETWORK)) == NETWORK


def test_only_what_the_door_reaches_joins_it() -> None:
    """Membership is per container, not per stack. The apps talk to the bus
    and not to browsers, so a browser's door has no route to any of them."""
    joined = {
        name
        for name, service in services().items()
        if NETWORK in (service.get("networks") or [])
    }
    assert joined == set(REACHED)


def test_what_joins_it_keeps_the_stacks_own_network() -> None:
    """Each of the three sits on two: the apps reach the broker and the store
    over this stack's own network, and naming a second one would otherwise
    take the first away."""
    for name in sorted(REACHED):
        assert "default" in (
            services()[name].get("networks") or []
        ), f"{name} would leave the network the apps reach it on"


def test_each_container_on_it_names_it_again() -> None:
    """The docker provider picks a container address, and without this label
    it picks whichever network it finds first — a route that works until it
    does not (rails49/installation ADR-0001)."""
    for name in sorted(REACHED):
        assert labels(services()[name])["traefik.docker.network"] == NETWORK


def test_the_door_routes_a_container_only_when_it_asks() -> None:
    """The door sees every container on the box and routes none by default,
    so the three opt in and nothing else may."""
    asked = {
        name
        for name, service in services().items()
        if labels(service).get("traefik.enable") == "true"
    }
    assert asked == set(REACHED)


def test_nothing_else_carries_a_router() -> None:
    """A router on a container the door cannot reach is a rule that resolves
    to nothing, which reads as a route and is not one."""
    loose = sorted(
        name
        for name, service in services().items()
        if name not in REACHED
        and any(key.startswith("traefik.") for key in labels(service))
    )
    assert not loose, f"{loose} declare routing and are not reached by the door"


def test_router_names_are_keyed_to_the_stack() -> None:
    """Not to the site: the site prefix named a route directory that is about
    to stop existing, and these names have to be unique across every stack the
    door sees rather than across this file."""
    named = (
        sorted(routers())
        + sorted(declared("middlewares"))
        + sorted(declared("services"))
    )
    stray = [one for one in named if not one.startswith(f"{stack()}-")]
    assert not stray, f"{stray} are not keyed to the stack `{stack()}`"


@pytest.mark.parametrize("name", ["app", "store", "mqtt", "mqtt-foreign"])
def test_the_hostname_comes_from_the_boxs_declaration(name: str) -> None:
    """One name, substituted by compose out of the box's own file. A literal
    here is what made naming a box a fork of this repository."""
    said = router(name)["rule"]
    assert said.startswith(HOST), f"{name} does not begin at the box's name"
    assert "rails49.org" not in said


@pytest.mark.parametrize("name", ["app", "store", "mqtt", "mqtt-foreign"])
def test_every_router_reaches_the_door_over_tls(name: str) -> None:
    settings = router(name)
    assert settings["entrypoints"] == "websecure"
    assert settings["tls.certresolver"] == "le"


def test_the_store_is_reached_at_its_own_port() -> None:
    """The image publishes nothing, so the door is told which port to dial."""
    assert (
        declared("services")[f"{stack()}-store"]["loadbalancer.server.port"] == "8765"
    )


def test_the_bus_is_reached_at_its_websocket_listener() -> None:
    """9001 and not 1883: what comes through the door is a browser, and a
    native client goes straight to the other one."""
    assert declared("services")[f"{stack()}-mqtt"]["loadbalancer.server.port"] == "9001"
    for name in ("mqtt", "mqtt-foreign"):
        assert router(name)["service"] == f"{stack()}-mqtt"


def test_every_router_states_its_priority() -> None:
    """Traefik's default priority is the rule's length. That was readable
    while every rule sat in one file; the rules now sit on three containers,
    where nothing shows a reader that lengthening one changes what another
    matches. So each says where it stands outright."""
    silent = sorted(
        name for name, settings in routers().items() if "priority" not in settings
    )
    assert not silent, f"{silent} leave their precedence to their rule's length"


def test_the_refusal_outranks_the_router_it_stands_in_front_of() -> None:
    """The whole of what stands between a page somebody's browser visits and
    the gestures a client may publish. It matches everything the plain bus
    router matches, so losing to it would let a foreign page through
    (ADR-0056)."""
    assert priority("mqtt-foreign") > priority("mqtt")


def test_a_path_outranks_the_app_it_is_served_under() -> None:
    """The app's rule is the bare host and matches every path under it,
    including the store's and the bus's."""
    for name in ("store", "mqtt", "mqtt-foreign"):
        assert priority(name) > priority("app"), f"{name} loses to the app"


def test_the_refusal_refuses_rather_than_proxies() -> None:
    """The middleware answers before the service behind it, so a foreign page
    is given no socket to be told over. No source address is the limited
    broadcast address, so every request routed here is refused."""
    middlewares = declared("middlewares")
    carried = [
        middlewares[one] for one in router("mqtt-foreign")["middlewares"].split(",")
    ]
    ranges = [
        one["ipallowlist.sourcerange"]
        for one in carried
        if "ipallowlist.sourcerange" in one
    ]
    assert ranges, "a foreign handshake is routed somewhere without being refused"
    assert ranges == ["255.255.255.255/32"]


def test_the_refusal_admits_the_apps_own_origin_and_nothing_else() -> None:
    """The rule `lib/origin.py` states at the store's face: an origin whose
    host is the app's own is the app on its own origin and goes through.
    Compared whole rather than matched, because the name comes from the
    declaration and a dot inside it cannot be escaped on its way into a
    pattern — `control.gleis49.org` as a pattern admits `control-gleis49.org`,
    which somebody may register."""
    admitted = set(ORIGIN.findall(rule("mqtt-foreign")))
    assert admitted == {
        f"https://{LABEL}.{DOMAIN}",
        f"http://{LABEL}.{DOMAIN}",  # TLS terminates at the door
    }
    assert FOREIGN not in admitted


def test_a_handshake_with_no_origin_is_not_what_is_refused() -> None:
    """No header means no page — a native throttle, `mosquitto_sub`, a test
    client — and those go through, as they do at the store's face. Matching
    `Origin` at all is what selects the refusing router."""
    assert "HeaderRegexp(`Origin`, `.`)" in rule("mqtt-foreign")


def test_the_two_ways_agree_while_both_exist() -> None:
    """The labels and the layout box's route file are the same routing said
    twice until the file goes, and the paths are the half a person edits. A
    prefix added to one and not the other is a path that works on whichever
    box has not been cut over yet."""
    table = yaml.safe_load((COMPOSE.parent / "routes/layout/site.yaml").read_text())
    said = {
        name: prefixes(str(one["rule"]))
        for name, one in cast(
            dict[str, dict[str, Any]], table["http"]["routers"]
        ).items()
    }
    for name in ("app", "store", "mqtt", "mqtt-foreign"):
        assert (
            prefixes(rule(name)) == said[f"layout-{name}"]
        ), f"the labels and the route file disagree about {name}'s paths"
