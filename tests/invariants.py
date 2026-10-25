"""The invariants of `tc49.lib.invariants`, checked over a running assembly.

ADR-0096 decision 3 says when each is checked: one over a single app's rows
after every message, by a subscriber on `#`; one over several apps' rows
(`cross_app`) each time `drain()` returns with nothing queued, since between
messages such an invariant can be broken for a moment — power `off` before the
dispatcher's `aspects` follow. A breach fails the test with the ADR, the rule
and the line that says what broke.
"""

from collections.abc import Collection
from collections.abc import Set as AbstractSet

from tc49.dispatcher import Incremental
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.invariants import INVARIANTS, Invariant, View, cross_app
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tests.harness import Assembly, StrategyFactory

INCREMENTAL_ONLY = frozenset({"0026"})
"""The ADRs whose invariant holds only where the dispatcher locks
`Incremental`: the strategy is not on the bus, so the caller says it."""


def breaches(view: View, invariants: Collection[Invariant]) -> list[str]:
    """Every breach of `invariants` in `view`, each with its ADR and rule."""
    return [
        f"ADR-{invariant.adr}: {invariant.states} — {line}"
        for invariant in invariants
        for line in invariant.breaches(view)
    ]


def checked(
    bus: InProcessBus,
    layout: Layout,
    roster: Roster,
    strategy: StrategyFactory = Incremental,
    without: AbstractSet[str] = frozenset(),
) -> None:
    """Check the invariants on `bus` from now on.

    `strategy` is the dispatcher's, which decides whether ADR-0026 is among
    them. `without` names invariants by function to leave out, each for an
    `xfail` test that shows it failing on the current code.
    """
    held = [
        invariant
        for invariant in INVARIANTS
        if invariant.breaches.__name__ not in without
        and (strategy is Incremental or invariant.adr not in INCREMENTAL_ONLY)
    ]
    each_message = [invariant for invariant in held if not cross_app(invariant)]

    def assert_held(invariants: Collection[Invariant], after: str) -> None:
        found = breaches(View(bus.last_values, layout, roster), invariants)
        assert not found, f"{after}:\n" + "\n".join(found)

    def message(topic: str, payload: Payload) -> None:
        assert_held(each_message, f"after {topic} {payload}")

    bus.subscribe("#", message)

    # `drain` is wrapped on this bus alone, since what calls it — the
    # simulator, a gesture, a turn of the live loop — holds the bus and not
    # this. A drain called inside a handler returns with the outer one's
    # messages still to come, so only the outermost counts.
    drain = bus.drain
    depth = [0]

    def drained() -> None:
        depth[0] += 1
        try:
            drain()
        finally:
            depth[0] -= 1
        if depth[0] == 0:
            assert_held(held, "with nothing left to deliver")

    bus.drain = drained


def check(
    assembly: Assembly,
    strategy: StrategyFactory = Incremental,
    without: AbstractSet[str] = frozenset(),
) -> None:
    """`checked` over an assembly's bus, drawing and roster."""
    checked(assembly.bus, assembly.layout, assembly.roster, strategy, without)
