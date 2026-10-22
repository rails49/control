"""What another repository uses of this one (ADR-0075).

`rails49/dccex` imports four modules of `tc49.lib` and dials three names
`deploy/compose.yaml` declares; `rails49/jmri` plans the same. Neither
repository's tests run against a control deploy, so a rename here breaks the
translator on the box and nothing fails first. The tests below hold the
imported names and the three deploy names.

A pull request that changes one here files an issue in rails49/dccex and in
rails49/jmri.

It reads files and imports names, and binds no socket.
"""

from importlib import import_module

import pytest

from tc49.bench.cli import command_line
from tests.system.test_compose import ROOT, services, words
from tests.system.test_router_labels import NETWORK, labels

NAMES = {
    "tc49.lib.bus": ("Bus", "Payload", "InProcessBus"),
    "tc49.lib.mqtt": ("MqttBus", "address"),
    "tc49.lib.clock": ("Clock",),
    "tc49.lib.inventory": (
        "ON",
        "OFF",
        "device_topic",
        "split_device",
        "TOPICS",
        "DEVICE_TOPICS",
        "WIDGET_TOPICS",
    ),
}
"""The four modules another repository may import, and the names in them it
imports today. `WIDGET_TOPICS` is the one it imports next, building a text
widget's topic from the key and the name (rails49/dccex#342)."""

MOSQUITTO = ROOT / "deploy/mosquitto.conf"


@pytest.mark.parametrize(
    ("module", "name"),
    [(module, name) for module, names in NAMES.items() for name in names],
)
def test_a_declared_name_is_importable(module: str, name: str) -> None:
    assert hasattr(import_module(module), name)


def test_native_mqtt_is_broker_on_1883() -> None:
    assert NETWORK in services()["broker"]["networks"]
    lines = MOSQUITTO.read_text().splitlines()
    assert "listener 1883" in [line.strip() for line in lines]


def test_the_stores_face_is_store_on_8765() -> None:
    """The port is the one `tc49 serve` takes from the command compose gives
    it, so a `--port` there moves the face as surely as a new default does."""
    store = services()["store"]
    assert NETWORK in store["networks"]
    run = words(store)
    assert run[0] == "tc49"
    assert command_line().parse_args(run[1:]).port == 8765


def test_the_brokers_websocket_listener_is_tc49_mqtt() -> None:
    key = "traefik.http.services.tc49-mqtt.loadbalancer.server.port"
    assert labels(services()["broker"]).get(key) == "9001"
