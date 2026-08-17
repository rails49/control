"""The store's HTTP face: what the layout editor talks to (ui/EDITOR.md).

Four routes, every one of them a store operation, which is why this belongs to
the store rather than to an app of its own — a `ui` package could not import
`tc49.store` and stay inside ADR-0013.

    GET  /drawings              the railroads there are
    GET  /drawings/<name>       one drawing, as the document it is
    PUT  /drawings/<name>       save it, keeping what the file says
    POST /review                what a drawing means, derived and explained

`review` is the one that carries the editor's whole view of topology: red
pins, junction membership, the derived layout, and why each pair of transits
does or does not run together. The front end reimplements none of it, so a
second union-find cannot disagree with the first inside the tool whose job is
to be believed.

It takes a *document* rather than a name because the interesting drawing is
the one being edited, which has not been saved and may not derive. Work in
progress is answered with 200 and a refusal inside; only a document that will
not load at all is a bad request.

The panel later adds a WebSocket bridge from `tc49/#` alongside this
(ui/PANEL.md). That is not a store operation and does not live here.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote

from yaml import YAMLError

from tc49.store.drawing import Drawing
from tc49.store.store import AssetStore

Response = tuple[int, dict[str, Any]]


def handle(store: AssetStore, method: str, path: str, body: Any) -> Response:
    """Route one request. A function of what was asked rather than of a socket,
    so the contract is testable without serving anything.

    Every way a document can be wrong answers with a status. A drawing that
    will not load is the client's problem or the file's, and either way the
    editor wants to read the reason rather than lose the connection.
    """
    try:
        return _route(store, method, path, body)
    except FileNotFoundError as missing:
        return 404, {"error": str(missing)}
    except (ValueError, TypeError, YAMLError) as bad:
        return 400, {"error": str(bad)}


def _route(store: AssetStore, method: str, path: str, body: Any) -> Response:
    route = unquote(path.split("?", 1)[0])  # a cache-buster is not a new route

    if method == "GET" and route == "/drawings":
        return 200, {"drawings": store.list()}

    if method == "POST" and route == "/review":
        if not isinstance(body, dict):
            return 400, {"error": "review takes a drawing document"}
        return 200, Drawing.from_document(body).review()

    name = route.removeprefix("/drawings/")
    if name != route and "/" not in name:
        if method == "GET":
            try:
                return 200, store.drawing(name)
            except FileNotFoundError:
                return 404, {"error": f"no drawing '{name}'"}
        if method == "PUT":
            return _put(store, name, body)

    return 404, {"error": f"no route {method} {route}"}


def _put(store: AssetStore, name: str, body: Any) -> Response:
    if not isinstance(body, dict):
        return 400, {"error": "a drawing document is required"}
    doc = cast(dict[str, Any], body)
    if doc.get("drawing") != name:
        return 400, {
            "error": f"drawing '{doc.get('drawing')}' cannot be saved as '{name}'"
        }
    store.put(doc)
    return 200, {"saved": name}


def make_server(root: Path, port: int = 8765) -> HTTPServer:
    """A server over `root`, not yet listening. One request at a time: there
    is one editor, and the YAML round trip behind `put` is a single shared
    reader. Handing the server back rather than running it is what lets a test
    start and stop one."""
    store = AssetStore(root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._answer("GET", None)

        def do_PUT(self) -> None:
            self._answer("PUT", self._body())

        def do_POST(self) -> None:
            self._answer("POST", self._body())

        def do_OPTIONS(self) -> None:
            """The preflight a browser sends before a JSON POST from the
            editor's own origin, which is not this one."""
            self._respond(200, {})

        def _answer(self, method: str, body: Any) -> None:
            try:
                status, payload = handle(store, method, self.path, body)
            except Exception as failure:  # noqa: BLE001 — a reply beats a reset
                status, payload = 500, {"error": repr(failure)}
            self._respond(status, payload)

        def _body(self) -> Any:
            try:
                length = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(length) or b"null")
            except ValueError:  # a bad length, or a body that is not JSON
                return None

        def _respond(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            # The editor is served from its own origin in development, so the
            # browser asks. Bound to the loopback, there is nobody else to ask.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(encoded)

    return HTTPServer(("127.0.0.1", port), Handler)
