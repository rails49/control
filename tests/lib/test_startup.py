"""`Alive`, an app saying it is up, held to its rate without a broker.

The apps' own suites hold each one to it against a real broker and wall time
(#1113); this holds the one rule they share on a clock the test turns.
"""

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.startup import Alive

TOPIC = "tc49/schedule/scheduler_alive_confirmed"


def test_it_is_said_at_once_and_then_once_a_second_whatever_the_turns() -> None:
    """Said on the first turn, so a page hears an app as soon as it is built,
    and then once a second by the monotonic clock, however often the loop
    turns in between: a turn every 10 ms is not a hundred frames a second."""
    bus = InProcessBus(Clock())
    heard: list[Payload] = []
    bus.subscribe(TOPIC, lambda _topic, payload: heard.append(payload))
    now = [100.0]
    alive = Alive(bus, TOPIC, monotonic=lambda: now[0])

    for _turn in range(350):  # 3.5 s of turns 10 ms apart
        alive.say()
        bus.drain()
        now[0] += 0.01

    assert heard == [{}] * 4
