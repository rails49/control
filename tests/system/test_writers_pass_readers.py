"""Every frame an app writes passes the reader for its topic (#763).

A frame's shape is written in four places — its inventory row, its reader in
`lib/payload.py`, the dict an app builds when it publishes, and BUS.md — and
the trace tap holds the first against the third. Nothing else held a writer
against its reader directly, and one pair met in no test at all: the
`wanted/*` rows `layout` writes and the `desired_*` readers that only
`rails49/dccex` calls (#587).

So the apps are run, everything they publish is recorded, and each recorded
frame is handed to its topic's reader twice: as published, and after a JSON
round trip, which is what a reader on the other side of a broker is handed.
Two kinds of run between them cover every writer in the table:

1. every bench scenario, assembled as the bench assembles it and run to
   quiescence — the dispatcher, scheduler, driver and simulator — and one
   scenario replayed onto a live run as a person's gestures, since
   `train_placed` is only ever the dispatcher's answer to a placement a
   person asked for, and an assembled run places its trains by constructor;
2. one `LayoutInterface` on the railroad `tests/layout/railroad.py` draws,
   driven with that module's helpers — `layout`'s writes.

A frame the test publishes itself is not checked: it is not an app's.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import pytest

from tc49.bench.replay import Replay
from tc49.bench.runner import assemble, assemble_live
from tc49.dispatcher.dispatch import submission
from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload, matches
from tc49.lib.clock import Clock
from tc49.lib.payload import (
    alignment,
    chosen,
    command,
    commanded_power,
    desired_aspect,
    desired_position,
    desired_speed,
    driving,
    grant,
    granted_aspect,
    kept_allocation,
    kept_facing,
    moving,
    occupancy,
    placement,
    power,
    readable_id,
    shown_aspects,
    taken,
)
from tests.harness import ASSETS, load
from tests.layout.railroad import (
    ALIGN,
    ASPECTS,
    DEVICE_TRACK,
    DRIVING_WANTED,
    FACING,
    MOVE,
    PLACED,
    TAKE_WANTED,
    align,
    energised,
    faces,
    move,
    railroad,
    stand,
    stock,
    switches,
    takes,
)

Frame = dict[str, Any]


def _keeps(frame: Frame, key: str, kept: dict[str, str] | None) -> bool:
    """Whether a map the reader answered equals the frame's: an entry
    dropped, added or changed is not kept."""
    stated = frame.get(key)
    return kept is not None and kept == stated


def _submitted(frame: Frame) -> bool:
    rid = readable_id(frame)
    return rid is not None and submission(frame, rid) is not None


def _allocation(frame: Frame) -> bool:
    kept = kept_allocation(frame)
    return (
        kept is not None
        and _keeps(frame, "trains", kept.trains)
        and _keeps(frame, "crossing", kept.crossing)
    )


@dataclass(frozen=True)
class Rule:
    """One row of the table: the topics, the reader, and when a frame
    passes it."""

    topic: str  # a filter: the `wanted/*` rows carry the address as a level
    reader: str
    passes: Callable[[Frame], bool]


TABLE: tuple[Rule, ...] = (
    Rule(
        "tc49/layout/move",
        "command",
        lambda f: (read := command(f)) is not None and read.speed is not None,
    ),
    Rule("tc49/layout/align", "alignment", lambda f: alignment(f) is not None),
    Rule(
        "tc49/dispatch/move_granted",
        "grant, granted_aspect, readable_id",
        lambda f: grant(f) is not None
        and granted_aspect(f) is not None
        and readable_id(f) is not None,
    ),
    Rule("tc49/dispatch/route_chosen", "chosen", lambda f: chosen(f) is not None),
    Rule(
        "tc49/dispatch/train_placed",
        "placement",
        lambda f: (read := placement(f)) is not None and read.block is not None,
    ),
    Rule("tc49/dispatch/request_submitted", "submission", _submitted),
    *(
        Rule(
            f"tc49/dispatch/{leaf}",
            "readable_id",
            lambda f: readable_id(f) is not None,
        )
        for leaf in ("request_admitted", "request_rejected", "request_completed")
    ),
    Rule(
        "tc49/dispatch/state/moving",
        "moving",
        lambda f: moving(f) == f.get("moving"),
    ),
    Rule(
        "tc49/dispatch/state/aspects",
        "shown_aspects",
        lambda f: _keeps(f, "aspects", shown_aspects(f)),
    ),
    Rule("tc49/dispatch/state/allocation", "kept_allocation", _allocation),
    Rule(
        "tc49/schedule/state/facing",
        "kept_facing",
        lambda f: _keeps(f, "facing", kept_facing(f)),
    ),
    Rule("tc49/layout/state/power", "power", lambda f: power(f) == f.get("power")),
    Rule(
        "tc49/layout/state/driving",
        "driving",
        lambda f: driving(f) == f.get("driving"),
    ),
    Rule("tc49/layout/state/taken", "taken", lambda f: _keeps(f, "taken", taken(f))),
    *(
        Rule(f"tc49/layout/{leaf}", "occupancy", lambda f: occupancy(f) is not None)
        for leaf in ("block_occupied", "block_vacated")
    ),
    Rule(
        "tc49/layout/state/wanted/traction/+",
        "desired_speed",
        lambda f: desired_speed(f) is not None,
    ),
    Rule(
        "tc49/layout/state/wanted/point/+",
        "desired_position",
        lambda f: desired_position(f) is not None,
    ),
    Rule(
        "tc49/layout/state/wanted/signal/+",
        "desired_aspect",
        lambda f: desired_aspect(f) is not None,
    ),
    Rule(
        "tc49/layout/state/wanted/track",
        "commanded_power",
        lambda f: commanded_power(f) is not None,
    ),
)


Recorded = list[tuple[str, Payload]]


def recording(bus: InProcessBus) -> Recorded:
    """Everything on `tc49/#` from here on. Subscribing hands the new
    subscriber every value already in `bus.last_values` as well, so the state
    a constructor published before anything could subscribe is recorded with
    the rest."""
    seen: Recorded = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append((topic, payload)))
    return seen


def scenario_ids() -> list[str]:
    return sorted(
        f"{path.parent.name}/{path.name.removesuffix('.scenario.yaml')}"
        for path in (ASSETS / "scenarios").glob("*/*.scenario.yaml")
    )


def bench_run(scenario_id: str) -> Recorded:
    """A bench scenario to quiescence. The harness publishes nothing here but
    the power press, which no row of the table reads."""
    assembly = assemble(*load(scenario_id))
    seen = recording(assembly.bus)
    assembly.simulator.run()
    return seen


REPLAYED = "crossover-yard/meet"


def replayed_run(scenario_id: str) -> Recorded:
    """A scenario replayed onto a live run, ticked with no waiting until every
    request it submits has completed — what `tests/bench/test_replay.py`
    runs. The replay's gestures land on no topic of the table."""
    layout, roster, scenario = load(scenario_id)
    assembly = assemble_live(layout, roster)
    seen = recording(assembly.bus)
    Replay(assembly.bus, layout, scenario)
    ticks = 0

    def done() -> bool:
        nonlocal ticks
        ticks += 1
        completed = [t for t, _p in seen if t == "tc49/dispatch/request_completed"]
        return len(completed) == len(scenario.requests) or ticks > 60

    assembly.simulator.run_live(3600.0, sleep=lambda _: None, stop=done)
    return seen


def layout_run() -> Recorded:
    """`layout` on the bench railroad: switched to `automatic`, `topped` in a
    throttle, the rails live, `single` standing in `up_w` facing the
    crossover, an aspect at the signalled end it departs through, the way set
    and the train moved over it. Every topic the test writes is left out, so
    what is left is `layout`'s."""
    clock = Clock()
    bus = InProcessBus(clock)
    seen = recording(bus)
    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()
    switches(bus, "automatic")
    takes(bus, "topped")
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    bus.publish(ASPECTS, {"aspects": {"up_w.B": "clear", "up_w.A": "stop"}})
    bus.drain()
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    ours = {
        DRIVING_WANTED,
        TAKE_WANTED,
        DEVICE_TRACK,
        PLACED,
        FACING,
        ASPECTS,
        ALIGN,
        MOVE,
    }
    return [(topic, payload) for topic, payload in seen if topic not in ours]


@pytest.fixture(scope="module")
def runs() -> dict[str, Recorded]:
    recorded = {scenario: bench_run(scenario) for scenario in scenario_ids()}
    recorded[f"{REPLAYED}, replayed"] = replayed_run(REPLAYED)
    recorded["layout"] = layout_run()
    return recorded


def rule_for(topic: str) -> Rule | None:
    return next((rule for rule in TABLE if matches(rule.topic, topic)), None)


def test_every_topic_in_the_table_has_a_recorded_frame(
    runs: dict[str, Recorded],
) -> None:
    """Otherwise the readers test would pass for nothing having been
    published."""
    heard = {topic for seen in runs.values() for topic, _payload in seen}
    unheard = [
        rule.topic
        for rule in TABLE
        if not any(matches(rule.topic, topic) for topic in heard)
    ]
    assert not unheard, f"no app wrote a frame on: {', '.join(unheard)}"


def test_every_frame_an_app_writes_passes_its_reader(
    runs: dict[str, Recorded],
) -> None:
    """Dropped, fallen back to a default, or a map entry dropped, added or
    changed — as published or after JSON — and the topic, the reader and
    the frame are named. Each distinct failure once, however often a run repeats it."""
    failures: dict[str, None] = {}
    for run, seen in runs.items():
        for topic, payload in seen:
            rule = rule_for(topic)
            if rule is None:
                continue
            for how, frame in (
                ("as published", payload),
                ("after JSON", json.loads(json.dumps(payload))),
            ):
                if not rule.passes(cast(Frame, frame)):
                    failures[
                        f"{topic}: {rule.reader} refused {frame!r} {how}" f" (in {run})"
                    ] = None
    assert not failures, "\n".join(failures)
