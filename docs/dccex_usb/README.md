# Command station over USB

The command station is reached over USB, and one process can hold the device.
That process is the `dccex-usb` app: it opens the serial device and mirrors it
on a TCP port, so everything else — the `dccex` translator, JMRI, a hand-held
throttle — is a client of the port and they coexist
([ADR-0043](../adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
DecoderPro keeps working with every app of ours down.

It has no HTTP face and no state of its own, and for a long while it had no
bus contract either — there was nothing of ours on either of its sides. That
changed with one thing it does that is not mirroring: **writing a released
firmware build onto the station**, which only the process holding the device
can do ([ADR-0065](../adr/0065-the-app-that-owns-the-device-flashes-it.md)).
So it now subscribes `tc49/layout/firmware_wanted` and publishes
`tc49/layout/state/device/refused/<id>` when it will not do it, and those two
rows are its whole contract in [BUS.md](../BUS.md). The mirror itself
still reads no payload and speaks no topic.

## The command line

```
python -m tc49.dccex_usb --broker broker:1883 --device /dev/dccex --port 2560
```

The device to open, the port to serve it on, and the broker where the flash
gesture arrives. `deploy/app.Dockerfile` passes these, and
`deploy/compose.yaml` maps the cable in as `/dev/dccex` and publishes 2560
([DEPLOY.md](../DEPLOY.md#the-command-station)). Two more are optional:
`--firmware-releases <url>`, where releases are read from, this
installation's fork by default; and `--id`, what this app calls itself on the
row it refuses on, the package's name by default.

**The broker is not waited for.** The five apps that publish opening rows wait
for it before they publish (`lib/startup.py`); this one has no opening rows,
and the port it serves is how DecoderPro, JMRI and the throttles reach the
command station — a broker that is down must not take the command station
down with it, which is the promise the app exists for. The client connects in
the background and subscribes again on every reconnect, so a flash asked for
after the broker comes back is answered.

There is no bind address. The server binds every interface, because the
container publishes the port and JMRI reaches it as `dccex-usb:2560`; what
limits its reach is the LAN, which is the trust boundary
([ADR-0042](../adr/0042-the-edge-terminates-tls-and-the-lan-is-the-trust-boundary.md)).
For the same reason there is no authentication and no limit on the number of
clients beyond the OS's — though there is a limit on how far behind one may
fall, which is a different question.

**A mirror that cannot serve its port exits.** Something else on 2560 — a
second copy of the app, a container that has not finished going away — is not
a state this app can mirror out of, so it ends non-zero with the reason on
stderr rather than staying up with no server behind it. `restart:
unless-stopped` in `deploy/compose.yaml` is what tries again, and a port that
is busy for a moment during a deploy comes good on the retry. The device is a
different matter: one that is not there yet is waited for, not exited on.

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

**While the device is away, what a client sends is dropped.** The app reopens
the device with backoff — it goes away when the command station is switched
off, or when the cable is pulled — and for the length of the grace below the
clients wait through it without noticing anything but that their commands did
nothing. A command is honored now or ignored: a queue that flushes on
reconnect is a train that moves minutes after someone asked for it, which is
why the broker keeps nothing across a restart either.

**An outage that outlasts the grace disconnects every client on the port.**
The grace is two reopens at the first backoff, about a second, counted off
the backoff rather than kept as a number of its own. A client cannot tell an
away device from a quiet one and this port has no way to tell it, so a mirror
that held its clients through a station switched off would leave the
translator publishing `tc49/layout/state/device/link/<id>: up` over a railroad
that cannot move. The socket closing is the whole signal: the translator's
session ends the way it already ends, the row goes `down`, and nothing is
inferred anywhere
([ADR-0066](../adr/0066-the-link-is-the-station-answering-not-the-socket-being-open.md)).
An outage the first reopen recovers is invisible to clients as it always was,
which is what the grace is for — a USB blip, not a flash — and a client that
connects to an away device is served the outage itself, its bytes dropped
because a command is honored now or ignored. The grace is the outage's and
not each client's, so one that arrives while an outage is being waited out
leaves with the clients already on it, and one that arrives after they are
gone starts the next grace and gets all of it. Falling too far behind is a
different reason to disconnect and keeps its own rule.

Every way the device can fail to be there is the same outage: a path that is
not there, a path that will not take the line discipline because it is no
tty, a device that is gone again the moment it is open. None of them ends the
retrying or holds a descriptor open, and a session that ends at once is
waited out rather than reopened straight away. Each outage says once that
what clients send is being dropped, and the next outage says it again.

It logs connects, disconnects — with the ones it made itself distinguishable
from the ones a client made — the device opening and closing, the first
message dropped in each outage, and the grace ending one, to stderr. Nothing
else: a mirror that logged the traffic would log the whole railroad.

## Writing the firmware

The station's firmware is built elsewhere, against the station's own source.
What this app does is write a **released build** onto the box on a gesture:
`tc49/layout/firmware_wanted`, carrying a `tag` and never a source. It is the
only process that can — it holds the serial device open, esptool cannot share
it, and no container can stop a sibling without the Docker daemon's socket,
which is root on the box (ADR-0065).

On the gesture, in this order, and the order is the point:

1. Resolve the `tag` against the release API of `--firmware-releases`.
2. Fetch `firmware.bin`.
3. Check it against the `digest` that API reports for the asset — a
   per-asset `sha256:…`, so a tag chosen at the moment of the gesture is
   still checked. esptool verifies what it wrote, not what was fetched.
4. **Then** close the serial device.
5. Run esptool.
6. Reopen the device by the existing path.

A network failure costs nothing that way. The reverse order leaves the
railroad with a closed port and no firmware.

esptool is a **subprocess with a timeout**, not a library call: this process
is the one every throttle, DecoderPro and the translator depend on, and
esptool manipulates the port and exits on error, so a subprocess is what buys
crash isolation, a timeout and a kill. It is a project dependency, pinned by
`uv.lock` and present in the one shared image, so `uv run esptool` works on a
laptop too. The command line, against the device the container already maps:

```
esptool --chip esp32 --port /dev/dccex --baud 460800 \
  --before default-reset --after hard-reset write-flash -z \
  --flash-mode dio --flash-freq 80m --flash-size 4MB 0x0 firmware.bin
```

Flash mode, frequency and size are the station core's own upload settings.
Hyphenated throughout: esptool 5 renamed the entry point and the subcommands,
and the underscore forms are deprecated aliases a later major drops.

**While it writes, the device is away and clients on 2560 are served the
device-away behaviour above** — their bytes dropped, and their connections
closed once the grace passes, because for that minute or two the device
genuinely is away and a flash outlasts any grace. The railroad going dark for
the length of a flash is the correct outcome: nobody expects trains to run
while the station is being written, and the guard against a flash under a
moving train is the client's, below. Progress needs no topic of its own: the
link is down and says so on `tc49/layout/state/device/link/<id>`, published by
the translator that has lost it, and when the station answers again that row
carries the `build` it now reports. There is no reply, no
correlation id and no outcome topic; a client that asked for a tag reads the
answer off the observed half.

**What it refuses**, each on `tc49/layout/state/device/refused/<id>` with
free-text `detail` and no `addr`: a tag with no such release, a release
carrying no `firmware.bin` or no digest for it, a digest that does not match,
esptool exiting non-zero, esptool outliving the timeout, the device absent,
and a second gesture while a flash is in flight — refused, not queued, for
the reason a client's bytes are dropped rather than queued. `latest` is
refused too: it names a different build depending on when it is read, and
what was written has to be sayable afterwards. Nothing is log-only; broken
hardware is reported, never worked around (ADR-0050). A gesture whose payload
cannot be read is dropped in silence, having nobody to answer (BUS.md,
rule 4).

**Whether it is safe to reset the station is the client's**, not this app's.
Flashing drops the rails and disconnects every throttle, and the guarantee
that this is not done under a moving train lives in the client written to
honour it — `tc49/dispatch/state/run` at `held` and
`tc49/layout/state/device/track` at `off` before it publishes — exactly as it
does for cutting track power (ADR-0051, ADR-0062). Reading the dispatcher's
state is the coupling this app has never had and the reason it is
trustworthy.

## Checking it against a real station

Nothing in the test suite needs the hardware — the tests use a pty as the
device, so the gate is green on a laptop with nothing plugged in. That holds
for the flash as well: esptool cannot write a pty and the gate reaches no
release API, so what fetches a URL and what runs a command are injected and
the suite substitutes its own. What the suite does hold is the ordering —
the device closed before the runner is called and reopened after. Verifying
the actual link is runtime's job, and it is one command:

```
$ nc gleis49.org 2560
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
