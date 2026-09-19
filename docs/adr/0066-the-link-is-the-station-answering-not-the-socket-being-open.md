# The link is the station answering, not the socket being open

Records the decision behind [#531](https://github.com/rails49/control/issues/531)
and [#527](https://github.com/rails49/control/issues/527). Amends
[docs/dccex_usb/README.md](../dccex_usb/README.md): its claim that while the
device is away a client's messages are dropped and the client stays connected.

[ADR-0065](0065-the-app-that-owns-the-device-flashes-it.md) said a flash is
verified by watching `tc49/layout/state/device/link/<id>` go `down` and come
back carrying the new `build`. It does not, and the reason turned out to be
older and wider than the flash.

## The row has been reporting the wrong thing

`dccex` publishes `device/link` from a TCP session to the mirror on 2560. The
session ends when the socket closes, and `dccex-usb` holds the socket open
through every serial outage on purpose — a client's bytes are dropped and the
client stays connected, because an outage measured in milliseconds is not worth
a reconnect. So the translator hears nothing, its session never ends, and the
row goes on saying `up` with whatever `build` it last saw.

That is true of a flash, and it was already true of a station switched off at
its own power switch, a pulled USB cable, and a station that has crashed. The
flash is the first case anyone checked. Nothing about it is special.

The cost is not confined to the row. `layout` folds the supply to `off` for any
id it has heard say `down`, so a link that should be `down` and is not leaves
`state/power` reading `on` while the station is unreachable, and the dispatcher
goes on driving trains at a command station that is off, wedged, or being
erased.

## What the row already means

This is not an open question. Three places say the same thing:

- [CONTEXT.md](../../CONTEXT.md), **Link**: whether a participant *can reach the
  hardware it drives*.
- `dccex`'s own module docstring: `up` while the connection is open *and the
  station has answered*, `down` otherwise.
- The same docstring, on the build: *the link is made of the station having
  answered*.

So the specification was right and the implementation never matched it. The
code checks that the station has answered once and never again.

The alternative — redefining the row to mean the transport is open, and
correcting the three passages that promise otherwise — was rejected. It would
take away the one thing the row exists for, which
[ADR-0050](0050-broken-hardware-is-reported-never-worked-around.md) states as
letting a view say the command station is unreachable rather than leaving the
railroad merely looking idle. A row that is `up` whenever a socket is open
cannot say that, and a value that reports something other than what it names is
the faked observation ADR-0050 refuses.

## Two mechanisms, because neither covers the other

**The app that knows says so.** `dccex-usb` is the app holding the serial
device; when it is away, that app is already in its reopen backoff. It closes
its TCP clients, the translator's session ends the way it already ends, and
`device/link` goes `down` through the existing path. Nothing is inferred and no
app learns anything about another. This covers the outages that happen on this
railroad: switched off, unplugged, flashing.

**The translator times out its poll.** A station that is powered, enumerated and
mute — wedged firmware — leaves the mirror's device open and healthy, so the
mirror has nothing to report. Only the far end can notice, and it notices by the
`<s>` poll going unanswered. This is the backstop and catches nothing else.

Neither is redundant. Dropping the second would leave a wedged station driving
trains blind; dropping the first would make every outage wait out a timeout long
enough to be safe, which is the wrong trade for the cases that actually occur.

## The two numbers, and what a wrong one costs

**The mirror's grace is two failed reopens**, about a second, and is
`FIRST_BACKOFF_S` rather than a constant of its own so there are not two numbers
to drift apart. Too short and a blip the first reopen recovers disconnects every
throttle for nothing. Too long and the row lies for longer. A second is past the
first retry and far inside a flash.

**The translator's timeout is ten missed polls**, ten seconds at `POLL_S`. This
is the number with teeth: `layout` folds any `down` to `state/power: off`, so
one that fires spuriously stops the railroad in the middle of a session. With
the mirror handling the outages that occur, this one fires only for a wedged
station and can afford to be generous. Ten seconds is well outside anything a
healthy station does with a status query under load.

## A flash is rare, and the railroad stopping during one is expected

Recorded because it is not derivable from the code and it settles what would
otherwise look like a cost to mitigate. Writing firmware onto the command
station is not a thing that happens during an operating session, and nobody
expects trains to run while the station is being written. So the railroad going
dark for the length of a flash — `state/power: off`, throttles disconnected
from 2560 — is the correct outcome rather than churn to be designed around.

It also means the client obligation in #519 stands unchanged: a control that
publishes `firmware_wanted` still requires the run held and the track off
first. This decision adds a truthful report of what the hardware is doing; it
does not add a second guard, and the responder still knows nothing about runs.

## Decision

1. `device/link` means the station answers. The transport being open is not the
   link, and the row is `down` whenever the station has stopped answering,
   whatever the reason.
2. `dccex-usb` disconnects its TCP clients once the serial device has been away
   for two failed reopens, rather than holding them open and dropping bytes for
   the whole outage.
3. `dccex` publishes `device/link: down` when the station has not answered the
   `<s>` poll for ten poll intervals.
4. Neither app learns what the other is doing. The mirror reports a device it
   holds; the translator reports a station that stopped answering. Neither knows
   a flash is happening.
5. `build` clears with the link, which
   [#520](https://github.com/rails49/control/issues/520)'s contract already
   requires — a `down` link carries none — so a stale pre-flash build stops
   being reported.
6. ADR-0065's verification path stands as written and becomes true. The
   passages stating it in [SYSTEM.md](../SYSTEM.md), `dccex_usb/firmware.py`
   and [docs/dccex_usb/README.md](../dccex_usb/README.md) are correct and are
   not rewritten.

## Alternatives not taken

**Redefine the row as the transport.** Covered above: it would cost the row its
only purpose and would be a faked observation under another name.

**Make the translator flash-aware**, so it lowers the link when a flash starts.
It would mean a translator subscribing to `firmware_wanted`, which is the
responder's row, and knowing about an operation performed by a different app on
hardware it does not hold. #519 already states that the responder must not learn
about runs; the same argument runs the other way. A translator acts on the
addresses it recognises and reports what its own hardware tells it
([ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
It would also fix one cause and leave the switched-off station reporting `up`.

**A heartbeat row, or a `detail` value naming the flash.** A second row would
carry what `device/link` already carries once it is correct, and CONTEXT.md
lists *heartbeat* among the words to avoid for exactly this reason. A `detail`
that named a flash would require the knowledge the point above refuses, and
what a person needs to read — the station is not answering — is what the free
text already says.

**Only the timeout, with no change to the mirror.** Simpler, one app touched,
and it does fix every case eventually. Rejected because the timeout would then
have to be short enough to be the primary signal, which puts the number that
stops the railroad under pressure from the cases the mirror can report exactly.

## Consequences

`dccex-usb` changes documented behaviour that clients on 2560 depend on: JMRI
and any throttle reconnect after an outage longer than the grace, where today
they do not. This is the deliberate part and is why the grace exists at all.

`dccex` holds one more piece of state, the time of the last answer.
[ADR-0062](0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)
refused a flag in the app and ADR-0063 held one in `layout` because a person
needed to see it; this is the second kind. What it holds is not a decision the
app took, it is when the hardware last spoke, and the row it feeds is the one
the app already publishes.

No contract changes. `device/link` keeps its payload, no topic is added or
removed, and `lib/inventory.py` is untouched, so this lands as two
implementation issues and no communication issue.

`state/power` will go `off` in cases where it previously stayed `on` — a
switched-off station, a pulled cable, a flash. That is the defect being fixed
and it is visible on the physical railroad: a station somebody switched off
mid-session now takes the supply row with it, where before the board stayed
green over a railroad that could not move.
