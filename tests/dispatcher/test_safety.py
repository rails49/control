"""Direct unit tests for safe() on hand-built states (SAFETY.md)."""

from tc49.dispatcher.safety import finishable, safe


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


def test_all_finish_when_the_state_is_safe() -> None:
    assert finishable(
        cur={"t": "A", "u": "X"},
        rem={"t": ["X", "B"], "u": ["C"]},
        idle=[],
        held={"t": [], "u": []},
    ) == {"t", "u"}


def test_a_train_crossing_an_obstacle_is_left_out() -> None:
    assert finishable(
        cur={"t": "X", "u": "P"},
        rem={"t": ["Y"], "u": ["Q"]},
        idle=["Y"],
        held={"t": [], "u": []},
    ) == {"u"}


def test_those_left_out_block_as_frozen_trains_do() -> None:
    # t cannot finish. u needs the block t stands in and v the block t holds,
    # so neither can either, and w is clear of it all.
    assert finishable(
        cur={"t": "X", "u": "P", "v": "R", "w": "M"},
        rem={"t": ["H", "S"], "u": ["X"], "v": ["H"], "w": ["N"]},
        idle=["S"],
        held={"t": ["H"], "u": [], "v": [], "w": []},
    ) == {"w"}


def test_a_circular_wait_is_left_out_whole() -> None:
    assert finishable(
        cur={"t": "A", "u": "B", "v": "M"},
        rem={"t": ["B"], "u": ["A"], "v": ["N"]},
        idle=[],
        held={"t": [], "u": [], "v": []},
    ) == {"v"}


def test_a_tie_goes_to_the_first_set_in_sorted_order() -> None:
    assert finishable(
        cur={"u": "B", "t": "A"},
        rem={"u": ["D"], "t": ["D"]},
        idle=[],
        held={"t": [], "u": []},
    ) == {"t"}


def test_a_larger_set_beats_an_earlier_smaller_one() -> None:
    # t ends on D, which u and v cross, and crosses E and F, where they end, so
    # t finishes with neither. {t} sorts first, and {u, v} is larger.
    assert finishable(
        cur={"t": "A", "u": "B", "v": "C"},
        rem={"t": ["E", "F", "D"], "u": ["D", "E"], "v": ["D", "F"]},
        idle=[],
        held={"t": [], "u": [], "v": []},
    ) == {"u", "v"}


def test_nobody_can_finish() -> None:
    assert (
        finishable(cur={"t": "A"}, rem={"t": ["X"]}, idle=["X"], held={"t": []})
        == frozenset()
    )


def test_no_active_trains() -> None:
    assert finishable(cur={}, rem={}, idle=[], held={}) == frozenset()
