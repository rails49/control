"""The camera app's HTTP face: `GET /picture/<railroad>/<train>`, the
picture of the camera car in that train, on control's own origin.

A page cannot reach the camera itself: a UI talks only to the bus, the store
and its own app's face, and an HTTPS page cannot embed an HTTP stream
(ADR-0082). So this answers for the camera, and the store never does.

**Which camera is asked on every request.** The roster is read from the store
each time (`Documents.roster`) and the train's `camera` taken
(`lib/roster.py`), so a camera car coupled to another train, or given another
address on the Stock screen, is what the next request reads.

The answers, each with no body but the picture:

- **404** — the store has no such railroad, the roster no such train, or the
  train carries no camera; and any other path or method.
- **502** — the camera sent no first frame within `silence_s`: unreachable,
  refusing, answering anything but 200 (a 401 included), or silent.
- **200** once the first frame is in hand, `multipart/x-mixed-replace` with a
  part per frame, each JPEG as the camera sent it. It ends when the camera's
  stream does, or when the camera goes `silence_s` without a frame. Nothing
  reconnects: a page asks again, adding a query string if it must, which is
  ignored here.

No `Access-Control-*` header: the face is control's UI's, on its origin.
"""

import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from tc49.camera.stream import Cameras
from tc49.lib.documents import Documents

PREFIX = "picture"
"""The one route's first level, which the door routes here (docs/DEPLOY.md)."""

BOUNDARY = "frame"


def to_stderr(line: str) -> None:
    print(f"camera: {line}", file=sys.stderr, flush=True)


class Face(ThreadingHTTPServer):
    """The server, holding what every request reads: the store and the open
    camera connections. A thread per request, because a request is a stream
    held open for as long as its page watches it."""

    def __init__(
        self,
        address: tuple[str, int],
        documents: Documents,
        cameras: Cameras,
        log: Callable[[str], None] = to_stderr,
    ) -> None:
        self.documents = documents
        self.cameras = cameras
        self.log = log
        super().__init__(address, Picture)


class Picture(BaseHTTPRequestHandler):
    """One request."""

    @property
    def face(self) -> Face:
        return cast(Face, self.server)

    def setup(self) -> None:
        super().setup()
        # A page that stops reading is let go of once it has held a write up
        # this long, so it stops counting as a reader of its camera.
        self.connection.settimeout(self.face.cameras.silence_s)

    def __getattr__(self, name: str) -> Any:
        # Every method but GET is a route that is not here. `http.server`
        # looks for a `do_<METHOD>` and answers 501 where there is none, and
        # there is no list of methods to write one for each of.
        if name.startswith("do_"):
            return self._nowhere
        raise AttributeError(name)

    def do_GET(self) -> None:
        camera = self._camera()
        if camera is None:
            self._nowhere()
            return
        cameras = self.face.cameras
        stream = cameras.join(camera)
        try:
            got = stream.next(0, cameras.silence_s)
            if got is None:
                self._empty(502)
                return
            self.send_response(200)
            self.send_header(
                "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while got is not None:
                count, frame = got
                self.wfile.write(
                    f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                    + frame
                    + b"\r\n"
                )
                self.wfile.flush()
                got = stream.next(count, cameras.silence_s)
            self.wfile.write(f"--{BOUNDARY}--\r\n".encode("ascii"))
        except OSError:
            pass  # the page went away, or stopped reading
        finally:
            cameras.leave(stream)

    def _camera(self) -> str | None:
        """The camera of the train the path names, or `None` where there is
        no such railroad, train or camera."""
        levels = urlsplit(self.path).path.split("/")
        if len(levels) != 4 or levels[0] or levels[1] != PREFIX:
            return None
        railroad, train = (unquote(level) for level in levels[2:])
        if not railroad or not train:
            return None
        try:
            roster = self.face.documents.roster(railroad)
        except FileNotFoundError:
            return None
        found = roster.trains.get(train)
        return None if found is None else found.camera

    def _nowhere(self) -> None:
        self._empty(404)

    def _empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        self.face.log(format % args)
