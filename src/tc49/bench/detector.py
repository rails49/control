"""A person at the keyboard where the camera will be (#315).

Nothing publishes `tc49/layout/state/device/sensor/<block>.<end>` on a
physical railroad. The detector is a camera that lives outside this repository
and publishes nothing yet, and there is no broker in the loop besides — the
bus is a Python object in one process (SYSTEM.md, *the bus*). So a `move` on
the steel has nothing to complete it, and the first train would cross into a
block the system never hears about.

For the first train a person supplies the readings. A line typed on the input
this is given is published as the row the detector it stands in for would
write:

    C3.A occupied
    C3.B clear

`layout` folds the two ends into `block_occupied` and `block_vacated` exactly
as it folds a camera's ([#288](https://github.com/rails49/control/issues/288)),
and the settling time sees a typed level as it would see a detector's. That is
the whole of the point: nothing downstream knows a person typed it.

**Not a bus contract change.** The topic and the payload are SYSTEM.md's
already and this writes what a detector writes, on the writing role a detector
holds (ADR-0035). **Not a panel gesture** either: the bridge enforces the
topics a page may publish and a device row is not among them (ADR-0034). This
stands in for hardware until a camera publishes, and it is meant to be as easy
to delete as it was to write — one module, one branch of the physical wiring,
and nothing above the layout interface touched.

**A client of the broker, and not an app** (ADR-0059, decision 5). `serve`
below is `tc49 readings`: a process that connects to the broker the railroad
runs on, reads the railroad's layout off the store's HTTP face to know which
block ends there are, and publishes what a person types — the same rows on the
same topic, reaching `layout` from another process now rather than from the
session that used to hold both. It stays in `bench` because what it stands in
for is hardware: a camera on a box of its own is what replaces it, and an app
is not (CLAUDE.md, *Apps*).

Where a camera would exit on nothing but a signal, this ends when its input
does: the whole of its work is that input, so a person pressing Ctrl-D and a
file of readings running out are both the detector being taken away.
"""

import queue
import sys
import threading
from collections.abc import Callable
from typing import TextIO

from tc49.lib.bus import Bus
from tc49.lib.inventory import CLEAR, OCCUPIED, UNKNOWN, device_topic
from tc49.lib.layout import Layout
from tc49.lib.mqtt import MqttBus

SENSOR = "tc49/layout/state/device/sensor"
"""The row a reading goes on, which is `DEVICE_TOPICS`' key for it: this
publishes a detector's row and invents nothing (tested)."""

LEVELS = (OCCUPIED, CLEAR, UNKNOWN)
"""What a person may say a block end reads, and the whole of it: the three
values of `occupancy` (SYSTEM.md, *what the hardware reports back*)."""

ENDS = ("A", "B")
"""The two ends a block has, which is what a sensor is addressed by."""

SHAPE = "<block>.<end> <level>"
"""The line, for the banner and for every refusal: one sensor and what it
reads."""

CLIENT_ID = "tc49-readings"
"""What `tc49 readings` calls itself to the broker, so a person reading the
broker's log finds the keyboard rather than a random string. Nothing in the
contract reads it: a topic has one writing role and no payload says who
published (SYSTEM.md, rule 4)."""

PERIOD_S = 0.1
"""Seconds between turns of the loop below: how long a typed line waits in the
queue the reader thread fills before the thread that publishes takes it. The
railroad's pacing is elsewhere entirely — a level is settled by `layout`
(ADR-0030) — so this only has to be short beside a person's typing."""

BROKER_S = 5.0
"""How long one wait for the broker lasts before it is said again. The wait is
resumed until the connection lands, so this is only how often a person is told
that the readings they are about to type have nowhere to go."""


class HandFed:
    """The detector a person is standing in for: a typed line published as the
    row a camera would write.

    Bound to a **railroad**, because the address is a block end of that
    railroad and a typo at the bench must not look like a detector: a reading
    for a block nothing has is one the dispatcher cannot explain, and an
    unexplained reading holds the run
    ([ADR-0048](docs/adr/0048-an-unexplained-reading-holds-the-run.md)).
    `layout` deliberately does not ask — a row that arrives there has a
    detector behind it, and folding it is that app's work either way — so the
    asking belongs here, at the keyboard, where the answer is a line to
    retype.

    Lines are read on **a thread of its own** and published on the loop's.
    A blocking read is not something the physical branch's loop can await
    without owning a thread it cannot abandon at Ctrl-C, and putting stdin on
    the loop with `connect_read_pipe` would leave the operator's terminal
    non-blocking after the session ended. So the thread does the one thing
    that blocks and hands the line over; `typed()` is what publishes, on the
    thread that drains the bus, which is what keeps a state topic off every
    thread but that one (`lib/inventory.py`, `INBOUND`).
    """

    def __init__(self, bus: Bus, layout: Layout, lines: TextIO, out: TextIO) -> None:
        """`lines` is where a person types them and `out` is where a line that
        is not one is said — the session's own input and banner."""
        self._bus = bus
        self._layout = layout
        self._lines = lines
        self._out = out
        self._typed: queue.SimpleQueue[str] = queue.SimpleQueue()
        # What the reader thread ran into, until a turn says it: an input that
        # cannot be read at all is the one thing that thread has to report,
        # and it reports it the way it hands a line over.
        self._unreadable: str | None = None
        # Set once that thread is finished — the input ended, or could not be
        # read at all — and every line it took is on the queue. A standalone
        # `tc49 readings` ends with its input and reads this; a session's loop
        # is the railroad's and goes on with or without a keyboard, so it does
        # not.
        self.ended = threading.Event()

    def opens(self) -> None:
        """Start reading, which the loop's owner does once it is running.

        A daemon thread, and never joined: at the end of a run it is blocked
        in a read on the session's own input, and the process is ending. A
        line that arrives after that is left in the queue, which is the same
        as one typed a moment later still.
        """
        threading.Thread(target=self._reads, name="detector", daemon=True).start()

    def _reads(self) -> None:
        """The thread: line after line until the input ends, or until it
        cannot be read at all.

        An input that raises is **handed over** like a line rather than said
        here: a session whose input cannot be read is one nobody is typing at
        and goes on driving, and the saying belongs on the turn with
        everything else this writes.
        """
        try:
            while line := self._lines.readline():
                self._typed.put(line)
        except (OSError, ValueError) as unreadable:
            self._unreadable = f"nothing can be read from this session: {unreadable}"
        finally:
            # After the last line is on the queue, so a reader of `ended` that
            # takes one more turn takes everything that was typed.
            self.ended.set()

    def typed(self) -> None:
        """Every line typed since the last turn, published or reported.

        Called on the loop's turn, so a level typed between two of them is
        seen where a camera's would have been: published now, delivered by
        this turn's drain, and settled on a later one.
        """
        trouble, self._unreadable = self._unreadable, None
        if trouble is not None:
            self._report(trouble)
        while True:
            try:
                line = self._typed.get_nowait()
            except queue.Empty:
                return
            refused = self.reads(line)
            if refused is not None:
                self._report(refused)

    def reads(self, line: str) -> str | None:
        """One line published as a reading: `None` where it went, or what was
        wrong with it in words.

        Reported and never raised, and the session runs on either way: this is
        a person typing beside a running railroad, and a typo is not a reason
        to stop one.

        The end letter and the level are taken in either case and the block
        name is not, which is the difference between a closed vocabulary and
        a name: a block is spelled the way the drawing spells it, while the
        two ends and the three levels are words this reads back to the person
        anyway. A blank line is a person pressing return and is nothing at
        all.
        """
        fields = line.split()
        if not fields:
            return None
        if len(fields) != 2:
            return f"'{line.strip()}' is not a reading — write it {SHAPE}"
        sensor, level = fields
        block, dot, end = sensor.partition(".")
        if not dot or not block:
            return f"'{sensor}' is no block end — a sensor is addressed <block>.<end>"
        if end.upper() not in ENDS:
            return f"'{sensor}' is no block end — a block has two, {' and '.join(ENDS)}"
        if block not in self._layout.blocks:
            return f"no block '{block}' on {self._layout.name}"
        if level.lower() not in LEVELS:
            return f"'{level}' is no level — {', '.join(LEVELS[:-1])} or {LEVELS[-1]}"
        at = f"{block}.{end.upper()}"
        self._bus.publish(
            device_topic(SENSOR, at), {"addr": at, "occupancy": level.lower()}
        )
        return None

    def _report(self, what: str) -> None:
        self._out.write(f"  {what}\n")
        self._out.flush()


def to_stderr(line: str) -> None:
    """The log: what is being waited for, and what came up. What a refusal
    says goes where the person typed it instead (`_report`), and `lib` says
    its own piece under its own prefix (`documents:`, `mqtt:`)."""
    print(f"readings: {line}", file=sys.stderr, flush=True)


def serve(
    bus: MqttBus,
    layout: Layout,
    lines: TextIO,
    out: TextIO,
    stop: threading.Event,
    period_s: float = PERIOD_S,
    log: Callable[[str], None] = to_stderr,
) -> None:
    """`tc49 readings`: the typed readings as a client of the broker.

    The broker first and blocking, because a publish made to a broker that is
    not there is dropped rather than queued (ADR-0050) — a reading typed into
    nothing would be a person watching the railroad ignore them, which is the
    one thing a stand-in for a detector must not do. The layout is the
    caller's, read off the store before this is called, and it is here for one
    reason only: a typo at the keyboard must not look like a detector
    (ADR-0048), which is what `reads` checks it against.

    Nothing is drained. This publishes and reads nothing — a detector holds a
    writing role and no reading one (ADR-0035) — so the turn is the queue the
    reader thread fills and no other.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. A person ends it by typing Ctrl-D, which is the input ending, or
    Ctrl-C, which raises where the process stands and is let out by the
    command.
    """
    if not _connected(bus, stop, log):
        return
    detector = HandFed(bus, layout, lines, out)
    detector.opens()
    log(
        f"up on '{layout.name}': type '{SHAPE}' —"
        f" {', '.join(LEVELS[:-1])} or {LEVELS[-1]}"
    )
    while not stop.is_set() and not detector.ended.is_set():
        detector.typed()
        stop.wait(period_s)
    # One turn after the reader thread finished: the line typed last is on the
    # queue by the time `ended` is set, and it is as much a reading as any
    # other. It publishes what a stop found waiting too, which is the same
    # line typed a moment earlier.
    detector.typed()
    if detector.ended.is_set():
        log("the input ended; nothing more will be typed")


def _connected(bus: MqttBus, stop: threading.Event, log: Callable[[str], None]) -> bool:
    """Wait for the broker, saying so, until it is there or the caller has
    stopped. A keyboard whose broker is missing has nowhere to publish, and
    reading the lines meanwhile would only be collecting readings that are
    stale by the time there is anywhere to put them."""
    while not stop.is_set():
        if bus.wait_connected(BROKER_S):
            return True
        log("waiting for the broker")
    return False
