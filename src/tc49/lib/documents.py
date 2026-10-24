"""The store's HTTP face, read from an app in its own process.

The scheduler, the dispatcher and the layout interface each take a `Layout`
and a `Roster` at construction. In its own container an app cannot import the
store to derive one (ADR-0013), so it reads them over the same face the editor
uses: `GET /layouts/<name>` for the layout the drawing derives to,
`GET /rosters/<name>` with `GET /catalogue` for the stock, merged and
validated here by `lib/stock.py` (ADR-0059 decision 5).

**A store that is not up yet is waited for.** Every app comes up alone,
against nothing, in whatever order the machine starts them, so an app reaching
a store that has not opened its socket is an ordinary state and not a fault:
the request is retried with backoff until the store answers. Said on stderr
each time rather than absorbed, so a person watching the container sees which
of the two is waiting for the other (ADR-0050).

**An answer ends the waiting, whatever it says.** A railroad with no drawing
is a `FileNotFoundError` and a drawing that does not derive yet is a
`ValueError` carrying the store's own words: both are answers, and retrying
either would be waiting for a person to edit a document rather than for a
process to come up. What is retried is the store not answering at all —
nothing listening, a connection refused or dropped, a reply that is not JSON —
and the 5xx it sends when it cannot answer a request it should have.

Standard library only: this is what an app is built on, and it fetches four
documents per build, and between builds only the roster a running app reads
once again for a train it has not got (SYSTEM.md, "read once per build").
The writes are the layout binding's: its record of which railroad it loaded
(`put_loaded`, ADR-0072 decision 5), and the railroad's clock when a person
sets it (`put_clock`, ADR-0090 decision 3).
"""

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, cast
from urllib.parse import quote

from tc49.lib.fast_clock import KeptClock, kept_clock
from tc49.lib.layout import Layout
from tc49.lib.roster import Model, Roster
from tc49.lib.stock import validate_model, validate_roster

FIRST_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0

TIMEOUT_S = 5.0
"""How long one request waits for the store before it counts as unanswered.
A store that has accepted the connection and then gone quiet is the same
outage as one that never accepted it, and the retry treats it as one."""


def to_stderr(line: str) -> None:
    """The default log: what is being waited for, and nothing else."""
    print(f"documents: {line}", file=sys.stderr, flush=True)


class Documents:
    """The documents a railroad is built from, off the store at `base_url`.

    Blocking, on the caller's own thread: an app that has no layout has
    nothing to do but wait for one, and this runs before its bus loop starts.

    Tests pass their own `log` and backoff bounds so a store that comes up
    late does so in milliseconds.
    """

    def __init__(
        self,
        base_url: str,
        *,
        log: Callable[[str], None] = to_stderr,
        first_backoff_s: float = FIRST_BACKOFF_S,
        max_backoff_s: float = MAX_BACKOFF_S,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._log = log
        self._first_backoff_s = first_backoff_s
        self._max_backoff_s = max_backoff_s
        self._timeout_s = timeout_s

    def layout(self, name: str) -> Layout:
        """The layout `name`'s drawing derives to, validated here as the
        store validates it there — one binding of the document, read by
        whoever holds it."""
        return Layout.from_document(self._get("layouts", name))

    def roster(self, name: str, *, once: bool = False) -> Roster:
        """The stock `name` owns, merged onto the installation's catalogue.

        Two documents because a car is only complete against a model, and the
        catalogue belongs to the installation rather than to the railroad
        (ADR-0045): the same pair the store puts together for a caller that
        can import it.

        `once` is the read a running app makes for a train it has not got
        (ADR-0091): one attempt each, and a store that does not answer is a
        `ConnectionError` rather than a wait its bus loop would sit through.
        """
        return validate_roster(
            self._get("rosters", name, once=once), self.catalogue(once=once)
        )

    def catalogue(self, *, once: bool = False) -> dict[str, Model]:
        """The models the installation knows, by name."""
        models = self._get("catalogue", once=once).get("models")
        if not isinstance(models, dict):
            raise TypeError(f"{self._base}/catalogue: no models in the reply")
        return {
            name: validate_model(doc, name)
            for name, doc in cast(dict[str, Any], models).items()
        }

    def clock(self, name: str) -> KeptClock | None:
        """The start time and speed-up railroad `name` keeps, or None where
        it keeps none and so starts at the box's wall time (ADR-0090,
        decision 4). One the store cannot read is a `ValueError`."""
        try:
            return kept_clock(self._get("clocks", name))
        except FileNotFoundError:
            return None

    def put_clock(self, name: str, kept: KeptClock) -> None:
        """Keep `kept` as railroad `name`'s clock, written as `put_loaded`
        writes the record: waited for until the store answers."""
        self._put("clocks", name, body=kept.document())

    def loaded(self) -> str:
        """The railroad the store records as loaded, and `""` where it records
        none (ADR-0072 decision 5). The layout binding's, read once as it
        starts; every other app follows the binding's state on the bus."""
        railroad = self._get("loaded").get("railroad")
        if not isinstance(railroad, str):
            raise TypeError(f"{self._base}/loaded: no railroad in the reply")
        return railroad

    def put_loaded(self, name: str) -> None:
        """Record `name` as the railroad loaded, for the binding to start on
        next time. Waited for as a read is: a binding that has loaded a
        railroad before the store is up still has to say which."""
        self._put("loaded", body={"railroad": name})

    def _get(self, *path: str, once: bool = False) -> dict[str, Any]:
        """One document, waited for until the store answers — or, `once`,
        asked for one time."""
        return self._asked(path, None, once)

    def _put(self, *path: str, body: dict[str, Any]) -> dict[str, Any]:
        """`body` put there, and the store's answer waited for."""
        return self._asked(path, body)

    def _asked(
        self, path: tuple[str, ...], body: dict[str, Any] | None, once: bool = False
    ) -> dict[str, Any]:
        """The store's answer at `path`, retried while it does not answer,
        and `once` raised as a `ConnectionError` instead. The route is given
        a level at a time and each is escaped: a name is one level, so a
        railroad called `a/b` is a name the store does not have rather than a
        route of its own."""
        where = self._base + "".join(f"/{quote(level, safe='')}" for level in path)
        backoff = self._first_backoff_s
        while True:
            try:
                return _fetch(where, self._timeout_s, body)
            except _Unanswered as away:
                if once:
                    raise ConnectionError(f"{where}: {away}") from None
                self._log(f"{where}: {away}, retrying in {backoff:.1f}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_s)


class _Unanswered(Exception):
    """The store did not answer — it is not up yet, or it could not. The one
    thing this file retries; everything else it was told is raised."""


def _fetch(
    where: str, timeout_s: float, sent: dict[str, Any] | None = None
) -> dict[str, Any]:
    asked = (
        urllib.request.Request(
            where,
            data=json.dumps(sent).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        if sent is not None
        else where
    )
    try:
        with urllib.request.urlopen(asked, timeout=timeout_s) as answer:
            body = json.load(answer)
    except urllib.error.HTTPError as answered:
        raise _answered(where, answered) from None
    except (OSError, ValueError) as away:
        # `URLError` is an `OSError`, which is also what a connection dropped
        # mid-reply raises, and a reply that is not JSON is a `ValueError`:
        # every one of them is a store that has not answered this request.
        raise _Unanswered(f"{away}") from None
    if not isinstance(body, dict):
        raise _Unanswered(f"answered with {type(body).__name__}, not a document")
    return cast(dict[str, Any], body)


def _answered(where: str, answered: urllib.error.HTTPError) -> Exception:
    """What the store said, as the exception a caller reads.

    A 404 and a 422 are answers about the documents somebody has: the railroad
    is not there, or its drawing does not derive yet. Neither is waited for —
    what would end the wait is a person editing, and an app has to say what it
    is missing rather than sit silent on it (ADR-0050).
    """
    said = _reason(answered)
    if answered.code == 404:
        return FileNotFoundError(f"{where}: {said}")
    if answered.code >= 500:
        return _Unanswered(f"{answered.code} {said}")
    return ValueError(f"{where}: {said}")


def _reason(answered: urllib.error.HTTPError) -> str:
    """The store's own words, which every refusal it makes carries in
    `error`. A body that is not one of ours leaves the status to speak."""
    try:
        body = json.load(answered)
    except ValueError:
        return f"{answered.code} {answered.reason}"
    said = cast(dict[str, Any], body).get("error") if isinstance(body, dict) else None
    return said if isinstance(said, str) else f"{answered.code} {answered.reason}"


def reread_roster(
    documents: Documents, railroad: str, log: Callable[[str], None]
) -> Callable[[], Roster | None]:
    """How the dispatcher built on `railroad` reads its roster again, for a
    placement naming a train it has not got (ADR-0091, decision 1). One
    attempt, on the bus loop's own thread: a store that does not answer, or a
    roster it refuses, is None and the placement is dropped as it was."""

    def read() -> Roster | None:
        try:
            return documents.roster(railroad, once=True)
        except (ConnectionError, FileNotFoundError, TypeError, ValueError) as no:
            log(f"roster of '{railroad}' not read again: {no}")
            return None

    return read
