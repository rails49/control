"""A camera car's camera, faked: a standard-library HTTP server on loopback
serving `multipart/x-mixed-replace` JPEG parts behind Basic auth, as the real
one does at `/media/?action=stream`.

It counts the connections it is given and the ones it has seen go, and keeps
the `Authorization` each was made with, which are what the suite asserts on
the camera's side: one connection per camera, made with the configured login
and closed once nobody reads it.
"""

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

from tests.ports import free_port

USER = "admin"
PASSWORD = "secret"
AUTHORIZATION = "Basic YWRtaW46c2VjcmV0"  # admin:secret
PATH = "/media/?action=stream"


def jpeg(number: int, size: int = 1024) -> bytes:
    """A frame telling which one it is: a JPEG's start and end markers around
    its number, padded to `size`."""
    said = f"{number:08d}".encode()
    return b"\xff\xd8" + said + b"\0" * max(0, size - len(said) - 4) + b"\xff\xd9"


class Camera:
    """One fake camera, listening on a port of its own.

    `answer` is what it does with a request: `"stream"` sends a frame every
    `period_s` — `end_after` of them and then ends the body, or forever where
    that is `None` — `"refuse"` answers 401, and `"silent"` answers 200 and
    then sends nothing.
    """

    def __init__(
        self,
        answer: str = "stream",
        *,
        period_s: float = 0.02,
        size: int = 1024,
        end_after: int | None = None,
    ) -> None:
        self.answer = answer
        self.period_s = period_s
        self.size = size
        self.end_after = end_after
        self.port = free_port()
        self.sent: list[bytes] = []
        self.authorizations: list[str | None] = []
        self.paths: list[str] = []
        self.gone = 0
        self._lock = threading.Lock()
        self._numbered = 0
        self._server = _Server(self)
        threading.Thread(
            target=self._server.serve_forever, args=(0.05,), daemon=True
        ).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}{PATH}"

    @property
    def connections(self) -> int:
        return len(self.authorizations)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def numbered(self) -> Iterator[bytes]:
        """The frames one connection is sent, each numbered across them all."""
        count = 0
        while self.end_after is None or count < self.end_after:
            with self._lock:
                self._numbered += 1
                frame = jpeg(self._numbered, self.size)
                self.sent.append(frame)
            yield frame
            count += 1
            time.sleep(self.period_s)


class _Server(ThreadingHTTPServer):
    def __init__(self, camera: Camera) -> None:
        self.camera = camera
        super().__init__(("127.0.0.1", camera.port), _Handler)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        camera = cast(_Server, self.server).camera
        camera.authorizations.append(self.headers.get("Authorization"))
        camera.paths.append(self.path)
        if camera.answer == "refuse" or self.headers.get("Authorization") != (
            AUTHORIZATION
        ):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="camera"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header(
            "Content-Type", "multipart/x-mixed-replace; boundary=myboundary"
        )
        self.end_headers()
        if camera.answer == "silent":
            time.sleep(30)
            return
        try:
            for frame in camera.numbered():
                self.wfile.write(
                    b"--myboundary\r\nContent-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                    + frame
                    + b"\r\n"
                )
                self.wfile.flush()
        except OSError:
            camera.gone += 1

    def log_message(self, format: str, *args: Any) -> None:
        pass
