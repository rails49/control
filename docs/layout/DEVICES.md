# The device rows, and how each translator carries them

The rows themselves are normative in
[SYSTEM.md](../SYSTEM.md#device-vocabulary) and bound in code as
`tc49.lib.inventory.DEVICE_TOPICS`. This page adds one column per translator:
what that hardware does with each row, and where it cannot do it at all.

The mapping columns are the evidence that the vocabulary is implementable
without naming hardware in it. A row every column can carry is settled. A row
a column cannot carry is not thereby wrong — the physical railroad decides
what a row means
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)) —
but it obliges that translator to do its best and say so, never to fake the
result ([ADR-0050](../adr/0050-broken-hardware-is-reported-never-worked-around.md)).

The two columns here are the two paths that exist. One speaks a command
station's own protocol. The other speaks JMRI's JSON servlet and so reaches
every railroad JMRI drives, which is why it is the wider of the two and why
its limits are worth stating precisely: they are the limits of a protocol
surface, not of JMRI, and not of the hardware underneath it.

## What `layout` asks of the hardware

| Topic | Payload | Description | JMRI | DCC-EX |
| --- | --- | --- | --- | --- |
| `wanted/track` | `power`: `on` \| `stopped` \| `off` | Railroad-wide desired power. `stopped` is the emergency stop: the rails stay live and every locomotive is halted, so decoders keep their addresses and can still be commanded. `off` is the supply removed. No address — power districts are a hardware fact, and a translator maps one railroad-wide value onto however many its hardware has. | `on` and `off` are a `power` post, state 2 and 4. `stopped` is `eStop` on every throttle the translator holds, which covers everything moving under our control and misses a locomotive somebody else is driving. `PowerManager.IDLE` means exactly `stopped` — "track power alive, command station broadcasting stop to all mobile decoders" — but the JSON servlet rejects state 8 on write and reports a layout sitting in it as `UNKNOWN`. | `on` → `<1>`, `off` → `<0>`, `stopped` → `<!>`, a one-shot broadcast with the track still live |
| `wanted/traction/<addr>` | `addr`, `speed`: −1.0 … 1.0 | Desired speed of one locomotive. The sign is direction along the track and the magnitude is the fraction of that locomotive's maximum; `0.0` is stop. Steps and speed tables stay inside a translator. | Acquire a throttle for `<addr>`, then `speed` is the magnitude and `forward` the sign. The number is never forwarded unchanged: JMRI reads `-1` as an emergency stop, where we mean full speed reverse. | `<t <addr> <step> <dir>>`. The magnitude maps onto DCC steps 2…127, step 1 being held for the emergency stop. |
| `wanted/function/<addr>/<number>` | `addr`, `function` (the number as a string), `value` (boolean) | One decoder function, on or off. A DCC function is one bit on the wire. Setting volume, brightness or momentum is decoder programming rather than function control, and would be a different row. Declared and subscribed by translators; written by nothing until a throttle asks. | `F<number>`, true or false, on the throttle held for `<addr>`. The function count is decoder-dependent and reported by the server. | `<F <addr> <number> 1\|0>` |
| `wanted/point/<addr>` | `addr`, `position`: `closed` \| `thrown` | One turnout's desired position. `align` carries the points its transit needs every time, so a translator throws what it is told and holds no table. What a layer in between remembers is its own business. | Post turnout state 2 or 4. JMRI keeps a turnout object of its own; that bookkeeping is invisible here. | `<a <decoder> <sub> <act>>`, a stateless accessory packet. The accessory number the drawing carries is split four sub-addresses to a decoder. |
| `wanted/signal/<addr>` | `addr`, `aspect`: `stop` \| `caution` \| `clear` | Deliberately a subset of prototype signalling. These three are the dispatcher's states and what the driver acts on ([ADR-0025](../adr/0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)); what a signal makes of a name is wiring rather than contract. | A `signalHead` takes the appearance as a number — red 1, yellow 4, green 16. A `signalMast` takes the aspect string that railroad's signal system uses for each of the three, which comes from translator configuration: the protocol has no way to ask a mast which aspects it accepts. | `<A <addr> <code>>`, an extended accessory packet, a head showing three aspects where a basic packet has two positions |

## What the hardware reports back

| Topic | Payload | Description | JMRI | DCC-EX |
| --- | --- | --- | --- | --- |
| `device/sensor/<block>.<end>` | `addr`, `occupancy`: `occupied` \| `clear` \| `unknown`; `reason` *optional* | Occupancy at one block end, published by whatever watches it. The topic is always `<block>.<end>`, on every railroad. The drawing carries the name the hardware knows that sensor by, defaulting to the same string and editable in the UI, and whoever publishes reads it from there. | Subscribe the sensor under the system name the drawing gives. `ACTIVE` is `occupied`, `INACTIVE` is `clear`, and both `UNKNOWN` and `INCONSISTENT` are `unknown` with a reason. The system name is required; a user name is not contractual. | Not published. A detector publishes this row, and sensors the station polls for itself are another client's business. |
| `device/point/<addr>` | `addr`, `position`: `closed` \| `thrown` | A turnout's measured position, published only where the hardware really reports one and silent otherwise. A UI drawing turnout positions reads `wanted/point` instead and accepts that a hand-thrown or broken turnout will disagree. | Publish only for turnouts whose `feedbackMode` observes something. Suppress mode 1, `DIRECT`, where `getKnownState()` is documented to return the commanded state and a reading is indistinguishable from an echo. | Not published. The station answers a throw with a position it has faked, which is what this row is never built from. |
| `device/track` | `power`: `on` \| `off`; `reason` *optional* | The supply as observed. It has no `stopped`: an emergency stop leaves the rails live, so the supply reads `on`, and that is the truth about the supply. Whether the railroad is standing under an emergency stop is `state/power`, held by `layout`. | State 2 is `on`, 4 is `off`, and `UNKNOWN` is read as `off`. Whether a given connection observes the supply or caches what it was told is a per-connection matter the protocol does not expose. | The `<p…>` lines, one per track. A track that is powered but watching a rising current, and one that has tripped, both read not-on. |
| `device/link/<id>` | `id`, `link`: `up` \| `down`; `detail` *optional* | Whether the publisher can reach its own hardware, keyed by whatever the publisher calls itself. | The websocket, with the heartbeat the server advertises in its `hello` (about 13.5 s by default). It cannot say whether JMRI reaches the command station: the JSON protocol exposes no connection status, though JMRI tracks one internally. That gap is the operator's to cover. | The connection to the port |
| `device/refused/<id>` | `id`, `addr` *optional*, `detail` | The hardware refused a command or could not parse it. Not a device state — the publisher's report on its own last exchange, each refusal overwriting the last, so no translator holds a table. It catches misconfiguration: an address the hardware does not have, a value out of range, an aspect a mast will not accept. It does not catch hardware that answers and does not obey, which no protocol reports. | The error responses, correlated to the command by the request's `id`. | Not available. The port is a shared broadcast stream that carries replies and unasked messages alike, so an error line cannot be attributed to our own command rather than another client's. |

## Two limits worth keeping straight

**JMRI is not its JSON servlet.** The servlet is a plug-in surface built for
web throttles and panels, and it is narrower than JMRI. `PowerManager.IDLE`
is the case that matters here: the capability is in JMRI's core interface and
implemented by several command stations, and the JSON layer neither accepts
nor reports it. The same pattern holds elsewhere — there is a programmer
constant and no programmer type, and a connection-status registry no service
publishes. "JMRI supports it" and "we can reach it over JSON" are different
claims, and only the second binds a translator.

**No protocol reports that hardware obeyed.** DCC is broadcast with no return
path for most decoders, so there is no acknowledgement to wait for and no
completion event to read. A command station that answers politely and drives
nothing is truthful on every row above. `device/refused` narrows the gap and
does not close it, and
[ADR-0058](../adr/0058-hardware-meets-the-bus-and-a-translator-is-only-for-hardware-that-cannot.md)
is why we do not try to close it by inference.
