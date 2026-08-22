"""`tc49 live --scenario`: a scenario run as a replay, not as a seed (#171).

A run is built from a railroad and a person places its trains, so the harness
keeps its file format by standing where the person stands: it publishes one
`tc49/ui/placement_wanted` per train, turns the ones the document faces the
other way, presses GO, and feeds the requests at their `at` boundaries — every
one of them a topic a browser writes.

What is asserted here is the two halves of AC 5: that the trains arrive
through the gesture and not through a constructor, and that the run the
replay produces is the run the same scenario produced when the apps were
handed the document.
"""

import io
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from tc49.bench.cli import main
from tc49.bench.replay import Replay, arrival_ends
from tc49.bench.runner import Assembly, assemble, assemble_live
from tc49.bench.session import Session
from tc49.lib.scenario import TrainSpec
from tests.harness import ROOT, events, load

SCENARIO = "crossover-yard/meet"


def tick_until(assembly: Assembly, done: Callable[[], bool], limit: int = 60) -> None:
    """The live loop, no waiting, until `done` or the tick limit."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return done() or ticks > limit

    assembly.simulator.run_live(0.0, sleep=lambda _: None, stop=stop)


def replayed() -> Assembly:
    """A live run over `crossover-yard` — a railroad, its roster, and nothing
    else — with the scenario replayed onto it and run to quiescence."""
    layout, roster, scenario = load(SCENARIO)
    assembly = assemble_live(layout, roster)
    Replay(assembly.bus, layout, scenario)
    tick_until(
        assembly,
        lambda: len(events(assembly.trace, "request_completed")) == 3,
    )
    return assembly


def placement(assembly: Assembly) -> dict[str, Any]:
    return dict(events(assembly.trace, "allocation")[-1]["trains"])


def workings(assembly: Assembly) -> list[tuple[Any, ...]]:
    return [
        (line["id"], line["train"], line["depart"], tuple(line["dest"]))
        for line in events(assembly.trace, "request_submitted")
    ]


def test_a_bare_block_becomes_both_of_its_ends() -> None:
    """A page computes its arrival ends from where the drop landed, so a
    gesture always carries ends; the file is allowed to write a block, and the
    expansion happens where the browser's own would."""
    assert arrival_ends(("yard_e",)) == ["yard_e.A", "yard_e.B"]
    assert arrival_ends(("yard_e.A", "dn_w")) == ["yard_e.A", "dn_w.A", "dn_w.B"]


def test_the_replay_places_every_train_through_the_gesture() -> None:
    """Through `placement_wanted`, and not through a constructor: the run
    opens with an empty layout and held, and each train arrives as a gesture
    the dispatcher answers with `train_placed`."""
    layout, roster, scenario = load(SCENARIO)
    assembly = assemble_live(layout, roster)
    assembly.bus.drain()
    opening = events(assembly.trace, "allocation")[-1]
    assert opening["trains"] == {} and opening["locks"] == {}
    assert events(assembly.trace, "run")[-1]["run"] == "held"

    Replay(assembly.bus, layout, scenario)

    wanted = [line["train"] for line in events(assembly.trace, "placement_wanted")]
    assert wanted == list(scenario.trains)
    placed = {
        line["train"]: line["block"] for line in events(assembly.trace, "train_placed")
    }
    assert placed == {train: spec.at for train, spec in scenario.trains.items()}
    # And the operator this stands in for presses GO once the railroad is laid
    # out, which is the last of the four leaves a person writes.
    assert events(assembly.trace, "run")[-1]["run"] == "running"


def test_the_replay_faces_each_train_the_way_the_document_does() -> None:
    """A placement carries no facing — the scheduler gives a train that was
    off the layout the letter `A` — so the document's other letter is a
    `reversal_wanted`, which is the correction a person would make (ADR-0019).
    """
    layout, roster, scenario = load(SCENARIO)
    assembly = assemble_live(layout, roster)
    Replay(assembly.bus, layout, scenario)

    assert events(assembly.trace, "facing")[-1]["facing"] == {
        "express_2": "up_e.A",
        "freight_1": "yard_w.B",
    }


def test_the_replayed_run_is_the_one_the_document_produced() -> None:
    """The same three workings, minted with the same ids and departing by the
    same ends, and the railroad ends up standing the same way — against the
    batch assembly, which is the run the scenario produced when the apps were
    handed the document.

    The departure end is the one thing a gesture cannot state, so this holds
    only while a scenario's `from` agrees with its facing, which
    `crossover-yard/meet`'s does. That is the difference a browser has too.
    """
    layout, roster, scenario = load(SCENARIO)
    document = assemble(layout, roster, scenario)
    document.simulator.run()

    replay = replayed()

    assert workings(replay) == workings(document)
    assert placement(replay) == placement(document)
    assert [line["id"] for line in events(replay.trace, "request_completed")] == [
        line["id"] for line in events(document.trace, "request_completed")
    ]


def test_a_placement_the_dispatcher_refuses_stops_the_replay() -> None:
    """Dropped in silence is right for a person and wrong for a document
    (ADR-0034): the train would be left off the layout and every request for
    it answered `no_origin`, a run silently unlike the file. The harness says
    so instead."""
    layout, roster, scenario = load(SCENARIO)
    doubled = replace(
        scenario,
        trains={train: TrainSpec("yard_w", "B") for train in scenario.trains},
    )
    assembly = assemble_live(layout, roster)

    with pytest.raises(ValueError, match="would not stand"):
        Replay(assembly.bus, layout, doubled)


def test_a_replay_and_a_kept_picture_are_two_placements_and_the_cli_refuses() -> None:
    """`--state` comes up standing the trains where the last session left
    them, and the replay's placements would then be refused one by one for the
    blocks those trains hold. Two sources for one placement, and no reason to
    choose between them."""
    out = io.StringIO()
    assert main(["live", "--scenario", SCENARIO, "--state", "run.json"], out) == 2
    assert "name one" in out.getvalue()


def test_a_scenario_is_the_only_thing_the_cli_may_replay() -> None:
    """CLI-only and never browser-reachable (#171): `plays` is the harness's
    way in, and it refuses anything that is not a scenario the store has."""
    session = Session(ROOT, 0.0)
    try:
        assert session.plays("crossover-yard/nonesuch") is not None
        assert session.plays("crossover-yard") is not None  # a railroad, not one
        assert session.plays(SCENARIO) is None
    finally:
        session.bridge.close()
