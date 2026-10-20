"""The camera side: one connection per camera, read a part at a time, and
the newest frame handed to whoever is reading it (ADR-0082, decision 3).

A camera car's camera speaks plain HTTP with Basic auth and sends MJPEG — a
`multipart/x-mixed-replace` body, one JPEG per part. Modelled on
[iot49/pnzeo](https://github.com/iot49/pnzeo)'s `Camera.frames()` and not
importing it: a part is read by its `Content-Length`, as pnzeo's
`_content_length` and `_read_exact` read it, and a part without one ends the
stream rather than being searched for its boundary.

**One connection per camera address**, however many pages are watching it,
and that includes two trains naming one camera car. A camera on the LAN is a
small device that serves few clients and serves each of them the same
picture; a second connection to it buys nothing but load. So every reader of
one address reads one `Stream`, and `Cameras` is what keeps it one.

**Each reader is handed the newest frame.** A reader that cannot keep up — a
page on a slow link, a tab gone to the background — skips the frames it was
too slow for. It never holds up the camera's stream or another reader: the
connection is read on a thread of its own, which only ever replaces the frame
it holds, and a reader is a wait for that frame to change.

**The connection outlives its last reader by a while.** A page that asks
again — a throttle handed another train and back, a reload — finds it still
open rather than paying for a new handshake, and a camera nobody is watching
is let go of once the wait is over.

Standard library only, as `lib/documents.py` is: the whole of the protocol is
a request line, a status line and a run of parts.
"""

import base64
import socket
import threading
from collections.abc import Callable, Iterator, Mapping
from typing import BinaryIO
from urllib.parse import urlsplit

SILENCE_S = 5.0
"""How long a camera may go without sending a frame before its stream counts
as ended: the first frame as well as every one after it. A camera that is
reachable and streaming sends several a second, so this is a camera that is
not — refusing, unreachable, or connected and silent."""

LINGER_S = 10.0
"""How long a connection is kept open once its last reader has left."""

USER = "admin"
"""The user a camera is logged into as where `TC49_CAMERA_USER` says none:
the camera's own default, which no box changes today (docs/DEPLOY.md)."""

MAX_LINE = 1024
"""The longest header line read. A camera's are a few dozen bytes; a longer
one is not a camera speaking MJPEG, and ends the stream."""


def stream_url(camera: str) -> str:
    """Where a camera at `camera` — a bare host name or IPv4 address, as the
    roster holds it (`lib/stock.py`) — serves its MJPEG."""
    return f"http://{camera}/media/?action=stream"


def credentials(environ: Mapping[str, str]) -> str:
    """The `Authorization` header every camera is asked with, from
    `TC49_CAMERA_USER` and `TC49_CAMERA_PASSWORD`. An unset or empty user is
    `admin`, and an unset password is empty: the camera's web login as it
    ships. Read once, as the app starts."""
    user = environ.get("TC49_CAMERA_USER") or USER
    password = environ.get("TC49_CAMERA_PASSWORD", "")
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def frames(body: BinaryIO) -> Iterator[bytes]:
    """The JPEGs of a `multipart/x-mixed-replace` body, as the camera sent
    them. Ends at the end of the body, at a part with no `Content-Length`,
    and at a part shorter than it says."""
    while True:
        headers = _part(body)
        if headers is None:
            return
        length = _content_length(headers)
        if length is None:
            return
        frame = _read_exact(body, length)
        if frame is None:
            return
        yield frame


def _part(body: BinaryIO) -> dict[str, str] | None:
    """The headers of the next part, read past the boundary and the blank
    lines around it; `None` at the end of the body."""
    headers: dict[str, str] = {}
    while True:
        line = body.readline(MAX_LINE)
        if not line or not line.endswith(b"\n"):
            return None
        line = line.strip()
        if not line:
            if headers:
                return headers
            continue
        if not headers and line.startswith(b"--"):
            continue  # the boundary, or the end of the body after it
        name, colon, value = line.partition(b":")
        if not colon:
            return None
        headers[name.strip().lower().decode("latin-1")] = value.strip().decode(
            "latin-1"
        )


def _content_length(headers: Mapping[str, str]) -> int | None:
    said = headers.get("content-length")
    if said is None or not said.isdigit():
        return None
    return int(said)


def _read_exact(body: BinaryIO, length: int) -> bytes | None:
    read = body.read(length)
    return read if len(read) == length else None


class Stream:
    """One connection to one camera, read on a thread of its own from the
    moment it is made until the camera stops or it is closed.

    Ended for good either way: a stream that has ended is never read again,
    and the next reader of that camera is given a new one (`Cameras`). The app
    does not reconnect by itself — a page asks again.
    """

    def __init__(
        self,
        camera: str,
        url: str,
        authorization: str,
        silence_s: float,
        ended: Callable[["Stream"], None],
    ) -> None:
        self.camera = camera
        self.readers = 0
        """How many requests are reading this. `Cameras`' to count, under its
        lock."""
        self.left = 0
        """How many times the last reader has left, so a wait that a reader
        joining and leaving again has overtaken closes nothing."""
        self._url = url
        self._authorization = authorization
        self._silence_s = silence_s
        self._ended_with = ended
        self._changed = threading.Condition()
        self._frame = b""
        self._count = 0
        self._ended = False
        self._socket: socket.socket | None = None
        threading.Thread(
            target=self._read, name=f"camera {camera}", daemon=True
        ).start()

    def next(self, after: int, timeout_s: float) -> tuple[int, bytes] | None:
        """The newest frame, once there is one newer than the `after`th, with
        its number; `None` where the stream ends or none comes in time."""
        with self._changed:
            self._changed.wait_for(
                lambda: self._count > after or self._ended, timeout_s
            )
            if self._count > after:
                return self._count, self._frame
            return None

    def close(self) -> None:
        """End the stream, waking every reader. Shut down rather than only
        closed, because a close does not wake the thread blocked reading it."""
        with self._changed:
            self._ended = True
            self._changed.notify_all()
            held = self._socket
        if held is not None:
            try:
                held.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # already gone

    def _read(self) -> None:
        try:
            self._stream()
        except (OSError, ValueError):
            pass  # not reachable, refused, gone quiet or gone: all an end
        finally:
            self.close()
            self._ended_with(self)

    def _stream(self) -> None:
        where = urlsplit(self._url)
        held = socket.create_connection(
            (where.hostname or "", where.port or 80), timeout=self._silence_s
        )
        with self._changed:
            self._socket = held
            if self._ended:
                held.close()
                return
        with held, held.makefile("rb") as body:
            path = where.path + (f"?{where.query}" if where.query else "")
            held.sendall(
                f"GET {path} HTTP/1.0\r\nHost: {where.netloc}\r\n"
                f"Authorization: {self._authorization}\r\n\r\n".encode("latin-1")
            )
            if not _answered_ok(body):
                return
            for frame in frames(body):
                with self._changed:
                    if self._ended:
                        return
                    self._frame = frame
                    self._count += 1
                    self._changed.notify_all()


def _answered_ok(body: BinaryIO) -> bool:
    """Whether the camera answered 200, with the rest of its headers read so
    the body is next. Anything else — a 401 included — is no stream."""
    status = body.readline(MAX_LINE).split()
    if len(status) < 2 or not status[0].startswith(b"HTTP/") or status[1] != b"200":
        return False
    while True:
        line = body.readline(MAX_LINE)
        if not line.endswith(b"\n"):
            return False
        if not line.strip():
            return True


class Cameras:
    """The open connections, one per camera address, and how many requests
    are reading each.

    `join` hands a reader the open connection to its camera, or opens one;
    `leave` counts it out, and a connection with no reader left is closed
    `linger_s` later unless somebody joins in between. A connection that ends
    by itself is forgotten at once, so the next reader opens another.

    `url` says where a camera address is read from. The camera's own path
    everywhere but the suite, which serves its cameras on loopback ports a
    roster's bare host name cannot carry.
    """

    def __init__(
        self,
        authorization: str,
        *,
        url: Callable[[str], str] = stream_url,
        silence_s: float = SILENCE_S,
        linger_s: float = LINGER_S,
    ) -> None:
        self.silence_s = silence_s
        self._authorization = authorization
        self._url = url
        self._linger_s = linger_s
        self._lock = threading.Lock()
        self._open: dict[str, Stream] = {}

    def join(self, camera: str) -> Stream:
        with self._lock:
            stream = self._open.get(camera)
            if stream is None:
                stream = Stream(
                    camera,
                    self._url(camera),
                    self._authorization,
                    self.silence_s,
                    self._forget,
                )
                self._open[camera] = stream
            stream.readers += 1
            return stream

    def leave(self, stream: Stream) -> None:
        with self._lock:
            stream.readers -= 1
            if stream.readers > 0:
                return
            stream.left += 1
            left = stream.left
        wait = threading.Timer(self._linger_s, self._linger_over, (stream, left))
        wait.daemon = True
        wait.start()

    def close(self) -> None:
        """Every connection, as the app ends."""
        with self._lock:
            streams = list(self._open.values())
            self._open.clear()
        for stream in streams:
            stream.close()

    def _linger_over(self, stream: Stream, left: int) -> None:
        with self._lock:
            if stream.readers > 0 or stream.left != left:
                return
            if self._open.get(stream.camera) is not stream:
                return
            del self._open[stream.camera]
        stream.close()

    def _forget(self, stream: Stream) -> None:
        with self._lock:
            if self._open.get(stream.camera) is stream:
                del self._open[stream.camera]
