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
from collections.abc import Callable
from itertools import pairwise
from urllib.parse import quote

import pytest
from rails49_testing.broker import until

from tests.camera.cameras import AUTHORIZATION, PATH, Camera
from tests.camera.conftest import (
    LINGER_S,
    RAILROAD,
    SILENCE_S,
    Railroad,
    asked,
    away,
    parts,
)

Fake = Callable[..., Camera]


def picture(train: str, railroad: str = RAILROAD) -> str:
    return f"/picture/{quote(railroad, safe='')}/{quote(train, safe='')}"


def test_two_readers_of_one_train_share_one_connection_and_its_bytes(
    railroad: Railroad, fake: Fake, face: int
) -> None:
    camera = fake()
    railroad.roster({"ore": camera.url})
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


@pytest.mark.parametrize(
    ("served", "written"),
    [("/?action=stream", "/?action=stream"), ("/", "")],
    ids=["path", "none"],
)
def test_a_camera_is_read_at_the_port_and_path_its_url_names(
    railroad: Railroad, fake: Fake, face: int, served: str, written: str
) -> None:
    """mjpg-streamer's path rather than the Pnzeo W3's, and a URL with no
    path at all, which is asked at `/`."""
    camera = fake(path=served)
    railroad.roster({"ore": f"http://127.0.0.1:{camera.port}{written}"})
    answer = asked(face, picture("ore"))
    assert answer.status == 200
    _, frame = next(parts(answer))
    assert frame in camera.sent
    assert camera.paths == [served]


def test_two_trains_with_two_cameras_get_a_connection_each(
    railroad: Railroad, fake: Fake, face: int
) -> None:
    ore, coal = fake(), fake()
    railroad.roster({"ore": ore.url, "coal": coal.url})
    for train, camera in (("ore", ore), ("coal", coal)):
        answer = asked(face, picture(train))
        _, frame = next(parts(answer))
        assert frame in camera.sent
    assert (ore.connections, coal.connections) == (1, 1)


def test_a_reader_that_stops_reading_holds_up_no_other(
    railroad: Railroad, fake: Fake, face: int
) -> None:
    """Frames big and fast enough that a reader taking none fills every
    buffer between it and the app within the test."""
    camera = fake(size=256 * 1024, period_s=0.01)
    railroad.roster({"ore": camera.url})
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
    railroad: Railroad, fake: Fake, face: int
) -> None:
    camera = fake()
    railroad.roster({"ore": camera.url})
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
    ("carries", "path"),
    [
        (True, picture("ore", railroad="nowhere")),
        (True, picture("coal")),
        (False, picture("ore")),
        (True, f"/picture/{RAILROAD}"),
        (True, f"/picture/{RAILROAD}/ore/more"),
        (True, "/rosters/oval"),
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
    fake: Fake,
    face: int,
    carries: bool,
    path: str,
) -> None:
    camera = fake()
    railroad.roster({"ore": camera.url if carries else None})
    answer = asked(face, path)
    assert answer.status == 404
    assert answer.read() == b""
    assert camera.connections == 0


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
def test_any_other_method_is_404(
    railroad: Railroad, fake: Fake, face: int, method: str
) -> None:
    railroad.roster({"ore": fake().url})
    answer = asked(face, picture("ore"), method=method)
    assert answer.status == 404
    assert not [name for name in answer.headers if name.startswith("Access-Control")]


@pytest.mark.parametrize("answer", ["away", "refuse", "silent", "elsewhere"])
def test_a_camera_that_sends_no_first_frame_is_502_in_time(
    railroad: Railroad, fake: Fake, face: int, answer: str
) -> None:
    """`elsewhere` is a camera asked at a path it does not serve."""
    if answer == "away":
        url = away()
    elif answer == "elsewhere":
        url = f"http://127.0.0.1:{fake().port}/other"
    else:
        url = fake(answer).url
    railroad.roster({"ore": url})
    began = time.monotonic()
    said = asked(face, picture("ore"))
    assert said.status == 502
    assert said.read() == b""
    assert time.monotonic() - began < SILENCE_S + 1.0


def test_a_stream_that_ends_ends_every_reader(
    railroad: Railroad, fake: Fake, face: int
) -> None:
    railroad.roster({"ore": fake(period_s=0.1, end_after=10).url})
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


def test_a_query_string_is_ignored(railroad: Railroad, fake: Fake, face: int) -> None:
    camera = fake()
    railroad.roster({"ore": camera.url})
    answer = asked(face, picture("ore") + "?t=12345")
    assert answer.status == 200
    _, frame = next(parts(answer))
    assert frame in camera.sent
    assert not [name for name in answer.headers if name.startswith("Access-Control")]


def test_the_camera_is_read_from_the_store_on_every_request(
    railroad: Railroad, fake: Fake, face: int
) -> None:
    before, after = fake(), fake()
    railroad.roster({"ore": before.url})
    answer = asked(face, picture("ore"))
    next(parts(answer))
    answer.close()
    railroad.roster({"ore": after.url})
    answer = asked(face, picture("ore"))
    _, frame = next(parts(answer))
    assert frame in after.sent
    assert (before.connections, after.connections) == (1, 1)


def test_a_railroad_and_a_train_are_one_level_each(
    railroad: Railroad, fake: Fake, face: int
) -> None:
    """A name with a slash in it is escaped, and is a name rather than two
    levels."""
    railroad.roster({"ore/coal": fake().url})
    answer = asked(face, picture("ore/coal"))
    assert answer.status == 200
