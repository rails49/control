"""The invariants of `tc49.lib.invariants`, checked over a running assembly.

ADR-0096 decision 3 says when each is checked: one over a single app's rows
after every message, by a subscriber on `#`; one over several apps' rows
(`cross_app`) each time `drain()` returns with nothing queued, since between
messages such an invariant can be broken for a moment — power `off` before the
dispatcher's `aspects` follow. The history invariants are handed each message
and keep a `Record` of them: on the in-process bus by a subscriber on `#`, so
the record is the one order every app heard, and the cross-app ones too, with
`QUIET` once nothing is left to deliver; under `InterleavingBus` each
subscriber sees its own order, so only those over one app's topics are checked,
on the order that app published them in. A breach fails the test with the
ADR, the rule and the line that says what broke.
"""

from collections.abc import Collection
from collections.abc import Set as AbstractSet

from tc49.dispatcher import Incremental
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.invariants import (
    HISTORY_INVARIANTS,
    INVARIANTS,
    QUIET,
    HistoryInvariant,
    Invariant,
    Record,
    View,
    cross_app,
)
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tests.harness import Assembly, StrategyFactory
from tests.interleaving import InterleavingBus

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


def history_breaches(
    record: Record,
    view: View,
    topic: str,
    payload: Payload,
    invariants: Collection[HistoryInvariant],
) -> list[str]:
    """Every breach of `invariants` on this message, each with its ADR and rule."""
    return [
        f"ADR-{invariant.adr}: {invariant.states} — {line}"
        for invariant in invariants
        for line in invariant.breaches(record, view, topic, payload)
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

    one_order = not isinstance(bus, InterleavingBus)
    history = [
        invariant
        for invariant in HISTORY_INVARIANTS
        if invariant.breaches.__name__ not in without
        and (one_order or not cross_app(invariant))
    ]
    record = Record(layout, bus.last_values)

    def heard(topic: str, payload: Payload) -> None:
        view = View(record.rows, layout, roster)
        found = history_breaches(record, view, topic, payload, history)
        assert not found, f"at {topic} {payload}:\n" + "\n".join(found)
        record.observe(topic, payload)

    if one_order:
        bus.subscribe("#", heard)
    else:
        # What one app published, in the order it published it: the order
        # its own topics' rules are about (ADR-0096, decision 3).
        publish = bus.publish

        def published(topic: str, payload: Payload) -> None:
            publish(topic, payload)
            heard(topic, payload)

        bus.publish = published

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
            if one_order:
                view = View(record.rows, layout, roster)
                found = history_breaches(record, view, QUIET, {}, history)
                assert not found, "with nothing left to deliver:\n" + "\n".join(found)

    bus.drain = drained


def check(
    assembly: Assembly,
    strategy: StrategyFactory = Incremental,
    without: AbstractSet[str] = frozenset(),
) -> None:
    """`checked` over an assembly's bus, drawing and roster."""
    checked(assembly.bus, assembly.layout, assembly.roster, strategy, without)
