"""dccex: the translator between the device vocabulary and the command station.

The first of the thin apps that hang under `layout` (ADR-0043). Above it the
bus carries the **device vocabulary** — what each device should do, and what
each is observed to do — and below it is one TCP connection to `dccex-usb`,
which owns the command station's serial device and serves it on port 2560 so
that JMRI and hand-held throttles share the same command station
(docs/dccex_usb/README.md). Not the USB device: `dccex-usb` owns that, and
this app is one client of the port beside the others.

**The boundary this app exists to hold.** Every other component is oblivious
to what powers the layout, and nothing above the layout interface expects
this command station or any other — they are one family of devices among
many. The `<…>` syntax is this app's private business: it appears on no bus
topic, in no other package and in no normative document, and `docs/dccex/`
is the only page in the repository that writes it down. A different command
station gets a different translator, or reaches the system through JMRI, and
nothing else moves.

*Subscribes* `tc49/layout/state/wanted/#`. *Publishes*
`tc49/layout/state/device/track` and `tc49/layout/state/device/link/dccex`.

**It acts on an address only if it recognises it**, and there is no ownership
table anywhere: a point or signal address whose first level is `dccex`, and
any traction or function address, which is bare because a decoder answers to
the number it was programmed with and traction cannot be split across systems
(ADR-0045). An address nothing answers to does no harm, as a packet nobody
picks up does.

**On connect it applies the retained desired state and does nothing else.**
The desired values are the whole picture, so there is no handshake and no
session state to agree: whatever `layout` last wanted is waiting on those
topics, and applying it is the whole of coming up. The track row goes first,
so nothing is commanded onto dead rails and a release's zeros land before the
speeds rather than over them.

**Powering on sends the startup file, if there is one.** `startup` names a
file of raw station commands, one per line, sent in order straight after the
track-on command; it is where a person writes the trip current each of this
railroad's power districts really takes, in the station's own language, and
the only place those values appear. A power district is a hardware fact that
reaches no bus topic (#217), and the file is not parsed beyond blank and
comment, so this app has no vocabulary for what is in it. Failing to read it
is logged and powers on anyway: a railroad coming up at the firmware's low
default trips early, which is safe and visible, where refusing to power on
over a missing file is neither (ADR-0050).

Three rules are not a row of the mapping table, and each is a way a train
could otherwise move on its own:

**The stop must latch.** `stopped` is the station's emergency-stop **lock**
and not its one-shot stop. A one-shot that any throttle on the same port can
drive away from would make the observed power an echo of a command rather
than an observation, and a lie the moment somebody picks up a hand-held
throttle. The lock is also queryable, which is why a restart reads it back
instead of remembering it.

**Clearing a stop is zero-then-release.** Under the lock the station keeps
every locomotive's pre-lock speed and resumes it on release, so a bare
release restarts every train at the speed it was doing when somebody hit
stop. Every locomotive this app has ever commanded is sent zero **first**.
Nothing in the software is in the path of those resumed packets, which makes
this the one remaining way a train moves without being asked.

**An overload is polled for.** A district that trips is not broadcast on TCP
— the station cuts it and says so on its USB diagnostics only — so this app
asks for the status on a cadence of its own, and `device/track` telling the
truth does not depend on a person noticing.

**A clean exit stands the railroad down**, `shutdown()`: zero to every
locomotive this app has commanded, then the track off. The process ending is
not by itself an instruction to the railroad — the station goes on running
whatever it was last told — and a session that exits over a rolling
locomotive leaves it rolling, which is not recoverable the way switching the
power back on is. Whoever constructs this app calls it before letting the
loop go (`bench/runner.py`).

**No `device/point` is ever published.** This railroad's turnouts have no
feedback and the station's answer to a throw is one it faked (ADR-0022), so
the row stays empty: a faked observation is worse than silence (ADR-0050).

**`device/link`** is `up` while the connection is open and the station has
answered, `down` otherwise, with `detail` carrying what a person would want
to read. That is where the physical link becomes visible at runtime, which is
where verifying it belongs — not in a gate that would need a powered layout
to pass.

The framing and the mapping are pure and live in `replies` and `commands`;
what is here is the connection and the state that a connection is made of.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple

from tc49.dccex import commands, replies
from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import OFF, ON, STOPPED, device_topic, split_device
from tc49.lib.payload import (
    commanded_power,
    desired_aspect,
    desired_function,
    desired_position,
    desired_speed,
)

_log = logging.getLogger(__name__)

SYSTEM = "dccex"
"""The first level of a point or signal address this app answers to, and the
address `device/link` carries: a hardware system names itself once."""

HOST = "dccex-usb"
PORT = 2560

WANTED = "tc49/layout/state/wanted/#"

WANTED_TRACTION = "tc49/layout/state/wanted/traction"
WANTED_FUNCTION = "tc49/layout/state/wanted/function"
WANTED_POINT = "tc49/layout/state/wanted/point"
WANTED_SIGNAL = "tc49/layout/state/wanted/signal"
WANTED_TRACK = "tc49/layout/state/wanted/track"

DEVICE_TRACK = "tc49/layout/state/device/track"
DEVICE_LINK = "tc49/layout/state/device/link"

UP = "up"
DOWN = "down"

POLL_S = 1.0
"""How often the station is asked what it is doing, which bounds how long a
tripped district reads as live and how long a fresh connection reads as
`down`. A second is far inside what a person recovering from either would
notice, and the two questions are two short lines on a port that carries the
whole railroad's traffic."""

FIRST_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0

READ_SIZE = 4096


Connect = Callable[[], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]
"""How a connection is made, injected so a test drives a socket pair rather
than hardware: nothing in the gate may need a command station."""


class Wanted(NamedTuple):
    """One desired value as this app holds it: the row and the address, which
    are the topic's, and the payload that arrived on it. Kept rather than the
    bytes it becomes, because what the track row is worth depends on whether
    a stop is latched at the moment it is applied."""

    row: str
    address: str
    payload: Payload


class DccEx:
    """The translator, on the bus and on one connection to `dccex-usb`.

    `run()` is the whole of the connection: it connects, applies the retained
    desired state, reads what the station says until the link goes, and
    reconnects with backoff, publishing `device/link: down` for the whole
    outage. The bus half needs none of it — a desired value that arrives
    while the link is down is remembered and applied on the next connect,
    which is the same thing that happens to the retained value at startup.
    """

    def __init__(
        self,
        bus: Bus,
        host: str = HOST,
        port: int = PORT,
        *,
        connect: Connect | None = None,
        startup: Path | None = None,
        poll_s: float = POLL_S,
        first_backoff_s: float = FIRST_BACKOFF_S,
        max_backoff_s: float = MAX_BACKOFF_S,
    ) -> None:
        self._bus = bus
        self._where = f"{host}:{port}"
        self._connect: Connect = connect or (
            lambda: asyncio.open_connection(host, port)
        )
        self._startup = startup
        self._poll_s = poll_s
        self._first_backoff_s = first_backoff_s
        self._max_backoff_s = max_backoff_s
        self._writer: asyncio.StreamWriter | None = None
        # The desired picture, one entry per topic in the order each topic
        # was first heard: what a connection is handed.
        self._wanted: dict[str, Wanted] = {}
        # Every locomotive this app has commanded, in that order — what a
        # release sends zero to. The link does not outlive it: the station
        # keeps a slot per locomotive and resumes it, so one commanded before
        # an outage is one that resumes after it.
        self._commanded: dict[str, None] = {}
        # What the station says about itself, and forgotten with the link:
        # an outage is not an observation, and what cannot be read may not be
        # called good (#181).
        self._answered = False
        self._tracks: dict[str, bool] = {}
        self._every: bool | None = None
        self._paused = False
        # Our own stop, which the link *does* outlive: forgetting it would
        # release a lock without sending the zeros first, and an extra set of
        # zeros costs nothing (ADR-0050).
        self._latched = False
        # Whether this app has switched this station's track on, which is
        # what makes the startup file a transition rather than a level.
        self._powered_on = False
        # What was last said on each of the two rows this app writes.
        self._track = ""
        self._link: tuple[bool, str] | None = None
        # The railroad is dark and the station unreached, which is what is
        # true before anything is connected, and a client joining now is
        # served that rather than an absence (ADR-0032).
        self._publish_link(False, f"not connected to {self._where}")
        self._publish_track()
        bus.subscribe(WANTED, self._on_wanted)

    # -- the bus: what the hardware should do --------------------------------

    def _on_wanted(self, topic: str, payload: Payload) -> None:
        """One desired value, remembered and — if the link is up — applied.

        The row and the address come from the **topic**, which is where a
        device topic states them; the payload repeats the address so a trace
        line reads on its own, and a repetition is not a second authority.

        A value that cannot be turned into a message is not remembered
        either: it is dropped whole, so a connect does not replay something
        that sent nothing when it arrived. Dropped silently and to the trace,
        the frame being on it by virtue of having been published — this app
        answers nothing, so a refusal would have nowhere to go (ADR-0034).
        """
        split = split_device(topic)
        if split is None:
            return
        row, address = split
        if not self._recognises(row, address):
            return
        wanted = Wanted(row, address, payload)
        if _built(wanted) is None:
            return
        self._wanted[topic] = wanted
        if self._writer is not None:
            self._act(wanted)

    def _recognises(self, row: str, address: str) -> bool:
        """Whether this app answers for the address, which is the whole of
        what it decides for itself. There is no ownership table: a translator
        recognises its own addresses and everything else is somebody's or
        nobody's, and an address nobody answers to does no harm.

        The two address shapes differ and the difference is physical. Traction
        and function are **bare** — a decoder answers to its number whoever
        sends the packet — so every one of them is this app's while it is the
        only thing driving track. A point or signal names its system first,
        fixed wiring being splittable across systems, so those are this app's
        only under `dccex`.
        """
        levels = address.split("/")
        if row == WANTED_TRACK:
            return True
        if row == WANTED_TRACTION:
            return len(levels) == 1 and bool(address)
        if row == WANTED_FUNCTION:
            return len(levels) == 2 and all(levels)
        if row in (WANTED_POINT, WANTED_SIGNAL):
            return len(levels) == 2 and levels[0] == SYSTEM and bool(levels[1])
        return False

    def _act(self, wanted: Wanted) -> None:
        """Send what one desired value asks of the station."""
        if wanted.row == WANTED_TRACK:
            self._act_track(wanted.payload)
            return
        message = _built(wanted)
        if message is None:
            return
        if wanted.row == WANTED_TRACTION:
            self._commanded[wanted.address] = None
        self._send(message)

    def _act_track(self, payload: Payload) -> None:
        """The power, the release that has to come before it, and the startup
        file that follows it.

        `on` while a stop may be latched is the dangerous transition and the
        only one with a rule: the station resumes every locomotive at the
        speed it held when the lock went on, so each is sent zero and only
        then is the lock released. "May be latched" is either the lock this
        app commanded or the lock the station has reported, because the two
        can disagree for one round trip and releasing without the zeros is
        the failure that matters. An unnecessary set of zeros stops trains
        that were already standing.

        The startup file goes **after** the track-on command and on every
        transition into `on` rather than at every `on`: a second `on` over
        rails that are already live asks the station for nothing new, and any
        other word — `off` or the lock — arms the next one. A link that goes
        takes the memory with it too, because the station on the far end of
        the next one may have restarted, and one that has forgotten its trip
        currents runs at the firmware's default until somebody notices.
        """
        power = commanded_power(payload)
        if power is None:
            return
        if power == ON and (self._latched or self._paused):
            for addr in self._commanded:
                self._send(commands.traction(addr, 0.0))
            self._send(commands.RELEASE)
            self._latched = False
        self._send(commands.track(power))
        if power == ON and not self._powered_on:
            self._send_startup()
        self._powered_on = power == ON
        if power == STOPPED:
            self._latched = True

    def _send_startup(self) -> None:
        """The startup file, read now and sent line by line.

        Read at the transition and not once at startup, so that editing the
        file and powering the railroad off and on is the whole of changing a
        trip current — there is no process to restart, and the values a
        person is adjusting are ones they adjust with the railroad in front
        of them.

        A file that is missing or cannot be read is logged and nothing else:
        the power-on goes ahead, because a railroad that refuses to come up
        over a configuration file is worse than one at whatever trip current
        the firmware defaults to (ADR-0050). What that default is belongs to
        the firmware and not here.
        """
        path = self._startup
        if path is None:
            return
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError) as unreadable:
            _log.warning("startup file %s not sent: %s", path, unreadable)
            return
        for message in commands.startup(text):
            self._send(message)

    def _applied(self) -> list[Wanted]:
        """The desired picture in the order a fresh connection is handed it:
        the track row first, then every other in the order the topics were
        first heard.

        Track first because the two things it can do have to happen before
        anything else does — power reaches the rails before a turnout is
        asked to throw, and a release's zeros land before the speeds that
        follow them rather than over the top of them.
        """
        held = list(self._wanted.values())
        return [w for w in held if w.row == WANTED_TRACK] + [
            w for w in held if w.row != WANTED_TRACK
        ]

    # -- the link: what the hardware reports ---------------------------------

    async def run(self) -> None:
        """Keep the link to the station, until cancelled."""
        backoff = self._first_backoff_s
        while True:
            try:
                reader, writer = await self._connect()
            except OSError as away:
                self._publish_link(False, f"connecting to {self._where}: {away}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_s)
                continue
            spoke = await self._session(reader, writer)
            # Opening is not proof the station is there. A session that ended
            # without a word keeps the backoff it was reached with, so a port
            # that accepts and drops is not a hot loop.
            if spoke:
                backoff = self._first_backoff_s
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._max_backoff_s)

    async def shutdown(self) -> None:
        """Stand the railroad down: zero to every locomotive this app has
        commanded, then the track off.

        The zeros come first and are the same zeros a release sends, for the
        same reason: the station keeps a speed per locomotive and resumes it,
        so a slot left holding one is a train that rolls again the moment
        somebody powers the rails. Cutting the supply over a held speed only
        postpones the motion.

        Sent on whatever link is open and nothing at all where none is — a
        railroad this app cannot reach is one it was not driving — and
        awaited out, because the next thing to happen is the process ending
        and a buffer nobody flushed is a command nobody sent.
        """
        for addr in self._commanded:
            self._send(commands.traction(addr, 0.0))
        self._send(commands.track(OFF))
        writer = self._writer
        if writer is not None:
            with contextlib.suppress(OSError):
                await writer.drain()

    async def _session(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> bool:
        """One connection, from the desired state going out to the link
        going down. Says whether the station spoke at all."""
        self._writer = writer
        for wanted in self._applied():
            self._act(wanted)
        polling = asyncio.create_task(self._poll())
        try:
            await self._listen(reader)
        finally:
            polling.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling
            self._writer = None
            spoke = self._answered
            self._forget()
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            self._publish_link(False, f"the link to {self._where} closed")
            self._publish_track()
        return spoke

    async def _listen(self, reader: asyncio.StreamReader) -> None:
        """Read the station until it stops talking to us."""
        buffered = b""
        try:
            while True:
                arrived = await reader.read(READ_SIZE)
                if not arrived:
                    return
                buffered, whole = replies.messages(buffered, arrived)
                for message in whole:
                    self._heard(message)
        except (ConnectionError, OSError):
            return

    async def _poll(self) -> None:
        """Ask the station what it is doing, for as long as the link lasts.

        The first question waits out the interval rather than going with the
        desired state: a connect applies that and nothing else, and a status
        the station volunteers on being commanded arrives sooner than a poll
        would anyway.
        """
        while True:
            await asyncio.sleep(self._poll_s)
            self._send(commands.STATUS)
            self._send(commands.LOCK_QUERY)

    def _heard(self, message: bytes) -> None:
        """One whole message from the station: the link is up, and the two
        facts this app reads may have moved. Everything else on the port is
        another client's conversation and is passed over."""
        if not self._answered:
            self._answered = True
            self._publish_link(True, f"connected to {self._where}")
        told = replies.reply(message)
        if isinstance(told, replies.Power):
            if told.track:
                self._tracks[told.track] = told.on
            else:
                # The line naming no track is sent only when every one of
                # them is on, or none is, so it says the same of each.
                self._every = told.on
                self._tracks = {name: told.on for name in self._tracks}
        elif isinstance(told, replies.Lock):
            self._paused = told.locked
            if not told.locked:
                # The station says the lock is off, so ours is discharged and
                # the next `on` needs no release.
                self._latched = False
        self._publish_track()

    def _forget(self) -> None:
        """Let go of everything the station told us, and of having powered
        it on, the link having gone.

        What cannot be read is not what was last read: a district that
        tripped while we were away, or a stop somebody cleared by hand, would
        otherwise stand as an observation nobody made. The power-on is the
        same kind of staleness pointing the other way — the station on the
        next link may be one that has just come up — so the next `on` sends
        the startup file again rather than assume the last one took."""
        self._answered = False
        self._tracks.clear()
        self._every = None
        self._paused = False
        self._powered_on = False

    def _send(self, message: bytes) -> None:
        """One whole message to the station, or nothing at all because the
        link is down. Dropped and never queued: a command is honoured now or
        ignored, and the desired value is held for the next connect, which is
        where a picture is restored rather than a backlog replayed."""
        writer = self._writer
        if writer is not None:
            writer.write(message)

    # -- the bus: what the hardware is observed to do ------------------------

    def _observed(self) -> str:
        """The power this app can say it sees, folded from what the station
        has reported.

        `on` only where every track it named is on: the digit is `1` for a
        track that is fully on and `0` both for one that has tripped and for
        one that is powered but watching a rising current, so anything else
        is `off`. A station that has said nothing reads `off` too, which is
        the direction a state topic must fail in (#181) — a supply that
        cannot be read is not one a train may move over.

        `stopped` is the station's own report of its lock and never this
        app's memory of having commanded one, which is what keeps the row an
        observation. It reaches here only over live rails, an emergency stop
        being every locomotive told to stand with the track still on.
        """
        if not self._answered:
            return OFF
        if self._tracks:
            powered = all(self._tracks.values())
        else:
            powered = self._every is True
        if not powered:
            return OFF
        return STOPPED if self._paused else ON

    def _publish_track(self) -> None:
        """The supply, on a last-value topic and only when the fold moves: a
        state topic republishing what it already holds is noise on the trace
        and news to nobody."""
        observed = self._observed()
        if observed != self._track:
            self._track = observed
            self._bus.publish(DEVICE_TRACK, {"power": observed})

    def _publish_link(self, up: bool, detail: str) -> None:
        """This app's link to the station, addressed by the system whose link
        it is. Republished when the reason changes as well as the word: while
        an outage lasts the row goes on saying so, and *why* is what a person
        reads (ADR-0050)."""
        said = (up, detail)
        if said == self._link:
            return
        self._link = said
        self._bus.publish(
            device_topic(DEVICE_LINK, SYSTEM),
            {"system": SYSTEM, "link": UP if up else DOWN, "detail": detail},
        )


def _built(wanted: Wanted) -> bytes | None:
    """The message one desired value becomes, or None where it becomes none
    — a payload that cannot be read, or a value this hardware has no packet
    for. The track row answers the power alone: the zeros and the release
    that may come before it are not this value's, they are the transition's.
    """
    row, address, payload = wanted
    if row == WANTED_TRACTION:
        speed = desired_speed(payload)
        return None if speed is None else commands.traction(address, speed)
    if row == WANTED_FUNCTION:
        addr, number = address.split("/")
        value = desired_function(payload)
        return None if value is None else commands.function(addr, number, value)
    if row == WANTED_POINT:
        position = desired_position(payload)
        return None if position is None else commands.point(_addr(address), position)
    if row == WANTED_SIGNAL:
        aspect = desired_aspect(payload)
        return None if aspect is None else commands.signal(_addr(address), aspect)
    power = commanded_power(payload)
    return None if power is None else commands.track(power)


def _addr(address: str) -> str:
    """What the hardware answers to, out of an address that named its system
    first. The system level has done its work by getting here — it is what
    said the address was this app's — and the packet carries the rest."""
    return address.split("/", 1)[1]
