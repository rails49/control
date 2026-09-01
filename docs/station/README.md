# Station

The command station is reached over USB, and one process can hold the device.
That process is the `station` app: it opens the serial device and mirrors it
on a TCP port, so everything else — the `dccex` translator, JMRI, a hand-held
throttle — is a client of the port and they coexist
([ADR-0043](../adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
DecoderPro keeps working with every app of ours down.

It has no bus topic, no HTTP face and no state. It is the one app with no
contract in [SYSTEM.md](../SYSTEM.md), because there is nothing of ours on
either of its sides.

## The command line

```
python -m tc49.station --device /dev/dccex --port 2560
```

Two flags, and they are the whole interface: the device to open and the port
to serve it on. `deploy/station.Dockerfile` passes exactly these, and
`deploy/compose.yaml` maps the cable in as `/dev/dccex` and publishes 2560
([DEPLOY.md](../DEPLOY.md#the-command-station)).

There is no bind address. The server binds every interface, because the
container publishes the port and JMRI reaches it as `station:2560`; what
limits its reach is the LAN, which is the trust boundary
([ADR-0042](../adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)).
For the same reason there is no authentication and no limit on the number of
clients beyond the OS's — though there is a limit on how far behind one may
fall, which is a different question.

The device is opened raw at 115200 8N1 — no echo, no line editing, no flow
control — so what a client sends is what the station receives.

## What it does with the bytes

**From the device to the clients: every byte, to every one of them,
unchanged.** Replies are not routed to whoever asked, because one serial
stream cannot say who asked: a reply to a throttle and a broadcast to
everyone look alike on it. Each client hears the whole conversation and
ignores what is not its business, which is what a shared bus has always
asked of the things on it.

**A client that has stopped reading is cut off.** Nothing waits for a client
to take what was fanned to it, so one that never does — a sleeping laptop, a
throttle whose Wi-Fi dropped, a hung DecoderPro — would have bytes buffered
for it for as long as the railroad runs, until the process is killed for
memory and *every* client loses the command station because one of them
walked out of range. Once more than a megabyte is outstanding to a client,
about a minute and a half of everything the device has to say, its connection
is closed and the log says it went too far behind rather than closing itself.
It may reconnect and pick the live conversation up. Not a bounded buffer that
discards instead: this direction is unframed, so dropping from the middle
hands the client half a message it reads as garbage, and not silence either —
if hardware or a peer breaks, the software says so (ADR-0050).

**From a client to the device: whole messages only.** A client's bytes are
buffered until a complete `<…>` message and then written in one write, so two
clients sending at once never interleave a command. Bytes outside a message —
before a `<`, after a `>` — are dropped; a second `<` starts the message over,
so `<<t 3 0 1>` is the one command `<t 3 0 1>`; a buffer that passes 1024
bytes without its `>` is discarded, and so are the bytes after it up to the
next `<`. A client that disconnects mid-message takes its partial message
with it. Nothing else of the protocol is read.

**While the device is away, what a client sends is dropped** and the client
stays connected. The app reopens the device with backoff — it goes away when
the command station is switched off, or when the cable is pulled — and the
clients wait through it without noticing anything but that their commands did
nothing. A command is honored now or ignored: a queue that flushes on
reconnect is a train that moves minutes after someone asked for it, which is
why the broker keeps nothing across a restart either.

Every way the device can fail to be there is the same outage: a path that is
not there, a path that will not take the line discipline because it is no
tty, a device that is gone again the moment it is open. None of them ends the
retrying or holds a descriptor open, and a session that ends at once is
waited out rather than reopened straight away. Each outage says once that
what clients send is being dropped, and the next outage says it again.

It logs connects, disconnects — with the ones it made itself distinguishable
from the ones a client made — the device opening and closing, and the first
message dropped in each outage, to stderr. Nothing else: a mirror that logged
the traffic would log the whole railroad.

## Checking it against a real station

Nothing in the test suite needs the hardware — the tests use a pty as the
device, so the gate is green on a laptop with nothing plugged in. Verifying
the actual link is runtime's job, and it is one command:

```
$ nc blocks49.local 2560
<s>
<iDCC-EX V-5.4.16 / ESP32 / EXCSB1_WITH_EX8874 G-9db8d0e>
<p0>
<c CurrentMAIN 0 C Milli 0 0 4000 1000>
```

`<s>` asks the station for its status; the banner naming the firmware, the
board and the motor shield is the station answering through the mirror. Open
a second `nc` alongside the first and send `<s>` from one: both see the reply,
which is the fan-out. With DecoderPro connected as a third client, the same
holds — that is the point of the app.
