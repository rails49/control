"""The scheduler's timetable writes are done off its loop's thread, in order
(#1352)."""

import threading

from rails49_testing.broker import until

from tc49.lib.fast_clock import DAY_S
from tc49.lib.timetable import Timetable
from tc49.scheduler.keeping import Kept


def timetable(name: str, start: int = 0) -> Timetable:
    return Timetable(name, "crossover-yard", start, DAY_S, {}, ())


class Slow:
    """A store that does no write until it is `opened`, and refuses a
    timetable named `refused`. `calls` is what it has done, in order."""

    def __init__(self) -> None:
        self.opened = threading.Event()
        self.calls: list[str] = []
        self.held: dict[str, Timetable] = {}

    def timetable(self, railroad: str, name: str) -> Timetable | None:
        return self.held.get(name)

    def put_timetable(self, timetable: Timetable) -> None:
        self.opened.wait()
        if timetable.name == "refused":
            raise ValueError("the store refused it")
        self.calls.append(f"put {timetable.name} {timetable.start}")
        self.held[timetable.name] = timetable

    def delete_timetable(self, railroad: str, name: str) -> None:
        self.opened.wait()
        self.calls.append(f"delete {name}")
        self.held.pop(name, None)


def test_a_write_returns_before_the_store_has_answered() -> None:
    store = Slow()
    kept = Kept(store, lambda line: None)

    kept.put_timetable(timetable("evening"))
    kept.delete_timetable("crossover-yard", "untitled")

    assert store.calls == []
    store.opened.set()
    assert until(lambda: len(store.calls) == 2)


def test_writes_and_deletes_are_done_in_the_order_asked() -> None:
    store = Slow()
    kept = Kept(store, lambda line: None)

    for start in (0, 60, 120):
        kept.put_timetable(timetable("untitled", start))
    kept.put_timetable(timetable("evening"))
    kept.delete_timetable("crossover-yard", "untitled")
    store.opened.set()

    assert until(lambda: len(store.calls) == 5)
    assert store.calls == [
        "put untitled 0",
        "put untitled 60",
        "put untitled 120",
        "put evening 0",
        "delete untitled",
    ]


def test_a_read_sees_every_write_asked_for_before_it() -> None:
    store = Slow()
    store.opened.set()
    kept = Kept(store, lambda line: None)

    for start in range(0, 3000, 60):
        kept.put_timetable(timetable("untitled", start))

    assert kept.timetable("crossover-yard", "untitled") == timetable("untitled", 2940)
    assert kept.timetable("crossover-yard", "evening") is None


def test_a_write_the_store_refuses_is_said_and_the_next_is_done() -> None:
    store = Slow()
    store.opened.set()
    said: list[str] = []
    kept = Kept(store, said.append)

    kept.put_timetable(timetable("refused"))
    kept.put_timetable(timetable("evening"))

    assert kept.timetable("crossover-yard", "evening") == timetable("evening")
    assert said == [
        "'crossover-yard': the timetable 'refused' was not kept: the store refused it"
    ]
