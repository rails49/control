"""A request that ends without arriving (ADR-0049, #271).

`tc49/dispatch/cancel_wanted` is a person saying that work is over: the train
broke down, the railroad changed under the route, or they simply want the
locomotive back. It names one **request** by its id (ADR-0080), and an id the
dispatcher does not hold is dropped in silence and to the trace like any other
gesture it cannot act on (ADR-0034).

What it leaves behind is a train at rest: every resource its request held is
released except the block it stands in, and one `request_cancelled` says which
request ended and why. The one thing it cannot do at once is take a move back,
nothing on the bus retracting a `move` already sent — so a cancellation that
lands mid-transit is deferred to the sensors that end it.

Driven at the bus, which is where a person's press arrives.
"""

from typing import Any, cast

from tc49.bench.runner import Assembly, assemble_live
from tc49.dispatcher import FullRoute
from tc49.lib.bus import Payload
from tc49.lib.inventory import OFF, ON
from tc49.lib.scenario import TrainSpec
from tests.harness import events, leaves, load, power, press, stock, ticks

CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"

STOCK = stock(freight_1=1100, express_2=600)


def two_trains() -> dict[str, TrainSpec]:
    """`crossover-yard` with the meet's placement and no timetable: the two
    trains nose to nose, each needing the other's end of the railroad."""
    return {
        "freight_1": TrainSpec("yard_w", "A-to-B"),
        "express_2": TrainSpec("up_e", "B-to-A"),
    }


def whole_route() -> Assembly:
    """A live railroad under `FullRoute`, where a launch locks every transit
    and every block beyond the origin — so a train cancelled mid-route is
    holding track it will never reach."""
    layout, _roster, _ = load("crossover-yard/meet")
    return assemble_live(layout, STOCK, two_trains(), FullRoute)


def cancel(assembly: Assembly, rid: str) -> None:
    press(assembly, CANCEL_WANTED, {"id": rid})


def drag(assembly: Assembly, train: str, *dest: str) -> str:
    """The gesture, and the id the scheduler minted for it: a drag's id
    carries the scheduler process's nonce (ADR-0033), so it is read back off
    the trace rather than spelled out."""
    press(assembly, REQUEST_WANTED, {"train": train, "dest": list(dest)})
    return str(last(assembly, "request_submitted")["id"])


def last(assembly: Assembly, leaf: str) -> dict[str, Any]:
    return events(assembly.trace, leaf)[-1]


def cancellations(assembly: Assembly) -> list[dict[str, Any]]:
    return leaves(assembly, "request_cancelled")


def locks(assembly: Assembly) -> dict[str, str]:
    return cast(dict[str, str], last(assembly, "allocation")["locks"])


def test_a_request_still_queued_is_revoked_and_never_launches() -> None:
    """A pending request has taken nothing, so cancelling it is the one
    event: it leaves the queue, and the power on that would have launched it
    finds nothing to launch."""
    assembly = whole_route()
    press(assembly, *power(OFF))
    request = drag(assembly, "freight_1", "yard_e.A")
    assert events(assembly.trace, "request_admitted")

    cancel(assembly, request)

    assert cancellations(assembly) == [
        {
            "time": 0.0,
            "event": "request_cancelled",
            "id": request,
            "reason": "revoked",
        }
    ]
    assert leaves(assembly, "lock_released") == []

    press(assembly, *power(ON))
    ticks(assembly, 6)
    assert leaves(assembly, "route_chosen") == []
    assert leaves(assembly, "request_completed") == []


def test_the_gesture_ends_the_one_request_it_names() -> None:
    """A request of the same train that does not follow the cancelled one
    stays in the list (ADR-0080). A second drag would follow the first
    (#827), so the second is one a page submits with its own departure end
    (BUS.md, rule 1)."""
    assembly = whole_route()
    press(assembly, *power(OFF))
    first = drag(assembly, "freight_1", "yard_e.A")
    second = "freight_1-page-1"
    press(
        assembly,
        "tc49/dispatch/request_submitted",
        {"id": second, "train": "freight_1", "depart": "yard_w.B", "dest": ["dn_w.A"]},
    )

    cancel(assembly, first)

    assert [line["id"] for line in cancellations(assembly)] == [first]
    assert [r["id"] for r in last(assembly, "allocation")["requests"]] == [second]


def test_a_cancelled_request_at_rest_gives_up_all_but_the_block_it_stands_in() -> None:
    """The release path whole: what a route took is given back as one
    `lock_released`, and what stays is the standing lock every parked train
    holds (GLOSSARY.md). Power off first, so the train is active with no move
    outstanding — the sweep that would have granted the next one is the one
    power `off` stops."""
    assembly = whole_route()
    request = drag(assembly, "freight_1", "yard_e.A")
    assert last(assembly, "route_chosen")["id"] == request
    ticks(assembly, 2, at={0: power(OFF)})
    assert locks(assembly)["dn_w"] == "freight_1"

    cancel(assembly, request)

    assert cancellations(assembly) == [
        {
            "time": 60.0,
            "event": "request_cancelled",
            "id": request,
            "reason": "revoked",
        }
    ]
    assert last(assembly, "lock_released") == {
        "time": 60.0,
        "event": "lock_released",
        "train": "freight_1",
        "resources": [
            "crossover.dn_straight",
            "dn_e",
            "east_ladder.from_dn",
            "yard_e",
        ],
    }
    assert locks(assembly) == {"dn_w": "freight_1", "up_e": "express_2"}
    assert last(assembly, "allocation")["requests"] == []


def test_a_train_cancelled_mid_route_holds_no_route_blocks_afterwards() -> None:
    """The `FullRoute` case the release path exists for: a launch locks
    `crossing_order()` — every transit and every block beyond the origin — so
    a train cancelled halfway is holding track it will never reach, and every
    train waiting on that track waits for a session restart without this."""
    assembly = whole_route()
    request = drag(assembly, "freight_1", "yard_e.A")
    ticks(assembly, 2, at={0: power(OFF)})
    held = locks(assembly)
    assert len([r for r, by in held.items() if by == "freight_1"]) > 1

    cancel(assembly, request)

    assert [r for r, by in locks(assembly).items() if by == "freight_1"] == ["dn_w"]


def test_what_a_cancellation_frees_is_granted_on_the_sweep_that_follows() -> None:
    """A cancellation moves the lock table, so the waiting set is
    reconsidered where it moves (ADR-0047): express_2, refused for as long as
    freight_1's whole route stood across the railroad, launches on the sweep
    the retirement runs rather than at some later event.

    Here that is the deferred retirement, which is the case with something to
    hand on: the cancellation lands mid-transit, the move runs to its
    sensors, and everything the route held goes back at once.
    """
    assembly = whole_route()
    cancelled = drag(assembly, "freight_1", "yard_e.A")
    refused = drag(assembly, "express_2", "yard_w.B")
    assert leaves(assembly, "grant_refused")[-1]["id"] == refused

    cancel(assembly, cancelled)
    ticks(assembly, 2)

    assert [line["id"] for line in leaves(assembly, "route_chosen")] == [
        cancelled,
        refused,
    ]
    retired = leaves(assembly, "request_cancelled")[0]["time"]
    assert leaves(assembly, "route_chosen")[-1]["time"] == retired


def test_a_cancellation_mid_move_grants_nothing_further() -> None:
    """A move already sent cannot be retracted (ADR-0037), so the request is
    marked and the train runs into the block it was granted — and takes no
    further move, wherever along its route it had got to."""
    assembly = whole_route()
    request = drag(assembly, "freight_1", "yard_e.A")
    granted = len(leaves(assembly, "move_granted"))

    cancel(assembly, request)
    ticks(assembly, 8)

    assert len(leaves(assembly, "move_granted")) == granted
    assert leaves(assembly, "request_completed") == []


def test_a_cancellation_mid_move_retires_when_the_move_ends_and_not_before() -> None:
    """The deferral has a definite end: `block_vacated` says the move the
    gesture could not take back is over, and the request retires there — as a
    cancellation and not a completion, the train having stopped short of
    where it was going."""
    assembly = whole_route()
    request = drag(assembly, "freight_1", "yard_e.A")

    cancel(assembly, request)
    assert cancellations(assembly) == []  # the move is still running

    ticks(assembly, 1)  # the head arrives
    assert cancellations(assembly) == []
    ticks(assembly, 1)  # the tail clears, and the move is over

    assert cancellations(assembly) == [
        {
            "time": 60.0,
            "event": "request_cancelled",
            "id": request,
            "reason": "revoked",
        }
    ]
    assert [r for r, by in locks(assembly).items() if by == "freight_1"] == ["dn_w"]


def test_a_cancellation_needs_no_power_off() -> None:
    """Cancelling is how one train's work ends, and turning the power off to
    do it would stop every other train to let one go. The power above is on
    throughout; this pins that it was never a precondition."""
    assembly = whole_route()
    request = drag(assembly, "freight_1", "yard_e.A")

    cancel(assembly, request)
    ticks(assembly, 4)

    assert assembly.dispatcher.state.power == ON
    assert [line["reason"] for line in cancellations(assembly)] == ["revoked"]


def test_a_gesture_naming_a_request_the_dispatcher_does_not_hold_says_nothing() -> None:
    """Dropped, not answered (ADR-0034): there is nothing to end.

    **Nothing** is read literally, which is what express_2's standing refusal
    is here for. A gesture that ends nothing frees nothing, so it sweeps
    nothing: a sweep would publish one more `grant_refused` for express_2.
    The gesture's own trace line is the whole of its record.
    """
    assembly = whole_route()
    # express_2 wants the block freight_1 is idle in, so it is refused and
    # stays refused: an idle train's block is permanently unavailable.
    drag(assembly, "express_2", "yard_w.B")
    refusals = len(leaves(assembly, "grant_refused"))
    assert refusals == 1
    before = assembly.trace

    cancel(assembly, "freight_1-1")

    assert [line["event"] for line in events(assembly.trace[len(before) :])] == [
        "cancel_wanted"
    ]
    assert len(leaves(assembly, "grant_refused")) == refusals


def test_a_deferred_cancellation_sweeps_nothing_either() -> None:
    """The same rule at the other end of it. A cancellation caught mid-move
    releases nothing yet — it marks the request and waits for the sensors —
    so there is nothing for a sweep to hand anybody, and the sweep runs where
    the retirement does instead."""
    assembly = whole_route()
    request = drag(assembly, "freight_1", "yard_e.A")
    drag(assembly, "express_2", "yard_w.B")
    refusals = len(leaves(assembly, "grant_refused"))
    before = assembly.trace

    cancel(assembly, request)

    assert [line["event"] for line in events(assembly.trace[len(before) :])] == [
        "cancel_wanted"
    ]
    assert len(leaves(assembly, "grant_refused")) == refusals


def test_a_gesture_naming_a_request_that_completed_says_nothing() -> None:
    assembly = whole_route()
    request = drag(assembly, "freight_1", "yard_e.A")
    ticks(assembly, 8)
    assert [line["id"] for line in leaves(assembly, "request_completed")] == [request]
    released = len(leaves(assembly, "lock_released"))

    cancel(assembly, request)
    ticks(assembly, 2)

    assert cancellations(assembly) == []
    assert len(leaves(assembly, "lock_released")) == released


def test_a_gesture_that_cannot_be_read_at_all_is_dropped() -> None:
    """Anyone may publish on the topic and nothing authenticates them, so the
    frame is read and never subscripted: what cannot be read ends no request
    and takes no app down (BUS.md, rule 4)."""
    assembly = whole_route()
    drag(assembly, "freight_1", "yard_e.A")

    for payload in ({}, {"id": 7}, {"id": ""}, {"train": "freight_1"}, "freight_1"):
        press(assembly, CANCEL_WANTED, cast(Payload, payload))

    assert cancellations(assembly) == []


# -- the requests chained after a cancelled one (#836) ------------------------


def test_a_drag_made_once_the_cancel_is_asked_departs_where_the_train_stopped() -> None:
    """The cancel is asked mid-move, so the request is still underway and the
    second drag chains after it (#827). It was made knowing the first is
    over, so it is not cancelled with it: once the train stops in `dn_w`,
    which it entered through A, it carries on through B and completes."""
    assembly = whole_route()
    first = drag(assembly, "freight_1", "yard_e.A")
    cancel(assembly, first)
    second = drag(assembly, "freight_1", "yard_e.A")
    assert last(assembly, "request_submitted")["after"] == first

    ticks(assembly, 12)

    assert [(c["id"], c["reason"]) for c in cancellations(assembly)] == [
        (first, "revoked")
    ]
    [chosen] = events(assembly.trace, "route_chosen", rid=second)
    assert chosen["route"][:2] == ["dn_w", "crossover.dn_straight"]
    assert [line["id"] for line in leaves(assembly, "request_completed")] == [second]


def test_a_drag_admitted_after_the_cancelled_request_retired_departs_too() -> None:
    """The same once the request has retired: a scheduler that has not yet
    heard it end chains after it, and the dispatcher settles the drag from
    where the train stopped. Power off first, so the cancel retires at the
    gesture."""
    assembly = whole_route()
    first = drag(assembly, "freight_1", "yard_e.A")
    ticks(assembly, 2, at={0: power(OFF)})
    cancel(assembly, first)
    second = "freight_1-late"
    press(
        assembly,
        "tc49/dispatch/request_submitted",
        {"id": second, "train": "freight_1", "dest": ["yard_e.A"], "after": first},
    )
    press(assembly, *power(ON))

    ticks(assembly, 12)

    assert [c["id"] for c in cancellations(assembly)] == [first]
    [chosen] = events(assembly.trace, "route_chosen", rid=second)
    assert chosen["route"][:2] == ["dn_w", "crossover.dn_straight"]
    assert [line["id"] for line in leaves(assembly, "request_completed")] == [second]


def test_a_drag_chained_before_the_cancel_is_asked_is_cancelled_with_it() -> None:
    """Made while the first request was still wanted, it was a plan to carry
    on from where that one would arrive, and that plan is over."""
    assembly = whole_route()
    first = drag(assembly, "freight_1", "yard_e.A")
    second = drag(assembly, "freight_1", "yard_w.B")
    cancel(assembly, first)
    assert cancellations(assembly) == []

    ticks(assembly, 2)

    assert [(c["id"], c["reason"]) for c in cancellations(assembly)] == [
        (first, "revoked"),
        (second, "revoked"),
    ]
    assert [line["id"] for line in leaves(assembly, "route_chosen")] == [first]


def test_a_drag_chained_after_a_waiting_request_is_cancelled_with_it() -> None:
    """A waiting request never moved the train, so nothing the person made
    after it has anywhere to start from but the request it followed."""
    assembly = whole_route()
    press(assembly, *power(OFF))
    first = drag(assembly, "freight_1", "yard_e.A")
    second = drag(assembly, "freight_1", "yard_w.B")
    assert last(assembly, "request_submitted")["after"] == first

    cancel(assembly, first)

    assert [(c["id"], c["reason"]) for c in cancellations(assembly)] == [
        (first, "revoked"),
        (second, "revoked"),
    ]
