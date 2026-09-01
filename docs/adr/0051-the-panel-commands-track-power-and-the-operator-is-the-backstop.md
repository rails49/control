# The panel commands track power, and the operator is the backstop

Resolves [#293](https://github.com/rails49/control/issues/293).
[ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)
parked the command half of track power on the reasoning that there was no
interface to write against. There is one now — the layout interface is the
core app `layout`, with hardware under it by address
([ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md))
— so it unparks.

One ADR and not two, because dropping the hardware backstop and making power
commandable are the same decision seen from two sides: the relay below is only
safe to remove *because* the command arrives.

## The row

`tc49/layout/power_wanted` — one event topic, browser-writable, one field
`power`, carrying ADR-0041's existing closed set `on` / `stopped` / `off`.

The topic is `layout`'s because `layout` is what answers it: a topic names the
component that responds to it and never the one that sent the frame
([SYSTEM.md](../SYSTEM.md#event-inventory), rule 4). One topic and one axis in
the command direction, for ADR-0041's own reason — two topics would make every
consumer decide what powered-off-and-emergency-stopped means. The bridge picks
the row up with no change of its own, the inbound set being read off the mark
([ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md)).

## Routing is panel → `layout` → `wanted/track`

The command goes to `layout`, which writes
`tc49/layout/state/wanted/track`, and whatever supplies power acts on that.
Not panel → a translator, for three reasons:

- ADR-0043 carves out desired power as device vocabulary, and every desired
  row has `layout` as its one writer (SYSTEM.md, rule 1). Routing round
  `layout` would leave that value with no writer at all.
- `layout` owns `tc49/layout/state/power`, and it must not publish a word
  about a railroad it never commanded.
- A second translator gets power for free this way, instead of needing a
  subscription of its own to the panel's gesture.

**No component expects a particular kind of hardware.** Whatever is
responsible for applying and cutting power does so when told, and it is the
system designer's job to put such a device there. `layout` cannot verify that
power really went away and does not try: it assumes the statement holds
([#232](https://github.com/rails49/control/issues/232)), and what it publishes
on `state/power` is what it commanded until something observed says otherwise.

## A power command is applied on arrival

There is no beat and no time quantisation —
[#243](https://github.com/rails49/control/issues/243) removed the boundary — so
a power command takes effect when it arrives, like everything else. That is
safe here rather than merely convenient: it changes no lock, it grants nothing,
and it races with nothing the dispatcher is deciding.

## The railroad comes up with power off

`layout` comes up having written `wanted/track: off`, and a person turns the
railroad on, normally from the panel. Nothing moves and no turnout throws until
they do. Thereafter `layout` never writes `off` of its own accord: it writes the
word it was told to write.

This is the guarantee the hardware already gave by coming back idle, held now
in the app — the same one ADR-0041 keeps when it says power returning to `on`
releases nothing, so an explicit GO still follows.

## The panel gets ON, STOP and OFF

- **STOP** is one click with no confirm. An emergency stop that asks "are you
  sure?" is not one, and `stopped` is cheap to recover from: the points are
  still where you left them.
- **ON** is safe by construction. ADR-0041 already guarantees that returning to
  `on` does not release the run, so nothing moves on this press either.
- **OFF is the drain trigger, never an immediate cut.** The panel publishes
  `tc49/dispatch/run_wanted: draining`, watches `tc49/dispatch/state/run` reach
  `held`, and only then publishes `power_wanted: off`. Both are topics the
  panel already writes, so `layout` never subscribes to the dispatcher.

An abrupt `off` would leave no point position trustworthy — the accessory
decoders lose the supply with everything else (ADR-0041) — and would strand
whatever was mid-transit. After a completed drain nothing is crossing, nothing
is committed, and every grant re-aligns, so the lost positions cost nothing.

The drain itself — `draining` as the third value of `state/run`, and the launch
gate — is [#294](https://github.com/rails49/control/issues/294) and is not
decided here. The panel's OFF is written against that value and is inert until
the dispatcher understands the word.

## The relay is out, and the operator is the backstop

ADR-0040's third leg — track power held on by a watchdog that must be kicked,
dropping a relay when it is not — is **dropped**, as a workaround for an
imagined problem. That section keeps its analysis: stopping really is two
commands, the broadcast is the gentler one, cutting the supply is the only one
that works when nothing else does, and neither survives the death of the
process holding the throttle. What it loses is the conclusion drawn from it.

The case it covered is real, and it is accepted with open eyes: a command
station refreshes its packets, so a train rolling when `layout` dies keeps
rolling until a person acts. **The operator is the backstop, as on every layout
ever built**, and a supervisor restart is free.

Two rules already in the repo say the same thing about the relay. ADR-0040's
own argument against building on an MQTT last will — "a watchdog that only
exists in production is a watchdog nobody has ever seen work" — applies to the
relay unchanged; it is one kicked contact nobody has ever watched drop. And
[ADR-0050](0050-broken-hardware-is-reported-never-worked-around.md) asks that a
failure be reported to a person who can act on it rather than absorbed by a
mechanism that hides it. A relay that cuts the railroad on a missed kick is the
software papering over its own death with steel.

What replaces it is the press. Before this decision a person at the panel had
no way at all to remove the supply or to stop every locomotive, and the relay
was the only thing standing in for one. Now both are one click, and the click
is the thing a person reaches for.

## Consequences

**The inventory gains one row, and the browser's write surface widens by one.**
The mark is what widens it, so the widening is deliberate and named where the
inbound set is pinned (ADR-0034).

**Nothing acts on the topic the day it lands.** `layout` acting on it is
[#287](https://github.com/rails49/control/issues/287), exactly as the manual
driving rows landed declared and unacted on. The panel's ON and STOP therefore
reach a railroad that does not yet answer, and its OFF waits on a `draining`
the dispatcher does not yet understand — three buttons that are contract before
they are behaviour.

**ADR-0040's third leg is deleted**, and ADR-0043's note carrying it to this
ticket — that a translator kicks that relay — goes with it. Legs 1 and 2 of
ADR-0040 are untouched; leg 1 was already deleted under
[ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md).

**No new word.** `on`, `stopped` and `off` are ADR-0041's closed set, carried
onto a second topic the way `run` is carried onto its own gesture, and
`draining` is #294's. The glossary is unchanged.

**Per-district power still reaches no topic.** One railroad-wide value desired
and one observed (ADR-0043); a district is a hardware fact, and a translator
maps the one value onto however many districts it drives.

**The simulator is untouched.** Simulated track is always live and a power cut
is a physical act (ADR-0030), so what exercises this is a test publishing the
topic, as it is for the observation half.
