# DCC-EX

The first translator under `layout`
([ADR-0043](../adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)):
a thin app, `dccex`, that subscribes to the **device vocabulary** and turns it
into the DCC-EX command station's own language, and publishes back what the
station reports.

**This page is the only place in the repository where that language is
written down.** Every other component is oblivious to what powers the layout:
nothing above the layout interface expects DCC-EX, or Lenz, or NCE, or
anything else — those are one family of devices among many. The `<…>` syntax
appears on no bus topic, in no other package and in no normative document
([SYSTEM.md](../SYSTEM.md#device-vocabulary) is the contract, and a test keeps
protocol names off the pages that are not about hardware). A different command
station gets a different translator, or reaches the system through JMRI, and
nothing else moves.

The facts below are from
[the DCC-EX research notes](https://github.com/rails49/control/blob/research/dccex/docs/research/dccex.md),
read against firmware 5.6.3. Getting one of them wrong is a bug in this app
and nowhere else.

## What it connects to

TCP **2560**, which the `dccex-usb` app serves from the USB device
([dccex_usb/README.md](../dccex_usb/README.md)). Not the USB device directly:
`dccex-usb` owns it, and the port is what lets JMRI and hand-held throttles
share the same command station. This app is one client of that port beside
the others, and every client is a peer — nothing in the firmware ranks them.

*Subscribes* `tc49/layout/state/wanted/#`. *Publishes*
`tc49/layout/state/device/track` and `tc49/layout/state/device/link/<id>`,
where the id is the one this app is started with — `dccex`, the package's
name, where it is given no other. The id is whatever the publisher calls
itself, a value and not a contract: it appears in no drawing, no configuration
and no list of ours (ADR-0059).

**It acts on every address it hears**, and there is no ownership table
anywhere. An address names no system — it is the string the drawing carries
and the hardware answers to
([ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md))
— so every point and signal address is this app's, as every traction and
function address is, a decoder answering to the number it was programmed with
whoever sends the packet
([ADR-0045](../adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
What this station has no packet for — a turnout numbered outside the accessory
range — falls away in the mapping below. An address nothing answers to does no
harm, as a packet nobody picks up does.

**On connect it applies the retained desired state and does nothing else.**
The desired values are the whole picture, so there is no handshake and no
session state to agree. The `wanted/track` row is applied first, so power
reaches the rails before a turnout is asked to throw and a release's zeros
land before the speeds rather than over the top of them.

## The startup file

`--startup <path>` names a file of raw station commands, one per line, that
this app sends **on every transition of `wanted/track` into `on`, straight
after the track-on command**. The flag is optional; with no file the byte
stream is exactly what it is without it.

That file is where this installation's **power district trip currents** are
written, and the only place they appear. This railroad has four districts,
A–D, and each takes the current its wiring can really carry; a district is a
hardware-level fact that reaches no bus topic
([#217](https://github.com/rails49/control/issues/217)), so no other component
learns there are four of them, or any.

```
# /etc/tc49/dccex-startup.txt — trip currents for the four districts
<= A LIMIT 3000>
<= B LIMIT 3000>
<= C LIMIT 1500>
<= D LIMIT 1500>
```

**The values above are this installation's**, not a default and not a
recommendation: what a district can take is what is wired to it, and the file
is where a person writes theirs. The command spelling is the station's, and it
wants firmware that has the per-district limit — that patch, the command and
flashing it are a separate project and not this repository's work
([rails49/CommandStation-EX#1](https://github.com/rails49/CommandStation-EX/issues/1)).
Until it lands the values are compiled into the station instead, which is a
reflash to change one and the reason for wanting the command at all.

**The file is not parsed beyond blank and comment.** A line beginning with `#`
is a note and a blank line is layout; every other line is stripped of
surrounding whitespace and handed to the station exactly as typed. That is the
whole point of it: a person writes anything their station understands —
auto-reverse and polarity are the same kind of hardware configuration and
belong here if they ever need setting — without this app growing a vocabulary
for it, and without a mechanism that would reach the scheduler, the dispatcher
or the driver.

**It is a transition and not a level.** A second `on` over rails that are
already live sends nothing: the station has the values. Any other word sends
them again — an `off` and back, and the emergency-stop lock and its release —
and so does a new link — the station on the far end of the
next one may be one that has just restarted, and one that has forgotten its
trip currents runs at the firmware's default until somebody notices.

**A file that is missing or cannot be read is logged and the railroad powers
on anyway.** Refusing to power on because a configuration file was missing is
worse than coming up at whatever the firmware defaults to
([ADR-0050](../adr/0050-broken-hardware-is-reported-never-worked-around.md)).
What that default is belongs to the firmware and not here, and it is a choice
made there: a station's trip currents are fixed when its firmware is built, so
one built with this railroad's four values is protected with no file at all and
the file only changes them. One built with the stock definition trips at 5000 mA
on every output, and a missing file leaves the wiring behind that.

## The mapping

| desired | sent |
| --- | --- |
| `wanted/traction/<addr>` `speed` | `<t addr step dir>` — the fraction scaled to 0–126 and the sign taken as the direction; `speed 0.0` sends step 0 |
| `wanted/point/<addr>` `position` | `<a addr sub act>`, a stateless accessory packet; `thrown` writes `1` |
| `wanted/signal/<addr>` `aspect` | `<A addr aspect>`, the extended accessory packet the head's wiring expects |
| `wanted/track` `on` | `<1>`, which reaches every track the station has |
| `wanted/track` `off` | `<0>` |
| `wanted/track` `stopped` | `<!>`, the one-shot emergency stop |
| `wanted/function/<addr>/<n>` `value` | `<F addr n 0\|1>`, the boolean as the bit — every value the row carries is one the station can be told |

Every row is a pure function in `commands.py`, asserted as "this value in,
these bytes out" with no socket and no hardware.

**A speed is a fraction and a step never leaves this app.** The magnitude is
the fraction of that locomotive's maximum and the sign is which way it runs
along the track, so `1.0` and `-1.0` are one step and two direction bits, and
a fraction past the range is full speed and never more — there is nothing
above a maximum to ask for. The station remembers the speed in a slot and
re-sends it forever as a reminder packet, which is why the lock below matters.

**A point address is the accessory number a throttle shows**, `1` upward, and
this app splits it into the packet's decoder address and sub-address, four to
a decoder. It is sent as `<a>` and never as `<T>`: `<T>` would put a turnout
table inside the station and answer with a position the station faked, and
`align` carries the points its transit needs every time so that a translator
throws what it is told and holds no table
([ADR-0031](../adr/0031-the-layout-carries-the-points-a-transit-needs.md)).

**What an aspect is worth to a head is wiring**, not contract: `stop` is `0`,
which the extended accessory packet reserves for stop, and `caution` and
`clear` are `1` and `2`. An aspect this table does not name is one no head
here is wired for and sends nothing.

**A function is a switch.** The station's `<F>` takes `0` or `1`, so the two
values a model may leave unstated are the two that reach the wire; a value
from a longer list — the `low` and `high` of a three-position vacuum — names a
state this hardware has no packet for, and nothing is sent.

Two rules are not a row of the table.

**The stop is `<!>` and holds nothing.** It broadcasts an emergency stop to
every decoder with the track still live, and changes nothing afterwards, so
any throttle on the port can drive away from it. That is deliberate: who may
move a train is the operator's decision, and the operator is the one holding
the layout. It also means `state/power` never reads `stopped` from a stop this
app sent — there is nothing left for the station to report — so the row goes
back to `on` as soon as the broadcast is out.

The station has an emergency-stop **lock** in later firmware, `<!P>` until
`<!R>` with `<!Q>` to ask, which would make `stopped` a state rather than an
act. It is not used, for two reasons
([#463](https://github.com/rails49/control/issues/463),
[#464](https://github.com/rails49/control/issues/464)). It is a
firmware-branch command of one product, so a `stopped` that meant "under a
lock" would put a station's private vocabulary inside a bus word every
railroad shares. And the station on the layout is older than it: below the
version that has the lock, the `!` opcode takes no suffix, so `<!P>`, `<!R>`
and `<!Q>` are all read as `<!>` and none of them says so. That is what made a
`<!Q>` in the poll an emergency stop once a second, and every train move a few
centimetres and stand.

**An overload is polled for, with `<s>` and with nothing else.** A district
that trips is not broadcast on TCP: the firmware cuts the output directly and
prints the diagnostic to USB serial only, so no client sees a `<p…>` line for
it. Once a second this app sends `<s>`, which makes the station restate every
track's power, so `device/track` telling the truth does not depend on a person
noticing. Nothing else goes in the poll. A poll runs for as long as the link
does, so a command in it that a station acts on rather than answers is acted
on for as long as the railroad is up, and a station says nothing about a
command it does not know.

## What it publishes back

**`device/track`** is folded from what the station says and never from what
this app commanded. `on` only where every track the station named is on — the
digit is `1` for a track that is fully on, and `0` both for one that has
tripped and for one that is powered but watching a rising current, so anything
else is `off`. `stopped` is the station's own `<!PAUSED>`, over live rails. A
station that has said nothing reads `off`, which is the direction a state
topic must fail in
([#181](https://github.com/rails49/control/issues/181)), and a link that goes
takes the reading with it: a district that tripped while this app was away
would otherwise stand as an observation nobody made.

**`device/link`** is `up` while the connection is open **and** the station has
answered, `down` otherwise, with `detail` carrying what a person would want to
read, on the row the app's id keys. An open socket is not a command station — `dccex-usb` accepts a client
with the serial cable unplugged — so the link is not called good until
something has come back on it. It goes on saying `down` for the whole outage,
which is where a broken link becomes visible: at runtime, to a person who can
act on it, and not in a gate that would need a powered layout to pass
([ADR-0050](../adr/0050-broken-hardware-is-reported-never-worked-around.md)).
The same words go on `device/track` as its `reason` while the station is
unreachable, so a person reading why the railroad is dark reads it off the
supply itself rather than off a second row. A district that has tripped gets
none: the station reported that and said nothing about why, and an invented
reason would be worse than none.

**No `device/point`.** This railroad's turnouts have no feedback and the
station's answer to a throw is one it faked
([ADR-0022](../adr/0022-a-symbol-carries-its-hardware-address.md)), so the row
stays empty however many turnouts are thrown. A faked observation is worse
than silence.

Everything else on the port is another client's conversation — a slot's speed,
a turnout the station keeps of its own, a sensor it polls, a fast clock — and
is passed over unread. Parsing what the mapping does not need is work with
nobody to read it.

## Standing the railroad down

`shutdown()` sends **zero to every locomotive this app has commanded**, in the
order they were commanded, and only then the track off. Whoever constructed
the app calls it before letting the loop go.

The process ending is not by itself an instruction to the railroad. The
station goes on running whatever it was last told, so a session that exits
over a rolling locomotive leaves it rolling, and that is not recoverable the
way switching the power back on is. The zeros come first because the station
keeps a speed per locomotive and resumes it, so cutting the supply over a held
speed only postpones the motion.

A link that was never open sends nothing at all. A railroad this app could not
reach is one it was not driving, and `_send` drops rather than queues.

## The command line

```
python -m tc49.dccex --broker <host:port> --station <host:port>
                     [--startup <file>] [--id <name>]
```

The process a container runs, coming up alone against a broker
([ADR-0059](../adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md),
decision 5) as `layout`, `scheduler`, `dispatcher`, `driver` and `simulator`
do, and as `dccex-usb` has all along.

**No railroad and no store.** Hardware needs no layout: this app reads the
wanted rows and writes what it observes, and there is nothing for a railroad's
name to select here — no document is read, and an address is the string the
hardware answers to rather than something looked up. `--station` is where
`dccex-usb` serves the command station, `--startup` the file of trip currents
below, and `--id` the name the link row is keyed by, the package's where it is
given no other. The id names the broker's client too, `tc49-<id>`: this is the
one app a railroad may run twice, and two clients sharing a client id take
turns disconnecting each other.

The drain period, the poll and the reconnect backoff are not flags. Nothing
outside the process has an opinion about them, and what the station is asked
and how often a lost link is retried are this app's own.

Coming up is the broker, then the desired picture, then the link. The two rows
the constructor states are publishes, and a publish made to a broker that is
not there is dropped rather than queued, so the broker is waited for first. The
desired rows the broker has retained are then waited for **before** the link is
opened, for a second: what a connection is handed is ordered with the track
first, where a value arriving over a link that is already up is acted on as it
arrives, and a speed reaching the station ahead of the power is a locomotive
that rolls the moment somebody makes the rails live
([#333](https://github.com/rails49/control/issues/333),
[ADR-0054](../adr/0054-the-railroad-comes-up-at-rest-and-points-replay.md)).

The app is also constructed on the bus directly, with where the station is
served:

```python
DccEx(bus, "dccex-usb", 2560, startup=Path("/etc/tc49/dccex-startup.txt"))
```

That is what `--startup` on this app's own command line does, and what the
harness's physical wiring does when it brings a run up on the physical
binding — this app and `layout` where the simulator would be
([bench/runner.py](../../src/tc49/bench/runner.py),
[#314](https://github.com/rails49/control/issues/314)). There is nowhere else
for the file to go, so `--startup` without `--station` is refused in a sentence
rather than accepted and dropped
([#334](https://github.com/rails49/control/issues/334)).

`run()` is the connection: it connects, applies the retained desired state,
reads what the station says until the link goes, and reconnects with backoff.
Nothing else waits on it — a desired value arriving while the link is down is
remembered and applied on the next connect, the way the retained value is at
startup. **No dependency is added**: the whole of it is `asyncio` streams, and
the image builds with `uv sync --frozen`.

**asyncio owns this app's process, and the session's only where a station is
named.** `_send` writes to an `asyncio.StreamWriter` from inside a bus
subscriber, so whichever thread drains the bus is the thread that writes to the
station: with the loop owning the process every subscriber already runs on the
loop thread and that write is where it belongs. Under `python -m tc49.dccex`
the drain is a coroutine beside `run()`, and the MQTT client's network thread
only appends to the queue that drain empties. Putting this app on a daemon
thread under a synchronous owner would mean marshalling with
`call_soon_threadsafe` — a cross-thread write where none exists today. A
session on the simulator keeps the synchronous loop it has always had; the two
share a signature and nothing else.

A signal is what ends the process, and the railroad is stood down on the way
out: the same `shutdown()` a session calls, before the link is let go.

## Checking it against a real station

Nothing in the test suite needs the hardware — the connection is injected and
the tests drive a socket pair — so the gate is green on a machine with nothing
plugged in. Verifying the actual link is runtime's job, and the row that
reports it is `device/link`.

With the railroad powered and a locomotive on address 3 standing on the main:

```
$ nc blocks49.local 2560
<s>
<iDCC-EX V-5.4.16 / ESP32 / EXCSB1_WITH_EX8874 G-devel-202504182148Z>
<p1 A>
<p1 B>
<p1>
<t 3 63 1>
<l 3 1 191 0>
```

The banner naming the firmware, the board and the motor shield is the station
answering through the mirror, which is what `device/link: up` is made of; the
`<p…>` lines are what `device/track` is folded from; and the `<l>` line is the
station saying what the locomotive is now doing, speed byte 191 being the
forward bit over step 63.

**Then wait, and watch the locomotive.** It should still be running ten
seconds later, and no further `<l 3 …>` should appear on the port. This is the
step that matters and the one the suite cannot take: every check above passes
against a station that is quietly stopping the train a second later, which is
exactly what a `<!Q>` in the poll did
([#463](https://github.com/rails49/control/issues/463)). A speed byte of 129 —
the direction bit over step 1 — is the emergency stop, and seeing one arrive
that nobody sent means something on this port is commanding the station rather
than asking it.

Send `<t 3 0 1>` to stop it again. `<!>` stops every locomotive at once and any
throttle may drive away from it afterwards, which is what `stopped` means here;
sending it is safe and leaves nothing to clear.

The version in the banner is worth reading. This station is older than the
firmware the mapping was researched against, and the difference is silent: an
unknown command draws no `<X>` and no reply at all, so a command this station
does not have does something else or does nothing, with nothing said either
way.
