"""`python -m tc49.camera` — the camera app as a process of its own.

It serves `GET /picture/<railroad>/<train>` (`face.py`) and reads the cameras
it relays (`stream.py`), and it is the one app that is **not on the bus**: it
publishes nothing and reads no row, so it is given no broker. What it is
given is the store, where the roster says which camera a train carries, read
on every request rather than once per build — so it follows no railroad
either, and needs none to come up: a request names its railroad.

The store is not waited for as the app comes up. A request made while the
store is away waits for it, as `lib/documents.py` waits, and nothing else
does.

The camera's login is the environment's, as a container is configured:
`TC49_CAMERA_USER` and `TC49_CAMERA_PASSWORD` on the service
(docs/DEPLOY.md), read once here. It ends on SIGTERM, as a container is
stopped.
"""

import contextlib
import os
import signal

from tc49.camera.face import Face, to_stderr
from tc49.camera.stream import Cameras, credentials
from tc49.lib.documents import Documents
from tc49.lib.startup import command_line

HOST = "127.0.0.1"
PORT = 8767
"""The port the face listens on: the store's 8765 and two up, 8766 being the
photo camera's in development (docs/DEPLOY.md)."""


def main() -> None:
    parser = command_line(
        prog="python -m tc49.camera",
        description="Relay each camera car's picture as"
        " GET /picture/<railroad>/<train>.",
        broker=False,
    )
    parser.add_argument(
        "--host", default=HOST, help=f"the interface to listen on (default {HOST})"
    )
    parser.add_argument(
        "--port", type=int, default=PORT, help=f"the port to listen on (default {PORT})"
    )
    args = parser.parse_args()
    cameras = Cameras(credentials(os.environ))
    face = Face((args.host, args.port), Documents(args.store), cameras)
    # SIGTERM is how a container is stopped: given SIGINT's handler, it raises
    # out of the server's wait.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    to_stderr(f"store {args.store}, serving on {args.host}:{args.port}")
    try:
        with contextlib.suppress(KeyboardInterrupt):
            face.serve_forever()
    finally:
        face.server_close()
        cameras.close()


if __name__ == "__main__":
    main()
