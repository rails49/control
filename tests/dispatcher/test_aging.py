"""The aging rule on the pending scan (#34).

The scan order is the policy seam DISPATCH.md names: aging only reorders
which safe launches are tried first, so everything here is queue order —
the safety argument is untouched and stays covered by the properties.
"""

from dataclasses import replace

from tc49.bench.runner import assemble_live
from tc49.dispatcher.dispatch import Request, aging_order
from tests.harness import RUN_WANTED, events, load, minted, press

REQUEST_WANTED = "tc49/schedule/request_wanted"


def req(rid: str, seq: int, refusals: int) -> Request:
    return Request(rid, rid, "A", ("east.A",), seq, 0, refusals)


def test_more_refused_request_outranks_an_older_fresher_one() -> None:
    # The widened-saturation wedge in miniature: the starved through-request
    # (young seq, many refusals) must be tried before the fresher final park
    # (old seq, few refusals) when the slot they contend for frees.
    final_park = req("t1-3", seq=2, refusals=1)
    starved = req("t4-2", seq=10, refusals=5)
    assert sorted([final_park, starved], key=aging_order) == [starved, final_park]


def test_equal_refusals_preserve_admission_order() -> None:
    # With nothing starved the scan is exactly the old oldest-first order,
    # so aging is invisible until a refusal separates two requests.
    a, b, c = req("a", 0, 0), req("b", 1, 0), req("c", 2, 0)
    assert sorted([c, a, b], key=aging_order) == [a, b, c]


def test_a_higher_priority_outranks_an_older_more_refused_one() -> None:
    # Strict across levels (ADR-0045): aging orders within a priority level
    # and gives way to priority between them.
    freight = Request("f", "f", "A", ("east.A",), 0, 0, 5, priority=(0, 2))
    express = Request("e", "e", "A", ("east.A",), 9, 0, 0, priority=(0, 1))
    assert sorted([freight, express], key=aging_order) == [express, freight]


def test_a_released_run_tries_the_higher_priority_train_first() -> None:
    # Admitted in the order freight_1, express_2 while held, as in
    # test_hold.py, so admission order alone would try freight_1 first. On
    # this railroad express_2 cannot leave while freight_1 stands where it
    # does: the higher is tried first and refused, and the lower still goes.
    layout, roster, scenario = load("crossover-yard/meet")
    ranked = replace(
        roster,
        trains={
            name: replace(train, priority=1 if name == "express_2" else 2)
            for name, train in roster.trains.items()
        },
    )
    assembly = assemble_live(layout, ranked, scenario.trains)
    press(assembly, RUN_WANTED, {"run": "held"})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    press(assembly, REQUEST_WANTED, {"train": "express_2", "dest": ["yard_w.B"]})
    press(assembly, RUN_WANTED, {"run": "running"})
    decided = [
        (line["event"], line["id"])
        for line in events(assembly.trace)
        if line["event"] in ("route_chosen", "grant_refused")
    ]
    assert decided == [
        ("grant_refused", minted(assembly, "express_2")),
        ("route_chosen", minted(assembly, "freight_1")),
    ]
