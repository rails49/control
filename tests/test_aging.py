"""The aging rule on the pending scan (#34).

The scan order is the policy seam DISPATCH.md names: aging only reorders
which safe launches are tried first, so everything here is queue order —
the safety argument is untouched and stays covered by the properties.
"""

from tc49.dispatcher.dispatch import Request, aging_order


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
