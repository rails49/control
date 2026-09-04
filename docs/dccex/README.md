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
| `wanted/track` `stopped` | `<!P>`, the station's emergency-stop **lock** |
| `wanted/function/<addr>/<n>` `value` | `<F addr n 0\|1>` |

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

Three rules are not a row of the table, and each is a way a train could
otherwise move on its own.

**The stop must latch.** `stopped` is `<!P>` and not `<!>`. The one-shot
`<!>` broadcasts an emergency stop and changes nothing afterwards, so any
throttle on the same port can drive away from it — which would make
`state/power` an echo of a command rather than an observation, and a lie the
moment somebody picks up a hand-held throttle. `<!P>` blocks every throttle
packet until `<!R>`, and `<!Q>` asks whether it is on, so a restart reads the
state back rather than remembering it.

**Clearing a stop is zero-then-release.** Under the lock the station keeps
every locomotive's pre-lock speed and resumes it on release, so a bare `<!R>`
restarts every train at the speed it was doing when somebody hit stop. Every
locomotive this app has ever commanded is sent step 0 **first**, and only then
`<!R>`. Nothing in the software is in the path of those resumed packets, which
makes this the one remaining way a train moves without being asked, and it has
a named test asserting the byte order. The release fires on an `on` following
either a lock this app commanded or one the station has reported, because the
two are a round trip apart and releasing without the zeros is the failure that
matters; an unnecessary set of zeros stops trains that were already standing.

**An overload is polled for.** A district that trips is not broadcast on TCP:
the firmware cuts the output directly and prints the diagnostic to USB serial
only, so no client sees a `<p…>` line for it. Once a second this app sends
`<s>`, which makes the station restate every track's power, and `<!Q>`, which
makes it restate the lock. `device/track` telling the truth does not depend on
a person noticing.

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
way switching the power back on is. The zeros come first for the same reason a
release's do: the station keeps a speed per locomotive and resumes it, so
cutting the supply over a held speed only postpones the motion.

A link that was never open sends nothing at all. A railroad this app could not
reach is one it was not driving, and `_send` drops rather than queues.

## The command line

It has none of its own, and that is the milestone and not the app: the bus is a
Python object inside one process ([SYSTEM.md](../SYSTEM.md#the-bus)), so no
app that speaks a bus topic has a command line — `layout`, `scheduler`,
`dispatcher` and `driver` have none either. `dccex-usb` does, and it is the
one app that speaks no bus topic at all.

The app is constructed on the bus like the rest of them, with where the
station is served:

```python
DccEx(bus, "dccex-usb", 2560, startup=Path("/etc/tc49/dccex-startup.txt"))
```

What constructs it today is `tc49 live <railroad> --station <host>:<port>`,
which brings a session up on the physical binding — this app and `layout`
where the simulator would be — and hands `--startup` straight through as that
argument ([bench/runner.py](../../src/tc49/bench/runner.py),
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

**asyncio owns that session's process, and only where a station is named.**
`_send` writes to an `asyncio.StreamWriter` from inside a bus subscriber, so
whichever thread drains the bus is the thread that writes to the station: with
the loop owning the process every subscriber already runs on the loop thread
and that write is where it belongs. Putting this app on a daemon thread under
a synchronous owner would mean marshalling with `call_soon_threadsafe` — a
cross-thread write where none exists today. A session on the simulator keeps
the synchronous loop it has always had; the two share a signature and nothing
else.

It gets a command line, and `deploy/` gets a container for it, the day the
broker arrives and each app is its own process
([ADR-0013](../adr/0013-apps-are-deployment-units.md)).

## Checking it against a real station

Nothing in the test suite needs the hardware — the connection is injected and
the tests drive a socket pair — so the gate is green on a machine with nothing
plugged in. Verifying the actual link is runtime's job, and the row that
reports it is `device/link`.

With the railroad powered and a locomotive on address 3 standing on the main:

```
$ nc blocks49.local 2560
<s>
<iDCC-EX V-5.6.3 / ESP32 / EXCSB1_WITH_EX8874 G-0ad3080>
<p0>
<1>
<p1 A>
<p1 B>
<p1>
<t 3 63 1>
<l 3 0 191 0>
<!P>
<!PAUSED>
```

The banner naming the firmware, the board and the motor shield is the station
answering through the mirror, which is what `device/link: up` is made of; the
`<p…>` lines are what `device/track` is folded from; and the locomotive should
stop on `<!P>` and **stay** stopped when you send `<t 3 63 1>` again, which is
the lock doing what the one-shot would not.

To get it back, send `<t 3 0 1>` and then `<!R>`, in that order — the app's
rule, done by hand — and the locomotive should still be standing after the
release. Doing it in the other order is the failure the rule exists for: the
station is holding the speed it had when the lock went on, and a bare `<!R>`
resumes it. Nothing in the software is in the path of those packets, so do not
send one to find out.
