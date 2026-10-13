# What control asks of a command station, in DCC-EX and in JMRI

Lists each capability control expects from the hardware under the layout
interface, the DCC-EX command that carries it, and the JMRI interface that
carries it, with how JMRI is reached from outside its own process. The point
is to see which capabilities a JMRI path can carry for any command station
JMRI supports, which it carries only for some connections, and which it
cannot carry at all.

Two earlier notes cover ground this one does not repeat.
[docs/research/jmri.md](https://github.com/rails49/control/blob/research/jmri/docs/research/jmri.md)
(#196) reads the JSON servlet: envelope, session, `get` as subscribe,
throttle sharing, and two clients on DCC-EX's port 2560.
[docs/layout/DEVICES.md](../layout/DEVICES.md) maps each device row onto a
JSON message and a DCC-EX command. This note goes one level down: the JMRI
core interfaces behind those JSON messages, which `jmrix` connections
implement them, and the capabilities that have no device row.

Sources are pinned:

- `rails49/control@cd9ea49` (main, 2026-10-13). Column 1 is read from
  [BUS.md](../BUS.md#device-vocabulary), `src/tc49/layout/interface.py`,
  [GOALS.md](../GOALS.md) and [MILESTONE-2.md](../MILESTONE-2.md).
- `rails49/dccex@2cf5036` (main, 2026-10-12), cloned at `~/iot/dccex`. What
  the translator sends is `src/dccex/commands.py`; what it reads is
  `src/dccex/replies.py`; its page is `docs/dccex/README.md`.
- `rails49/CommandStation-EX@a1b729b` (tag `v5.6.4-rails49.18`, 2026-10-12),
  cloned at `~/iot/CommandStation-EX`. This is the rails49 fork of DCC-EX
  5.6.4. A command marked (rails49) is in the fork and not upstream; the
  fork's own reference is `docs/commands.md`, which points to the upstream
  [command summary](https://dcc-ex.com/reference/software/command-summary-consolidated.html)
  for the rest. Paths in the DCC-EX column are into this checkout.
- `JMRI/JMRI@23604e8` (master, 2026-08-26), the commit #196 and
  [roster.md](roster.md) were read at. Paths in the JMRI column are under
  `java/src/jmri/` unless they start with `help/`. Cloned shallow and read
  only.

The control column says where the capability stands in this repository:

- `today`: `layout` writes the row, or a participant publishes it, now.
- `declared`: a row of the device vocabulary that nothing writes or
  publishes yet.
- `translator`: done by the DCC-EX translator for its own purposes, on no
  bus row.
- `goal`: named only in GOALS.md.
- `out`: ruled out in MILESTONE-2.md.

## The table

| # | Capability control expects | Control | DCC-EX | JMRI | Notes |
| --- | --- | --- | --- | --- | --- |
| Locomotives | | | | | |
| 1 | Set one locomotive's speed and direction: `wanted/traction/<addr>`, a signed fraction of maximum ([BUS.md:715](../BUS.md#device-vocabulary)) | today (`interface.py:741`) | `<t cab speed dir>`, speed 0–126, dir 1 forward (`DCCEXParser.cpp:332`; translator `commands.py:121`) | `ThrottleManager.requestThrottle` (`ThrottleManager.java:82`) returns a `DccThrottle`; `Throttle.setSpeedSetting(float)` and `setIsForward` (`Throttle.java:262`, `:301`). DCC-EX: `DCCppThrottle.setSpeedSetting` (`jmrix/dccpp/DCCppThrottle.java:180`). JSON `throttle` with `speed` and `forward` (`server/json/throttle/JsonThrottle.java:238-243`); WiThrottle `M` (`jmrit/withrottle/DeviceServer.java:215`) | JMRI's speed is a magnitude 0.0–1.0 with any negative value an emergency stop (`Throttle.java:253-262`), so the sign goes to `setIsForward`. Both sides report the commanded speed, not the moving one: DCC-EX broadcasts `<l cab 0 speedbyte fn>` to every client on any change (`CommandDistributor.cpp:231`; `docs/commands.md`, *The loco line*), and JMRI's DCC-EX throttle takes it in (`DCCppThrottle.java:324`). Control reads neither. |
| 2 | Set one decoder function on or off: `wanted/function/<addr>/<n>`, a boolean ([BUS.md:716](../BUS.md#device-vocabulary)) | declared (no writer, `interface.py:144`) | `<F cab fn 0\|1>` (`DCCEXParser.cpp:800`; translator `commands.py:138`) | `Throttle.setFunction(int, boolean)` (`Throttle.java:311`); DCC-EX sends `<F>` (`DCCppThrottle.java:89-92`). JSON `F<n>` on the throttle, up to the throttle's own function count (`JsonThrottle.java:258-261`) | JMRI also has momentary functions (`Throttle.java:325`); the bus has no word for them. |
| 3 | Drive several locomotives in one train | today, as one traction row per addressed car (`interface.py:123-128`, `:670-713`) | Not used. The station has consists, `<^ …>` (`DCCEXParser.cpp:814`) and CV19 by `<W CONSIST …>` (`:571-572`) | `ConsistManager` (`ConsistManager.java:31`). DCC-EX registers none and gets the default `NmraConsistManager` (`jmrix/DefaultSystemConnectionMemo.java:328-336`); NCE has its own (`jmrix/nce/NceConsistManager.java`). JSON `consist` answers 503 where no manager exists (`server/json/consist/JsonConsistHttpService.java:46`) | Not needed: `layout` composes each car's sign itself (ADR-0045). Listed because JMRI offers it. |
| Points and signals | | | | | |
| 4 | Set a point `closed` or `thrown`: `wanted/point/<addr>` ([BUS.md:717](../BUS.md#device-vocabulary)) | today (`interface.py:543`) | `<a addr sub act>`, a stateless accessory packet; the translator splits the linear number four to a decoder (`DCCEXParser.cpp:396`; `commands.py:152-173`). The alternative `<T id 0\|1>` drives a turnout the station holds in a table (`DCCEXParser.cpp:446`) | `TurnoutManager.provideTurnout` (`TurnoutManager.java:75`), `Turnout.setCommandedState` (`DigitalIO.java:38`) with `CLOSED`/`THROWN` (`Turnout.java:82-89`). DCC-EX: `DCCppTurnout.forwardCommandChangeToLayout` (`jmrix/dccpp/DCCppTurnout.java:177-222`) sends `<a>` in DIRECT mode with the same linear split (`DCCppMessage.java:1858-1869`), `<T>` in MONITORING, `<Z>` in EXACT. JSON `turnout` post state 2 or 4; WiThrottle `PTA` (`DeviceServer.java:322`) | Which DCC-EX command JMRI sends is the turnout's configured feedback mode, not a choice per message. |
| 5 | Report a point's measured position: `device/point/<addr>` ([BUS.md:762](../BUS.md#device-vocabulary)) | declared, and a goal (GOALS.md, *What the app is assumed to be told*) | None measured. `<H id state>` is the station's table repeating what it was told (`Turnouts.cpp:110-118`, broadcast at `CommandDistributor.cpp:179-183`); the translator reads it only for its script (`replies.py:71-89`) and publishes no `device/point` ([BUS.md:877-881](../BUS.md#device-vocabulary)) | `Turnout.getKnownState` (`DigitalIO.java:56`) under a feedback mode (`Turnout.java:90-142`). JSON returns `state` and `feedbackMode` (`server/json/turnout/JsonTurnoutHttpService.java:55`, `:70`) | Varies by connection. Every connection has ONESENSOR and TWOSENSOR, which take the position from JMRI sensors (`implementation/AbstractTurnout.java:319`). Hardware feedback: LocoNet EXACT and INDIRECT (`jmrix/loconet/LnTurnout.java:57`), XpressNet EXACT (`jmrix/lenz/XNetTurnout.java:149`), which Z21 inherits (`jmrix/roco/z21/Z21XNetTurnout.java:15`). DCC-EX's MONITORING and EXACT are the station's own echo ("fakes the response", `DCCppTurnout.java:35-41`). NCE adds MONITORING only (`jmrix/nce/NceTurnout.java:64`). DIRECT returns the commanded state (`Turnout.java:90-96`). |
| 6 | Show `stop`, `caution` or `clear` on a signal: `wanted/signal/<addr>` ([BUS.md:718](../BUS.md#device-vocabulary)) | today (`interface.py:1067`) | `<A addr value>`, an extended accessory packet; 0 is stop and the rest is the decoder's (`DCCEXParser.cpp:439-445`; `commands.py:176-188`, values `:49`) | `SignalMast.setAspect(String)` (`SignalMast.java:78`) or `SignalHead.setAppearance(int)` (`SignalHead.java:87`; RED 1, YELLOW 4, GREEN 16 at `:58-62`). `implementation/DccSignalMast.java` builds extended accessory packets and sends them through `CommandStation.sendPacket` (`:159-161`; `CommandStation.java:32`). JSON `signalMast` takes an aspect name checked against `getValidAspects` (`server/json/signalmast/JsonSignalMastHttpService.java:65-71`); `signalHead` takes an appearance number (`server/json/signalhead/JsonSignalHeadHttpService.java:63-76`) | Which mast aspect or head appearance stands for each of the three names is JMRI configuration. A DCC signal mast needs a connection that registers a `CommandStation`: DCC-EX (`jmrix/dccpp/DCCppSystemConnectionMemo.java:183`, sent as `<M …>` by `DCCppCommandStation.java:335-345`), NCE (`NceSystemConnectionMemo.java:93`), XpressNet (`XNetSystemConnectionMemo.java:172-175`), LocoNet (`LocoNetSystemConnectionMemo.java:177`), Z21 (`Z21SystemConnectionMemo.java:225`). |
| Track power | | | | | |
| 7 | Turn the supply on or off: `wanted/track` `on`/`off` ([BUS.md:719](../BUS.md#device-vocabulary)) | today (`interface.py:1191`) | `<1>`, `<0>`; per track `<1 X>`, `<0 X>` (`DCCEXParser.cpp:638`, `:670`; `commands.py:191-215`) | `PowerManager.setPower(ON\|OFF)` (`PowerManager.java:42-58`); DCC-EX `DCCppPowerManager.setPower` (`jmrix/dccpp/DCCppPowerManager.java:41-56`). JSON `power` post state 2 or 4 (`server/json/power/JsonPowerHttpService.java:71-85`); WiThrottle `PPA` (`jmrit/withrottle/TrackPowerController.java:80-83`) | One railroad-wide value on both sides. |
| 8 | Emergency stop: every locomotive told to stand, rails live: `wanted/track` `stopped` ([CONTEXT.md](../../CONTEXT.md), *Emergency stop*) | today (`interface.py:1187`) | `<!>`, one shot; each loco stays stopped until its next `<t>` (`DCCEXParser.cpp:700-706`; `commands.py:212-213`). The lock `<!P>`, `<!R>`, `<!Q>` with `<!PAUSED>`/`<!RESUMED>` broadcasts (`DCCEXParser.cpp:701-704`, `CommandDistributor.cpp:382-390`) is not sent (`commands.py:199-208`) | `PowerManager.IDLE` (`PowerManager.java:44`), documented as track power alive with the station broadcasting stop on some LocoNet systems (`:14-24`). Per locomotive, `setSpeedSetting(-1)`; DCC-EX sends `<t cab -1 1>` (`DCCppThrottle.java:217-224`, `DCCppMessage.java:2639-2648`). JSON throttle `eStop` (`JsonThrottle.java:231-233`) | Varies by connection. `implementsIdle()` is false unless overridden (`PowerManager.java:78`). XpressNet returns true and sends its emergency stop for IDLE (`jmrix/lenz/XNetPowerManager.java:29-31`, `:50-53`); Z21 gets an XpressNet connection through its tunnel (`jmrix/roco/z21/Z21XPressNetTunnel.java:256`). LocoNet returns true only for DB150, DCS100, DCS200, DCS210 and DCS240 (`jmrix/loconet/LnPowerManager.java:215-236`). DCC-EX and NCE do not override it. JSON refuses IDLE on post and reports it as UNKNOWN (`JsonPowerHttpService.java:44-53`, `:83-85`). JMRI's DCC-EX code can build `<!>` (`DCCppMessage.java:2658`) and nothing calls it. |
| 9 | Observe the supply: `device/track` `on`/`off` ([BUS.md:763](../BUS.md#device-vocabulary)) | today, published by the translator | `<pN X>` per track, then `<p0>`/`<p1>` when all agree, then `<p1 MAIN>`/`PROG`/`JOIN`, broadcast to every client on any change (`CommandDistributor.cpp:306-350`); `<s>` restates them (`DCCEXParser.cpp:720`). Translator reads `replies.py:56-69`, `:269-296` | `PowerManager.getPower` plus its property change. DCC-EX: `DCCppPowerManager.message` (`:72-82`) reads every `<p…>` line as the whole railroad's state. JSON pushes `power` on change, ON/OFF/UNKNOWN only (`JsonPowerHttpService.java:44-53`) | Observed or acknowledged varies by connection. DCC-EX broadcasts a change caused by any client, so JMRI's reading is observed. NCE sets its state from the station's reply to a power command JMRI sent or saw sent (`jmrix/nce/NcePowerManager.java:66-88`), which is an acknowledgement, not a reading. |
| 10 | Name a district the hardware cut: `device/track` `reason` ([BUS.md](../BUS.md#device-vocabulary), *It also names a district*) | today, published by the translator | `<* TRACK X FAST OVERLOAD … *>` (rails49 Guard), `POWER OVERLOAD`, `FAULT PIN`, `NORMAL` (`MotorDriver.cpp:706`, `:808`, `:819`), sent on USB only (`docs/commands.md`, *What comes back*), plus `<p0 X>`. Translator reads `replies.py:102-117`, `:329-336` | No core interface: `PowerManager` has no districts. `DCCppReply.getPowerDistrictStatus` exists (`jmrix/dccpp/DCCppReply.java:1253-1265`) with no caller outside that file. `<* … *>` is formatted for the monitor only (`DCCppReply.java:276-277`). JSON: none | Not carried by JMRI. |
| 11 | Cut the supply when `layout` stops saying it is alive: `tc49/layout/alive_confirmed` once a second ([BUS.md:465-478](../BUS.md)) | today, translator sends `<G 3>` on each one (`commands.py:116`) | `<G n>` host timeout (rails49): no `<G>` within n s stops every loco, turns every track off (`DCCEXParser.cpp:790-791`, `HostTimeout.cpp`; `docs/commands.md`, *Host Timeout*) | No interface. JSON zeroes the speed of throttles held only by a closing socket (`JsonThrottle.java:190-195`). That covers the JSON socket, not `layout`, and removes no power | Not carried by JMRI. Upstream DCC-EX lacks it too. |
| Detection | | | | | |
| 12 | Report occupancy at a block end: `device/sensor/<block>.<end>` `occupied`/`clear`/`unknown` ([BUS.md:761](../BUS.md#device-vocabulary)) | today, published by a detector or typed by a person; not by the station ([BUS.md](../BUS.md#device-vocabulary), *Two of the observed rows*) | Sensors defined with `<S id vpin pullup>` (`DCCEXParser.cpp:503`) broadcast `<Q id>`/`<q id>` on change (`Sensors.cpp:144`, `CommandDistributor.cpp:175-177`); `<Q>` lists them (`DCCEXParser.cpp:716`). The translator reads none (`replies.py:13-14`) | `SensorManager.provideSensor` (`SensorManager.java:43`), `Sensor.ACTIVE`/`INACTIVE` (`Sensor.java:25-26`); DCC-EX `DCCppSensor` follows `<Q>`/`<q>` (`jmrix/dccpp/DCCppSensor.java:128-133`). JSON `sensor`, pushed after a `get` (jmri.md §3) | Every connection read registers a `SensorManager`: DCC-EX (`DCCppSystemConnectionMemo.java:145`), NCE (`NceSystemConnectionMemo.java:117`), XpressNet (`XNetSystemConnectionMemo.java:122`), Z21 (`Z21SystemConnectionMemo.java:83`), LocoNet (`LocoNetSystemConnectionMemo.java:200`). |
| Station link and health | | | | | |
| 13 | Say whether the station is answering: `device/link/<id>` `up`/`down` ([BUS.md:764](../BUS.md#device-vocabulary); [ADR-0066](../adr/0066-the-link-is-the-station-answering-not-the-socket-being-open.md)) | today, published by the translator | Poll `<s>` once a second; the banner `<iDCC-EX …>` and power lines answer (`DCCEXParser.cpp:720`; `commands.py:72`). Ten polls without an answer lower the link (dccex `docs/dccex/README.md`, *Ten unanswered polls*) | `jmrix/ConnectionStatus.java` tracks each connection as `Connected`/`Not Connected` (`:33-34`, `:84-121`). Nothing under `server/json/` reads it. JSON `ping`/`pong` and the advertised heartbeat cover the socket to JMRI only (jmri.md §2) | Not carried over JSON: a JSON client sees JMRI, not the station. |
| 14 | Notice the station restarted, and send the desired state again | translator (dccex ADR-0021) | Stash: `<JM 32000 1>` sets it, `<JM 32000>` answers `<jM 32000 n>`, empty after a boot (`DCCEXParser.cpp:1570-1587`, `Stash.cpp:56`; `commands.py:86-101`) | No JSON message. Not checked whether JMRI's own DCC-EX connection detects a restart | |
| 15 | Report a command the hardware refused: `device/refused/<id>` ([BUS.md:765](../BUS.md#device-vocabulary)) | declared | `<X>` (`DCCEXParser.cpp:1025`). On a port shared by several clients it cannot be tied to one sender's command ([DEVICES.md](../layout/DEVICES.md)) | Setters throw `JmriException` (e.g. `PowerManager.java:58`). JSON answers `error` with the request's `id` (jmri.md §2) | JSON can attribute a refusal; DCC-EX on a shared port cannot. |
| Track setup | | | | | |
| 16 | Set each district's mode and current limit, so a railroad's wiring works (reversing sections, a programming track) | translator, through the railroad's script (dccex ADR-0013, ADR-0018) | `<= X MODE>` (`DCCEXParser.cpp:772`), `<JG X mA>` (rails49 set form, `:843-856`); `<=>` and `<JG>` read them back | No core interface for a track mode or a current limit. JMRI's DCC-EX connection reads modes from `<=>` into `DCCppCommandStation.setTrackMode` (`DCCppPowerManager.java:90-93`) and track currents as `Meter`s (`jmrix/dccpp/DCCppPredefinedMeters.java`, `Meter.java`). JSON: none | Station-specific on both sides. |
| Programming | | | | | |
| 17 | Read and write decoder CVs | out ([MILESTONE-2.md:171](../MILESTONE-2.md#out-of-scope); a different row per [ADR-0063](../adr/0063-the-desired-half-may-ask-for-what-the-observed-half-cannot-report.md)) | Programming track `<W>`, `<V>`, `<B>`, `<R>` (`DCCEXParser.cpp:564-635`); on the main `<w cab cv val>`, `<b …>` (`:509`, `:525`), `<r cab cv>` with RailCom (`:516`) | `GlobalProgrammerManager.getGlobalProgrammer` (`GlobalProgrammerManager.java:46`), `AddressedProgrammerManager.getAddressedProgrammer` (`AddressedProgrammerManager.java:50`), `Programmer.writeCV`/`readCV` (`Programmer.java:94`, `:116`). DCC-EX: direct byte mode on the programming track (`jmrix/dccpp/DCCppProgrammer.java:56-60`), ops byte and bit on the main (`DCCppOpsModeProgrammer.java:109-113`). JSON: a `programmer` token and no service (`server/json/JSON.java:253`; no `programmer` package) | NCE and XpressNet register programmers only for some station models (`NceSystemConnectionMemo.java:127-133`, `XNetSystemConnectionMemo.java:80-85`). DecoderPro reaches the station on 2560 today, outside control. |

## Gaps

- An emergency stop with the rails live (row 8) exists in JMRI's core as
  `PowerManager.IDLE` only on XpressNet (Lenz and Z21) and on five LocoNet
  command stations. DCC-EX and NCE do not implement it, and the JSON
  servlet neither accepts nor reports it on any connection. Over JSON the
  only stop is `eStop` per held throttle, which misses a locomotive no JSON
  client holds.
- Two rails49 capabilities have no JMRI interface at all: the host timeout
  that cuts power when `layout` goes quiet (row 11), and the named tripped
  district (row 10). JMRI's DCC-EX connection also folds per-district
  `<p…>` lines into one on/off value (row 9).
- The link row (13) asks whether the station answers. JMRI tracks that in
  `ConnectionStatus`, and no remote protocol exposes it. A JSON client knows
  only that JMRI answers.
- Observed or acknowledged depends on the connection. DCC-EX broadcasts
  power and sensor changes from any client, so JMRI observes them; NCE's
  power state is the reply to a command JMRI sent or saw (row 9). A
  turnout's known state is a measurement only on connections with hardware
  feedback (LocoNet, XpressNet, Z21) or through sensors; on DCC-EX it is an
  echo (row 5).
- Track modes and current limits (row 16) and restart detection (row 14)
  are DCC-EX matters the translator handles with the station's own
  commands. JMRI offers no generic interface for either.
- JMRI carries cleanly rows 1, 2, 4, 6, 7 and 12: speed and direction,
  functions, points, signals, power on and off, and sensors, on every
  connection read here. Signals need a `CommandStation`, which all five
  connections register, and an aspect mapping kept in JMRI's configuration.
- Not expected by control and offered by JMRI: consists (row 3), momentary
  functions, `Reporter`s that name a train at a detector (LocoNet
  `jmrix/loconet/LnReporterManager.java`, Z21
  `Z21SystemConnectionMemo.java:71`; none registered by DCC-EX). GOALS.md
  has detectors anonymous and the dispatcher naming the train.
