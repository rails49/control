# A cross expires, and an unfinished one stops the train

[ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md) left
this open in as many words: *"The brake is shared; an emergency stop is more,
and it is not here."* This is where the more arrives, and it is not one
button. It is three obligations on the **layout interface**, which is the only
component holding a throttle.

The watchdog is **not the driver's**. The driver is a stateless, layout-blind
translator that turns a grant into a `cross` and holds nothing
([SYSTEM.md](../SYSTEM.md#driver)); it has no channel to the command station
and nothing to stop. The control loop that executes a `cross` — throttle up,
watch the detector, stop — is private to the layout interface, where the
braking curve and detector geometry already live
([ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)). So the
duty sits where the hardware is, exactly as the align-before-cross obligation
already does.

## Silence alone is already safe

The tempting design — a heartbeat, and stop when it stops — solves a problem
this system does not have. A `cross` is **bounded and self-terminating**: it
names one transit into one block, it ends at a detector, and that block was
locked before the grant was published. Kill the scheduler, the dispatcher, the
driver and the broker mid-transit and every rolling train finishes into track
reserved for it and stands there. Nothing is steering, and nothing needs to be.

That is a property worth naming, because it is what makes the hazards below the
short list rather than the long one, and it is a property of the command
vocabulary rather than of any implementation. A continuous-throttle design
would not have it, and this decision is a reason not to build one.

## A cross expires

The hazard is not a lost command. It is a **late** one.

At-least-once delivery and a persistent session mean a broker may redeliver a
`cross` after a reconnect, seconds or minutes after it was granted. Acting on
it starts a train into a block whose lock has since been released — a grant
honoured after the authority behind it has gone. `SYSTEM.md` already takes the
at-least-once mindset seriously enough to number the boundary so a duplicate is
trivially ignorable; a duplicated `cross` is the same argument with steel
behind it.

So **`cross` carries the boundary it was granted on**, and the layout interface
acts on it only if that boundary is the current one or the one before —
the N+1 skew [ADR-0009](0009-layout-interface-owns-time.md) describes, and no
wider. Anything older is dropped and traced. The window is stated in
boundaries and not in seconds because the layout interface *mints* the
boundary: it is the one component that always knows which number is current,
without a clock reading that would have to agree with anyone else's.

**This amends `SYSTEM.md`'s "no other event carries a `boundary` field."** That
line is right about observation — the trace tap stamps what it records, and
nothing needs to carry a number for a reader's benefit. It is wrong about
action. A stamp applied by an observer is not available to the actor, and the
actor here is deciding whether to move a locomotive.

Rejected: **expiry by wall clock in the adapter**, dropping any `cross` more
than N milliseconds old by local receipt time. It cannot distinguish a
redelivered command from a fresh one, which is the entire failure mode — both
arrive now.

Rejected: **a liveness state topic**, the dispatcher republishing the boundary
it last handled. It detects a wedged dispatcher, which the expiry window
already covers by starving the adapter of fresh commands, and it writes a
retained value every boundary — which the durable binding answers with a
whole-file rewrite per beat ([SYSTEM.md](../SYSTEM.md#the-bus)).

## An unfinished transit stops the train, and wedges the block

The second hazard is local and needs no bus at all: the detector never fires.
A stall, a dirty rail, a failed detector, a derailment. The train is under
power with no terminating event.

The control loop is therefore **bounded**: if the detector does not fire within
the transit's allowance, the layout interface stops the train and gives up on
the `cross`.

It then publishes **nothing**. Its outbound vocabulary is anonymous occupancy
and the boundary, and it never asserts train identity
([SYSTEM.md](../SYSTEM.md#layout-interface)) — a stall report naming a train
would be the adapter claiming exactly the knowledge detectors cannot honestly
give. The dispatcher sees no sensor event, so the block stays locked and the
train is a permanent obstacle ([SAFETY.md](../dispatcher/SAFETY.md)).

**Safe but wedged is the deliberate outcome.** The recourse is a person, and
it already exists: hold the run, and say where the train actually stands with
`tc49/ui/placement_wanted` ([ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md)).
A stalled train is a thing someone has to walk over and look at; inventing a
topic to describe it would add a fault vocabulary to the bus and still not
move the locomotive.

Rejected: **retrying the cross.** A transit that timed out did so for a
physical reason, and a second throttle-up against a derailment makes it worse.

## Stopping is two commands, and the second one is the backstop

*Stop* is not one thing on DCC.

- **An emergency stop broadcast** — speed zero to every decoder — needs the
  track still powered and the command station still reachable. It is the
  gentler stop and the one to try first.
- **Cutting track power** works when nothing else does, and is therefore the
  only one that can be the backstop.

And neither survives the adapter's own death. If the process holding the
throttle dies, no software above it can stop a train, because every layer above
speaks to the rails through it.

So the last leg is **not software**: track power is held on by something that
stops holding when the adapter stops running — a watchdog that must be kicked,
dropping a relay when it isn't. This is the same layer
[ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md)
already leans on when it says the rails are dead until a person switches them
on, and the same reason: a guarantee that survives the software has to live
under it.

## Not built on MQTT

An MQTT last will would announce a dead connection promptly, and it is the
obvious tool. It is **not the mechanism** here.

The bus contract is the MQTT-safe intersection
([ADR-0008](0008-bus-contract-is-the-mqtt-safe-intersection.md)) — nothing may
rely on what MQTT cannot give. A safety property built on a last will inverts
that rule without repealing it: it relies on what MQTT *alone* can give, so the
in-process binding cannot hold it and the simulator cannot exercise it. A
watchdog that only exists in production is a watchdog nobody has ever seen
work.

The three legs above are all inside the contract. Expiry rides a number every
binding already mints; the transit bound and the power backstop are the
adapter's own business either way. A last will remains **permitted as a faster
detector** of one failure mode, at the broker layer, changing no behaviour that
is not already correct without it.

## Consequences

**`cross` gains a field, and the inventory says so.** It becomes
`train, connection, transit, into, boundary` — alongside the `speed` that
[ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md) already
has it gaining. The driver mints neither: both ride in from `move_granted`,
which keeps the driver stateless.

**The expiry window is testable today**, before any hardware exists. The
simulator is a layout-interface binding like any other, so a replayed `cross`
can be delivered to it and refused, in the milestone-1 in-process bus. That is
the point of putting the mechanism in the contract rather than in the adapter.

**The simulator's binding of the other two legs is a no-op**, and stays behind
the interface ([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)):
a simulated detector always fires and a simulated rail has no power. The
timeout and the relay are the physical binding's, and no app grows a field or a
branch for them.

**A wedged block has no automatic recovery**, by choice. Named here so it is
not later discovered as a gap: the dispatcher has no notion of a failed
transit, nothing cancels a request, and the operator's path out is the hold
plus a placement.

**This is milestone-2 work**, not milestone 1
([MILESTONE-1.md](../MILESTONE-1.md)) — there is no hardware adapter yet, and
the transit bound and the power watchdog arrive with the DCC-EX driver. Only
the `boundary` field on `cross` and its refusal rule land earlier, because they
are contract and because a stale command is dangerous the day the broker
replaces the in-process bus, which is before any hardware.
