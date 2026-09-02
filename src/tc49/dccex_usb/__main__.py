"""`python -m tc49.station` — the command line the container runs.

Two flags and no more, the ones `deploy/station.Dockerfile` passes: the
device to open and the port to serve it on. There is no bind address, because
the server binds every interface and what limits its reach is the LAN
(ADR-0042).
"""

import argparse
import asyncio
import contextlib

from tc49.station.station import Station


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tc49.station",
        description="Mirror the command station's serial device on a TCP port.",
    )
    parser.add_argument("--device", required=True, help="the serial device to open")
    parser.add_argument("--port", type=int, required=True, help="the TCP port to serve")
    args = parser.parse_args()
    device: str = args.device
    port: int = args.port
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(Station(device, port).run())


if __name__ == "__main__":
    main()
