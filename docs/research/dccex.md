# What DCC-EX offers

Resolves [#195](https://github.com/rails49/control/issues/195). What the
DCC-EX command station gives a hardware binding of the layout interface, read
against the contract in [SYSTEM.md](../SYSTEM.md#layout-interface),
[ADR-0040](../adr/0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md)
and [ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md).
Sections 1–5 are fact with a source per claim; section 6 is inference and says
so. DCC-EX is a product name and belongs on a binding's own page, never in a
normative doc; this file is research, not contract.

Sources, pinned:

- **Firmware**: [DCC-EX/CommandStation-EX](https://github.com/DCC-EX/CommandStation-EX)
  at commit `0ad3080` (2026-07-22, `version.h` says `5.6.3`); the latest
  tagged release is `v5.6.1-Prod` (2026-07-06). File:line references below
  are against that commit.
- **Command summary**: [command-summary-consolidated.html](https://dcc-ex.com/reference/software/command-summary-consolidated.html).
- **TrackManager**: [dcc-ex.com/trackmanager](https://dcc-ex.com/trackmanager/index.html),
  [dcc-vs-dc.html](https://dcc-ex.com/reference/hardware/dcc-vs-dc.html).
- **Hardware**: [motor-boards.html](https://dcc-ex.com/reference/hardware/motor-boards.html),
  [motor-board-config.html](https://dcc-ex.com/reference/hardware/motorboards/motor-board-config.html),
  [ex-motor-shield-8874.html](https://dcc-ex.com/reference/hardware/motorboards/ex-motor-shield-8874.html),
  [ex-csb1](https://dcc-ex.com/ex-csb1/index.html),
  [rtr-connecting.html](https://dcc-ex.com/ex-commandstation/rtr-connecting.html),
  [rtr-booster.html](https://dcc-ex.com/ex-commandstation/rtr-booster.html).
- **EX-WebThrottle**: [ex-webthrottle](https://dcc-ex.com/ex-webthrottle/index.html)
  and [DCC-EX/WebThrottle-EX](https://github.com/DCC-EX/WebThrottle-EX)
  (`master`, GPL-3.0, last push 2026-05-22, changelog top 1.3.51).

## 1. The command set as it bears on the contract

Every command is `<letter params>` over a byte stream. Replies to a command go
back to the stream that sent it; *broadcasts* (section 2) go to every client.
Speeds and addresses below are as the firmware parses them, which is stricter
than the summary page in places.

| Command | What the station does | Reply / broadcast | Firmware |
| --- | --- | --- | --- |
| `<t cab speed dir>` | Sets cab speed. `speed` is `-1` (emergency stop) or `0..126`; the parser maps `-1`→DCC 1, `1..126`→`2..127`. `dir` 1 = forward. `cab` 1..10239. The station remembers the speed in a slot and *re-sends it as a reminder packet forever* (the DCC refresh loop), so a throttle sets a target and walks away. | Broadcast `<l cab 0 speedByte functMap>` to everyone. The 4-param legacy form also gets `<T reg speed dir>` back. | `DCCEXParser.cpp:331-389`, `DCC.cpp:101-135`, reminders `DCC.cpp:1015-1060` |
| `<t cab>` | Reports the slot for a cab. | `<l cab ...>` or `<l cab -1 128 0>` if unknown | `DCCEXParser.cpp:337-347` |
| `<F cab fn 0\|1>` | Function F0–F68 on/off; state held in the slot and refreshed. | Broadcast `<l ...>` | `DCCEXParser.cpp:795`; summary page |
| `<!>` | **Emergency stop all**: one DCC broadcast packet (address 0, speed code 1) to every decoder, DC tracks set to stop, every slot's reminder rewritten to e-stop. Track stays powered. Throttles "can immediately start driving again". | `<l cab 0 1 0>` per slot | `DCCEXParser.cpp:699-705`, `DCC.cpp:1190-1213` |
| `<!P>` / `<!R>` / `<!Q>` | **E-stop lock**: same broadcast, then *every* throttle packet is blocked and replaced by the e-stop packet until `<!R>`. Reminders keep their pre-lock speeds so locos resume on release. `<!Q>` queries. Not on the summary page; firmware only. | Broadcast `<!PAUSED>` / `<!RESUMED>` | `DCCEXParser.cpp:700-703`, `DCC.cpp:1216-1231`, `CommandDistributor.cpp:382` |
| `<a addr sub act>` / `<a linear act>` | Sends a basic accessory packet (on, then off after 100 ms). 9-bit address, 2-bit sub, linear 1..2044. **Stateless**: "It does not store or retain any information regarding the current status of that accessory." | Nothing | `DCCEXParser.cpp:395-436`, `DCC.cpp:371-405` |
| `<T id C\|T>` (also `0\|1`) | Throws a turnout *defined in the station* (`<T id DCC addr sub>`, servo, or vpin). The station keeps its position, optionally in EEPROM. DCC++ classic polarity: throw writes a 1 in the packet unless `DCC_TURNOUTS_RCN_213` is compiled in. | `<H id 1\|0>` broadcast on change; `<X>` on failure | `DCCEXParser.cpp:1181-1233`, `Turnouts.cpp:110-125,378-387` |
| `<A addr aspect>` | Extended accessory (RCN-213) packet: 11-bit address, 5-bit aspect, "0 is always stop". Stateless. If EXRAIL has a `DCCX_SIGNAL` on that address it intercepts the command first. | Nothing | `DCCEXParser.cpp:438-443`, `DCC.cpp:407-458`, `EXRAIL2Parser.cpp:53-58` |
| `<1>` / `<0>` | Track power on/off: no arg = all tracks; `MAIN`, `PROG`, `JOIN` (prog track carries the main signal), or a track letter `A`–`H`. `<0>` also drops JOIN. | `<p…>` broadcasts, see section 2 | `DCCEXParser.cpp:637-697` |
| `<= A MODE [cab]>` | TrackManager: set the mode of output A–H. Modes parsed: `MAIN`, `MAIN_INV`, `MAIN_AUTO`, `PROG`, `OFF`/`NONE`, `EXT`, `BOOST`/`BOOST_INV`/`BOOST_AUTO` (only with `BOOSTER_INPUT`), `AUTO`, `INV`, `DC cab`, `DC_INV cab`/`DCX cab`. **A mode change switches that track's power off** ("a safety precaution to prevent runaway locos"). No current-limit argument exists. | Broadcast `<= A MODE [cab]>` then the power broadcast | `TrackManager.cpp:388-441`, `TrackManager.cpp:375-377` |
| `<=>` | Lists every track's mode. | `<= A MAIN>` … per track | `TrackManager.cpp:391-395` |
| `<s>` | Status. **The only "get power status" command.** | `<iDCC-EX V-… / board / shield G-sha>`, the full power broadcast, `<H…>` per turnout, `<Q…>`/`<q…>` per sensor | `DCCEXParser.cpp:719-725` |
| `<JI>` / `<JG>` | Current per track / trip threshold per track, in mA. `<JI>` reports `-1` for a track in OVERLOAD. | `<jI mA mA …>`, `<jG mA mA …>` | `DCCEXParser.cpp:838-846`, `TrackManager.cpp:639-647,680-687` |
| `<c>` | Legacy JMRI meter: **track 0 only**, "regardless of track settings". | `<c CurrentMAIN mA C Milli 0 max 1 trip>` | `TrackManager.cpp:626-637` |
| `<S id vpin pullup>` / `<S>` / `<Q>` | Define a sensor on a (virtual) pin; list definitions; list current states. | `<Q id vpin pullup>` per definition; `<Q id>`/`<q id>` per state | `Sensors.cpp:40-67`, `DCCEXParser.cpp:502,715` |
| `<D SPEED28\|SPEED128>` | Speed-step mode for throttle packets. | — | `DCCEXParser.cpp:1295-1300` |
| `<m cab accel [decel]>` | Momentum in ms/step, applied by the station's reminder loop. | — | `DCCEXParser.cpp:531` |
| `<- [cab]>` | Forget slot(s): stops refreshing, does not stop the loco. | `<l cab 0 1 0>` `<- cab>` | `DCCEXParser.cpp:789`, `CommandDistributor.cpp:302` |

DC mode, for completeness: `<= A DC 1234>` gives the *output* a virtual cab
address, and `<t 1234 …>` then drives the whole track as PWM; "In DC mode the
direction is dependent upon the track polarity"
([dcc-vs-dc.html](https://dcc-ex.com/reference/hardware/dcc-vs-dc.html)).

## 2. What the station broadcasts unasked

Broadcast routing (`CommandDistributor.cpp:40-50,137-170`): a broadcast of
type `COMMAND_TYPE` is written to **every serial port** the station parses
commands on, **every TCP client whose first byte was `<`**, and every
WebSocket client. WiThrottle clients get a translated form of some of them.

| Broadcast | When | Firmware |
| --- | --- | --- |
| `<p1 A>` / `<p0 B>` per track, then `<p1>` or `<p0>` **only if every track is on / none is on** (a mixed state sends no global line), then `<p1 MAIN>`, `<p1 PROG>`, or `<p1 JOIN>` | Whenever a `setTrackPower` call actually changed a track's power, on every mode change, and on `<s>`. The per-track digit is `'1'` only for `POWERMODE::ON`; `ALERT` (powered, watching) and `OVERLOAD` (cut) both print `0`. | `CommandDistributor.cpp:306-380`, `TrackManager.cpp:558-559,588-589,615-624` |
| `<H id 1\|0>` | A station-defined turnout changed position, from any client or from EXRAIL. Only on real change. | `Turnouts.cpp:110-125`, `CommandDistributor.cpp:179` |
| `<Q id>` / `<q id>` | A defined sensor went active / inactive. Sensors are polled round-robin: a new cycle starts every 10 ms (`cycleInterval = 10000` µs), a change must hold for one extra scan (`minReadCount = 1`), at most one change is broadcast per pass and at most 16 sensors are read per `loop()`. Pin-change devices can push the state in, but the broadcast still waits for the scan. | `Sensors.cpp:93-159`, `Sensors.h:88-90` |
| `<l cab 0 speedByte functMap>` | Any speed or function change to a slot, from any client, `<!>`, and consist followers. | `CommandDistributor.cpp:231-300` |
| `<= A MODE [cab]>` | Track mode change. | `TrackManager.cpp:484-500` |
| `<!PAUSED>` / `<!RESUMED>` | E-stop lock set / cleared. | `CommandDistributor.cpp:382-390` |
| `<jC minutes rate>` | Fast clock tick. `<I id pos moving>` turntable. `<m "text">` free-text message from EXRAIL. | `CommandDistributor.cpp:189-230,392` |
| `<* … *>` diagnostics, e.g. `<* TRACK A POWER OVERLOAD 5123mA (max 5000mA) detected after … *>`, `<* TRACK A POWER RESTORE … *>`, `<* TRACK A NORMAL … *>` | **USB serial only**: `DIAG` prints straight to `USB_SERIAL`, never into the TCP ring. | `StringFormatter.cpp:36-42`, `MotorDriver.cpp:572-663` |

**What is not broadcast.** An overload trip. `checkPowerOverload` calls
`MotorDriver::setPower(OVERLOAD)` directly (`MotorDriver.cpp:613,630`) and
only `TrackManager::setTrackPower` / `streamTrackState` call
`broadcastPower`, so a district that trips and later restores produces no
`<p…>` line on any client. It is visible by polling `<JI>` (`-1` for that
track) or `<s>` (per-track `<p0 A>`), by the `<* … *>` line on USB, or through
an EXRAIL `ONOVERLOAD(A)` handler in the station (`EXRAILMacros.h:647`,
`EXRAIL2.cpp:1564`). Also not broadcast: `<a>` and `<A>` results (stateless),
current readings (poll `<JI>`), and RailCom block enter/exit, which go to
EXRAIL `ONBLOCKENTER`/`ONBLOCKEXIT` only (`Railcom.cpp:72`).

Initial state is served on request, not on connect: a new client gets nothing
until it sends `<s>`.

## 3. The link: serial, and what port 2560 is

**Serial.** `SerialManager` opens the USB port at 115200 and parses `<…>` from
it; `SERIAL1_COMMANDS`…`SERIAL6_COMMANDS` and `SERIAL_BT_COMMANDS` add more
command ports, each a peer (`SerialManager.cpp:54-96`, `config.example.h:304,328`).
A serial port carries one byte stream: the station has no notion of two
clients behind one serial, replies to a command go to that port, and every
broadcast goes to every command serial (`SerialManager.cpp:108-113`). Serial
and network are serviced in the same `loop()` and broadcasts fan out to both
(`CommandStation-EX.ino:189-205`, `CommandDistributor.cpp:143-165`), so USB
and WiFi/Ethernet work concurrently; the docs do not say so, the code does.

**TCP 2560.** `IP_PORT` defaults to 2560 (`config.example.h:79`,
`defines.h:297-300`); the EX-CSB1 quick start says "The IP address is usually
`192.168.4.1` when using Access Point mode, and the port is `2560`". It is
**one listener for every protocol**: on a client's first transmission the
distributor looks at the first byte — an HTTP `GET` is a WebSocket upgrade,
`<` is a native client, anything else is WiThrottle — and remembers the type
per client (`CommandDistributor.cpp:66-100`, `Websockets.cpp:25-50`). mDNS
advertises the same port as `_withrottle._tcp` (`WifiESP32.cpp:322`,
`EthernetInterface.cpp:120`, `WifiInterface.cpp:381`). The station
multiplexes clients itself: `MAX_NUM_TCP_CLIENTS` is 10 on ESP32, 9 on STM32
Ethernet, 8 on serial WiFi shields (`defines.h:275-285`); an Arduino Ethernet
shield is bounded by its `MAX_SOCK_NUM` (`EthernetInterface.cpp:46-47,146-147`);
the ESP8266-AT path uses `CIPMUX=1` (`WifiInterface.cpp:377`) and the docs
size it at "up to 5 WiFi Throttles". Every native client receives every
broadcast; replies to a command go only to its sender. All clients are peers:
nothing in the firmware ranks them, so any client may `<1>`, `<0>` or `<t>`.

Answer to the ticket's question: the serial link cannot be shared by two host
processes at the station's end — that multiplexing has to be a host-side
proxy. Over TCP the station already is that proxy, and it also serves a
browser directly over WebSocket on the same port.

## 4. Per-track current limiting that already exists

**Every output is a `MotorDriver` with its own trip current.** The board
definition passes `tripMilliamps` per output
(`MotorDriver(power, signal, signal2, brake, current, senseFactor, tripMilliamps, fault)`,
[motor-board-config.html](https://dcc-ex.com/reference/hardware/motorboards/motor-board-config.html)).
The constructor converts it to a raw ADC threshold, caps it at the optional
global `MAX_CURRENT` from `config.h` ("in mA", to protect an undersized
supply), and clamps it to what the ADC can read (`MotorDriver.cpp:197-215`,
`config.example.h:68-73`). A prog track uses a fixed 250 mA (`TRIP_CURRENT_PROG`,
`MotorDriver.h:388`) except during ACK, JOIN or boost.

Stock definitions (`MotorDrivers.h:72-131`), trip in mA per output:

| `MOTOR_SHIELD_TYPE` | Outputs | Trip | Fault pin | Docs |
| --- | --- | --- | --- | --- |
| `STANDARD_MOTOR_SHIELD` (Arduino R3 / clones) | 2 | 1500 | none | "1.3 – 1.5" A |
| `EX8874_SHIELD` (EX-MotorShield8874) | 2 | 5000 | yes | "peak 5A of load per channel", DRV8874, "Fault detection in addition to overcurrent reporting" |
| `EXCSB1` | 2 | 5000 | yes | "dual … 5A outputs, including variable current limit control", "Software programmable over-current protection, and hardware over-current, over-temperature and reverse voltage protection" |
| `EXCSB1_WITH_EX8874` | 4 | 5000 each | yes | "four total districts" |
| `IBT_2_WITH_ARDUINO`, `POLOLU_*`, … | 1–2 | per definition | varies | see motor-boards.html |

**Trip behaviour** is a per-output state machine `ON → ALERT → OVERLOAD →
ALERT → ON` documented in a comment block (`MotorDriver.cpp:495-553`, code
`555-672`). From `ON`, a fault pin or a current sample over the threshold
moves to `ALERT` (still powered); 100 ms of overcurrent (5 ms if the fault
pin agrees) cuts that output to `OVERLOAD`; it retries after 40 ms, doubling
each time up to 10 s, and returns to `ON` after 20 ms of good samples. Only the
affected output is cut, "unless fault pins are shared" (the Arduino shield's
common fault pin, `MotorDriver.h:255`). A `MAIN_AUTO` track inverts its phase
on `ALERT` instead — that is the auto-reverser. One output is sampled per
`DCC::loop()` pass, round robin (`TrackManager.cpp:506-518`, `DCC.cpp:1016`).
An EX-CSB1 in booster mode kills all its outputs when the district it follows
shorts ([rtr-booster.html](https://dcc-ex.com/ex-commandstation/rtr-booster.html)).

**No runtime command sets a trip current.** `parseEqualSign` takes a mode and
an optional DC cab and nothing else; `<D ACK LIMIT>` is the prog-track ACK
detection threshold, not a trip (`DCCEXParser.cpp:1326-1331`). The docs agree
the limit "must be set when creating the MotorDriver definition". The
EX-CSB1's "variable current limit control" is not a firmware knob I could
find; whether it is a hardware setting on the DRV8874 is left open here (the
board's schematic was not read).

**What a per-district current-limit command would touch**, from the code:

1. `MotorDriver`: a setter that reassigns `tripMilliamps`, recomputes
   `rawCurrentTripValue` with the same `MAX_CURRENT` cap and ADC clamp the
   constructor applies (`MotorDriver.cpp:197-215`), and leaves
   `progTripValue` alone. `checkCurrent` reads the raw value each sample, so
   the new limit takes effect on the next pass with no other change
   (`MotorDriver.h:323-329`).
2. `TrackManager::parseEqualSign`: one new branch, e.g.
   `<= A LIMIT mA>`, resolving the letter to `track[t]` the way the DC form
   does (`TrackManager.cpp:437-443`). No `DCCEXParser` change unless a new
   top-level letter is wanted (`DCCEXParser.cpp:771`).
3. Reporting comes free: `<JG>` already reads the live raw trip value
   (`TrackManager.cpp:680-687`) and the LCD line does too. A broadcast would
   need either a new `<jG …>` push or an extension of `streamTrackState`'s
   format (`TrackManager.cpp:484-500`).
4. Optional persistence through `EEStore`, and a docs entry.
5. Hardware bound: the firmware limit only bites below the H-bridge's own
   protection, and above `MAX_CURRENT`'s cap it is silently reduced.

## 5. EX-WebThrottle as prior art

- A static page (HTML, jQuery, JavaScript), hosted at
  `https://DCC-EX.github.io/WebThrottle-EX` and downloadable as an
  `index.html` bundle; a PWA (`manifest.json`, `sw.js`). GPL-3.0, version
  1.3.51.
- Connects with the **Web Serial API only**: `navigator.serial.requestPort()`
  and `port.open({ baudRate: 115200 })` in `js/commandController.js`; "USB
  serial cable from your computer"; Chromium 89+ (Chrome, Opera, Edge). No
  TCP or WebSocket path, although the station would accept one on 2560.
- Sends `<s>`, `<t …>`, `<F …>`, `<0>`/`<1>`, `<JR>`, `<JA>`, `<JT>`,
  `<R …>`, `<D WIFI SHOW>`; parses `<p`, `<l`, `<H`, `<j…`, `<i`, `<r`/`<v`,
  `<m` and `<*` by first characters (`js/commandController.js`).
- UI: one active loco (rotary knob or vertical slider, ±, up/stop/down
  direction), function buttons with per-loco labels, power slider,
  turnouts/points page driven from the station's `<JT>` list, routes page from
  `<JA>`, CV programmer, and a log window: "The commands being sent to the
  Command Station and its responses will display in the log window." An
  emulator mode runs without hardware (`js/emulator.js`).

## 6. What it means for the contract

Everything in this section is **inference** from the facts above, offered for
the binding's design; nothing here amends SYSTEM.md.

**The vocabulary fits, with one seam to choose.** The contract's transit-level
`align` carries address-and-position pairs and expects an adapter that "throws
what it is told and holds no table" (SYSTEM.md). That is `<a linear act>`
exactly: stateless, one packet per pair. `<T id C|T>` would instead put a
turnout table in the station and return `<H>` broadcasts, which the contract
has no reader for. Prefer `<a>`; `<T>` is what the station's own throttles and
JMRI expect, so a layout that also runs those may want the table anyway.
`<A addr aspect>` is a signal head on the rails, not a dispatcher aspect, and
stays unused unless physical signals are driven from the layout interface.

**The throttle-up / watch-the-detector / stop loop maps directly.** `cross`
becomes `<t cab speed dir>` (with the station refreshing the packet),
the detector is a `<Q id>` on a station-defined sensor, and the stop is
`<t cab 0 dir>` or `<t cab -1 dir>`. Sensor ids are anonymous integers, which
is what the contract's "anonymous occupancy sensors" asks for, and `<q id>`
gives the release half. The 10 ms scan and one-change-per-pass rule bound
detector latency at the station; the bound on a transit in ADR-0040 has to
include it. Momentum (`<m>`) and the braking curve can live in the station or
the binding; the contract says the binding owns them, which argues for
`<m cab 0>` and shaping speed in the binding.

**`state/power` has an observable for each value, but not a clean one.** `on`
is `<p1>` or the relevant `<p1 A>`; `off` is `<p0 …>`; the station's
e-stop lock (`<!P>` → `<!PAUSED>`) is the only *state* that matches
`stopped`, since a plain `<!>` changes nothing observable afterwards. Two
gaps matter for ADR-0041: an **overload trip is silent** on TCP, so a binding
that wants `off` to be true when a district has tripped must poll `<JI>` or
`<s>` at some cadence or run an `ONOVERLOAD` script in the station; and the
per-track digit reports `ALERT` as `0` while the rails are still live, so
`<p0 A>` is "not `on`", not "no volts". Both are arguments for the binding
publishing `off` conservatively on anything but `1`.

**Stopping is the two commands ADR-0040 names, and neither is a watchdog.**
`<!>` is the emergency-stop broadcast, needing power and reachability;
`<0 A>` is the supply cut, per district, so accessory decoders on a separate
output (`<= C MAIN>`) can keep their supply while a running district loses
it — which softens ADR-0041's "no point position can be trusted afterwards"
for a layout wired that way. Nothing in the firmware drops power when a client
disappears; the relay under the software that ADR-0040 requires is still the
backstop. The e-stop lock is worth noting as a station-side "held": while
locked, no throttle from any client moves anything until `<!R>`.

**Topology.** One native client on 2560 is enough for the binding, and the
station will multiplex Engine Driver, JMRI and a browser beside it. But every
client is a peer: the bus's one-writing-role rule (ADR-0035) stops at the
binding, and a person's throttle app can move a train the dispatcher has not
granted. The `<l>` broadcast is how the binding would notice; what it does
then is the open half of SYSTEM.md's "unexpected sensor" question, seen from
the other side.

**Per-district current limits are a firmware change, not a command.** The
station has the state (one trip value per output, read live by the sampler)
and the reporting (`<JG>`), and lacks only the setter and a parse branch
(section 4). It is a small patch to a GPL-3.0 project with an active
maintainer; the ticket's "new per-district current-limit command" is
feasible and touches four places.
