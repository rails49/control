"""Direct unit tests for safe() on hand-built states (SAFETY.md)."""

from tc49.dispatcher.safety import safe


def test_empty_dispatch_is_trivially_safe() -> None:
    assert safe(cur={}, rem={}, idle=[], held={})


def test_mid_transit_cur_is_the_far_block() -> None:
    # u is crossing X -> Y, and Y is its destination (rem empty). Its origin
    # X counts as free — the release is guaranteed by Lemma 1 — so t, whose
    # route needs X, is feasible. Counting X as held would park u's dest on
    # X and wedge t.
    assert safe(
        cur={"u": "Y", "t": "A"},
        rem={"u": [], "t": ["X", "B"]},
        idle=[],
        held={"u": [], "t": []},
    )


def test_idle_trains_are_permanent_obstacles() -> None:
    assert not safe(cur={"t": "A"}, rem={"t": ["X", "B"]}, idle=["X"], held={"t": []})
    assert safe(cur={"t": "A"}, rem={"t": ["X", "B"]}, idle=["C"], held={"t": []})


def test_finishers_park_on_their_destination() -> None:
    # Two active trains committed to the same destination block: neither
    # ordering works, because the first to finish parks on D.
    assert not safe(
        cur={"t1": "A", "t2": "B"},
        rem={"t1": ["D"], "t2": ["D"]},
        idle=[],
        held={"t1": [], "t2": []},
    )
    # Distinct destinations order fine.
    assert safe(
        cur={"t1": "A", "t2": "B"},
        rem={"t1": ["D"], "t2": ["E"]},
        idle=[],
        held={"t1": [], "t2": []},
    )


def test_self_intersecting_routes_pass() -> None:
    # A route may revisit a block it released earlier; blocks are checked
    # against other trains only.
    assert safe(cur={"t": "A"}, rem={"t": ["B", "A", "C"]}, idle=[], held={"t": []})


def test_frozen_active_trains_block_a_route() -> None:
    # u frozen in X blocks t, unless u can be ordered first and its parked
    # destination clears the way.
    assert not safe(
        cur={"t": "A", "u": "X"},
        rem={"t": ["X", "B"], "u": ["A"]},
        idle=[],
        held={"t": [], "u": []},
    )
    assert safe(
        cur={"t": "A", "u": "X"},
        rem={"t": ["X", "B"], "u": ["C"]},
        idle=[],
        held={"t": [], "u": []},
    )


def test_a_held_block_obstructs_another_train() -> None:
    # u stands in X and has already locked Y ahead of it; t stands in A and
    # needs Y. Neither ordering works: u cannot go first, because t sits on A
    # and u's route needs it, and t cannot go first, because Y is u's.
    assert not safe(
        cur={"t": "A", "u": "X"},
        rem={"t": ["Y", "B"], "u": ["Y", "A"]},
        idle=[],
        held={"t": [], "u": ["Y"]},
    )
    # The same state with nothing held ahead is safe: t runs through Y, parks
    # on B, and u follows. Holding Y is the whole difference, and it is the
    # difference the check could not see before.
    assert safe(
        cur={"t": "A", "u": "X"},
        rem={"t": ["Y", "B"], "u": ["Y", "A"]},
        idle=[],
        held={"t": [], "u": []},
    )


def test_a_train_is_not_obstructed_by_what_it_holds() -> None:
    # t has locked the rest of its own route. A held block obstructs everyone
    # but its holder, exactly as cur does.
    assert safe(cur={"t": "A"}, rem={"t": ["Y", "B"]}, idle=[], held={"t": ["Y", "B"]})
