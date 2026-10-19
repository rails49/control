"""The waiting requests are a list a person orders (ADR-0080, #823).

The dispatcher serves the list in its order: a new request goes in after
every request of the same or a higher priority, each waiting request is
offered the first claim in turn, and one that cannot start is passed over for
a later one. A person moves a request with `reorder_wanted` and ends one with
`cancel_wanted`, both by id. A request with `after` starts where the train's
earlier request ends.

Driven at the bus: requests are published on `request_submitted` as a
scheduler would, so `depart` and `after` are the test's to state.
"""

from dataclasses import replace
from typing import Any

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.bus import Payload
from tc49.lib.inventory import OFF, ON
from tc49.lib.roster import Train
from tc49.lib.scenario import TrainSpec
from tests.harness import events, leaves, load, power, press, stock, ticks

REQUESTS = "tc49/dispatch/request_submitted"
REORDER_WANTED = "tc49/dispatch/reorder_wanted"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"


def meet() -> Assembly:
    """`crossover-yard` with freight_1 in `yard_w` and express_2 in `up_e`.

    The yard's two blocks are terminal: `yard_w` is reached through its B end
    alone and `yard_e` through its A end alone."""
    layout, roster, scenario = load("crossover-yard/meet")
    return assemble_live(layout, roster, scenario.trains)


def submit(
    assembly: Assembly,
    rid: str,
    train: str,
    depart: str | None,
    *dest: str,
    after: str | None = None,
) -> None:
    payload: Payload = {"id": rid, "train": train, "depart": depart, "dest": [*dest]}
    if after is not None:
        payload["after"] = after
    press(assembly, REQUESTS, payload)


def reorder(assembly: Assembly, rid: str, before: str | None) -> None:
    press(assembly, REORDER_WANTED, {"id": rid, "before": before})


def listed(assembly: Assembly) -> list[str]:
    """The ids `state/allocation` lists, in its order."""
    return [request["id"] for request in picture(assembly)["requests"]]


def picture(assembly: Assembly) -> dict[str, Any]:
    return events(assembly.trace, "allocation")[-1]


def ids(assembly: Assembly, leaf: str) -> list[str]:
    return [str(line["id"]) for line in leaves(assembly, leaf)]


# -- the list's order ---------------------------------------------------------


def test_a_new_request_goes_in_after_every_request_of_the_same_or_higher_priority() -> (
    None
):
    """Two trains of priority 1, one of 2 and one with none, submitted out of
    that order: the list is ordered by priority, and by arrival within one."""
    layout, _, _ = load("crossover-yard/meet")
    roster = stock()
    roster = replace(
        roster,
        trains={
            "low": Train(stated_length=600, priority=2),
            "fast": Train(stated_length=600, priority=1),
            "none": Train(stated_length=600),
            "express": Train(stated_length=600, priority=1),
        },
    )
    assembly = assemble_live(
        layout,
        roster,
        {
            "low": TrainSpec("yard_w", "A-to-B"),
            "fast": TrainSpec("up_e", "B-to-A"),
            "none": TrainSpec("dn_e", "B-to-A"),
            "express": TrainSpec("up_w", "B-to-A"),
        },
    )
    press(assembly, *power(OFF))

    submit(assembly, "none-1", "none", "dn_e.A", "dn_w.B")
    submit(assembly, "low-1", "low", "yard_w.B", "dn_w.A")
    submit(assembly, "fast-1", "fast", "up_e.B", "yard_e.A")
    submit(assembly, "express-1", "express", "up_w.A", "yard_w.B")

    assert listed(assembly) == ["fast-1", "express-1", "low-1", "none-1"]


def test_a_later_request_starts_where_an_earlier_one_cannot() -> None:
    """express_2 is first in the list and wants the block freight_1 stands
    in, so it is refused; freight_1's request, behind it, still starts. The
    list keeps its order: express_2 is still first."""
    assembly = meet()
    submit(assembly, "express_2-1", "express_2", "up_e.A", "yard_w.B")
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")

    assert ids(assembly, "grant_refused")[0] == "express_2-1"
    assert ids(assembly, "route_chosen") == ["freight_1-1"]
    assert listed(assembly) == ["express_2-1", "freight_1-1"]
    assert "route" in picture(assembly)["requests"][1]


def test_refusals_do_not_reorder_the_list() -> None:
    """The refusal count that aged the queue is gone (ADR-0080): a request
    refused many times keeps its place, and so does the one behind it."""
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "up_e.A")
    submit(assembly, "express_2-1", "express_2", "up_e.A", "yard_w.B")
    for _ in range(3):
        press(assembly, *power(ON))
        press(assembly, *power(OFF))

    assert listed(assembly) == ["freight_1-1", "express_2-1"]


# -- reorder_wanted -----------------------------------------------------------


def test_a_request_moves_in_front_of_another_or_to_the_end() -> None:
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "express_2-1", "express_2", "up_e.B", "yard_e.A")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")

    reorder(assembly, "express_2-1", "freight_1-1")
    assert listed(assembly) == ["express_2-1", "freight_1-1", "freight_1-2"]

    reorder(assembly, "express_2-1", None)
    assert listed(assembly) == ["freight_1-1", "freight_1-2", "express_2-1"]


def test_the_list_is_served_in_its_new_order() -> None:
    """freight_1 and express_2 both want `dn_w`, from either end, so only
    the first in the list starts; the reorder decides which."""
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "express_2-1", "express_2", "up_e.A", "dn_w.B")

    reorder(assembly, "express_2-1", "freight_1-1")
    press(assembly, *power(ON))

    decided = [
        (line["event"], line["id"])
        for line in events(assembly.trace)
        if line["event"] in ("route_chosen", "grant_refused")
    ]
    assert decided == [
        ("route_chosen", "express_2-1"),
        ("grant_refused", "freight_1-1"),
    ]


def test_a_reorder_naming_a_started_request_is_dropped() -> None:
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    press(assembly, *power(OFF))
    submit(assembly, "express_2-1", "express_2", "up_e.A", "yard_w.B")
    assert ids(assembly, "route_chosen") == ["freight_1-1"]
    before = listed(assembly)

    reorder(assembly, "express_2-1", "freight_1-1")
    reorder(assembly, "freight_1-1", None)

    assert listed(assembly) == before


def test_a_reorder_naming_an_unknown_request_is_dropped() -> None:
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "express_2-1", "express_2", "up_e.B", "yard_e.A")
    trace = assembly.trace

    reorder(assembly, "ghost-1", "freight_1-1")
    reorder(assembly, "express_2-1", "ghost-1")

    assert [line["event"] for line in events(assembly.trace[len(trace) :])] == [
        "reorder_wanted",
        "reorder_wanted",
    ]


def test_a_reorder_putting_a_chained_request_before_the_one_it_follows_is_dropped() -> (
    None
):
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")

    reorder(assembly, "freight_1-2", "freight_1-1")
    reorder(assembly, "freight_1-1", None)

    assert listed(assembly) == ["freight_1-1", "freight_1-2"]


# -- cancel_wanted by id ------------------------------------------------------


def test_cancelling_a_waiting_request_cancels_the_one_chained_after_it() -> None:
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")

    press(assembly, CANCEL_WANTED, {"id": "freight_1-1"})

    assert [
        (line["id"], line["reason"]) for line in leaves(assembly, "request_cancelled")
    ] == [
        ("freight_1-1", "revoked"),
        ("freight_1-2", "revoked"),
    ]
    assert listed(assembly) == []


def test_cancelling_an_underway_request_cancels_its_follower_when_it_retires() -> None:
    """The move already sent runs to its sensors (ADR-0049), and the request
    chained after it goes when it does, never having started."""
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")

    press(assembly, CANCEL_WANTED, {"id": "freight_1-1"})
    assert leaves(assembly, "request_cancelled") == []
    ticks(assembly, 4)

    assert ids(assembly, "request_cancelled") == ["freight_1-1", "freight_1-2"]
    assert ids(assembly, "route_chosen") == ["freight_1-1"]
    assert listed(assembly) == []


def test_cancelling_a_chained_request_leaves_the_one_it_follows() -> None:
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")

    press(assembly, CANCEL_WANTED, {"id": "freight_1-2"})
    ticks(assembly, 8)

    assert ids(assembly, "request_cancelled") == ["freight_1-2"]
    assert ids(assembly, "request_completed") == ["freight_1-1"]


# -- after --------------------------------------------------------------------


def test_a_chained_request_waits_listed_with_no_departure_end() -> None:
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")

    assert ids(assembly, "request_admitted") == ["freight_1-1", "freight_1-2"]
    assert picture(assembly)["requests"][1] == {
        "id": "freight_1-2",
        "train": "freight_1",
        "depart": None,
        "dest": ["yard_e.A"],
        "after": "freight_1-1",
    }


def test_a_chained_request_departs_by_the_end_opposite_the_one_it_came_in_by() -> None:
    """freight_1 comes into `dn_w` through A, so it carries on through B and
    over the crossover, rather than back into the yard it came from."""
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")
    ticks(assembly, 12)

    assert ids(assembly, "request_completed") == ["freight_1-1", "freight_1-2"]
    [chained] = events(assembly.trace, "route_chosen", rid="freight_1-2")
    assert chained["route"][:2] == ["dn_w", "crossover.dn_straight"]


def test_a_chained_request_is_rejected_where_that_end_leads_nowhere() -> None:
    """`yard_e` is terminal: a train that came in through A has no B to carry
    on through, and the request after it is rejected `unreachable` when the
    first arrives."""
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "yard_e.A")
    submit(assembly, "freight_1-2", "freight_1", None, "dn_w.A", after="freight_1-1")
    ticks(assembly, 12)

    assert ids(assembly, "request_completed") == ["freight_1-1"]
    [rejected] = leaves(assembly, "request_rejected")
    assert (rejected["id"], rejected["reason"]) == ("freight_1-2", "unreachable")
    assert listed(assembly) == []


def test_a_chained_request_is_cancelled_where_the_one_it_follows_is_rejected() -> None:
    """freight_1-2 states only the end letter A, so its reachability waits
    for its launch from `dn_w`, whose A end leads back into the terminal
    `yard_w` and never to `up_e.B`: it is rejected there, and the request
    chained after it is cancelled `revoked`."""
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "dn_w.A")
    submit(assembly, "freight_1-2", "freight_1", "A", "up_e.B")
    submit(assembly, "freight_1-3", "freight_1", None, "yard_e.A", after="freight_1-2")
    ticks(assembly, 8)

    [rejected] = leaves(assembly, "request_rejected")
    assert (rejected["id"], rejected["reason"]) == ("freight_1-2", "unreachable")
    [cancelled] = leaves(assembly, "request_cancelled")
    assert (cancelled["id"], cancelled["reason"]) == ("freight_1-3", "revoked")


def test_a_request_after_one_rejected_at_admission_is_cancelled() -> None:
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "up_e.B")
    submit(assembly, "freight_1-2", "freight_1", None, "yard_e.A", after="freight_1-1")

    assert ids(assembly, "request_rejected") == ["freight_1-1"]
    assert ids(assembly, "request_admitted") == ["freight_1-2"]
    [cancelled] = leaves(assembly, "request_cancelled")
    assert (cancelled["id"], cancelled["reason"]) == ("freight_1-2", "revoked")


def test_a_request_after_one_already_arrived_departs_where_that_one_left_it() -> None:
    """A request that stands where it is asked to go completes in the sweep
    that admits it, so a scheduler chaining the next one can be late. That
    request starts the way the first would have."""
    assembly = meet()
    submit(assembly, "freight_1-1", "freight_1", "yard_w.B", "yard_w.B")
    assert ids(assembly, "request_completed") == ["freight_1-1"]

    submit(assembly, "freight_1-2", "freight_1", None, "dn_w.A", after="freight_1-1")
    ticks(assembly, 8)

    assert ids(assembly, "request_completed") == ["freight_1-1", "freight_1-2"]


def test_after_naming_no_request_of_the_train_is_malformed() -> None:
    assembly = meet()
    press(assembly, *power(OFF))
    submit(assembly, "express_2-1", "express_2", "up_e.B", "yard_e.A")

    submit(assembly, "freight_1-1", "freight_1", None, "dn_w.A", after="express_2-1")
    submit(assembly, "freight_1-2", "freight_1", None, "dn_w.A", after="ghost-1")
    press(
        assembly,
        REQUESTS,
        {
            "id": "freight_1-3",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["dn_w.A"],
            "after": "express_2-1",
        },
    )

    assert [
        (line["id"], line["reason"]) for line in leaves(assembly, "request_rejected")
    ] == [
        ("freight_1-1", "malformed"),
        ("freight_1-2", "malformed"),
        ("freight_1-3", "malformed"),
    ]
