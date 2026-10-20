"""`python -m tc49.camera`, started as a compose service starts it: it
answers on the port it is given and ends on SIGTERM (#851)."""

import http.client
import sys
from pathlib import Path

from tests.apps import Process
from tests.brokers import until
from tests.camera.conftest import RAILROAD, Railroad
from tests.ports import free_port


def answers(port: int) -> int | None:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        connection.request("GET", f"/picture/{RAILROAD}/ore")
        return connection.getresponse().status
    except OSError:
        return None


def test_it_answers_on_its_port_and_ends_on_sigterm(
    railroad: Railroad, store: str, tmp_path: Path
) -> None:
    railroad.roster({"ore": None})
    port = free_port()
    app = Process(
        [sys.executable, "-m", "tc49.camera", "--store", store, "--port", str(port)],
        tmp_path / "camera.log",
    )
    app.start()
    try:
        assert until(lambda: answers(port) == 404, 15), app.said()
    finally:
        app.stop()
    assert not app.running
