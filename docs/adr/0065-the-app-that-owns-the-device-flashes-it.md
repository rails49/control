# The app that owns the device flashes it

Records the decision behind [#519](https://github.com/rails49/control/issues/519),
[#520](https://github.com/rails49/control/issues/520),
[#521](https://github.com/rails49/control/issues/521) and
[#522](https://github.com/rails49/control/issues/522). Amends
[docs/dccex_usb/README.md](../dccex_usb/README.md): its claim that the app has
no bus topic, no state and no contract in [SYSTEM.md](../SYSTEM.md). Amends
[docs/MILESTONE-2.md](../MILESTONE-2.md): its out-of-scope row placing a way to
flash the command station outside this repository.

The command station's firmware is built elsewhere, against the station's own
source, and that does not change. What changes is that writing a released build
onto the box becomes something the running system does, on a gesture, rather
than something a person does from a checkout.

## Flashing needs the device let go

Writing flash means owning the serial port, and `dccex-usb` holds it open for
as long as the railroad is up — that is the whole point of the app (ADR-0043).
Two openers fight over the line discipline and the reset lines, so the mirror
has to let go for the duration.

Nothing in a container can make it. A container stops a sibling only through
the Docker daemon's socket, which is root on the box, and handing root over the
daemon to a process whose job is to rewrite a microcontroller's flash is a
larger decision than the one being made. So there are two shapes: something
outside the containers sequences the stop, the flash and the start — a script,
fed over ssh — or the process that holds the device does the whole thing.

**The device's owner is the only thing that can hand the device over.** A
separate flasher plus a release handshake needs both processes on the bus,
adds a race between the release and the open, and saves nothing: at the end of
it the mirror has the subscription anyway.

## The gesture is a gesture like the others

Nothing new is needed on the bus. [SYSTEM.md](../SYSTEM.md#event-inventory)
already has three kinds of topic — state, event and the two imperative
commands — and nine rows carrying the `browser` mark, which *is* the browser's
write permission rather than a note about it. A flash request is the tenth
gesture row, named like the rest: `tc49/layout/firmware_wanted`, under `layout`
because hardware hangs under the layout interface (ADR-0043).

It is an event, so rule 2 already says it is never replayed. That is worth
spelling out on this row, because it is the row where breaking the rule costs a
command station: a retained flash request reflashes the box every time the
responder reconnects to the broker.

**The payload names a tag and never a source.** The LAN is the trust boundary
and there is no authentication on purpose (ADR-0042), so a payload carrying a
repository or a URL would let anyone on the wifi make the command station fetch
and execute an arbitrary binary. A tag can only select among builds already
published to the one place the responder is configured to look, and that place
is a flag on the app. This is the difference between a gesture that chooses
among the railroad's own artifacts and one that chooses what the railroad runs.

`latest` is not a legal value for the same family of reasons and one of its
own: it names a different build depending on when it is read, and the point of
the gesture is to be able to say afterwards what was written.

## The result is observed, never replied to

There is no reply, no correlation id and no outcome topic. The flash is a
desired half, and what happened is read off the observed half — the split the
whole system is built on, and the one ADR-0063 restated when the two halves
turned out not to be symmetric.

`tc49/layout/state/device/link/<id>` gains an optional `build` (#520). The
translator already parses the station's banner to decide `link: up` and throws
the build away; publishing it puts *which build is on the box* on the bus,
where a UI can compare it against the tag it asked for. It also ends a claim
that could only ever be maintained by hand: `docs/DEPLOY.md` stops naming a
firmware version, because the railroad now says.

Progress needs nothing either. While the station is being written the link is
genuinely down, and a failure goes on `device/refused/<id>`, whose `addr` is
already optional for refusals that had no address (ADR-0063).

## The guarantee lives in the client

Flashing resets the station: the rails drop and every throttle on the mirror's
port disconnects. The responder does not check whether that is safe.

This is ADR-0051's and ADR-0062's arrangement, unchanged. Cutting track power
is a two-step gesture the panel performs — ask the dispatcher to drain, watch
`tc49/dispatch/state/run` reach `held`, then publish — and the guarantee that
the supply is never removed under a moving train "lives in the one client that
was written to honour it". A client that emits a flash is obliged the same way:
`run: held` and `device/track: off` before it publishes.

The alternative is the mirror subscribing to the dispatcher's run state, which
would put the shape of a railroad's operations inside the app whose whole
correctness argument is that it is a byte mirror with no opinions. The operator
is the backstop, as they were for power.

## What it costs

`dccex-usb` stops being contract-free. It gains a broker connection, a client
id, its first rows in SYSTEM.md and a dependency on a flashing tool, and it is
the one process every throttle, DecoderPro and the translator depend on being
up. That is the price of this decision and it is not small.

What holds it down: esptool runs as a **subprocess with a timeout**, so its
failures and its port handling cannot reach the mirror's own; a second gesture
while a flash is in flight is **refused, not queued**, which is what the app
already does with client bytes while the device is away; and the runner is
injected, so the suite exercises the ordering — device closed before the flash,
reopened after — without hardware.

The download and its check happen **before** the device is closed. A network
failure then costs nothing, where the other order leaves the railroad with a
closed port and no firmware.

## Decision

1. The app that owns a device is the app that flashes it. `dccex-usb`
   subscribes to `tc49/layout/firmware_wanted` and gains `--broker`, an `--id`
   and a configured release source.
2. `tc49/layout/firmware_wanted` is an event row marked `browser`, carrying one
   field, `tag`. It is never retained.
3. The source of the binary is configuration and never payload.
4. The download is checked against the digest the release API reports before
   the device is closed.
5. `tc49/layout/state/device/link/<id>` gains an optional free-text `build`, the
   identifier the hardware reports for what it is running — not the whole
   banner, which is one vendor's format.
6. There is no reply. Success is read off `device/link`, failure off
   `device/refused/<id>`, and both are the publisher's ordinary rows.
7. A client that emits the gesture is obliged to sequence it against
   `dispatch/state/run` and `device/track`. The responder checks neither.

## Alternatives not taken

**A host script over ssh**, stopping the container, running esptool in a
one-shot container and starting it again. It was the design until the last
round of the discussion and it is smaller than this one by a wide margin: no
new contract, no subscription in the mirror, no dependency. It was rejected
because it puts the operation outside the running system — performable only
from a checkout, with an ssh key, by someone at a terminal, and verifiable only
by reading that terminal's output. Everything else a person does to this
railroad is a gesture on the bus with the result on a state row, and there is
no property of flashing that makes it the exception. The cost is honest: this
is materially more machinery for something that happens perhaps twice a year.

**The Docker socket in a flasher container.** Root on the box, handed to the
one container that writes firmware. Rejected on that sentence alone.

**A resident flasher beside the mirror, with a release handshake.** Both
processes end up on the bus, and a race is added between the release and the
open. It buys separation that the shared image does not give anyway.

**Baking the firmware into an image** with `ADD --checksum`, so the digest is
checked at build time and the image records which build the box runs. It is the
stronger integrity story and it is incompatible with choosing the tag at the
moment of the gesture. The release API publishes a per-asset digest, so the
check survives; what is lost is that the checkout no longer records the build,
and `device/link` carrying it is the better answer to that question anyway.

**A reply topic, or a correlation id on the gesture.** Neither exists anywhere
else in this system, and the observed half already answers the question. A
reply would also have to be published by an app that has just spent a minute
not listening to anything.

**The responder refusing a flash while a run is moving.** It would need the
mirror to read the dispatcher's state, which is the coupling this app has never
had and the reason it is trustworthy.

## Consequences

`docs/dccex_usb/README.md` loses its central claim, and SYSTEM.md gains rows for
an app that had none. The app boundary rule is unaffected: it imports
`tc49.lib` and itself, as every app does.

The first flash still needs a deploy, because the flasher has to be on the box
before it can flash. `scripts/deploy.sh` is unchanged by this decision and is
not part of the flash path afterwards.

The `MILESTONE-2.md` row narrows rather than disappears. Building the firmware
is still a separate project against the station's own source; writing a
released build onto the station is this repository's work from here.

Nothing above the layout interface changes. No topic outside
`tc49/layout/…/device/…` moves, the simulator publishes no link row and is
untouched (ADR-0030), and a railroad whose hardware has no firmware to speak of
carries a gesture nobody answers, which does no harm (ADR-0059).
