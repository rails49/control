"""Assembling the components on one bus and running a scenario to quiescence.

The wiring the CLI and the test suite share, so there is exactly one of it.
Nothing here is a contract — the components find each other by topic, not by
this module — but the order matters for the trace: the tap subscribes first,
so it sees every event (BUS.md, the bus).

A run assembled here is built on the **simulator**, which is the binding of
the layout interface that lives in one process with the apps it is wired to.
The physical binding is two processes on a broker — `layout` and a translator
— and is assembled by nothing: it was a branch of `assemble_live` until #587,
when the translator left for [`rails49/dccex`](https://github.com/rails49/dccex)
(dccex ADR-0014).
"""

import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tc49.dispatcher import Dispatcher, FullRoute, Incremental, LockingStrategy
from tc49.driver import Driver
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout, connected_facing
from tc49.lib.roster import Roster
from tc49.lib.scenario import Scenario, TrainSpec
from tc49.lib.trace import TraceTap
from tc49.scheduler import Scheduler
from tc49.simulator import Simulator
from tc49.store import AssetStore

NONCE = "bench"
"""The nonce the harness's scheduler mints drag ids from.

A replay feeds its document as drags (`bench/replay.py`), and a drag's id
carries the minting process's nonce (ADR-0033). Left to `secrets` that would
make two runs of one document differ in every id, which is the one thing a
replay is for. Stated here instead, so a replayed run is reproducible the way
a timetable's was. Nothing is protected by its being unguessable: the
collision the nonce prevents needs a second scheduler process, and a bench run
has one.
"""

StrategyFactory = Callable[[Layout, int], LockingStrategy]

DEFAULT_K = 2  # BENCHMARKS.md records its golden numbers at this budget

STRATEGIES: dict[str, StrategyFactory] = {
    "FullRoute": FullRoute,
    "Incremental": Incremental,
}


FIXTURES = "bench"
"""The directory inside a checkout holding the harness's inputs: the drawings
and rosters under `layouts/`, the models under `catalogue/`, and the placements
under `scenarios/`. They sit under the bench rather than beside `src/` because
they are what the benchmark is run *on* and not the system's own data, and a
directory at the top level reads as a place to put a railroad (#319)."""


def find_root(start: Path | None = None) -> Path:
    """The repo root: the nearest ancestor holding `bench/layouts/`.

    The railroads and the scenarios are repo data, not package data — the
    wheel ships `src/tc49` alone — so the benchmark commands only mean
    anything inside a checkout. Searching for the data rather than counting
    `..` from `__file__` makes that work from any subdirectory and fail with
    a sentence instead of a `FileNotFoundError` on a path nobody wrote.
    """
    for candidate in (start or Path(__file__)).resolve().parents:
        if (candidate / FIXTURES / "layouts").is_dir():
            return candidate
    raise FileNotFoundError(
        f"no '{FIXTURES}/layouts/' directory in any parent — `tc49 bench` and"
        " `tc49 sweep` read the railroads and scenarios from a checkout of the"
        " repository, and are not usable from an installed wheel"
    )


def find_assets(start: Path | None = None) -> Path:
    """The store root inside a checkout: the fixtures the asset store serves.

    The store is rooted at a directory holding `layouts/`, `catalogue/` and
    `scenarios/` (LAYOUT.md), which in a checkout is `bench/` and not the
    checkout itself — the repo root is where `benchmarks/expected/` and the
    UI's generated sources are, and those are not the store's.
    """
    return find_root(start) / FIXTURES


def load(store: AssetStore, scenario_id: str) -> tuple[Layout, Roster, Scenario]:
    """A scenario, and the layout and roster of the railroad it names — which
    is what assembling wants. The three are one railroad's: the drawing it
    derives from, the trains it owns, and where this run stands them
    (ADR-0039)."""
    scenario = store.get(scenario_id)
    assert isinstance(scenario, Scenario)
    layout = store.get(scenario.layout)
    assert isinstance(layout, Layout)
    return layout, store.roster(scenario.layout), scenario


def railroad(store: AssetStore, name: str) -> tuple[Layout, Roster]:
    """A railroad: the layout its drawing derives to, and the trains it owns.

    The whole of what a live run is built from (#171). A drawing that does not
    derive raises `ValueError` here, where a session can refuse the name on
    the joining client's own thread instead of taking a running railroad down
    with it; a name the store answers with anything but a layout is not a
    railroad's, and reads as one that is not there.
    """
    layout = store.get(name)
    if not isinstance(layout, Layout):
        raise FileNotFoundError(f"no railroad '{name}'")
    return layout, store.roster(name)


def placement(trains: dict[str, TrainSpec]) -> dict[str, str]:
    """Train to the block it starts in: what the dispatcher and the simulator
    take of a document's placement. Neither reads facing (ADR-0019)."""
    return {train: spec.at for train, spec in trains.items()}


def facing(layout: Layout, trains: dict[str, TrainSpec]) -> dict[str, str]:
    """Train to the run it would make across its block: what the scheduler
    takes of the same placement, the document's bare `A-to-B` qualified by the
    block it is written beside. Through `connected_facing`, so a train
    standing in a terminal block is turned off the wall however the document
    writes it (#145).
    """
    return {
        train: connected_facing(layout, f"{spec.at}.{spec.facing}")
        for train, spec in sorted(trains.items())
    }


@dataclass
class Assembly:
    """Everything wired on one bus, held so a caller can peek at live state.

    The binding of the layout interface here is the `simulator`, the one that
    runs in the same process as the apps it is wired to (ADR-0030). A run on
    steel is `layout` and a translator as processes of their own on a broker
    (dccex ADR-0014 d.6), which nothing assembles.
    """

    bus: InProcessBus
    dispatcher: Dispatcher
    simulator: Simulator
    layout: Layout
    roster: Roster
    k: int
    _out: io.StringIO
    clock: Clock

    @property
    def trace(self) -> str:
        return self._out.getvalue()

    @property
    def simulation(self) -> Simulator:
        """The simulator this run is bound to: what a caller that wants the
        engine itself goes through — the batch loop, and a live loop a test
        paces turn by turn rather than on a wall clock."""
        return self.simulator


def assemble(
    layout: Layout,
    roster: Roster,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
) -> Assembly:
    clock = Clock()
    bus = InProcessBus(clock)
    out = io.StringIO()
    TraceTap(bus, out, clock)
    stood = placement(scenario.trains)
    Scheduler(
        bus, layout, facing(layout, scenario.trains), scenario.requests, nonce=NONCE
    )
    dispatcher = Dispatcher(bus, layout, roster, stood, make_strategy(layout, k))
    Driver(bus)
    return Assembly(
        bus,
        dispatcher,
        Simulator(bus, layout, clock, stood),
        layout,
        roster,
        k,
        out,
        clock,
    )


def assemble_live(
    layout: Layout,
    roster: Roster,
    trains: dict[str, TrainSpec] | None = None,
    make_strategy: StrategyFactory = Incremental,
    k: int = DEFAULT_K,
    retained: dict[str, Payload] | None = None,
) -> Assembly:
    """The live wiring (#71): **a railroad and its roster**, and no timetable.
    That is the whole of what a run an operator drives is built from (#171) —
    a drawing, the trains the railroad owns, and a person who places them.

    Which sources a run has is configuration rather than a rule (ADR-0036), and
    a live run is given no timetable at all: a scenario is the harness's file
    format, and `bench/replay.py` replays one as gestures instead.

    `trains` stands them before anything runs instead, and is the harness's
    own: the suite's runs, and the baseline a replay is measured against. A
    run an operator drives is passed none — it comes up with an empty layout
    and held, and the trains arrive as gestures (ADR-0039).

    Locking is **incremental** here, where `assemble` keeps the `FullRoute`
    baseline (#165). It is what the panel's two colours mean: an increment
    is the next transit with the block beyond it, so green creeps along a
    cyan path and its length says how far the train may go (ui/PANEL.md).
    Claiming a whole route up front is a measurement baseline, not the
    behaviour to hand an operator on a shared railroad.

    `retained` is what a broker was already holding when these apps came up
    (#123): each row is on its topic before anything subscribes, so an app
    adopts its own the way a restarted one adopts what the broker kept for it
    (ADR-0059 decision 3). Placement and facing are then that picture's rather
    than the seed's.

    The binding is the **simulator**, and a station is no longer something
    this can be handed: naming one put `LayoutInterface` and the `DccEx`
    translator where the simulator would be until #587, and the translator is
    [`rails49/dccex`](https://github.com/rails49/dccex) now. A run on steel is
    those two as processes of their own on a broker, with the typed readings a
    third (`tc49 readings`), and `bench` assembles none of it.
    """
    document = trains or {}
    stood = placement(document)
    clock = Clock()
    bus = InProcessBus(clock)
    # On their topics before anything subscribes, and drained with nothing
    # listening: what is left is the last-value map, which is what a late
    # subscriber is handed — an app adopting its own row reads it at
    # construction exactly as it reads the broker's retained one.
    for topic, value in (retained or {}).items():
        bus.publish(topic, value)
    bus.drain()
    out = io.StringIO()
    TraceTap(bus, out, clock)
    Scheduler(bus, layout, facing(layout, document), nonce=NONCE)
    dispatcher = Dispatcher(bus, layout, roster, stood, make_strategy(layout, k))
    Driver(bus)
    return Assembly(
        bus,
        dispatcher,
        Simulator(bus, layout, clock, stood),
        layout,
        roster,
        k,
        out,
        clock,
    )


def run_scenario(
    layout: Layout,
    roster: Roster,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
    event_limit: int = 100_000,
) -> str:
    """Wire everything on one bus, run to quiescence, return the trace."""
    assembly = assemble(layout, roster, scenario, make_strategy, k)
    assembly.simulation.run(event_limit)
    return assembly.trace
