# What JMRI's JSON servlet offers

Resolves [#196](https://github.com/rails49/control/issues/196). Reads JMRI's
JSON protocol, the `jsa1987/jmri-docker` image and JMRI's DCC-EX connection to
judge whether a JMRI binding of the layout interface
([SYSTEM.md](../SYSTEM.md#layout-interface)) is the same shape as a direct
DCC-EX one. The contract it is read against: commands in (`align` with
address-and-position pairs, `cross` with a boundary), anonymous occupancy and
`state/power` out, the throttle-up / watch-the-detector / stop loop private to
the binding ([ADR-0040](../adr/0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md),
[ADR-0041](../adr/0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).

Sources are pinned: `JMRI/JMRI@23604e8` (master, 2026-08-26; JSON protocol
5.4.0), `DCC-EX/CommandStation-EX@0ad3080` (master, 2026-07-22; firmware
5.6.3), `jsa1987/jmri-docker@f9c3bc7` (main, 2026-08-10). Paths below are into
those commits. `www.jmri.org` sits behind a bot challenge, so its help pages
were read from the same files in the JMRI repository (`help/en/html/...`),
which is what the site serves.

Each claim is tagged: **[fact]** is stated in or read off a source;
**[inference]** is this document's reading of it.

## 1. Three doors into one protocol

[fact] JMRI speaks one JSON protocol over three transports
(`java/src/jmri/server/json/package-info.java`):

| Transport | Where | Default port |
| --- | --- | --- |
| RESTful HTTP | `/json/v5/<type>` and `/json/v5/<type>/<name>` on the Web Server | 12080 (`help/en/html/web/JsonServlet.shtml`) |
| WebSocket | `/json` on the same Web Server; an HTTP GET of `/json/` opens a test console | 12080 |
| Raw TCP "JSON Server" | newline-free JSON objects on a plain socket, "functionally identical to the JSON WebSocket interface" | 2056 (`JsonServerPreferences.DEFAULT_PORT`) |

[fact] The WebSocket and TCP servers share one handler (`JsonClientHandler`),
so everything below about subscriptions holds for both. The REST door has no
subscriptions; it is request/reply only.

[fact] Protocol version is `5.4.0`, path segment `v5`
(`JSON.V5_PROTOCOL_VERSION`, `JSON.V5`). A client may name a version in its
`hello`; absent one, 5.x is used.

## 2. Envelope, methods, session

[fact] Client message (`schema/json-client.json`): `{type, data, method?, id?}`.
`method` is one of `get` (default when absent), `post` (modify), `put`
(create), `delete`, `list`. `id` is a positive integer the server echoes on
direct responses only. List requests are `{"type":"sensor","method":"list"}`
or `{"list":"sensor"}` and answer with a JSON array of `{type,data}` objects.

[fact] Server message (`schema/json-server.json`): `{type, data, id?}` or an
array of them; `{"type":"pong"}` and `{"type":"goodbye"}` carry no data.
Errors are `{"type":"error","data":{"code":<http-ish int>,"message":...}}`
(`JsonException.getJsonMessage`).

[fact] Session: on connect the server itself sends a `hello`
(`JsonServer.handleClient`, `JsonWebSocket.onOpen` push `HELLO_MSG` through
the handler) with `JMRI` version, `json` `"5.4.0"`, `version` `"v5"`,
`heartbeat` (ms), `railroad`, `node`, `activeProfile`
(`util/JsonUtilHttpService.getHello`). The advertised `heartbeat` is
`0.9 × heartbeatInterval`; the WebSocket idle timeout is
`1.1 × heartbeatInterval` (`JsonWebSocket.onOpen`); the interval defaults to
15000 ms (`JsonServerPreferences`). A client keeps the socket alive with
`{"type":"ping"}` → `{"type":"pong"}`; either side closes cleanly with
`{"type":"goodbye"}`. Server shutdown sends `goodbye` first.

[inference] A binding must therefore ping at least every ~13 s or JMRI drops
it; there is no application-level acknowledgement beyond the echoed `id`.

[fact] Names are **system names** (`"IS2"`, `"DT5"`), not user names; a
`get` by user name is answered but logged as a client bug
(`JsonNamedBeanSocketService.onMessage`). Schema validation of client
messages is off by default (`validateClientMessages = false`).

## 3. Subscription semantics: a `get` is a subscribe

[fact] The help page states it in one line: *"get"ting an item sets up a
listener which sends all subsequent changes as well*. The code:
`JsonNamedBeanSocketService.onMessage` adds a `PropertyChangeListener` to the
bean after **any** `get`, `post` or `put` on it, and that listener re-sends
the whole object (`doGet`) on every property change, with `id` 0. Listeners
live for the socket and are removed on close.

[fact] Two things arrive without any per-object request:

- A **manager listener** is registered at connect for every named-bean type
  (`JsonNamedBeanSocketService` constructor). When a bean of that type is
  added or removed, the connection receives the **full list** of that type,
  unasked.
- A **throttle** sends its full status when acquired and every change
  afterwards (section 5).

[fact] `list` deliberately does **not** subscribe to the items listed
(`JsonSocketService.onList` contract). Protocol 5.0.0 "removes code that
creates listeners for objects not requested by the client". The package doc
adds that none of this is *guaranteed* — services are pluggable and "a
single service will be the only responder" is explicitly not promised.

[inference] For the layout interface this means: at start-up the binding
must enumerate the sensors it cares about and `get` each one. After that,
each occupancy change arrives as a complete sensor object on the socket.
The order between two sensors' events is the order JMRI's Swing property
change events fired, which the protocol does not define.

## 4. The object types the contract needs

State integers are shared across types (`JSON.java`): `0` UNKNOWN, `2` ON /
ACTIVE / CLOSED, `4` OFF / INACTIVE / THROWN, `8` IDLE / INCONSISTENT.

### Sensor (`sensor/sensor-*.json`, `JsonSensorHttpService`)

[fact] Server: `{name, userName, comment, properties[], inverted, state}` with
`state` ∈ {0, 2, 4, 8}. Client `post` may set `state` 2 or 4 (sets JMRI's
*known* state), `inverted`, `userName`, `comment`. Nothing in the message
names a train — it is the anonymous detector the contract asks for.

### Turnout (`turnout/turnout-*.json`, `JsonTurnoutHttpService`)

[fact] Server: `{name, userName, comment, properties[], inverted, state,
feedbackMode, feedbackModes[], sensor[2]}`. Client `post` `{name, state: 2|4}`
commands it (2 = closed, 4 = thrown). For a DCC-EX connection with prefix `D`
the system name is `DT<n>`; `DCCppTurnout.forwardCommandChangeToLayout`
sends `<T n state>` when the turnout's feedback mode is MONITORING (a turnout
defined on the command station) and the raw accessory command `<a ...>`
otherwise (DIRECT).

[inference] So `align`'s `{addr, position}` pairs
([ADR-0031](../adr/0031-the-layout-carries-the-points-a-transit-needs.md))
map to one `post` per pair, with `addr` string-prefixed into a JMRI system
name. Which of the two DCC-EX commands JMRI then emits is a JMRI turnout
setting, not something the binding can choose per message.

### Power (`power/power-*.json`, `JsonPowerHttpService`, `JsonPowerSocketService`)

[fact] Server: `{name, prefix?, default, state}`; client `{prefix?, name?,
state?}`. `post` with `state` 2 or 4 sets power on the named connection
(`prefix` wins over `name`, omit both for the default). Any power message
from the client subscribes the socket to that power manager; `list`
subscribes to all of them. Afterwards every power change arrives unasked.

[fact] Although schema and help list `8` (IDLE), `JsonPowerHttpService.doGet`
emits only ON, OFF, and **UNKNOWN for everything else**. JMRI's own DCC-EX
power manager (`DCCppPowerManager`) knows only ON/OFF from `<p1>`/`<p0>`
replies and has no notion of an emergency stop.

[inference] Over JMRI a DCC-EX layout can report `on` and `off` but never
`stopped`. The third value of `tc49/layout/state/power` (ADR-0041) has no
source on this path; a JMRI binding would publish `off` for a dead rail and
nothing for a broadcast `<!>`.

### Signal head (`signalhead/signalHead-*.json`)

[fact] Server: `{name, userName, comment, properties[], aspect, lit, held,
state, appearance, appearanceName}`; `state` is the appearance integer or
`0x100` when held. Client `post` sets `state` to a valid appearance or held.
A signal head is a JMRI object driven through JMRI's own hardware config; it
is not a DCC-EX concept.

[inference] Nothing in the contract commands a signal — aspects are
`tc49/dispatch/state/aspects`, a state the panel renders
([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).
A JMRI binding could mirror that state onto physical heads as a convenience,
but that is outside the layout interface's vocabulary and would be a second
consumer of a dispatcher state topic, not a layout-interface duty.

## 5. Throttle (`throttle/throttle-*.json`, `JsonThrottle`, `JsonThrottleSocketService`)

[fact] Acquire: `{"type":"throttle","data":{"name":"<client token>",
"address":754}}`, optionally `isLongAddress`, `rosterEntry` instead of
`address`, and `prefix` to pick a connection. Every later message names the
same `name`. The server answers with the full status and then pushes it on
every change: `address, speed, forward, F0..F28, speedSteps, clients, name,
throttle` (`throttle` is the deprecated alias of `name`), plus `rosterEntry`
and `prefix` when set.

[fact] Commands are properties in `data`, processed in key order
(`JsonThrottle.onMessage`): `speed` (float; JMRI's throttle scale, `-1`
being emergency stop), `forward`, `F<n>` booleans, `eStop: null` (sets speed
−1 and stops processing the message), `idle: null` (speed 0), `status: null`
(resend status), `release: null`. `eStop` and `idle` are **not in the client
schema**, whose `additionalProperties` is `false`; with validation on they
would be rejected.

[fact] Sharing: `JsonThrottleManager` keys throttles by DCC address only.
A second JSON client (or the same one twice) asking for the same address
gets the *same* JMRI throttle, and every holder is told the new `clients`
count. A `release` from one holder leaves the throttle with the others. When
a socket closes, each throttle it held is closed; if it was the **last**
holder the speed is set to 0 and the JMRI throttle released
(`JsonThrottle.close`).

[fact] Any change to the underlying JMRI throttle — from a JMRI GUI throttle
window, a WiThrottle client, or a loco-state broadcast from the command
station — is pushed to every JSON holder (`JsonThrottle.propertyChange`).

[inference] This gives a JMRI binding one thing the direct binding has to
build: the socket dying zeroes the speed of every locomotive it alone held.
It is not the power backstop ADR-0040 asks for — it lives in software above
the rails — but it is a fourth leg for free, covering the binding-to-JMRI
link only.

## 6. `jsa1987/jmri-docker`

[fact] From `base/v5.16/Dockerfile` and `scripts/entrypoint.sh`: Debian
13 slim, `openjdk-21-jre`, the JMRI 5.16 tarball from `builds.jmri.org`,
an LXQt desktop under Xvfb, TigerVNC on 5901 and noVNC on 6901. The
entrypoint copies a default profile into `/home/jmri/.jmri`, fixes
permissions, `chmod a+rw /dev/ttyUSB*`, starts the noVNC proxy and
`vncserver`, and waits. **It does not start JMRI**; DecoderPro and PanelPro
are desktop launchers a person clicks through the browser at
`http://host:6901` (or a VNC viewer on 5901). That is how "a GUI (DecoderPro)
is reached". Releases: v5.8 … v5.16 (16-Jul-2026); `stable` is 5.16,
`testing` 5.17.2 (README). The Docker Hub description is the GitHub README
plus a link back (compared byte-for-byte).

[fact] The default profile (`assets/jmri-default/Default/profile/profile.xml`)
defines one connection — the **DCC++ simulator**, prefix `D`, user name
`DCC++` — and three start-up actions: Web Server, WiThrottle server, system
console. So out of the box the Web Server (12080, with `/json` REST and
WebSocket) and WiThrottle (12090) run; the TCP JSON Server on 2056 is
`EXPOSE`d but not started. Switching the connection to a real command
station is done in JMRI's preferences through the GUI and persists in the
`/home/jmri` volume.

[fact] How it reaches a command station (README): over Ethernet/WiFi nothing
special is needed — "tested for DCC-EX stations connected via Ethernet".
Over USB, `--device /dev/ttyUSBx:/dev/ttyUSB0` on a Linux host; the `jmri`
user is in `dialout`; a device on another machine or a Windows host goes
through USB/IP. Compose examples publish 5901, 6901, 12080, 12090 and
optionally 1234 (LocoNet over TCP), 2056 (JSON), 4303 (SRCP), 2048
(SimpleServer), or attach the container to an ipvlan.

[inference] For this repo's deployment ([DEPLOY.md](../DEPLOY.md) style,
one container per app), the image is a GUI appliance, not a headless
service: nothing brings JMRI up without a click, and configuration is a
Swing dialog. Running it headless would mean an autostart entry and a
pre-baked `profile.xml` of our own.

## 7. JMRI and DCC-EX over TCP 2560 — can two clients share the port?

**Yes.** [fact], from both ends:

*Command station side.* `CommandDistributor` keeps a
`clients[MAX_NUM_TCP_CLIENTS]` table; a client's type is decided by its
**first byte** — `<` makes it a native-protocol (`COMMAND_TYPE`) client, a
WebSocket handshake a WebSocket client, anything else WiThrottle
(`CommandDistributor::parse`). Direct replies go back to the issuing client;
**broadcasts go to every client of that type** (`broadcastToClients`): loco
state `<l cab 0 speedByte funcs>` on any throttle change (`broadcastLoco`),
turnout `<H id state>`, sensor `<Q id>`/`<q id>`, power `<p…>`, clock, track
mode. The command-reference page says the same in words: the `<l>` reply "is
not a direct response, but rather a broadcast that will be triggered as a
result of any throttle command being issued by any device", and power
`<pOnOFF [track]>` is "a broadcast that will be triggered as a result of any
power state changes". An emergency stop `<!>` from any client stops every
loco (`DCCEXParser`, case `'!'`).

Limits (`defines.h`): `MAX_NUM_TCP_CLIENTS` is 10 on ESP32, 9 on STM32
wired Ethernet (a LwIP bug makes the 11th kick an old connection, so the
firmware refuses at 9), 8 otherwise. Two further caps sit below that number:
on the ESP8266-AT WiFi shield the firmware only issues `AT+CIPMUX=1` and
`AT+CIPSERVER=1,<port>` (`WifiInterface.cpp`) and never raises
`AT+CIPSERVERMAXCONN`, and Espressif's AT link IDs run 0–4, i.e. **five**
connections ([ESP-AT TCP/IP commands](https://docs.espressif.com/projects/esp-at/en/latest/esp32/AT_Command_Set/TCP-IP_AT_Commands.html));
on W5100/W5500 shields the cap is the Ethernet library's `MAX_SOCK_NUM`
(`EthernetInterface.h` takes it from `Ethernet.h`, not from DCC-EX). Port
2560 is `IP_PORT` in `config.example.h`. The ESP32 keeps one shared 10 KiB
outbound ring for all clients (`WifiESP32.cpp`) and logs `OUTBOUND FULL`
when a client's reply does not fit.

*JMRI side.* `DCCppEthernetAdapter` is an ordinary TCP client, default
`COMMUNICATION_TCP_PORT = 2560`, with reconnect on loss. It holds no lock
on the station and expects to be one of several: `DCCppThrottleManager`
routes every `<l>` broadcast to the matching open throttle, which updates
speed, direction and functions "directly … to avoid a message loop"
(`DCCppThrottle.handleLocoState`); `DCCppPowerManager` follows `<p…>`
broadcasts and notes that "newer versions of DCC-EX only broadcast power
state changes"; `DCCppSensor` follows `<Q>/<q>`. JMRI's DCC-EX help page
(`help/en/html/hardware/dcc-ex/index.shtml`) documents the Ethernet
connection as "Check … that the Port is set to 2560 (DCC-EX default)" and
says nothing about exclusivity.

[fact] JMRI also offers the reverse arrangement: **DCC-EX Over TCP**
(`jmrix/dccpp/dccppovertcp/Server`, default port also 2560,
`DCCppConstants.DCCPP_OVER_TCP_PORT`), a relay in which JMRI owns the
station link and re-serves the raw `<…>` protocol to any number of clients,
"such as EngineDriver" or a second JMRI. A direct binding could attach there
instead of to the station.

[inference] Coexistence is real and symmetric: whatever one client does, the
other sees as a broadcast. The consequences a design has to accept:

- Two writers, one loco. The station obeys the last `<t>`; JMRI will mirror
  the binding's speed in its throttle window and vice versa. The contract's
  one-writing-role rule ([ADR-0035](../adr/0035-a-topic-has-one-writing-role.md))
  says only one of them may be the layout role on the bus; the other is an
  operator tool.
- Power and `<!>` are global. A person's OFF in DecoderPro is an `off` the
  binding observes and the dispatcher holds on — which is exactly what
  ADR-0041 wants.
- Sensor and turnout broadcasts are anonymous and identical for both
  clients; neither gets more than the other.
- Client count is small (5–10), so a "JMRI + direct binding + EX-WebThrottle"
  household is fine; a fleet of hand-held throttles is not.

## 8. What it means for the contract

[inference] **Same shape.** A JMRI binding is the same kind of thing as a
DCC-EX binding: a process that subscribes `tc49/drive/+`,
`tc49/dispatch/align` and the placement facts, owns throttles, watches
detectors, mints the boundary, and publishes anonymous occupancy and
`state/power`. Every contract-level property survives:

| Contract element | Over JMRI JSON | Over DCC-EX native |
| --- | --- | --- |
| `align` → points `{addr, position}` | one turnout `post` per pair, `addr` → `DT<addr>` system name | one `<T addr state>` or `<a …>` per pair |
| `cross` → throttle-up / watch / stop | throttle `speed` then sensor object pushes, then `speed: 0` | `<t cab speed dir>`, `<Q id>`/`<q id>` broadcasts, `<t cab 0 dir>` |
| anonymous occupancy | sensor `state` 2/4, no train field exists | `<Q>`/`<q>` carry an id only |
| `state/power` | `on`/`off` from power pushes; **no `stopped`** | `<p1>`/`<p0>` broadcasts; `<!>` shows only as per-loco `<l>` speed-1 broadcasts, plus the newer `<!Q>` lock query |
| boundary | binding's own clock either way | same |
| align-before-cross pairing, transit bound, power backstop | binding's own either way | same |

The differences are all *inside* the binding, which is where the contract
puts them:

1. **Subscribe by touching.** Occupancy arrives only for sensors the binding
   has `get` once; the binding therefore needs the sensor list at start
   (from the layout asset's addresses, the same way it needs point
   addresses). The DCC-EX path gets every sensor broadcast unasked.
2. **Naming.** JMRI system names (`DS<n>`, `DT<n>`, connection prefix) stand
   between `addr` and the wire. For a DCC-EX connection the rule is a string
   prefix; for any other JMRI-supported hardware it is JMRI configuration,
   which is the whole reason to want a JMRI binding — it is the generic one.
3. **Liveness.** A ping every ≤13 s, and JMRI zeroing the speed of an
   orphaned throttle. Neither replaces the hardware watchdog of ADR-0040.
4. **Sharing.** JMRI's throttle for an address is one object shared by every
   holder; a person's throttle window and the binding are equals. The
   direct path has the same property one level down (two TCP clients, last
   `<t>` wins), so this is not new, only closer.
5. **Operations.** A Java desktop application in a VNC container, configured
   by dialog, versus a serial/TCP line protocol. This is the real cost, and
   it is deployment, not contract.

[inference] **Recommendation.** Build the direct DCC-EX binding first; it is
the physical railroad's own protocol
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md))
and gives `stopped`. Keep JMRI as what section 7 shows it can be without
any code here: an operator's programming and panel tool on the same port
2560, coexisting with the binding. A JMRI *binding* stays a documented
option for a layout whose hardware only JMRI speaks; when written it needs
its own page under `docs/<binding>/`, since SYSTEM.md names no products.

## Open points not settled by the sources

- Whether JMRI's DCC-EX throttle manager refuses or shares an address that
  a JMRI GUI throttle already holds when the JSON client asks with
  `canHandleDecisions = false` (`JsonThrottle.getThrottle` passes `false`;
  `notifyDecisionRequired` is a no-op). Not exercised here.
- DCC-EX's newer estop lock (`<!P>`/`<!R>`/`<!Q>` → `<!PAUSED>`/`<!RESUMED>`,
  `DCCEXParser`) is a candidate source for `stopped` on the direct path;
  JMRI does not parse it.
- The ESP-AT five-connection figure is the AT firmware's default, read from
  Espressif's manual, not measured on a shield.
