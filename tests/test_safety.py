"""Direct unit tests for safe() on hand-built states (SAFETY.md)."""

from tc49.safety import safe


def test_empty_dispatch_is_trivially_safe() -> None:
    assert safe(cur={}, rem={}, idle=[])


def test_mid_transit_cur_is_the_far_block() -> None:
    # u is crossing X -> Y, and Y is its destination (rem empty). Its origin
    # X counts as free — the release is guaranteed by Lemma 1 — so t, whose
    # route needs X, is feasible. Counting X as held would park u's dest on
    # X and wedge t.
    assert safe(cur={"u": "Y", "t": "A"}, rem={"u": [], "t": ["X", "B"]}, idle=[])


def test_idle_trains_are_permanent_obstacles() -> None:
    assert not safe(cur={"t": "A"}, rem={"t": ["X", "B"]}, idle=["X"])
    assert safe(cur={"t": "A"}, rem={"t": ["X", "B"]}, idle=["C"])


def test_finishers_park_on_their_destination() -> None:
    # Two active trains committed to the same destination block: neither
    # ordering works, because the first to finish parks on D.
    assert not safe(cur={"t1": "A", "t2": "B"}, rem={"t1": ["D"], "t2": ["D"]}, idle=[])
    # Distinct destinations order fine.
    assert safe(cur={"t1": "A", "t2": "B"}, rem={"t1": ["D"], "t2": ["E"]}, idle=[])


def test_self_intersecting_routes_pass() -> None:
    # A route may revisit a block it released earlier; blocks are checked
    # against other trains only.
    assert safe(cur={"t": "A"}, rem={"t": ["B", "A", "C"]}, idle=[])


def test_frozen_active_trains_block_a_route() -> None:
    # u frozen in X blocks t, unless u can be ordered first and its parked
    # destination clears the way.
    assert not safe(
        cur={"t": "A", "u": "X"}, rem={"t": ["X", "B"], "u": ["A"]}, idle=[]
    )
    assert safe(cur={"t": "A", "u": "X"}, rem={"t": ["X", "B"], "u": ["C"]}, idle=[])
