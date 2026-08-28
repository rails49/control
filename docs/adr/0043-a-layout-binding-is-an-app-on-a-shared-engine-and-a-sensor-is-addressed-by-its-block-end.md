# A layout binding is an app on a shared engine, and a sensor is addressed by its block end

Resolves the main question of the milestone-2 map
([#194](https://github.com/rails49/control/issues/194)): what shape the
physical binding of the layout interface takes, stated once for every
binding and any layout. Four rulings.

## A binding is an app in this repo, and the hardware-neutral half is `lib`'s

Everything the layout interface owes the contract that no hardware decides —
pairing `align` before `cross`, the `cross` expiry window, the transit bound,
minting the boundary, turning sensor level into block events, and saying
`state/power` ([SYSTEM.md](../SYSTEM.md#layout-interface),
[ADR-0040](0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md),
[ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md))
— is an **engine** in `tc49.lib`: the Python binding of the layout-interface
contract, beside the rest of `lib`. A **layout binding** is then an app that
imports the engine and adds one device: `dccex` speaks the command station's
`<…>` protocol, `jmri` speaks JMRI's JSON servlet so that every railroad
JMRI supports runs this software without a binding of its own. Each is a
deployment unit of its own ([ADR-0013](0013-apps-are-deployment-units.md)),
and **exactly one binding app runs per railroad**, because the `layout` role
has one writer ([ADR-0035](0035-a-topic-has-one-writing-role.md)). The
`simulator` is unchanged and free to adopt the engine.

The physical binding is the normative one
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)), so it
lives where the contract is shaped rather than chasing it through a package
release from another repo.

Rejected: **a device-level vocabulary on the bus** — throttle, turnout,
sensor and power topics by address, a dumb adapter per hardware underneath
and a translating layer above, the shape
[#173](https://github.com/rails49/control/issues/173) sketched. It spreads
the control loop that ADR-0040 keeps private — throttle up, watch the
detector, stop — across two processes and a broker, with at-least-once
delivery in the middle, exactly where a late command is dangerous. The device
seam is a small interface in code: set a speed, throw a point, cut or restore
power, observe power.

Rejected: **one hardware app with the device chosen by configuration.**
Bindings are separate things coupled by the bus and by shared library code,
as the scheduler, dispatcher and driver are; that shape holds here too.

## Sensors are the one device on the bus, addressed by block end

The DCC bus is output-only in effect, which is why occupancy is separate
hardware that already speaks MQTT. So the **sensor wire is a bus contract**,
not a device behind the seam: detector hardware publishes a retained state
per sensor — `occupied`, `clear` or `unknown` — and the engine reads it, does
the debounce, the level-to-edge and the two-ends-into-one-block fold, and
publishes `block_occupied` and `block_vacated`. `unknown` is first-class:
silence is not a clear reading
([#153](https://github.com/rails49/control/issues/153)). The topic's grammar
and payload are a ticket of their own; a detector on another layout meets the
same door with a republisher and touches nothing here. A late sensor only
delays a stop inside the transit bound, so putting this one wire on the bus
costs nothing ADR-0040 defends.

A sensor is **addressed by the block end it watches**, `<block>.<end>` with
the end `A` or `B` — the drawing's own names. The block-end `sensors` ids the
drawing carried ([DRAWING.md](../store/DRAWING.md#hardware-ids)) go, and the
binding holds no table. This inverts
[ADR-0022](0022-a-symbol-carries-its-hardware-address.md) for sensors only: a
point is a decoder with a fixed address the drawing must carry; a sensor is
software someone configures, so it takes its address from the drawing. On a
camera the block end is the sensor's name; over JMRI it is the sensor's user
name; a station-defined `<Q>` sensor needs a republisher. Points keep riding
on `align` ([ADR-0031](0031-the-layout-carries-the-points-a-transit-needs.md)).

## The command station is reached over USB, through a port the stack serves

The only link to the command station that anything relies on is **USB**. A
small app, `station`, owns the serial device and serves **TCP 2560**: a
mirror of the serial traffic, each client's bytes held until a complete
`<…>` message and written whole so two clients never interleave on the wire,
every serial byte fanned out to every client. The binding is one client of
that port among peers; JMRI and hand-held throttles are the others. USB is
also the only channel that carries the station's overload diagnostics, which
is what lets `off` be honest without polling. A `station` that dies takes
nothing down but the port; a binding that dies leaves DecoderPro working.

Rejected: the station's own network port, which multiplexes clients itself
but puts the safety link on Wi-Fi; and the binding owning the serial port,
which makes a safety loop double as a server and its death take the port.

## JMRI is provided, and a JMRI binding is in scope

The stack brings JMRI up as a third-party container on 2560 with its GUI
reachable for configuration and DecoderPro, needing nothing of ours but
compose. Decoder programming stays outside the layout interface. The `jmri`
binding is separate from that and is milestone-2 work; one limitation is
recorded now rather than discovered: JMRI reports power as on or off only, so
a railroad bound through it never says `stopped`.

## Consequences

- `tc49/layout/*` names the bus **role** of the layout interface and has
  nothing to do with the store's layout document; the collision with the
  glossary's *layout* stands, noted rather than renamed.
- The broker container exists before the first train, since the camera
  publishes to it, while the apps still share the in-process bus
  ([#173](https://github.com/rails49/control/issues/173) holds: the
  hardware step forces neither MQTT nor containers on the apps).
- Implementation issues: the drawing drops block-end sensor ids; the
  `station` server. New map tickets: the sensor wire; the JMRI binding's
  mapping of addresses to JMRI names.
