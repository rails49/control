# Hardware meets the bus, and a translator is only for hardware that cannot

**Amended by [ADR-0059](0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md), 2026-09-03:** the scaffolding named under *Consequences* — `tc49 live --station` constructing the translator in the session's process — is removed, and the debt of a deployment requiring one box's hardware is [#357](https://github.com/rails49/control/issues/357).

Resolves [#357](https://github.com/rails49/control/issues/357).
[ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)
put hardware under the layout interface by address and got the mechanism
right. It then said who may write a translator, and left the impression that a
translator is a layer everything passes through. Neither holds.

## What ADR-0043 already settles, and this does not touch

An address names its system as its first level — `dccex/12`, `jmri/LT3` — and
the topic carries the system as a level, so **whatever answers for a system
subscribes that system and an address nothing answers to does no harm**, as a
DCC packet nobody picks up does. No ownership table exists anywhere. Zero, one
or several answer, per what is wired. State rather than command, so something
coming up finds positions to set rather than a history to replay. Any detector
meets the same door through a republisher.

That is already a design in which the hardware is somebody else's business.
The code agrees: a point's address is checked for shape and never against a
list of known systems, so `mine/7` derives today.

## The bus is the interface, and a translator is not a layer

ADR-0043's heading reads "Translators are optional, coexist, **and live
here**", and under it:

> Each is an app in this repo and a container of its own (ADR-0013).

Two things are wrong with that. The smaller one is *here*: **the contract is
the event bus and the inventory that describes it, not this source tree.**
Somebody may run a container they wrote, in any language, from a repository we
will never see, and if it subscribes the topics for its system and drives what
answers to those addresses then it is exactly as much a part of the railroad
as ours.

The larger one is the word itself. **A translator exists because a command
station speaks a dialect, and for no other reason.** Stations speak countless
dialects and many are quirky; DCC-EX's `<…>` is one, JMRI's JSON servlet is
another. `dccex` is named for a dialect it absorbs, not for a stage every
command passes through. Hardware built to speak the bus **needs no translator
at all** — it subscribes its system's topics and drives its own rails, and
there is nothing between it and them to write, configure or deploy.

So the shape is not *layout → translator → hardware*. It is *layout → bus*,
and then whatever is wired listens. A translator is what you write when the
thing you bought will not listen.

## We do not check that the trains move

Whatever answers for a system has two halves. The first is on the bus and we
can see it: the topics, the payload shapes, the addresses it claims. The
second is a locomotive rolling, and **we cannot see that at all, so we do not
pretend to.**

There is no registration, no health check, no declaration that a system is
present. Something that subscribes and drives nothing looks exactly like a
railroad that is not wired yet, and both look like a railroad whose owner is
still building. Any check we invented here would be a check on the half we can
observe, reported as though it covered the half we cannot — which is worse
than saying nothing, because it would be believed.

Somebody who built the hardware finds out their trains do not move by watching
their trains not move. They will know before we could tell them, and if they
are wasting their time it is not a fault this app can report.

## Consequences

**Deployment may not require any particular hardware.** The layout profile
today fails to start at all without one specific USB cable at one `by-id`
path, taking the store and the UI down with it. That is the concrete debt this
ADR creates, and what #357 now asks for: the hardware a box owns is that box's
choice, and everything that is not hardware comes up without it.

**`tc49 live --station` is scaffolding.** It constructs the `dccex` translator
in the session's own process, which is the bench harness wiring apps together
(CLAUDE.md) and not the shape the end state has. In GOALS.md's end state
whatever answers for a system is a participant on the broker, and a session
drives no hardware itself.

**`docs/SYSTEM.md` is a public contract.** Its event inventory is what
somebody building hardware reads, so a change to it is a change to an
interface strangers implement, not internal documentation. That is a
constraint on us, not on them.

**The `jmri` translator ADR-0043 designs is smaller than it looked.** It is
one dialect we have not absorbed yet, not a hole in the interface: somebody
with a railroad JMRI drives can write it today without us.

**The simulator is unchanged and is not a translator.** It is a
whole-interface binding behind the layout interface, and simulation never
becomes a field, a topic or a branch anywhere else
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)).
