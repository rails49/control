"""The live-session assembly (#71), at the assembly-over-the-bus seam.

`assemble_live` is the wiring `tc49 live` runs: no timetable, the bridge
the only way in. The tests here attach a real bridge and client to that
assembly and walk the whole loop — a gesture in, the request the scheduler
composes from it, the dispatcher's answer and the run's events back out over
the same socket — pacing the simulator with an injected time source, never
the wall clock.

The client sends `{train, dest}` and nothing else: the id and the departure
end are the scheduler's (ADR-0036), so a test that wants to name a request
reads the id off the trace rather than choosing one.

The last section is `Session`, the loop `tc49 live` actually runs (#148): a
whole session on a port, its railroad named by whoever joins and swapped by
whoever names another. It comes up with an empty layout and held, so the
trains are put on it by gesture, which is what an operator does (#171). That
one is paced by a real, very short period, because the loop under test is the
one that owns the clock.
"""

import io
import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection, connect

from tc49.bench.runner import Assembly, assemble_live
from tc49.bench.session import Session, state_for
from tc49.lib.bridge import Bridge
from tc49.lib.bus import Payload
from tests.harness import ASSETS, events, load

WANTED = "tc49/schedule/request_wanted"
REVERSAL = "tc49/schedule/reversal_wanted"
PLACEMENT = "tc49/dispatch/placement_wanted"

TIMEOUT = 5.0

PERIOD_S = 0.02
"""A session's command-poll period. Short enough that a handful of polls pass
in no time, long enough that a swap is a swap and not a race against the very
first turn."""


@pytest.fixture
def assembly() -> Assembly:
    layout, _roster, scenario = load("crossover-yard/meet")
    return assemble_live(layout, _roster, scenario.trains)


@pytest.fixture
def bridge(assembly: Assembly) -> Iterator[Bridge]:
    bridge = Bridge(assembly.bus)
    yield bridge
    bridge.close()


@pytest.fixture
def client(bridge: Bridge) -> Iterator[ClientConnection]:
    with connect(f"ws://127.0.0.1:{bridge.port}") as connection:
        deadline = time.monotonic() + TIMEOUT
        while bridge.connections == 0:  # registration follows the handshake
            assert time.monotonic() < deadline
            time.sleep(0.01)
        yield connection


def tick_until(assembly: Assembly, done: Callable[[], bool], limit: int = 50) -> None:
    """Run the live loop, no waiting, until `done` or the tick limit."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return done() or ticks > limit

    assembly.simulation.run_live(3600.0, sleep=lambda _: None, stop=stop)


def frames_until(client: ClientConnection, leaf: str) -> list[dict[str, Any]]:
    """Received frames up to and including the first with that event leaf."""
    received: list[dict[str, Any]] = []
    while True:
        frame = json.loads(client.recv(timeout=TIMEOUT))
        received.append(frame)
        if frame["topic"].rsplit("/", 1)[-1] == leaf:
            return received


def drag(
    client: ClientConnection, assembly: Assembly, train: str, dest: list[str]
) -> str:
    """Send a gesture frame, drain until the request it composes lands on the
    bus, and answer with the id the scheduler minted for it — the client
    writes from its own thread, so arrival is a wait, not a given."""
    before = len(events(assembly.trace, "request_submitted"))
    client.send(
        json.dumps({"topic": WANTED, "payload": {"train": train, "dest": dest}})
    )
    deadline = time.monotonic() + TIMEOUT
    while len(events(assembly.trace, "request_submitted")) == before:
        assert time.monotonic() < deadline, "the gesture composed nothing"
        assembly.bus.drain()
        time.sleep(0.01)
    return cast(str, events(assembly.trace, "request_submitted")[-1]["id"])


# Every shape ADR-0036 drops: read rather than trusted, and dropped in
# silence, a gesture carrying no id to address an answer to.
UNCOMPOSABLE: list[object] = [
    "freight_1 to yard_e",  # not an object at all
    {},  # neither field
    {"train": None, "dest": ["yard_e.A"]},  # no train
    {"train": "freight_1", "dest": "yard_e.A"},  # dest a string, not ends
    {"train": "freight_1", "dest": ["yard_e.A", 7]},  # not all ends
    {"train": "ghost", "dest": ["yard_e.A"]},  # a train it holds no facing for
]


def test_a_live_run_locks_incrementally() -> None:
    """The default `assemble_live` runs, pinned (#165). A live session locks
    the next transit plus the block beyond it and commits the rest, which is
    what the panel's two colours mean: green creeps along a cyan path as the
    train advances (ui/PANEL.md). `FullRoute`, the batch harness's baseline,
    would lock the whole route here and the route would come up all green.

    The assembly is built here rather than taken from the fixture: what is
    pinned is the strategy `assemble_live` picks when no caller names one,
    so this test has to be the one leaving it unnamed.
    """
    layout, _roster, scenario = load("crossover-yard/meet")
    assembly = assemble_live(layout, _roster, scenario.trains)
    assembly.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assembly.bus.drain()
    tick_until(assembly, lambda: bool(events(assembly.trace, "route_chosen")))
    assert events(assembly.trace, "route_chosen"), "the request never launched"

    lines = events(assembly.trace)
    at = next(i for i, line in enumerate(lines) if line["event"] == "route_chosen")
    chosen, granted = lines[at], lines[at + 1]  # the grant the launch made
    assert len(chosen["route"]) > 3, "a route this short cannot show the difference"
    assert granted["event"] == "lock_granted"  # an arrival on the spot has none
    # The route is interleaved block, transit, block, ... so the first
    # increment is the pair after the block the train stands in.
    assert granted["resources"] == chosen["route"][1:3]


def test_there_is_no_timetable_and_facing_is_still_published(
    assembly: Assembly,
) -> None:
    """crossover-yard/meet schedules three workings from the start; a live
    run is given no timetable at all (ADR-0036), so nothing is submitted and
    the railroad just waits. Facing is not off with it: it is where the trains
    were stood, and a joining page has no other source for a direction
    arrow."""
    tick_until(assembly, lambda: False, limit=10)
    assert events(assembly.trace, "request_submitted") == []
    assert events(assembly.trace, "route_chosen") == []
    [placed] = events(assembly.trace, "facing")
    assert placed["facing"] == {
        "express_2": "up_e.B-to-A",
        "freight_1": "yard_w.A-to-B",
    }


def test_the_session_survives_every_gesture_it_cannot_compose(
    assembly: Assembly,
) -> None:
    """#107's lesson at the scheduler (ADR-0036): anything at all can be
    published where a person's page writes, so each uncomposable shape in
    turn, then an honest drag that runs to completion — the railroad ticked
    through all of it, nothing was published in answer, and every frame is a
    line in the trace by virtue of having been published."""
    assembly.bus.drain()  # the startup cascade, so what follows is the answer
    before = len(events(assembly.trace))
    for payload in UNCOMPOSABLE:
        assembly.bus.publish(WANTED, cast(Payload, payload))
        assembly.bus.drain()
    assert events(assembly.trace, "request_submitted") == []
    assert len(events(assembly.trace)) == before + len(UNCOMPOSABLE)

    assembly.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assembly.bus.drain()
    tick_until(
        assembly,
        lambda: bool(events(assembly.trace, "request_completed", rid="freight_1-1")),
    )
    assert events(assembly.trace, "request_completed", rid="freight_1-1")


def test_a_gesture_is_composed_answered_and_run_over_the_same_socket(
    assembly: Assembly, client: ClientConnection
) -> None:
    """The whole loop from a drag: the frame names a train and a block's two
    ends, the scheduler supplies the id and the departure end off facing, and
    everything the dispatcher then says comes back over the same socket."""
    rid = drag(client, assembly, "freight_1", ["yard_e.A", "yard_e.B"])
    assert rid == "freight_1-1"
    [composed] = events(assembly.trace, "request_submitted", rid=rid)
    assert composed["depart"] == "yard_w.B"  # facing, which the drag never named

    tick_until(
        assembly, lambda: bool(events(assembly.trace, "request_completed", rid=rid))
    )
    received = frames_until(client, "request_completed")
    leaves = [frame["topic"].rsplit("/", 1)[-1] for frame in received]
    assert "request_submitted" in leaves  # what the gesture became
    assert "request_admitted" in leaves  # the dispatcher's answer
    assert "route_chosen" in leaves  # then the committed route
    assert received[-1]["payload"] == {"id": rid}


def test_a_rejection_comes_back_with_its_reason(
    assembly: Assembly, client: ClientConnection
) -> None:
    """Dropped on the outer third of a terminal block's blind end: yard_e.B
    is an end nothing connects to, so no train can enter through it. The
    filter-free drag (#67) relies on this answer arriving rather than on the
    panel pre-judging it, and the scheduler judges nothing either."""
    rid = drag(client, assembly, "freight_1", ["yard_e.B"])
    tick_until(
        assembly, lambda: bool(events(assembly.trace, "request_rejected", rid=rid))
    )
    [rejection] = [
        frame
        for frame in frames_until(client, "request_rejected")
        if frame["topic"].rsplit("/", 1)[-1] == "request_rejected"
    ]
    assert rejection["payload"]["reason"] == "no_entry"


def test_a_drag_on_a_moving_train_is_answered_and_the_session_lives(
    assembly: Assembly, client: ClientConnection
) -> None:
    """A grant names the next block before the sensor does, and facing
    follows the grant, so a drag on a train that is not idle composes a
    departure end in a block the dispatcher does not yet have it in. The
    scheduler judges none of that — it composes and submits like any other
    gesture — and admission judges the drag from where the committed route
    arrives (#135, ADR-0047): dn_w.A cannot be entered from yard_e, so the
    answer is `unreachable`, and the railroad runs on around it (#73)."""
    first = drag(client, assembly, "freight_1", ["yard_e.A"])
    tick_until(
        assembly, lambda: bool(events(assembly.trace, "move_granted", rid=first))
    )
    second = drag(client, assembly, "freight_1", ["dn_w.A"])
    [composed] = events(assembly.trace, "request_submitted", rid=second)
    assert composed["depart"] == "dn_w.B"  # where the grant is taking it
    [rejected] = events(assembly.trace, "request_rejected", rid=second)
    assert rejected["reason"] == "unreachable"
    tick_until(
        assembly, lambda: bool(events(assembly.trace, "request_completed", rid=first))
    )
    assert events(assembly.trace, "request_completed", rid=first)


def test_a_reloaded_page_is_served_the_picture_and_answered_again(
    assembly: Assembly, bridge: Bridge, client: ClientConnection
) -> None:
    """#106's own reproduction, over the socket.

    A page drags and goes away. The page that replaces it joins a session
    already running, so it is served the run's picture — where the train
    stands and what it is running — instead of nothing, and its own drag is
    answered. Ids are no longer the page's business at all (ADR-0036): a
    reload cannot re-use one the dispatcher has seen because it mints none,
    which is what left the marker stuck in "requested" for good.
    """
    rid = drag(client, assembly, "freight_1", ["yard_e.A"])
    tick_until(assembly, lambda: bool(events(assembly.trace, "route_chosen", rid=rid)))
    client.close()  # the tab is reloaded: no close handshake, just gone

    with connect(f"ws://127.0.0.1:{bridge.port}") as reloaded:
        deadline = time.monotonic() + TIMEOUT
        while bridge.connections == 0:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        [picture] = [
            frame["payload"]
            for frame in frames_until(reloaded, "allocation")
            if frame["topic"].rsplit("/", 1)[-1] == "allocation"
        ]
        assert picture["trains"]["freight_1"]  # somewhere, and the page knows it
        assert [request["id"] for request in picture["requests"]] == [rid]

        again = drag(reloaded, assembly, "freight_1", ["dn_w.A"])
    assert again != rid  # the counter is the scheduler's and never rewinds
    answered = [
        line["event"]
        for line in events(assembly.trace, rid=again)
        if line["event"] in ("request_admitted", "request_rejected")
    ]
    assert answered, "the drag got no answer at all"


def test_a_reversal_turns_the_arrow_and_asks_the_dispatcher_for_nothing(
    assembly: Assembly, client: ClientConnection
) -> None:
    """The other leaf a page may write, over the same socket (#124): the
    frame names a train, the scheduler flips its facing and republishes, and
    the panel's arrow turns. No request is composed and no `tc49/dispatch`
    topic carries anything, nothing having moved.

    `express_2` stands in `up_e`, a through block: `freight_1`'s `yard_w` is
    terminal, where the gesture is a no-op and the arrow would not move to be
    watched (#145)."""
    assembly.bus.drain()  # the startup cascade, so what follows is the answer
    dispatched = len([one for one in events(assembly.trace) if "id" in one])
    client.send(json.dumps({"topic": REVERSAL, "payload": {"train": "express_2"}}))

    deadline = time.monotonic() + TIMEOUT
    while len(events(assembly.trace, "facing")) < 2:
        assert time.monotonic() < deadline, "the reversal turned nothing"
        assembly.bus.drain()
        time.sleep(0.01)

    turned = events(assembly.trace, "facing")[-1]
    assert turned["facing"] == {
        "express_2": "up_e.A-to-B",
        "freight_1": "yard_w.A-to-B",
    }
    assert events(assembly.trace, "request_submitted") == []
    assert len([one for one in events(assembly.trace) if "id" in one]) == dispatched


def test_a_reversal_naming_a_train_the_session_lacks_is_dropped(
    assembly: Assembly, client: ClientConnection
) -> None:
    """Every shape the scheduler drops, in silence and to the trace: the
    frame is a line by virtue of having been published, and nothing answers
    it — a gesture carries no id to address an answer to (ADR-0034)."""
    assembly.bus.drain()
    before = len(events(assembly.trace))
    dropped: list[object] = ["freight_1", {}, {"train": 7}, {"train": "ghost"}]
    for payload in dropped:
        assembly.bus.publish(REVERSAL, cast(Payload, payload))
        assembly.bus.drain()

    assert len(events(assembly.trace)) == before + len(dropped)
    assert len(events(assembly.trace, "facing")) == 1  # the placement, unturned


# --- the session: one railroad at a time, named by whoever joins -------------


@pytest.fixture
def session() -> Iterator[Session]:
    """A whole session, idle, its loop on a thread of its own — which is what
    `tc49 live` with no railroad named is."""
    live = Session(ASSETS, PERIOD_S)
    thread = threading.Thread(target=live.run, args=(io.StringIO(),), daemon=True)
    thread.start()
    yield live
    live.stop()
    thread.join(TIMEOUT)
    live.bridge.close()


def joining(live: Session, railroad: str) -> ClientConnection:
    """A client naming the railroad it wants, the way the panel does."""
    return connect(f"ws://127.0.0.1:{live.bridge.port}/{railroad}")


def put(client: ClientConnection, train: str, block: str) -> dict[str, Any]:
    """A train off the layout stood on a block, answered with the
    `train_placed` that says the dispatcher accepted it.

    The gesture a session's railroad is laid out with, since a run is built
    from a railroad and nothing places its trains for the operator (#171).

    The power value is waited for first. A session builds each assembly on
    its own thread and hands it to the bridge afterwards, so a frame sent
    between the handshake and the swap would be published onto the bus being
    torn down — and the new assembly's own opening statement is proof this
    client is being fed it.
    """
    payload_of(client, "power")
    client.send(
        json.dumps({"topic": PLACEMENT, "payload": {"train": train, "block": block}})
    )
    return payload_of(client, "train_placed")


def payload_of(client: ClientConnection, leaf: str) -> dict[str, Any]:
    """The payload of the first frame with that event leaf."""
    return frames_until(client, leaf)[-1]["payload"]


def test_a_client_names_the_railroad_and_the_session_builds_it(
    session: Session,
) -> None:
    """An idle session runs nothing until a path names a railroad. What comes
    back first is the new assembly's opening drain — the startup cascade — so
    the run's value and its empty picture arrive as live frames and there is
    nothing to seed (ADR-0032).

    The layout is empty and the run is **held**, which is the ordinary cold
    start of a run an operator drives (#171, ADR-0039): every train the
    railroad owns is known and off the layout, and there is nothing to do but
    place them and press GO."""
    with joining(session, "crossover-yard") as client:
        assert payload_of(client, "run")["run"] == "held"
        assert payload_of(client, "allocation")["trains"] == {}

        assert put(client, "freight_1", "yard_w") == {
            "train": "freight_1",
            "block": "yard_w",
        }
        assert payload_of(client, "facing")["facing"] == {"freight_1": "yard_w.A-to-B"}


def test_the_same_path_rejoins_the_run_already_going(session: Session) -> None:
    """A reloaded tab restarts nothing: the path is the one already running,
    so the client is served the picture — the train the first tab placed is
    in it — and drops into the run where it is."""
    with joining(session, "crossover-yard") as client:
        put(client, "freight_1", "yard_w")
        with joining(session, "crossover-yard") as rejoined:
            assert payload_of(rejoined, "allocation")["trains"]["freight_1"]
        # And the first client is still being served the same run: its next
        # gesture lands on the same assembly and is answered there.
        client.send(
            json.dumps(
                {
                    "topic": PLACEMENT,
                    "payload": {"train": "express_2", "block": "up_e"},
                }
            )
        )
        assert payload_of(client, "train_placed")["train"] == "express_2"


def test_naming_another_railroad_swaps_the_assembly_and_closes_the_old_client(
    session: Session,
) -> None:
    """One operator, one railroad. The session tears the assembly down and
    builds a fresh one for the railroad named, so the counter starts again;
    the client left on the old path is closed rather than fed another
    railroad's events."""
    with joining(session, "crossover-yard") as first:
        assert payload_of(first, "power")["power"] == "on"
        with joining(session, "reversing-loops-v0") as second:
            assert put(second, "north", "station_a_1")["block"] == "station_a_1"
            with pytest.raises(ConnectionClosed):
                while True:
                    first.recv(timeout=TIMEOUT)


def test_a_path_naming_no_railroad_is_refused_and_the_run_lives(
    session: Session,
) -> None:
    """A typo must not take down a live railroad: the client is answered with
    an error frame and closed, and the run it never named ticks on."""
    with joining(session, "crossover-yard") as client:
        assert payload_of(client, "power")["power"] == "on"
        with joining(session, "nonesuch") as mistaken:
            assert json.loads(mistaken.recv(timeout=TIMEOUT)) == {
                "error": "no railroad 'nonesuch'"
            }
            with pytest.raises(ConnectionClosed):
                mistaken.recv(timeout=TIMEOUT)
        # The run it never named lives on: a gesture is still answered.
        assert put(client, "freight_1", "yard_w")["train"] == "freight_1"


def test_each_railroad_the_session_runs_keeps_its_own_picture(
    tmp_path: Path,
) -> None:
    """A picture belongs to the railroad it is a picture of (#151).

    One operator may switch railroads all evening, and a session keeps one
    path. A single file behind it would hand the next railroad the last one's
    placement — and the train names do not tell them apart, `fixed` and
    `flexible` standing on two different layouts in the scenarios shipped
    here, so a block of the wrong layout would be adopted and no gesture on
    this one could clear it. So the path names one file per railroad.
    """
    kept = tmp_path / "run.json"
    live = Session(ASSETS, PERIOD_S, state=kept)
    thread = threading.Thread(target=live.run, args=(io.StringIO(),), daemon=True)
    thread.start()
    try:
        with joining(live, "crossover-yard") as client:
            assert put(client, "freight_1", "yard_w")["train"] == "freight_1"
        with joining(live, "reversing-loops-v0") as other:
            assert put(other, "north", "station_a_1")["train"] == "north"
    finally:
        live.stop()
        thread.join(TIMEOUT)
        live.bridge.close()

    pictures = {
        layout: json.loads(state_for(kept, layout).read_text())[
            "tc49/dispatch/state/allocation"
        ]
        for layout in ("crossover-yard", "reversing-loops-v0")
    }
    assert set(pictures["crossover-yard"]["trains"]) == {"freight_1"}
    assert set(pictures["reversing-loops-v0"]["trains"]) == {"north"}


def test_a_railroads_file_is_named_beside_the_session_path() -> None:
    """Beside it and never it: two railroads must not be able to collide on
    one name, and the path the operator typed is the stem they share."""
    kept = Path("runs/tonight.json")
    assert state_for(kept, "reversing-loops-v0") == Path(
        "runs/tonight.reversing-loops-v0.json"
    )
    assert state_for(kept, "crossover-yard") != state_for(kept, "reversing-loops-v0")
    assert state_for(kept, "reversing-loops-v0").parent == kept.parent
