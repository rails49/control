"""What every camera test stands on: a store served on a thread, holding a
roster the test writes, and the camera app's face in front of it with its
waits shortened."""

import http.client
import threading
from collections.abc import Iterator, Mapping
from http.server import HTTPServer
from pathlib import Path

import pytest
import yaml

from tc49.camera.face import Face
from tc49.camera.stream import Cameras
from tc49.lib.documents import Documents
from tc49.store.server import make_server
from tests.camera.cameras import AUTHORIZATION, PATH, Camera
from tests.harness import catalogued
from tests.ports import free_port

RAILROAD = "oval"

SILENCE_S = 1.0
"""The app's 5 s, shortened."""

LINGER_S = 1.0
"""The app's 10 s, shortened."""


def quiet(line: str) -> None:
    """A log nothing reads."""


class Railroad:
    """The store's root, and the roster of `RAILROAD` in it."""

    def __init__(self, root: Path) -> None:
        self.root = root
        catalogued(root)
        (root / "layouts").mkdir()

    def roster(self, trains: Mapping[str, str | None]) -> None:
        """A roster whose trains each carry the camera named, or none. Trains
        naming one camera share the car carrying it, a camera being one car's
        (`lib/stock.py`)."""
        cars: dict[str, dict[str, str]] = {
            "loco": {"model": "arnold-ce68", "addr": "3"}
        }
        made: dict[str, list[dict[str, str]]] = {}
        for train, camera in trains.items():
            made[train] = [{"car": "loco"}]
            if camera is not None:
                car = f"car-{camera}"
                cars[car] = {"model": "bench-600", "camera": camera}
                made[train].append({"car": car})
        doc = {
            "roster": RAILROAD,
            "cars": cars,
            "trains": {train: {"cars": list_} for train, list_ in made.items()},
        }
        (self.root / "layouts" / f"{RAILROAD}.roster.yaml").write_text(
            yaml.safe_dump(doc)
        )


class Served:
    """A server on a thread of its own, stopped with the test."""

    def __init__(self, server: HTTPServer) -> None:
        self.server = server
        self._thread = threading.Thread(
            target=server.serve_forever, args=(0.05,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)


class Lens:
    """Where each camera host name a roster may hold is reached: the suite's
    cameras listen on loopback ports, which a bare host name cannot carry."""

    def __init__(self) -> None:
        self.cameras: dict[str, Camera] = {}
        self.away: dict[str, str] = {}

    def url(self, camera: str) -> str:
        if camera in self.cameras:
            return self.cameras[camera].url
        return self.away.setdefault(camera, f"http://127.0.0.1:{free_port()}{PATH}")


@pytest.fixture
def railroad(tmp_path: Path) -> Iterator[Railroad]:
    yield Railroad(tmp_path)


@pytest.fixture
def lens() -> Iterator[Lens]:
    found = Lens()
    yield found
    for camera in found.cameras.values():
        camera.stop()


@pytest.fixture
def store(railroad: Railroad) -> Iterator[str]:
    port = free_port()
    served = Served(make_server(railroad.root, port))
    yield f"http://127.0.0.1:{port}"
    served.stop()


@pytest.fixture
def cameras(lens: Lens) -> Iterator[Cameras]:
    opened = Cameras(
        AUTHORIZATION, url=lens.url, silence_s=SILENCE_S, linger_s=LINGER_S
    )
    yield opened
    opened.close()


@pytest.fixture
def face(store: str, cameras: Cameras) -> Iterator[int]:
    """The camera app's port."""
    port = free_port()
    documents = Documents(store, log=quiet, first_backoff_s=0.01, max_backoff_s=0.05)
    served = Served(Face(("127.0.0.1", port), documents, cameras, log=quiet))
    yield port
    served.stop()


def asked(
    port: int, path: str, method: str = "GET", timeout_s: float = 10.0
) -> http.client.HTTPResponse:
    """The face's answer to one request, its body unread."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout_s)
    connection.request(method, path)
    return connection.getresponse()


def parts(answer: http.client.HTTPResponse) -> Iterator[tuple[str, bytes]]:
    """Each part of a `multipart/x-mixed-replace; boundary=frame` body: its
    type and its bytes, read by its `Content-Length`. Read here rather than
    with the app's own reader, which is what is under test."""
    while True:
        line = answer.readline()
        if not line:
            return
        if line.strip() in (b"", b"--frame--"):
            continue
        assert line == b"--frame\r\n", line
        headers: dict[str, str] = {}
        while (line := answer.readline()) not in (b"\r\n", b""):
            name, _, value = line.decode().partition(":")
            headers[name.strip().lower()] = value.strip()
        yield headers["content-type"], answer.read(int(headers["content-length"]))
