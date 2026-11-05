"""A request cancelled while its train runs on to the far sensor, with the move
back out held, ends as the train stops (#1176).

`layout`, the scheduler, the dispatcher and the driver on a line of four blocks,
with `tc49.lib.invariants` held throughout. The train stays at its far sensor,
and the move it was to make next never starts.
"""

from tests.layout.railroad import heard, speeds
from tests.system.test_far_sensor_stop import TRAIN, Railroad

CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
REQUEST_CANCELLED = "tc49/dispatch/request_cancelled"
REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
REVERSAL_WANTED = "tc49/schedule/reversal_wanted"
MOVE_WITHDRAWN = "tc49/layout/move_withdrawn"
ALLOCATION = "tc49/dispatch/state/allocation"


def test_a_request_cancelled_with_its_move_held_is_revoked_at_the_far_sensor() -> None:
    railroad = Railroad()
    submitted = heard(railroad.bus, REQUEST_SUBMITTED)
    cancelled = heard(railroad.bus, REQUEST_CANCELLED)
    answered = heard(railroad.bus, MOVE_WITHDRAWN)
    railroad.requests("b.A")
    railroad.read("b.A")
    railroad.read("a.B", "clear")
    railroad.read("b.A", "clear")
    assert len(railroad.completed) == 1
    assert railroad.stops() == 0

    # Its last request over and the train still running on to `b.B`: the next
    # goes back out through `b.A`, and is held for the arrival.
    railroad.bus.publish(REVERSAL_WANTED, {"train": TRAIN})
    railroad.bus.drain()
    railroad.requests("a.B")
    [(_topic, back)] = railroad.granted[1:]
    assert back["into"] == "a"
    assert railroad.app.position[TRAIN] == "b"
    assert railroad.stops() == 0
    assert back["transit"] in railroad.bus.last_values[ALLOCATION]["occupied"][TRAIN]

    _topic, request = submitted[-1]
    railroad.bus.publish(CANCEL_WANTED, {"id": request["id"]})
    railroad.bus.drain()
    assert answered == []
    assert cancelled == []
    assert railroad.stops() == 0

    running = len(railroad.written)
    railroad.read("b.B")

    # The arrival's `0.0`, and `_withdraw`'s second one.
    assert {speed for _addr, speed in speeds(railroad.written[running:])} == {0.0}
    assert [payload["into"] for _topic, payload in answered] == ["a"]
    assert [payload["reason"] for _topic, payload in cancelled] == ["revoked"]
    assert railroad.app.position[TRAIN] == "b"
    assert railroad.moving() is False
    picture = railroad.bus.last_values[ALLOCATION]
    assert picture["locks"] == {"b": TRAIN}
    assert picture["occupied"] == {TRAIN: ["b"]}
    assert picture["trains"] == {TRAIN: "b"}
