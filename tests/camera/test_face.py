"""`GET /picture/<railroad>/<train>`, against a store on a thread and fake
cameras on loopback (ADR-0082; #851).

What is asserted is what a page and a camera each see: the answer's status,
its headers and the bytes in its parts on one side, and on the other how
many connections the camera was given, with which login, and when they went.
The app's 5 s and 10 s are shortened to `SILENCE_S` and `LINGER_S`.
"""

import http.client
import threading
import time
from itertools import pairwise
from urllib.parse import quote

import pytest

from tests.brokers import until
from tests.camera.cameras import AUTHORIZATION, PATH, Camera
from tests.camera.conftest import (
    LINGER_S,
    RAILROAD,
    SILENCE_S,
    Lens,
    Railroad,
    asked,
    parts,
)


def picture(train: str, railroad: str = RAILROAD) -> str:
    return f"/picture/{quote(railroad, safe='')}/{quote(train, safe='')}"


def watching(lens: Lens, name: str, camera: Camera) -> Camera:
    lens.cameras[name] = camera
    return camera


def test_two_readers_of_one_train_share_one_connection_and_its_bytes(
    railroad: Railroad, lens: Lens, face: int
) -> None:
    camera = watching(lens, "cam-a", Camera())
    railroad.roster({"ore": "cam-a"})
    one, two = asked(face, picture("ore")), asked(face, picture("ore"))
    for answer in (one, two):
        assert answer.status == 200
        assert answer.getheader("Content-Type") == "application/octet-stream"
        assert answer.getheader("Cache-Control") == "no-store"
        read = [part for part, _ in zip(parts(answer), range(5), strict=False)]
        assert all(kind == "image/jpeg" for kind, _ in read)
        assert all(frame in camera.sent for _, frame in read), "a frame was changed"
        numbers = [camera.sent.index(frame) for _, frame in read]
        assert numbers == sorted(set(numbers)), "frames out of order or repeated"
    assert camera.connections == 1
    assert camera.authorizations == [AUTHORIZATION]
    assert camera.paths == [PATH]


def test_two_trains_naming_one_camera_share_its_connection(
    railroad: Railroad, lens: Lens, face: int
) -> None:
    camera = watching(lens, "cam-a", Camera())
    railroad.roster({"ore": "cam-a", "coal": "cam-a"})
    for train in ("ore", "coal"):
        answer = asked(face, picture(train))
        assert answer.status == 200
        next(parts(answer))
    assert camera.connections == 1


def test_a_reader_that_stops_reading_holds_up_no_other(
    railroad: Railroad, lens: Lens, face: int
) -> None:
    """Frames big and fast enough that a reader taking none fills every
    buffer between it and the app within the test."""
    camera = watching(lens, "cam-a", Camera(size=256 * 1024, period_s=0.01))
    railroad.roster({"ore": "cam-a"})
    stalled = asked(face, picture("ore"))
    next(parts(stalled))
    reading = asked(face, picture("ore"))
    seen: list[float] = []
    for _, _frame in parts(reading):
        seen.append(time.monotonic())
        if seen[-1] - seen[0] > 2 * SILENCE_S:
            break
    gaps = [later - earlier for earlier, later in pairwise(seen)]
    assert max(gaps) < SILENCE_S / 2, "the other reader was held up"
    assert camera.connections == 1


def test_the_connection_outlives_its_last_reader_by_the_wait(
    railroad: Railroad, lens: Lens, face: int
) -> None:
    camera = watching(lens, "cam-a", Camera())
    railroad.roster({"ore": "cam-a"})
    first = asked(face, picture("ore"))
    next(parts(first))
    first.close()
    time.sleep(LINGER_S / 2)
    assert camera.gone == 0, "closed before the wait was over"
    again = asked(face, picture("ore"))
    next(parts(again))
    again.close()
    assert camera.connections == 1, "a request during the wait opened another"
    time.sleep(LINGER_S / 2)
    assert camera.gone == 0, "the second reader's wait was cut short by the first's"
    assert until(lambda: camera.gone == 1, LINGER_S * 3)
    assert camera.connections == 1


@pytest.mark.parametrize(
    ("trains", "path"),
    [
        ({"ore": "cam-a"}, picture("ore", railroad="nowhere")),
        ({"ore": "cam-a"}, picture("coal")),
        ({"ore": None}, picture("ore")),
        ({"ore": "cam-a"}, f"/picture/{RAILROAD}"),
        ({"ore": "cam-a"}, f"/picture/{RAILROAD}/ore/more"),
        ({"ore": "cam-a"}, "/rosters/oval"),
    ],
    ids=[
        "no-railroad",
        "no-train",
        "no-camera",
        "short",
        "long",
        "elsewhere",
    ],
)
def test_nothing_to_relay_is_404_with_no_body(
    railroad: Railroad,
    lens: Lens,
    face: int,
    trains: dict[str, str | None],
    path: str,
) -> None:
    camera = watching(lens, "cam-a", Camera())
    railroad.roster(trains)
    answer = asked(face, path)
    assert answer.status == 404
    assert answer.read() == b""
    assert camera.connections == 0


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
def test_any_other_method_is_404(
    railroad: Railroad, lens: Lens, face: int, method: str
) -> None:
    watching(lens, "cam-a", Camera())
    railroad.roster({"ore": "cam-a"})
    answer = asked(face, picture("ore"), method=method)
    assert answer.status == 404
    assert not [name for name in answer.headers if name.startswith("Access-Control")]


@pytest.mark.parametrize("answer", ["away", "refuse", "silent"])
def test_a_camera_that_sends_no_first_frame_is_502_in_time(
    railroad: Railroad, lens: Lens, face: int, answer: str
) -> None:
    if answer != "away":
        watching(lens, "cam-a", Camera(answer))
    railroad.roster({"ore": "cam-a"})
    began = time.monotonic()
    said = asked(face, picture("ore"))
    assert said.status == 502
    assert said.read() == b""
    assert time.monotonic() - began < SILENCE_S + 1.0


def test_a_stream_that_ends_ends_every_reader(
    railroad: Railroad, lens: Lens, face: int
) -> None:
    watching(lens, "cam-a", Camera(period_s=0.1, end_after=10))
    railroad.roster({"ore": "cam-a"})
    readers = [asked(face, picture("ore")) for _ in range(2)]
    read: list[int] = []

    def drain(answer: http.client.HTTPResponse) -> None:
        read.append(sum(1 for _ in parts(answer)))

    threads = [threading.Thread(target=drain, args=(one,)) for one in readers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=SILENCE_S + 3)
    assert not any(thread.is_alive() for thread in threads), "a response never ended"
    assert len(read) == 2 and all(read)


def test_a_query_string_is_ignored(railroad: Railroad, lens: Lens, face: int) -> None:
    camera = watching(lens, "cam-a", Camera())
    railroad.roster({"ore": "cam-a"})
    answer = asked(face, picture("ore") + "?t=12345")
    assert answer.status == 200
    _, frame = next(parts(answer))
    assert frame in camera.sent
    assert not [name for name in answer.headers if name.startswith("Access-Control")]


def test_the_camera_is_read_from_the_store_on_every_request(
    railroad: Railroad, lens: Lens, face: int
) -> None:
    before = watching(lens, "cam-a", Camera())
    after = watching(lens, "cam-b", Camera())
    railroad.roster({"ore": "cam-a"})
    answer = asked(face, picture("ore"))
    next(parts(answer))
    answer.close()
    railroad.roster({"ore": "cam-b"})
    answer = asked(face, picture("ore"))
    _, frame = next(parts(answer))
    assert frame in after.sent
    assert (before.connections, after.connections) == (1, 1)


def test_a_railroad_and_a_train_are_one_level_each(
    railroad: Railroad, lens: Lens, face: int
) -> None:
    """A name with a slash in it is escaped, and is a name rather than two
    levels."""
    watching(lens, "cam-a", Camera())
    railroad.roster({"ore/coal": "cam-a"})
    answer = asked(face, picture("ore/coal"))
    assert answer.status == 200
