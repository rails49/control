# The layout interface is a core app, and hardware hangs under it by address

Resolves the main question of the milestone-2 map
([#194](https://github.com/rails49/control/issues/194)): the shape of the
physical binding of the layout interface, stated once for every kind of
hardware and any layout.

**Amended for
[#299](https://github.com/rails49/control/issues/299), 2026-09-02:** the small
app called `station` below is now `dccex-usb` — the package `tc49.dccex_usb`,
the compose service and the image `dccex-usb`, its page
[docs/dccex_usb/README.md](../dccex_usb/README.md). The word `station` was a
block's role as well ([CONTEXT.md](../../CONTEXT.md), **Role**), and one name
could not be both. Nothing it does changed, so the text below is left as it
was written and the old name read as the new one.

## The layout interface is `layout`, always running, hardware-independent

Everything [SYSTEM.md](../SYSTEM.md#layout-interface) and the ADRs put on
"the layout interface" that no hardware decides is one core app, `layout`,
named for the bus role it alone writes: it keeps the beat
([ADR-0027](0027-the-tick-is-the-simulators-grant-boundary.md); on the
physical railroad a fixed period of real time, and the railroad's sped-up
clock is a *second*, separate clock —
[ADR-0044](0044-the-boundary-period-is-real-time-and-the-fast-clock-is-out-of-the-control-path.md)
corrects this line), pairs `align` before
`move`, expires a `move`, runs each transit — speed up, watch the far-end
sensor, stop, and stop anyway at the transit bound
([ADR-0040](0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md)) —
folds sensor state into `block_occupied` and `block_vacated`, publishes
`state/power`
([ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)),
and keeps the position table. Time and the detector watch are control's
own, not a command station's, which may not exist.

## A device-level vocabulary hangs under it, on the bus

Below the transit-level contract a second vocabulary appears, **on the
bus**: retained state topics written by `layout` naming what the hardware
should do — desired speed per locomotive address, desired position per point
address, desired power per district — and observed state written back by
whatever hardware reports it. **Translators** are thin apps, one per hardware
system, that act on every desired-state message they hear (never only on
change: `align` names its points every time because a hand may have flipped
one, and a translator throws what it is told) and on the retained value when
they connect. They publish observed state only when the hardware reports it;
a commanded position is never echoed back as a measured one
([ADR-0022](0022-a-symbol-carries-its-hardware-address.md)).

State rather than command is what makes the extra hop safe under
at-least-once delivery: a replayed message carries the value that is already
current, and a translator coming up finds positions to set. The exact grammar
and payloads are a ticket of the map.

**An address names its system as its first level** — `dccex/12`, `jmri/LT3`
— and the topic carries the system as a level, so a translator subscribes its
own system and an address nothing answers to does no harm, as a DCC packet
nobody picks up does. No ownership table exists anywhere. The drawing's
`addr` was always "whatever the hardware answers to"; naming the hardware
there is not a new kind of knowledge.

## Translators are optional, coexist, and live here

> **"Live here" no longer holds, and neither does the heading's premise.** A
> translator exists because a command station speaks a dialect; hardware built
> to speak the bus needs none, and one somebody else wrote is as much part of
> the railroad as ours. See
> [ADR-0058](0058-hardware-meets-the-bus-and-a-translator-is-only-for-hardware-that-cannot.md).
> The mechanism in this section — addresses naming a system, no ownership
> table, zero or several answering — stands.

`dccex` speaks the command station's `<…>` protocol; `jmri` speaks JMRI's
JSON servlet and is the path for every railroad JMRI supports, with one known
limit — JMRI reports power as on or off only, so it never says `stopped`.
Zero, one or both run, per what is wired: a railroad may start on hardware
JMRI drives and add a command station later. Each is an app in this repo and
a container of its own ([ADR-0013](0013-apps-are-deployment-units.md)); the
physical binding is the normative one
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)) and
lives where the contract is shaped. The `simulator` is unchanged in shape: a
whole-interface binding, as today. (It does gain the fast-clock field every
binding mints, per
[ADR-0044](0044-the-boundary-period-is-real-time-and-the-fast-clock-is-out-of-the-control-path.md).)

The command station is reached over **USB only**. A small app, `station`,
owns the serial device and serves **TCP 2560**: a mirror of the serial
traffic, each client's bytes held until a complete `<…>` message and written
whole so two clients never interleave, every serial byte fanned out to every
client. `dccex` is one client of that port; JMRI and hand-held throttles are
the others, and DecoderPro keeps working with every app of ours down.

## Sensors are addressed by their block end

The DCC bus is output-only in effect, so occupancy is other hardware and
arrives on the bus as retained state per sensor — `occupied`, `clear` or
`unknown`, and `unknown` is first-class
([#153](https://github.com/rails49/control/issues/153)). A sensor is
addressed by the block end it watches, `<block>.<end>`, the drawing's own
names: on a camera that is the sensor's name, over JMRI the sensor's user
name, and any other detector meets the same door through a republisher. The
block-end `sensors` ids the drawing carried
([DRAWING.md](../store/DRAWING.md#hardware-ids)) go. This inverts ADR-0022
for sensors only — a point is a decoder with a fixed address the drawing
must carry, a sensor is software someone configures and takes its address
from the drawing. Points keep riding on `align`
([ADR-0031](0031-the-layout-carries-the-points-a-transit-needs.md)).

## Rejected

**A hardware-neutral library each binding imports**, the device seam in
code. It makes every binding carry the core, and it forbids two hardware
systems on one railroad, which is a normal way a layout grows.

**A separate repo for the binding.** It is the normative binding and would
chase the contract through a package release.

**The station's own network port**, which multiplexes clients itself. The
safety link stays on USB, which is also the only channel carrying the
station's overload diagnostics.

## Consequences

- The broker container exists before the first train, since the camera
  publishes to it, while the apps may still share the in-process bus. JMRI
  is a third-party container on 2560 with its GUI reachable; nothing of ours
  is in either.
- Carried to the power ticket: a translator stops when the beat stops, and
  the ordering that keeps a retained speed from moving a train on reconnect.
- `tc49/layout/*` names the bus role and has nothing to do with the store's
  layout document; the collision with the glossary's *layout* stands, noted.
