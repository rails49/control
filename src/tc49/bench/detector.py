"""A person at the keyboard where the camera will be (#315).

Nothing publishes `tc49/layout/state/device/sensor/<block>.<end>` on a
physical railroad. The detector is a camera that lives outside this repository
and publishes nothing yet, and there is no broker in the loop besides — the
bus is a Python object in one process (SYSTEM.md, *the bus*). So a `move` on
the steel has nothing to complete it, and the first train would cross into a
block the system never hears about.

For the first train a person supplies the readings. While a session runs on
the physical binding, a line typed on its input is published as the row the
detector it stands in for would write:

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
"""

import queue
import threading
from typing import TextIO

from tc49.lib.bus import Bus
from tc49.lib.inventory import CLEAR, OCCUPIED, UNKNOWN, device_topic
from tc49.lib.layout import Layout

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
