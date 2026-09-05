"""The real assembly over the in-process bus, shared by the suite.

The wiring itself lives in `tc49.bench.runner`, so the suite and the benchmark CLI
drive an identical assembly; what is here is the loading and trace-reading
convenience the tests want.
"""

import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from tc49.bench.runner import (
    Assembly,
    StrategyFactory,
    assemble,
    assemble_live,
    find_assets,
    find_root,
    run_scenario,
)
from tc49.bench.runner import load as load_scenario
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster, Train
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore

__all__ = [
    "ASSETS",
    "ROOT",
    "RUN_WANTED",
    "Assembly",
    "StrategyFactory",
    "build",
    "catalogued",
    "events",
    "leaves",
    "live",
    "load",
    "press",
    "railroads",
    "retaining",
    "run",
    "run_wanted",
    "runs",
    "stock",
    "ticks",
    "timetabled",
]

ROOT = find_root()  # the checkout: the goldens and the generated sources
ASSETS = find_assets()  # one definition of where the railroads live: `bench/`


def catalogued(root: Path) -> Path:
    """`root` given the installation's catalogue, which a copied roster needs.

    A roster does not travel alone: its cars name models, and a model belongs
    to the installation rather than to the railroad (ADR-0045), so a scratch
    root with `layouts/` and no `catalogue/` is a roster naming models nothing
    has.
    """
    shutil.copytree(ASSETS / "catalogue", root / "catalogue")
    return root


build = assemble
run = run_scenario


def load(scenario_id: str) -> tuple[Layout, Roster, Scenario]:
    """The wiring module's loader against the one root the suite uses."""
    return load_scenario(AssetStore(ASSETS), scenario_id)


def live(scenario_id: str, retained: dict[str, Payload] | None = None) -> Assembly:
    """A live run over the railroad a scenario names, its trains stood where
    that document stands them.

    A run an operator drives is built from a railroad alone and a person
    places the trains (#171); a test that wants a railroad already laid out
    asks the harness to stand them, which is what `bench/replay.py` replays as
    gestures. `retained` is what the broker was already holding when these
    apps came up, for a test about what an app adopts.
    """
    layout, roster, scenario = load(scenario_id)
    return assemble_live(layout, roster, scenario.trains, retained=retained)


def retaining(rows: dict[str, Payload], clock: Clock | None = None) -> InProcessBus:
    """A bus with those rows already on their topics, as a broker holds them
    for an app that comes up under a running railroad (ADR-0059, decision 3).

    Published and drained with nothing subscribed yet, so what is left is the
    last-value map alone: an app built on this bus adopts its own row at
    construction exactly as it adopts the broker's retained one, and nothing
    is delivered twice. Only a state row survives the round trip, which is the
    bus keeping its own promise whatever a test asks it to hold.
    """
    bus = InProcessBus(clock or Clock())
    for topic, value in rows.items():
        bus.publish(topic, value)
    bus.drain()
    return bus


def railroads() -> list[str]:
    """The railroads this checkout has, in name order.

    A test that needs a railroad and does not care which takes one from here
    rather than spelling a name. The library railroads are renamed and moved
    under #319, and a test that named one would then go red for a reason that
    is not its own.
    """
    return AssetStore(ASSETS).list()


def stock(**lengths: int) -> Roster:
    """A roster of a suite's own: the trains a railroad owns and how long each
    is (ADR-0039).

    A suite that stands up its own scenario stands up the stock it places
    beside it, the two being one railroad's — and a train here that the
    scenario places nowhere is exactly the train that comes up **off the
    layout**.
    """
    return Roster(
        "test", {name: Train(stated_length=length) for name, length in lengths.items()}
    )


def events(
    trace: str, leaf: str | None = None, rid: str | None = None
) -> list[dict[str, Any]]:
    """Parsed trace lines, optionally filtered by event leaf and request id."""
    lines = [json.loads(line) for line in trace.splitlines()]
    return [
        line
        for line in lines
        if (leaf is None or line["event"] == leaf)
        and (rid is None or line.get("id") == rid)
    ]


def press(assembly: Assembly, topic: str, payload: Payload) -> None:
    """A gesture as a page puts it on the bus, delivered on its own drain."""
    assembly.bus.publish(topic, payload)
    assembly.bus.drain()


def ticks(
    assembly: Assembly,
    count: int,
    at: dict[int, tuple[str, Payload]] | None = None,
) -> None:
    """`count` turns of the live loop, with the gesture `at` keys pressed
    just before the turn each is keyed to. Each turn advances the run clock
    to the next scheduled sensor event and fires it, so a turn is "the next
    thing the railroad does" — or a quiet step, on a railroad with nothing
    scheduled.

    The live loop rather than the batch one: it does not stop on quiescence,
    which is exactly what a test of a railroad standing still needs.
    """
    now = 0
    plan = at or {}

    def stop() -> bool:
        nonlocal now
        if now >= count:
            return True
        if now in plan:
            assembly.bus.publish(*plan[now])
        now += 1
        return False

    # A period longer than any delay, so each turn's step reaches the next
    # scheduled event exactly; the sleep is injected away.
    assembly.simulation.run_live(3600.0, sleep=lambda _: None, stop=stop)


RUN_WANTED = "tc49/dispatch/run_wanted"
"""The leaf a person's press of the run's one button lands on. Every
dispatcher suite that drives the run names it, so it is named here once."""


@pytest.fixture
def timetabled() -> Assembly:
    """`crossover-yard/meet` with its timetable on: three requests minted
    into the run in the file's order, freight_1's return working last."""
    return build(*load("crossover-yard/meet"))


def run_wanted(state: str) -> tuple[str, Payload]:
    """A press of the run's one button, as `ticks` plans one."""
    return (RUN_WANTED, {"run": state})


def leaves(assembly: Assembly, leaf: str) -> list[Payload]:
    """The trace's lines for one event leaf."""
    return events(assembly.trace, leaf)


def minted(assembly: Assembly, train: str, nth: int = 1) -> str:
    """The id the scheduler minted for `train`'s `nth` request, counting
    from one in the order it submitted them.

    A gesture's id carries the scheduler process's nonce (ADR-0033), so a
    test that pressed a drag reads the id back off the trace instead of
    spelling it out. A timetable's stays `<train>-N` and can still be
    written.
    """
    ids = [
        str(line["id"])
        for line in events(assembly.trace, "request_submitted")
        if line["train"] == train
    ]
    return ids[nth - 1]


def runs(assembly: Assembly) -> list[str]:
    """Every value `tc49/dispatch/state/run` took, in the order it took them.

    Consecutive repeats collapse, because the row carries `moving` beside the
    run word and is republished when that moves on its own — a running run
    whose last train arrives says `running` again with `moving` false, and
    that is not the run taking a value (#406). The dispatcher compares the
    whole row before publishing, so a repeat is never an identical one;
    `run_rows` is what reads the rows as they went out.
    """
    said = [word for word, _ in run_rows(assembly)]
    return [word for i, word in enumerate(said) if i == 0 or word != said[i - 1]]


def run_rows(assembly: Assembly) -> list[tuple[str, bool]]:
    """Every `tc49/dispatch/state/run` row as it was published: the run word
    and whether anything was moving (ADR-0062)."""
    return [
        (str(line["run"]), bool(line.get("moving"))) for line in leaves(assembly, "run")
    ]


class Recording(InProcessBus):
    """An in-process bus that remembers the order it was called in.

    For the one thing a functional test cannot see: an app must subscribe
    before it publishes its opening rows. Over a broker a publish is
    asynchronous where a subscribe waits to be acknowledged, so publishing
    first drops any gesture arriving in the gap, and an event is not retained.
    In one process the gap has no width, so the order is asserted here rather
    than waited for.
    """

    def __init__(self) -> None:
        super().__init__(Clock())
        self.calls: list[str] = []

    def subscribe(self, topic_filter: str, handler: object) -> None:  # type: ignore[override]
        self.calls.append(f"subscribe {topic_filter}")
        super().subscribe(topic_filter, cast(object, handler))  # type: ignore[arg-type]

    def publish(self, topic: str, payload: Payload) -> None:
        self.calls.append(f"publish {topic}")
        super().publish(topic, payload)


def subscribed_before_publishing(bus: Recording) -> None:
    """Assert it of whatever was just built on `bus`."""
    published = [i for i, call in enumerate(bus.calls) if call.startswith("publish")]
    subscribed = [i for i, call in enumerate(bus.calls) if call.startswith("subscribe")]
    assert subscribed, "it subscribed to nothing"
    assert published, "it published nothing"
    assert max(subscribed) < min(
        published
    ), f"a row went out before the subscriptions were live: {bus.calls}"
