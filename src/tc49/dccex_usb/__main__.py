"""`python -m tc49.dccex_usb` — the command line the container runs.

The device to open and the port to serve it on are the mirror's own two flags
and the whole of what it was for a while (ADR-0043). What the rest are for is
the one thing this app does that is not mirroring: writing a released build
onto the command station, which only the process holding the device can do
(ADR-0065, `firmware.py`). There is still no bind address, because the server
binds every interface and what limits its reach is the LAN (ADR-0042).

- `--broker <host:port>`, where the gesture arrives and where a refusal goes.
- `--firmware-releases <url>`, where releases are read from, defaulting to
  this installation's fork. **Configuration and never payload**: the LAN
  carries no authentication on purpose, so a source on the wire would let
  anyone on the wifi run an arbitrary binary on the command station.
- `--id`, the name its refusals are keyed by, defaulting to the package's.

**The mirror does not wait for the broker**, where the five apps that publish
opening rows do (`lib/startup.py`, step 2). It has no opening rows to publish,
and the port it serves is what DecoderPro, JMRI and the hand-held throttles
reach the command station through — a broker that is not there must not take
the command station away with it, which is the promise this app exists for.
The client connects in the background and its subscription goes again with
every reconnect, so a flash asked for after the broker comes back is answered
(`lib/mqtt.py`).

**No documents and no railroad**, for the translator's reasons one level down
(ADR-0059, decisions 5 and 6): nothing here is looked up in a drawing, and
a railroad loaded under it changes neither the cable nor the station on the
end of it.

**asyncio owns this process.** The mirror is a loop and the bus's network
thread only fills a queue, so the drain beside the mirror is what hands a
gesture to the loop — which is the thread that closes the device and runs
esptool, the same thread that would otherwise be writing a client's bytes to
it.
"""

import asyncio
import contextlib
import signal
import sys
import threading

from tc49.dccex_usb.firmware import ID, RELEASES, Flasher
from tc49.dccex_usb.station import Station, to_stderr
from tc49.lib.bus import Bus
from tc49.lib.mqtt import MqttBus, address
from tc49.lib.startup import PERIOD_S, command_line

CLIENT_PREFIX = "tc49-"
"""What this app calls itself to the broker, in front of its id, so the log
names a mirror rather than a random string and two boxes with a command
station each are two clients. Nothing in the contract reads it: a topic has
one writing role and no payload says who published (BUS.md, rule 4)."""


def serve(
    bus: Bus,
    device: str,
    port: int,
    stop: threading.Event,
    id: str = ID,
    releases: str = RELEASES,
    period_s: float = PERIOD_S,
) -> None:
    """The app: the mirror, the flasher on it, and the drain that feeds it.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be, and `main` lets that out. So does a mirror that cannot
    serve — the port is taken, and this comes back raising rather than
    staying up with nothing behind it (#526).
    """
    station = Station(device, port)
    flasher = Flasher(bus, station, releases, id=id)
    to_stderr(f"serving {device} on {port} as '{id}', flashing from {releases}")
    asyncio.run(mirroring(station, flasher, bus, stop, period_s))


async def mirroring(
    station: Station,
    flasher: Flasher,
    bus: Bus,
    stop: threading.Event,
    period_s: float,
) -> None:
    """The mirror and the drain, on the one loop, until the process ends.

    **The mirror ending ends this**, which is why the drain waits on the task
    rather than on the clock: a port already taken raises out of the mirror,
    and a drain that went round anyway would leave a live process with no TCP
    server, no device and nothing said (#526). The failure is what the
    teardown's `await` carries out, so it reaches `main` and the exit status
    and `restart: unless-stopped` gets its turn — which is what a box whose
    2560 is busy for a moment during a deploy depends on.

    A flash in flight is waited out where there is still a loop to wait on:
    the mirror gives the device back when the flash is done with it, and
    ending in the middle of one leaves the station half written. A signal
    arriving mid-flash is not something this can hold off — the cancellation
    it raises is what ends the wait — and neither is the container's kill.
    """
    mirror = asyncio.create_task(station.run())
    try:
        while not stop.is_set() and not mirror.done():
            bus.drain()
            await asyncio.wait((mirror,), timeout=period_s)
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await flasher.settled()
        mirror.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await mirror


def main() -> None:
    parser = command_line(
        prog="python -m tc49.dccex_usb",
        description="Mirror the command station's serial device on a TCP port,"
        " and write a released firmware build onto it when asked.",
        railroad=False,
        store=False,
    )
    parser.add_argument("--device", required=True, help="the serial device to open")
    parser.add_argument("--port", type=int, required=True, help="the TCP port to serve")
    parser.add_argument(
        "--firmware-releases",
        default=RELEASES,
        metavar="URL",
        help="where releases are read from, this installation's fork by"
        " default; never taken from a payload",
    )
    parser.add_argument(
        "--id",
        default=ID,
        help=f"what this app calls itself on the row it refuses on,"
        f" '{ID}' by default",
    )
    args = parser.parse_args()
    try:
        host, port = address(args.broker)
    except ValueError as refused:
        parser.error(str(refused))
    # A signal is what ends this app, and SIGTERM is the one a container is
    # stopped with: given SIGINT's own handler it raises where the process
    # stands, and the mirror lets the device go on the way out either way.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    print(f"broker {host}:{port}", file=sys.stderr, flush=True)
    bus = MqttBus(host, port, client_id=f"{CLIENT_PREFIX}{args.id}")
    try:
        with contextlib.suppress(KeyboardInterrupt):
            serve(
                bus,
                args.device,
                args.port,
                threading.Event(),
                args.id,
                args.firmware_releases,
            )
    finally:
        bus.close()


if __name__ == "__main__":
    main()
