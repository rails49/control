"""Writing a released build onto the command station.

The firmware is built elsewhere, against the station's own source, and that
does not change; what this makes is the writing of a released build onto the
box something the running system does on a gesture, rather than something a
person does from a checkout (ADR-0065). The gesture is
`tc49/layout/firmware_wanted`, one field, a `tag`, and **this app is the only
thing that can answer it**: flashing means owning the serial port, the mirror
holds it for as long as the railroad is up, and no container can stop a
sibling without handing a process the Docker daemon's socket.

**The payload names a tag and never a source.** The LAN is the trust boundary
and carries no authentication on purpose (ADR-0042), so a payload that said
where to fetch from would let anyone on the wifi have the station fetch and
run an arbitrary binary. Where releases are read from is a flag on this app,
and a tag can only choose among the builds already published there. `latest`
is not a tag either: it names a different build depending on when it is read,
and the point of the gesture is to be able to say afterwards what was written.

**The order is the point.** The release is resolved, the binary fetched and
its digest checked *before* the device is let go. A network failure then costs
nothing, where the other order leaves the railroad with a closed port and no
firmware. esptool verifies what it wrote and not what was fetched, so the
digest the release API reports for the asset is what says the bytes are the
ones that were published.

**esptool is a subprocess with a timeout**, injected as a runner so the suite
substitutes a fake — nothing in the gate may need a command station, and the
suite's device is a pty, which esptool cannot flash. A subprocess is also what
keeps its failures off this process: it manipulates the port and exits on
error, and this is the process every throttle, DecoderPro and the translator
depend on being up.

**There is no reply and no progress topic.** The flash is a desired half and
what happened is read off the observed half: the link goes down while the
station is written and comes back carrying the `build` it now reports, and
every way this refuses goes on `tc49/layout/state/device/refused/<id>`, whose
`addr` is optional for a refusal that named no address (ADR-0063). Nothing is
log-only: broken hardware is reported, never worked around (ADR-0050).

**A second gesture while a flash is in flight is refused, not queued.** A
command is honoured now or ignored, which is what this app already does with
what a client sends while the device is away; a queued flash is a station that
reboots minutes after somebody asked.
"""

import asyncio
import hashlib
import json
import tempfile
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import NamedTuple, Protocol, cast
from urllib.parse import quote

from tc49.dccex_usb.station import to_stderr
from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import device_topic

FIRMWARE_WANTED = "tc49/layout/firmware_wanted"
DEVICE_REFUSED = "tc49/layout/state/device/refused"

ID = "dccex-usb"
"""What this app calls itself on the row it refuses on where it is started
with no other name: the package's, because a name has to come from somewhere.
A value and not a contract — the id is whatever the publisher calls itself and
appears in no drawing and no list of ours (ADR-0059)."""

RELEASES = "https://api.github.com/repos/rails49/CommandStation-EX/releases"
"""Where releases are read from unless a box says otherwise: this
installation's fork of the command station's source, whose releases carry a
`firmware.bin` and a digest for it. Configuration rather than payload, which
is the whole of what keeps the gesture from naming what the station runs
(ADR-0042, ADR-0065)."""

ASSET = "firmware.bin"
"""The release asset that is written to the station."""

SHA256 = "sha256:"
"""The digest form the release API reports per asset, and the one form read
here. A digest in any other form checks nothing, so what it covers is refused
rather than written."""

CHIP = "esp32"
FLASH_BAUD = "460800"
FLASH_MODE = "dio"
FLASH_FREQ = "80m"
FLASH_SIZE = "4MB"
ADDRESS = "0x0"
"""The upload settings, which are the station core's own."""

LATEST = "latest"

TIMEOUT_S = 300.0
"""How long esptool is given before it is killed. Writing four megabytes at
460800 baud is a minute or two, and what this bounds is the other case: a tool
that has stopped talking to a station that has stopped answering, with the
mirror off the port for as long as it lasts."""

FETCH_S = 60.0
"""How long one fetch is given. Both of them happen before the device is let
go, so what this costs when it runs out is nothing but a refusal."""

ACCEPT = "application/vnd.github+json"


class Asset(NamedTuple):
    """The firmware a release carries: where to fetch it, and the digest the
    API reports for it. The digest is empty where the API reports none, which
    is a refusal rather than an unchecked write."""

    url: str
    digest: str


class Ran(NamedTuple):
    """What running a command came to: its exit status, or None where it
    outlived the timeout and was killed, and what it said while doing so."""

    code: int | None
    said: str


Fetch = Callable[[str], Awaitable[bytes]]
"""How bytes are read off a URL, injected so the suite reaches no network."""

Runner = Callable[[Sequence[str], float], Awaitable[Ran]]
"""How a command is run to its end, injected so the suite runs no esptool:
nothing in the gate may need a command station (docs/dccex_usb/README.md)."""


class Device(Protocol):
    """What a flash needs of the thing that owns the serial device.

    The mirror, and nothing else this package has — `Station` satisfies it by
    having the members. Narrow on purpose: what the flash may do to the
    railroad's one live port is exactly these three things, and a test can
    stand in for all of them.
    """

    @property
    def path(self) -> str: ...

    @property
    def held(self) -> bool: ...

    def released(self) -> AbstractAsyncContextManager[None]: ...


def release_url(releases: str, tag: str) -> str:
    """Where the release API is asked about one tag.

    The tag is **escaped whole**: it arrives off a bus with no authentication
    on it (ADR-0042), and a tag that kept its slashes would name a path of the
    caller's choosing under the host this app was configured with.
    """
    return f"{releases.rstrip('/')}/tags/{quote(tag, safe='')}"


def asset(document: object, name: str = ASSET) -> Asset | None:
    """The firmware asset a release document names, or None where it names
    none.

    Read the way a payload is read (BUS.md, rule 4) and for the same
    reason one level out: this is a document from a service, and a build that
    reached into it would be taken down by whatever the service returned the
    day it returned something else.
    """
    if not isinstance(document, dict):
        return None
    listed = cast(dict[str, object], document).get("assets")
    if not isinstance(listed, list):
        return None
    for entry in cast(list[object], listed):
        if not isinstance(entry, dict):
            continue
        fields = cast(dict[str, object], entry)
        if fields.get("name") != name:
            continue
        url, digest = fields.get("browser_download_url"), fields.get("digest")
        if not isinstance(url, str):
            return None
        return Asset(url, digest if isinstance(digest, str) else "")
    return None


def matches(binary: bytes, digest: str) -> bool:
    """Whether what was fetched is what the release says it published.

    A digest this cannot read matches nothing: the check is the whole reason a
    tag chosen at runtime is safe to write, so an unchecked binary is refused
    rather than written (ADR-0065, decision 4).
    """
    if not digest.lower().startswith(SHA256):
        return False
    return hashlib.sha256(binary).hexdigest() == digest[len(SHA256) :].strip().lower()


def argv(device: str, firmware: Path) -> list[str]:
    """What esptool is given, against the device this app already holds.

    Hyphenated throughout: esptool 5 renamed the entry point and the
    subcommands, and the underscore forms are deprecated aliases a later major
    drops. The flash mode, frequency and size are the station core's own
    upload settings, and the tool is pinned by `pyproject.toml` — the version
    the repository was tested at, in the one shared image.
    """
    return [
        "esptool",
        "--chip",
        CHIP,
        "--port",
        device,
        "--baud",
        FLASH_BAUD,
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write-flash",
        "-z",
        "--flash-mode",
        FLASH_MODE,
        "--flash-freq",
        FLASH_FREQ,
        "--flash-size",
        FLASH_SIZE,
        ADDRESS,
        str(firmware),
    ]


async def fetch(url: str) -> bytes:
    """What is at `url`, read off the loop's thread.

    In a thread because the mirror is on this loop: the fan-out happens while
    a release is being fetched, and a client whose bytes waited on a download
    would be a throttle that did nothing for a minute.
    """
    return await asyncio.to_thread(_read, url)


def _read(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": ACCEPT})
    with urllib.request.urlopen(request, timeout=FETCH_S) as answer:
        return cast(bytes, answer.read())


async def run(command: Sequence[str], timeout_s: float) -> Ran:
    """Run a command to its end, killing it where it outlives `timeout_s`.

    Its output is kept whole and both streams are one: what a refusal carries
    is the last thing the tool said, and which stream it said it on is not
    something a person reading a bus row has any use for.
    """
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        said, _ = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError:
        process.kill()
        await process.wait()
        return Ran(None, "")
    return Ran(process.returncode, said.decode(errors="replace"))


def wanted_tag(payload: object) -> str | None:
    """The build a gesture asks for, or None where it asks for none.

    A gesture that cannot be read is **dropped**, in silence and with no
    refusal to publish: a refusal is addressed to nobody, the gesture carries
    no id, and a frame nobody can read names no station to answer about
    (BUS.md, rule 4, ADR-0034).
    """
    if not isinstance(payload, dict):
        return None
    tag = cast(dict[str, object], payload).get("tag")
    return tag if isinstance(tag, str) and tag else None


def said(output: str) -> str:
    """The last thing a tool said, for the row a person reads. Its whole
    output on a state row would be a screenful where a sentence is wanted, and
    what an error was is the end of it."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


class Flasher:
    """The gesture answered: a released build written onto the command
    station by the app that owns its device.

    Constructed on the bus and the mirror, and subscribing as it is built, as
    every app's own class does. `run_wanted` is not a thing this reads and
    neither is anything else about the railroad: whether it is safe to reset
    the station lives in the client written to honour it, which is where the
    guarantee about cutting track power lives too (ADR-0051, ADR-0062,
    ADR-0065).
    """

    def __init__(
        self,
        bus: Bus,
        device: Device,
        releases: str = RELEASES,
        *,
        id: str = ID,
        fetch: Fetch = fetch,
        runner: Runner = run,
        timeout_s: float = TIMEOUT_S,
        log: Callable[[str], None] = to_stderr,
    ) -> None:
        self._bus = bus
        self._device = device
        self._releases = releases
        self._id = id
        self._fetch = fetch
        self._runner = runner
        self._timeout_s = timeout_s
        self._log = log
        # The one flash there may be, held so a second gesture is refused
        # rather than queued, and so that the process ending can wait for the
        # one in flight rather than leaving a station half written.
        self._flashing: asyncio.Task[None] | None = None
        bus.subscribe(FIRMWARE_WANTED, self._wanted)

    @property
    def flashing(self) -> bool:
        """Whether a flash is in flight. What a second gesture is refused on."""
        return self._flashing is not None

    async def settled(self) -> None:
        """Come back once the flash in flight, if there is one, is over.

        What the process waits on as it ends: the mirror gives the device back
        when the flash is done with it, and an exit in the middle of one would
        leave the station written halfway and the port closed.
        """
        flashing = self._flashing
        if flashing is not None:
            await asyncio.shield(flashing)

    def _wanted(self, topic: str, payload: Payload) -> None:
        """A build asked for: refused here, or started as a task of its own.

        Started rather than awaited because this runs on the loop that is the
        mirror: the fan-out goes on for the whole of a fetch — which the
        device is held through — and the port goes on being served for the
        whole of the flash after it, which is what lets a client that was
        disconnected by the outage come back to a mirror that is answering.
        """
        tag = wanted_tag(payload)
        if tag is None:
            return
        if tag == LATEST:
            self._refuse(
                f"'{LATEST}' is not a build: it names a different one depending"
                " on when it is read, and what was written has to be sayable"
                " afterwards"
            )
            return
        if self.flashing:
            self._refuse(f"a flash is already under way, so '{tag}' was not started")
            return
        if not self._device.held:
            self._refuse(
                f"the command station is not there — '{tag}' was not written"
                f" to {self._device.path}"
            )
            return
        self._flashing = asyncio.create_task(self._flash(tag))

    async def _flash(self, tag: str) -> None:
        """One flash, from the release to the station, and the refusal it came
        to where it came to one.

        Every way out of it publishes or leaves the row alone, and the flag
        falls whichever way it went: an app that refused a flash and then
        refused every one after it because a failure left the flag standing
        would be worse than the failure. Nothing waits after the flag falls,
        so the gesture that is answered next is answered by an app that has
        already said what became of this one.
        """
        self._log(f"flashing '{tag}' from {self._releases}")
        try:
            refusal = await self._written(tag)
        except Exception as raised:  # noqa: BLE001 — reported, never absorbed
            refusal = f"writing '{tag}' to the command station failed: {raised}"
        finally:
            self._flashing = None
        if refusal is None:
            self._log(f"flashed '{tag}'")
            return
        self._refuse(refusal)

    async def _written(self, tag: str) -> str | None:
        """The build written, or why it was not.

        The order is ADR-0065's and the whole of the care in this file: the
        release is resolved, fetched and checked while the mirror still holds
        the device, and only then is the device let go.
        """
        url = release_url(self._releases, tag)
        try:
            document = json.loads(await self._fetch(url))
        except (OSError, urllib.error.URLError, ValueError) as away:
            return f"no release '{tag}' at {url}: {away}"
        found = asset(document)
        if found is None:
            return f"release '{tag}' carries no {ASSET}"
        if not found.digest:
            return f"release '{tag}' reports no digest for {ASSET}, so it is unchecked"
        try:
            binary = await self._fetch(found.url)
        except (OSError, urllib.error.URLError) as away:
            return f"{ASSET} for '{tag}' could not be fetched from {found.url}: {away}"
        if not matches(binary, found.digest):
            return (
                f"{ASSET} for '{tag}' is not what the release reports"
                f" ({found.digest}), so it was not written"
            )
        return await self._runs(tag, binary)

    async def _runs(self, tag: str, binary: bytes) -> str | None:
        """The device handed over, esptool run on it, and the device taken
        back — the one ordering that can leave the railroad with a closed port
        and no firmware if it is got wrong."""
        with tempfile.TemporaryDirectory() as workspace:
            firmware = Path(workspace) / ASSET
            firmware.write_bytes(binary)
            command = argv(self._device.path, firmware)
            async with self._device.released():
                ran = await self._runner(command, self._timeout_s)
        if ran.code is None:
            return (
                f"writing '{tag}' outlived {self._timeout_s:.0f}s and was killed;"
                f" the command station may be half written"
            )
        if ran.code != 0:
            return (
                f"writing '{tag}' failed: esptool exited {ran.code}. {said(ran.said)}"
            )
        return None

    def _refuse(self, detail: str) -> None:
        """This app's report on its own last exchange, keyed by what it calls
        itself. No `addr`: a flash names no device address, which is the case
        that row's schema already allows for (ADR-0063)."""
        self._log(f"refused: {detail}")
        self._bus.publish(
            device_topic(DEVICE_REFUSED, self._id),
            {"id": self._id, "detail": detail},
        )
