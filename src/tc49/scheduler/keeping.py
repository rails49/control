"""The store client the scheduler keeps timetables through, and the one that
writes off the loop's thread (#1345, #1352).

`Timetables` is the three calls the scheduler makes, which
`tc49.lib.documents.Documents` has. `Kept` is those calls with the writes
done on a thread of its own, as `tc49.lib.clock_row.Keeping` writes the
clock. `python -m tc49.scheduler` hands the scheduler a `Kept`; a test hands
it a store of its own.
"""

import queue
import threading
from collections.abc import Callable
from typing import Protocol

from tc49.lib.timetable import Timetable


class Timetables(Protocol):
    """A railroad's timetables in the store. The railroad is the layout's
    name."""

    def timetable(self, railroad: str, name: str) -> Timetable | None:
        """Timetable `name` of `railroad`, or None where the store has none.
        One the store cannot read is a `ValueError` or a `TypeError`."""
        ...

    def put_timetable(self, timetable: Timetable) -> None:
        """Keep `timetable` under its own `layout` and `name`, in place of
        the one the store has there."""
        ...

    def delete_timetable(self, railroad: str, name: str) -> None:
        """Delete timetable `name` of `railroad`. One the store does not
        have is no error."""
        ...


class Kept:
    """`store` with each write and delete done on a thread of its own, in the
    order they were asked for.

    `Documents` waits for a store that does not answer. On the loop's thread
    that wait would hold up every gesture and the scheduler's
    `alive_confirmed`, so `put_timetable` and `delete_timetable` return at
    once. A write the store refuses is said on `log` and the next one is
    done. The thread starts at the first write and is a daemon: a write still
    waiting when the app stops is lost.

    `timetable` reads on the caller's thread, after every write asked for
    before it is done, so a read sees what was written.
    """

    def __init__(self, store: Timetables, log: Callable[[str], None]) -> None:
        self._store = store
        self._log = log
        self._waiting: queue.Queue[tuple[str, Callable[[], None]]] = queue.Queue()
        self._thread: threading.Thread | None = None

    def timetable(self, railroad: str, name: str) -> Timetable | None:
        self._waiting.join()
        return self._store.timetable(railroad, name)

    def put_timetable(self, timetable: Timetable) -> None:
        self._ask(
            f"'{timetable.layout}': the timetable '{timetable.name}' was not kept",
            lambda: self._store.put_timetable(timetable),
        )

    def delete_timetable(self, railroad: str, name: str) -> None:
        self._ask(
            f"'{railroad}': the timetable '{name}' was not deleted",
            lambda: self._store.delete_timetable(railroad, name),
        )

    def _ask(self, failed: str, write: Callable[[], None]) -> None:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._write, name="timetable-keeping", daemon=True
            )
            self._thread.start()
        self._waiting.put((failed, write))

    def _write(self) -> None:
        while True:
            failed, write = self._waiting.get()
            try:
                write()
            except (OSError, ValueError, TypeError) as refused:
                self._log(f"{failed}: {refused}")
            finally:
                self._waiting.task_done()
