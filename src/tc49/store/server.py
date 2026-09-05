"""The store's HTTP face: what the layout editor talks to (ui/EDITOR.md).

Every route is a store operation, which is why this belongs to the store
rather than to an app of its own — a `ui` package could not import
`tc49.store` and stay inside ADR-0013.

    GET  /drawings              the railroads there are
    GET  /drawings/<name>       one drawing, as the document it is
    PUT  /drawings/<name>       save it, keeping what the file says
    POST /review                what a drawing means, derived and explained
    GET  /layouts/<name>        the layout that drawing derives to
    GET  /rosters/<name>        one railroad's roster, as the document it is
    PUT  /rosters/<name>        save it, keeping what the file says
    GET  /rosters/<name>/trains its trains, each with its length and the
                                functions its cars declare
    GET  /catalogue             every model the installation knows, by name
    GET  /catalogue/<name>      one model, as the document it is
    PUT  /catalogue/<name>      save it, keeping what the file says
    GET  /backup                whether the store can be backed up, is being,
                                and what there is to restore to
    PUT  /backup                turn automated backup on or off
    POST /backup/commit         back the store up now, and attempt a push
    POST /backup/restore        put the store back as a backup held it
    POST /backup/repository     back up to an empty repository the person made

`review` is the one that carries the editor's whole view of topology: red
pins, the portal labels that pair with nothing, junction membership, the
derived layout, and why each pair of transits does or does not run together.
The front end reimplements none of it, so a second union-find cannot disagree
with the first inside the tool whose job is to be believed.

`/layouts/<name>` is the other derivation, and it is the apps': the scheduler,
the dispatcher and the layout interface each take a `Layout` at construction,
and in its own process none of them can import the store to derive one
(ADR-0013, ADR-0059 decision 5). Read-only, since a layout is derived and
never authored (ADR-0015), and a drawing that does not derive yet is a 422
rather than a refusal inside a 200 — `review`'s caller is drawing the fault
on the canvas, and this one is an app that has nothing to run on.

**The route is the document, so `GET` and `PUT` on `/rosters/<name>` are
inverses**: the roster as the file has it, which is what an editing surface
needs and what makes a roster creatable from the app at all. Until it was, a
person could draw a railroad and save it and then not put a train on it — the
flow the app exists for stopped one step short (#388). Strict, unlike a
drawing: a drawing is readable half-made because there is a picture to look at,
and a roster is not. A roster arriving without a car is that car removed, so
removing one needs no verb.

`/rosters/<name>/trains` is the run views': a run is built from a railroad, and
its stock is the railroad's roster (ui/PANEL.md, ADR-0039); what the run is
doing is the bus's to say and never this face's. The run view reads a train's
length off it
and the throttle reads what a person driving that train can switch
(ui/THROTTLE.md), both of them derived from the cars the train is made of. It
is a path of its own because it is a *derived* answer and deliberately
withholds the cars, the addresses and the function numbers an editing surface
has to have, so one route could not serve both.

A **scenario is not served at all**. It is the harness's file format, read off
disk by `tc49 bench` and by `tc49 live --scenario`, and never
browser-reachable (#171).

Either way the roster is the railroad's and not the run's: which trains it owns
does not change while a session is up, and what the bus says is where they are.

The **catalogue** routes are the installation's rather than any railroad's: a
model is what a product is and a car names one (ADR-0045). They answer
documents rather than the merged models a roster is read against, because what
reads them is the screen that edits them — and because a model document keeps
fields nothing here will ever branch on, the shelf a locomotive lives on among
them (`lib/stock.py`). One file per model, which is what keeps two entries
independently editable and a backup's `git diff` readable.

`PUT /catalogue/<name>` is the first write on this face that is not a
drawing's, and it is the one a fresh box needs: with no `catalogue/` directory
every car names a model the installation has not got, so no roster can be
written at all (#392). There is **no `DELETE`** — this face has no DELETE verb
for any document, and an unused model costs nothing.

`review` takes a *document* rather than a name because the interesting drawing is
the one being edited, which has not been saved and may not derive. Work in
progress is answered with 200 and a refusal inside; only a document that will
not load at all is a bad request.

The **backup** routes are store operations like the rest: what they act on is
the installation's store, which is what this server has open, and a browser
cannot shell out to git. The app drives git and does not own it, so a store
that is not a repository is answered rather than initialized, and what git
said comes back as it came (ADR-0053, #321). It becomes one by adopting an
empty repository the person made, cloned at the address they give (#355). A
save is what arms the idle timer, which is why every `PUT` — a drawing's, a
model's, a roster's — tells the backup it happened, the one place the two
meet.

**Every route is refused to a page on another origin.** A request carrying an
`Origin` header that is not this server's own `Host` is answered 403 and
nothing here runs, and no `Access-Control-*` header is sent at all. The app
fetches these routes on its own origin — through vite's proxy in development
and through the same proxy that serves the page on a layout server — so it
never needed one. Vite rewrites `Host` to the proxy's target, which is why a
page served from this machine is admitted whatever the `Host` (ADR-0057).
What this stops is a page somebody's browser happens to visit driving the
store of a railroad it is on the same network as, which is not what "the LAN
is the trust boundary" ever meant (ADR-0055, ADR-0042). A request with no
`Origin` at all is a native client and goes through: the LAN boundary is
unchanged.

The run view reads `tc49/#` from the broker alongside this, over its own
WebSocket listener (ui/PANEL.md, ADR-0059 decision 4). That is not a store
operation and does not live here.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote

from yaml import YAMLError

from tc49.lib.origin import is_own_page
from tc49.lib.roster import Roster
from tc49.store.backup import Backup, Said
from tc49.store.drawing import Drawing
from tc49.store.store import AssetStore

Response = tuple[int, dict[str, Any]]


def handle(
    store: AssetStore, backup: Backup, method: str, path: str, body: Any
) -> Response:
    """Route one request. A function of what was asked rather than of a socket,
    so the contract is testable without serving anything.

    Every way a document can be wrong answers with a status. A drawing that
    will not load is the client's problem or the file's, and either way the
    editor wants to read the reason rather than lose the connection.
    """
    try:
        return _route(store, backup, method, path, body)
    except FileNotFoundError as missing:
        return 404, {"error": str(missing)}
    except (ValueError, TypeError, YAMLError) as bad:
        return 400, {"error": str(bad)}


def _route(
    store: AssetStore, backup: Backup, method: str, path: str, body: Any
) -> Response:
    route = unquote(path.split("?", 1)[0])  # a cache-buster is not a new route

    if method == "GET" and route == "/drawings":
        return 200, {"drawings": store.list()}

    if route.startswith("/backup"):
        return _backup(backup, method, route, body)

    if method == "POST" and route == "/review":
        if not isinstance(body, dict):
            return 400, {"error": "review takes a drawing document"}
        return 200, Drawing.from_document(body).review()

    if method == "GET" and route == "/catalogue":
        # An installation with no `catalogue/` directory knows no models,
        # which is every fresh box: an empty map rather than a 404.
        return 200, {"models": store.models()}

    model = route.removeprefix("/catalogue/")
    if model != route and "/" not in model:
        if method == "GET":
            try:
                return 200, store.model(model)
            except FileNotFoundError:
                return 404, {"error": f"no model '{model}'"}
        if method == "PUT":
            return _put_model(store, backup, model, body)

    rest = route.removeprefix("/rosters/")
    if rest != route:
        # The document is the route, so `/rosters/<name>` alone is the roster
        # itself and the run view's derived answer hangs below it. Which is
        # why the guard is a partition rather than a refusal of every path
        # with a '/' in it, as the drawing's and the model's still are.
        railroad, _, derived = rest.partition("/")
        if method == "GET" and derived == "trains":
            return 200, _trains(store.roster(railroad))
        if not derived:
            if method == "GET":
                return 200, store.roster_document(railroad)
            if method == "PUT":
                return _put_roster(store, backup, railroad, body)

    railroad = route.removeprefix("/layouts/")
    if method == "GET" and railroad != route and "/" not in railroad:
        return _layout(store, railroad)

    name = route.removeprefix("/drawings/")
    if name != route and "/" not in name:
        if method == "GET":
            try:
                return 200, store.drawing(name)
            except FileNotFoundError:
                return 404, {"error": f"no drawing '{name}'"}
        if method == "PUT":
            return _put(store, backup, name, body)

    return 404, {"error": f"no route {method} {route}"}


def _layout(store: AssetStore, name: str) -> Response:
    """The layout a railroad's drawing derives to, as the document
    `Layout.from_document` reads.

    Derived and never stored (ADR-0015), so this is the drawing read and
    derived on the way out and there is no `PUT`: what a person edits is the
    drawing, and a layout arriving here would be a second description of the
    same railroad.

    **Three answers, and an app has to tell them apart.** 404 is a railroad
    with no drawing — the name is wrong, or nothing has been drawn under it
    yet. 422 is a drawing that is there and does not derive: work in progress,
    which the editor shows as red pins and unpaired portals (`review`), and
    which an app can do nothing with but say what is wrong and wait for
    somebody to finish it. A drawing that will not load at all stays a 400
    like every other route's, the fault being in the document rather than in
    what it describes.

    It exists because an app in its own process cannot import the store to
    derive one (ADR-0013, ADR-0059 decision 5); `lib/documents.py` is what
    reads it.
    """
    try:
        drawing = Drawing.from_document(store.drawing(name))
    except FileNotFoundError:
        return 404, {"error": f"no drawing '{name}'"}
    try:
        return 200, drawing.derive()
    except ValueError as refusal:
        return 422, {"error": str(refusal)}


def _backup(backup: Backup, method: str, route: str, body: Any) -> Response:
    """The five backup routes.

    **A refusal comes back inside a 200**, the way `review`'s does. Nothing
    here is a bad request: the store not being a repository, a remote that is
    not there and a restore over documents that were never backed up are all
    states of somebody's machine that the UI has to read and say, and a status
    code would leave it guessing which of them it was. `ok` says whether it
    happened and `said` carries git's own words.
    """
    if method == "GET" and route == "/backup":
        return 200, backup.status()

    if method == "PUT" and route == "/backup":
        if not isinstance(body, dict) or not isinstance(
            (on := cast(dict[str, Any], body).get("automatic")), bool
        ):
            return 400, {"error": "the switch takes {'automatic': true|false}"}
        backup.switch(on)
        return 200, backup.status()

    if method == "POST" and route == "/backup/commit":
        return _said(backup, backup.back_up())

    if method == "POST" and route == "/backup/restore":
        # The backup to come back to, and the last one where none is named:
        # a person restoring usually names an earlier one, the session they
        # want undone having been backed up itself.
        wanted: Any = (
            cast(dict[str, Any], body).get("commit") if isinstance(body, dict) else None
        )
        return _said(backup, backup.restore(str(wanted) if wanted else "HEAD"))

    if method == "POST" and route == "/backup/repository":
        if not isinstance(body, dict) or not isinstance(
            (url := cast(dict[str, Any], body).get("url")), str
        ):
            return 400, {"error": "adopting takes {'url': '<address>'}"}
        return _said(backup, backup.adopt(url))

    return 404, {"error": f"no route {method} {route}"}


def _said(backup: Backup, said: Said) -> Response:
    """What git made of it, over the state it left behind. One shape for both
    driving routes, so a surface reads the answer and the store's standing
    from one reply and cannot draw them from different moments."""
    return 200, {"ok": said.ok, "said": said.words, **backup.status()}


def _put(store: AssetStore, backup: Backup, name: str, body: Any) -> Response:
    if not isinstance(body, dict):
        return 400, {"error": "a drawing document is required"}
    doc = cast(dict[str, Any], body)
    if doc.get("drawing") != name:
        return 400, {
            "error": f"drawing '{doc.get('drawing')}' cannot be saved as '{name}'"
        }
    store.put(doc)
    # The save that arms the idle timer. It says a document was written and
    # nothing about which — what moved is git's answer, and a person editing a
    # roster by hand under the same store is as much a change as this is.
    backup.saved()
    return 200, {"saved": name}


def _trains(roster: Roster) -> dict[str, Any]:
    """What the run views read a roster for: each train's length and what a
    person driving it can switch.

    Derived rather than written down, which is why it is a path of its own
    below the document: `/rosters/<name>` is the roster as the file has it and
    `GET` and `PUT` there are inverses, and one answer cannot be both that and
    this. The cars a train is made of, their addresses and which function
    number each name sits on are the stock screen's and the translator's, not
    a view's (ui/THROTTLE.md, ADR-0045). Written out rather than `asdict`,
    which would put every field of the document on this face the day one is
    added — and would drop both of these, which a train derives.
    """
    return {
        "roster": roster.railroad,
        "trains": {
            name: {
                "length": train.length,
                "functions": [
                    {"name": function.name, "values": list(function.values)}
                    for function in train.functions
                ],
            }
            for name, train in sorted(roster.trains.items())
        },
    }


def _put_roster(store: AssetStore, backup: Backup, name: str, body: Any) -> Response:
    """One railroad's roster, created or replaced.

    Whole-document like every other write on this face, so a roster arriving
    without a car is that car removed and removing one needs no verb of its
    own. Strict: a drawing is readable half-made because there is a picture to
    look at, and a roster is not, so a document that does not validate is a
    400 carrying the validator's words and nothing is written.
    """
    if not isinstance(body, dict):
        return 400, {"error": "a roster document is required"}
    store.put_roster(cast(dict[str, Any], body), name)
    # As a drawing's save does, and for the same reason: a roster written is a
    # document of the store that has moved (#388).
    backup.saved()
    return 200, {"saved": name}


def _put_model(store: AssetStore, backup: Backup, name: str, body: Any) -> Response:
    """One model, created or replaced.

    The name in the path is what the document is filed under and what every
    car refers to it by, so a document naming another model is refused rather
    than filed under this one — the disagreement `_put` catches for a drawing,
    caught here by the validator and in the words it puts it in.
    """
    if not isinstance(body, dict):
        return 400, {"error": "a model document is required"}
    store.put_model(cast(dict[str, Any], body), name)
    # As a drawing's save does, and for the same reason: a model written is a
    # document of the store that has moved (#392).
    backup.saved()
    return 200, {"saved": name}


def make_server(
    root: Path,
    port: int = 8765,
    host: str = "127.0.0.1",
    backup: Backup | None = None,
) -> HTTPServer:
    """A server over `root`, not yet listening. One request at a time: there
    is one editor, and the YAML round trip behind `put` is a single shared
    reader. Handing the server back rather than running it is what lets a test
    start and stop one.

    Loopback unless told otherwise: it is the only client that ever needed to
    reach this, and the proxy that now does runs in a container, which cannot
    reach a macOS host's loopback (ADR-0042, docs/DEPLOY.md).

    The backup is taken rather than made where the caller has one — a session
    holds it so that its watch thread and its own quit commit drive the same
    timers this server's saves arm (`tc49 live`, #321)."""
    store = AssetStore(root)
    backing = backup if backup is not None else Backup(root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._answer("GET", None)

        def do_PUT(self) -> None:
            self._answer("PUT", self._body())

        def do_POST(self) -> None:
            self._answer("POST", self._body())

        def do_OPTIONS(self) -> None:
            """A preflight only ever comes from a page on another origin, and
            the answer to those is no (ADR-0055). Refused in the terms that
            make it a refusal to a browser: no `Access-Control-Allow-Origin`
            in the reply, whatever the status says."""
            self._respond(403, {"error": "cross-origin request refused"})

        def _answer(self, method: str, body: Any) -> None:
            if not self._same_origin():
                self._respond(403, {"error": "cross-origin request refused"})
                return
            try:
                status, payload = handle(store, backing, method, self.path, body)
            except Exception as failure:  # noqa: BLE001 — a reply beats a reset
                status, payload = 500, {"error": repr(failure)}
            self._respond(status, payload)

        def _same_origin(self) -> bool:
            """Whether this request comes from the page this server is part
            of, which is the only browser it serves (ADR-0055).

            The rule itself is `lib/origin.py`, written once so that this
            face and the proxy middleware in front of the broker's cannot
            drift (ADR-0057, ADR-0059 decision 4).
            """
            return is_own_page(self.headers.get("Origin"), self.headers.get("Host"))

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
            # No `Access-Control-*` at all: the app fetches these routes on
            # its own origin, in development through vite's proxy and on a
            # layout server through the same proxy that serves the page, so
            # nothing this server answers needs a browser's permission to be
            # read (ADR-0055).
            self.end_headers()
            self.wfile.write(encoded)

    return HTTPServer((host, port), Handler)
