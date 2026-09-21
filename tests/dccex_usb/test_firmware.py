"""Tests at the flash seam, with no station, no network and no esptool.

The suite's device is a pty, which esptool cannot write, and nothing in the
gate may reach a release API. So the two things that leave this process are
injected — what fetches a URL, and what runs a command — and what is asserted
here is everything but them: the URL a tag becomes, the digest check that
makes a tag chosen at runtime safe to write, the argv esptool is given, the
ordering the railroad depends on, and every way a flash is refused.

The device is a fake here; `tests/dccex_usb/test_station.py` holds the real
one to the same handover against a pty.
"""

import asyncio
import contextlib
import hashlib
import json
from collections.abc import AsyncGenerator, Sequence
from pathlib import Path

import pytest

from tc49.dccex_usb.firmware import (
    ASSET,
    DEVICE_REFUSED,
    FIRMWARE_WANTED,
    ID,
    Asset,
    Flasher,
    Ran,
    argv,
    asset,
    matches,
    release_url,
    wanted_tag,
)
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import device_topic
from tests.dccex_usb.test_station import Log, Pty, station

RELEASES = "https://api.example.invalid/repos/rails49/CommandStation-EX/releases"
TAG = "v5.6.4-rails49.1"
DEVICE = "/dev/dccex"
BINARY = b"the build the railroad asked for"
DIGEST = f"sha256:{hashlib.sha256(BINARY).hexdigest()}"
DOWNLOAD = "https://releases.example.invalid/firmware.bin"
TIMEOUT_S = 30.0
SETTLE_S = 5.0

REFUSED = device_topic(DEVICE_REFUSED, ID)


def release(digest: object = DIGEST, name: str = ASSET) -> bytes:
    """A release document, as the API answers a tag with one."""
    return json.dumps(
        {
            "tag_name": TAG,
            "assets": [
                {"name": "notes.txt", "browser_download_url": "…", "digest": "…"},
                {"name": name, "browser_download_url": DOWNLOAD, "digest": digest},
            ],
        }
    ).encode()


class FakeDevice:
    """The mirror, faked: what it was asked to do, in the order it was asked.

    `order` is what the ordering test reads, and the fake runner appends to
    the same list — so "released, ran, resumed" is one sequence rather than
    two that have to be lined up.
    """

    def __init__(self, held: bool = True) -> None:
        self.path = DEVICE
        self.held = held
        self.order: list[str] = []

    @contextlib.asynccontextmanager
    async def released(self) -> AsyncGenerator[None]:
        self.order.append("released")
        self.held = False
        try:
            yield
        finally:
            self.held = True
            self.order.append("resumed")


class FakeFetch:
    """What a URL answers with, and a record of what was asked for."""

    def __init__(
        self,
        document: bytes | Exception | None = None,
        binary: bytes | Exception = BINARY,
    ) -> None:
        self._answers: dict[str, bytes | Exception] = {
            release_url(RELEASES, TAG): release() if document is None else document,
            DOWNLOAD: binary,
        }
        self.asked: list[str] = []

    async def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        answer = self._answers.get(url, OSError(f"nothing at {url}"))
        if isinstance(answer, Exception):
            raise answer
        return answer


FLASHED = Ran(0, "")
"""What esptool comes to where it wrote the station."""


class FakeRunner:
    """esptool, faked: what it was given, and what it came to.

    It reads the file it was pointed at as it runs, because the flash writes
    that file into a directory that is gone by the time the test looks — and
    what reached the disk is the thing being asserted anyway.
    """

    def __init__(self, ran: Ran = FLASHED, *, waits: bool = False) -> None:
        self._ran = ran
        self._let_go = asyncio.Event() if waits else None
        self.commands: list[Sequence[str]] = []
        self.timeouts: list[float] = []
        self.wrote: list[bytes] = []
        self.order: list[str] | None = None
        self.called = asyncio.Event()

    async def __call__(self, command: Sequence[str], timeout_s: float) -> Ran:
        self.commands.append(command)
        self.timeouts.append(timeout_s)
        self.wrote.append(Path(command[-1]).read_bytes())
        if self.order is not None:
            self.order.append("ran")
        self.called.set()
        if self._let_go is not None:
            await self._let_go.wait()
        return self._ran

    def let_go(self) -> None:
        assert self._let_go is not None
        self._let_go.set()


class Flash:
    """One flasher on one bus, and the gestures a test makes at it."""

    def __init__(
        self,
        device: FakeDevice | None = None,
        fetch: FakeFetch | None = None,
        runner: FakeRunner | None = None,
    ) -> None:
        self.bus = InProcessBus(Clock())
        self.device = device if device is not None else FakeDevice()
        self.fetch = fetch if fetch is not None else FakeFetch()
        self.runner = runner if runner is not None else FakeRunner()
        self.refusals: list[str] = []
        self.bus.subscribe(REFUSED, self._refused)
        self.flasher = Flasher(
            self.bus,
            self.device,
            RELEASES,
            fetch=self.fetch,
            runner=self.runner,
            timeout_s=TIMEOUT_S,
            log=lambda line: None,
        )

    def _refused(self, topic: str, payload: Payload) -> None:
        self.refusals.append(str(payload.get("detail")))

    def wants(self, payload: Payload | str = TAG) -> None:
        """A gesture published and delivered, as a browser makes one."""
        frame = {"tag": payload} if isinstance(payload, str) else payload
        self.bus.publish(FIRMWARE_WANTED, frame)
        self.bus.drain()

    async def settled(self) -> None:
        """Wait out the flash in flight, whichever way it ended, and deliver
        what it published."""
        await asyncio.wait_for(self.flasher.settled(), SETTLE_S)
        self.bus.drain()


# -- the pure units ----------------------------------------------------------


def test_a_tag_is_asked_about_by_the_release_api() -> None:
    assert release_url(RELEASES, TAG) == f"{RELEASES}/tags/{TAG}"


def test_a_releases_url_with_a_trailing_slash_is_the_same_url() -> None:
    assert release_url(f"{RELEASES}/", TAG) == release_url(RELEASES, TAG)


def test_a_tag_cannot_walk_out_of_the_releases_it_was_configured_with() -> None:
    """A tag arrives off a bus with no authentication on it (ADR-0042), so it
    is escaped whole: nothing in it names a path of its own choosing."""
    asked = release_url(RELEASES, "../../../other/releases/tags/v1")

    assert asked.startswith(f"{RELEASES}/tags/")
    assert "/" not in asked[len(RELEASES) + len("/tags/") :]


def test_the_firmware_asset_is_where_to_fetch_it_and_its_digest() -> None:
    assert asset(json.loads(release())) == Asset(DOWNLOAD, DIGEST)


def test_a_release_without_the_firmware_names_no_asset() -> None:
    assert asset(json.loads(release(name="other.bin"))) is None


@pytest.mark.parametrize(
    "document", ["", [], {"assets": "several"}, {"assets": [1, 2]}, {}]
)
def test_a_document_that_cannot_be_read_names_no_asset(document: object) -> None:
    assert asset(document) is None


def test_an_asset_the_api_reports_no_digest_for_carries_none() -> None:
    found = asset(json.loads(release(digest=None)))

    assert found is not None and found.digest == ""


def test_the_digest_is_what_says_the_bytes_are_the_published_ones() -> None:
    assert matches(BINARY, DIGEST)
    assert not matches(BINARY + b"!", DIGEST)


def test_a_digest_in_a_form_this_cannot_read_matches_nothing() -> None:
    """An unchecked binary is refused rather than written (ADR-0065)."""
    assert not matches(BINARY, "")
    assert not matches(BINARY, hashlib.sha256(BINARY).hexdigest())
    assert not matches(BINARY, f"md5:{hashlib.md5(BINARY).hexdigest()}")


def test_the_argv_esptool_is_given() -> None:
    """Hyphenated throughout: esptool 5 renamed the entry point and the
    subcommands, and the underscore forms are aliases a later major drops."""
    assert argv(DEVICE, Path("/tmp/firmware.bin")) == [
        "esptool",
        "--chip",
        "esp32",
        "--port",
        DEVICE,
        "--baud",
        "460800",
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write-flash",
        "-z",
        "--flash-mode",
        "dio",
        "--flash-freq",
        "80m",
        "--flash-size",
        "4MB",
        "0x0",
        "/tmp/firmware.bin",
    ]


@pytest.mark.parametrize(
    "payload", ["a tag", {}, {"tag": 5}, {"tag": ""}, {"build": TAG}]
)
def test_a_gesture_that_names_no_build_asks_for_none(payload: object) -> None:
    assert wanted_tag(payload) is None


# -- the flash ---------------------------------------------------------------


def test_the_release_is_written_to_the_station_and_nothing_is_refused() -> None:
    async def scenario() -> None:
        flash = Flash()

        flash.wants()
        await flash.settled()

        assert flash.refusals == []
        assert flash.runner.wrote == [BINARY]
        assert flash.runner.timeouts == [TIMEOUT_S]
        command = list(flash.runner.commands[0])
        assert command[:-1] == argv(DEVICE, Path(ASSET))[:-1]
        assert command[-1].endswith(f"/{ASSET}")

    asyncio.run(scenario())


def test_the_device_is_let_go_before_esptool_and_taken_back_after() -> None:
    """The one ordering that can break the railroad (ADR-0065): two openers
    fight over the line discipline, and a flash that ran with the mirror on
    the port would leave the railroad with neither."""

    async def scenario() -> None:
        flash = Flash()
        device, runner = flash.device, flash.runner
        assert isinstance(runner, FakeRunner)
        runner.order = device.order

        flash.wants()
        await flash.settled()

        assert device.order == ["released", "ran", "resumed"]
        assert device.held

    asyncio.run(scenario())


def test_the_device_is_let_go_only_once_the_build_is_fetched_and_checked() -> None:
    """A network failure costs nothing: the reverse order leaves the railroad
    with a closed port and no firmware."""

    async def scenario() -> None:
        flash = Flash(fetch=FakeFetch(binary=b"a different build"))

        flash.wants()
        await flash.settled()

        assert flash.device.order == []
        assert flash.runner.commands == []
        assert len(flash.refusals) == 1
        assert "not what the release reports" in flash.refusals[0]

    asyncio.run(scenario())


def test_a_tag_with_no_such_release_is_refused() -> None:
    async def scenario() -> None:
        flash = Flash(fetch=FakeFetch(document=OSError("HTTP Error 404: Not Found")))

        flash.wants()
        await flash.settled()

        assert len(flash.refusals) == 1
        assert f"no release '{TAG}'" in flash.refusals[0]
        assert flash.device.order == []

    asyncio.run(scenario())


def test_a_release_that_carries_no_firmware_is_refused() -> None:
    async def scenario() -> None:
        flash = Flash(fetch=FakeFetch(document=release(name="other.bin")))

        flash.wants()
        await flash.settled()

        assert flash.refusals == [f"release '{TAG}' carries no {ASSET}"]

    asyncio.run(scenario())


def test_a_release_the_api_reports_no_digest_for_is_refused() -> None:
    """Unchecked is not written: the per-asset digest is what makes a tag
    chosen at the moment of the gesture safe (ADR-0065, decision 4)."""

    async def scenario() -> None:
        flash = Flash(fetch=FakeFetch(document=release(digest=None)))

        flash.wants()
        await flash.settled()

        assert len(flash.refusals) == 1
        assert "reports no digest" in flash.refusals[0]
        assert flash.device.order == []

    asyncio.run(scenario())


def test_esptool_exiting_non_zero_is_refused_in_its_own_words() -> None:
    async def scenario() -> None:
        flash = Flash(runner=FakeRunner(Ran(2, "A fatal error occurred: no serial")))

        flash.wants()
        await flash.settled()

        assert len(flash.refusals) == 1
        assert "esptool exited 2" in flash.refusals[0]
        assert "A fatal error occurred: no serial" in flash.refusals[0]
        assert flash.device.held, "the device is not taken back"

    asyncio.run(scenario())


def test_esptool_outliving_the_timeout_is_refused() -> None:
    async def scenario() -> None:
        flash = Flash(runner=FakeRunner(Ran(None, "")))

        flash.wants()
        await flash.settled()

        assert len(flash.refusals) == 1
        assert "was killed" in flash.refusals[0]
        assert flash.device.held

    asyncio.run(scenario())


def test_a_flash_asked_for_while_the_station_is_away_is_refused() -> None:
    """The device is not there — switched off, or the cable is out — and a
    station that is not there is not written to."""

    async def scenario() -> None:
        flash = Flash(device=FakeDevice(held=False))

        flash.wants()
        await flash.settled()

        assert len(flash.refusals) == 1
        assert "not there" in flash.refusals[0]
        assert flash.fetch.asked == []

    asyncio.run(scenario())


def test_a_second_gesture_while_a_flash_is_in_flight_is_refused_not_queued() -> None:
    """A command is honoured now or ignored, which is what this app already
    does with what a client sends while the device is away; a queued flash is
    a station that reboots minutes after somebody asked."""

    async def scenario() -> None:
        runner = FakeRunner(waits=True)
        flash = Flash(runner=runner)

        flash.wants()
        await asyncio.wait_for(runner.called.wait(), SETTLE_S)
        flash.wants("v5.6.4-rails49.2")

        assert len(flash.refusals) == 1
        assert "already under way" in flash.refusals[0]

        runner.let_go()
        await flash.settled()

        assert len(runner.commands) == 1

    asyncio.run(scenario())


def test_latest_is_not_a_build() -> None:
    """It names a different build depending on when it is read, and what was
    written has to be sayable afterwards (ADR-0065)."""

    async def scenario() -> None:
        flash = Flash()

        flash.wants("latest")
        await flash.settled()

        assert len(flash.refusals) == 1
        assert flash.fetch.asked == []

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [{}, {"tag": 5}, {"tag": ""}, {"build": TAG}])
def test_a_gesture_that_cannot_be_read_is_dropped_without_raising(
    payload: Payload,
) -> None:
    """BUS.md, rule 4: a gesture carries no id, so a refusal would be
    addressed to nobody and there is no station to name in one either."""

    async def scenario() -> None:
        flash = Flash()

        flash.wants(payload)
        await flash.settled()

        assert flash.refusals == []
        assert flash.fetch.asked == []
        assert not flash.flasher.flashing

    asyncio.run(scenario())


# -- the wiring --------------------------------------------------------------


def test_the_mirror_is_off_the_port_while_esptool_runs() -> None:
    """The flasher on the real mirror, with a pty for the command station.

    The fake runner is called with the device closed and the mirror has it
    again afterwards — the one ordering that can leave the railroad with a
    closed port and no firmware (ADR-0065). esptool cannot write a pty, which
    is why what runs is a fake and what is asserted is the handover.
    """

    async def scenario() -> None:
        log = Log()
        cable = Pty()
        app = station(cable.path, log)
        bus = InProcessBus(Clock())
        held: list[bool] = []

        async def runner(command: Sequence[str], timeout_s: float) -> Ran:
            held.append(app.held)
            return FLASHED

        refusals: list[Payload] = []
        bus.subscribe(REFUSED, lambda topic, payload: refusals.append(payload))
        flasher = Flasher(
            bus,
            app,
            RELEASES,
            fetch=FakeFetch(),
            runner=runner,
            log=lambda line: None,
        )
        await app.start()
        try:
            await log.wait_for("serial open")

            bus.publish(FIRMWARE_WANTED, {"tag": TAG})
            bus.drain()
            await asyncio.wait_for(flasher.settled(), SETTLE_S)
            bus.drain()

            assert held == [False], "esptool ran with the mirror on the port"
            await log.wait_for_count("serial open", 2)
            assert app.held
            assert refusals == []
        finally:
            await app.close()
            cable.close()

    asyncio.run(scenario())
