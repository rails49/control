# Broken hardware is reported, never worked around

Resolves [#280](https://github.com/rails49/control/issues/280). Two findings
in the batch review of [#273](https://github.com/rails49/control/issues/273)
turned out to be one defect wearing different clothes:

- the station's reconnect loop died on the failure it exists to survive, and
  the app then dropped everything every client sent, forever — it papered over
  a pulled cable by becoming a black hole;
- the station buffered without limit for a client that had stopped reading,
  until it was killed for memory and took the command station away from every
  other client — it papered over a peer that had gone by absorbing the cost
  itself.

Both were written as if the software's job were to keep going no matter what
the hardware did. It is not. Neither had a rule to point at, and both got past
review, so the rule is written down here.

## The rule

**Broken hardware is reported, never worked around.** When a device, a link or
a peer fails, the software says so, keeps saying so while the failure lasts,
and does the least it can that stays truthful. It does not absorb the failure
silently, does not queue work for a device that is gone, and does not pretend
the failure did not happen. Repair is a person's job; the software's job is to
make it obvious that repair is needed.

*The least it can that stays truthful* is the operative half, and it is a
ceiling rather than a floor. Three things it forbids:

- **No stand-in.** Nothing synthesizes the answer the device would have given,
  and nothing reports a state it can no longer observe.
- **No queue.** Work addressed to a device that is not there ends there. A
  buffer that drains on reconnect is the failure arriving late instead of the
  failure being reported.
- **No silence a reader mistakes for success.** A failure that produces the
  same output as a working railroad is the one answer nobody can act on.

## It is ADR-0030's operating corollary

[ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md) ranks the
two bindings of the layout interface: the physical railroad is normative, and
where the two could differ it decides. That settles what the software is
*for*. This settles what it may *hide*. The same railroad decides both, and
for the same reason — a convenience that reads well against a simulator, where
nothing is ever unplugged, becomes a defect to find on a layout where things
are unplugged all the time.

Both findings are simulator-shaped thinking in an app that has no simulator:
keeping going and staying quiet is right for a process whose peer cannot fail,
and wrong for a process holding a cable somebody can trip over.

## A payload is data; a device is a condition

This is the distinction a reader will get wrong, so it is stated plainly.

[SYSTEM.md](../SYSTEM.md) rule 4 says a consumer validates every payload it
reads and **never raises on one**: an unreadable payload is dropped, or
answered where the payload carries an id
([ADR-0034](0034-the-bridge-enforces-the-topic-the-dispatcher-the-payload.md),
[ADR-0021](0021-a-bad-request-is-answered-not-raised.md)). That rule stands
untouched, and this one does not reach it.

A **payload** is data. It arrived once, it was wrong once, and dropping it
loses one message from a source that proves nothing about itself. There is
nothing to keep reporting: the next payload is a fresh question.

**Broken hardware** is a condition. It did not arrive; it *holds*, and it goes
on holding until a person changes something on the railroad. The two get
opposite treatment for the same reason — truthfulness. Dropping a payload
claims nothing; dropping an outage after mentioning it once leaves the
software claiming, by its silence, that the railroad is working.

Rule 4's own escape hatch is the shape to copy: `state/power` fails towards
`off` ([#181](https://github.com/rails49/control/issues/181)), which is the
consumer's rule about the condition the payload was reporting, not about the
payload.

## Where the repo already does this

The rule is not new behaviour. It is the argument that four existing
decisions were made by, none of which could cite it.

**A command is honored now or ignored.** While the device is away, what a
client sends the station is dropped and the client stays connected; a queue
that flushes on reconnect is a train that moves minutes after someone asked
for it, which is why the broker keeps nothing across a restart either
([docs/station/README.md](../station/README.md),
[#219](https://github.com/rails49/control/issues/219),
[#202](https://github.com/rails49/control/issues/202)). The drop *is* the
least it can do that stays truthful, and the outage says on stderr that it is
happening.

**Emergency stop is a hardwired contact, and no software command stops a
locomotive.** The stop is a control on the command station, reported to the
app as `stopped` on `tc49/layout/state/power`, and the run holds on it
([CONTEXT.md](../../CONTEXT.md), **Emergency stop**;
[ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
`move` carries no speed field and nothing on the bus retracts one, so
[ADR-0049](0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md) puts
stopping a locomotive out of scope even in the case that wants it most
([#271](https://github.com/rails49/control/issues/271),
[#232](https://github.com/rails49/control/issues/232)). A software stop would
be a work-around for the contact: it would work until the thing that took the
locomotive away was the thing carrying the command.

**An unexplained reading holds the run**
([ADR-0048](0048-an-unexplained-reading-holds-the-run.md)). A detector reading
the lock table cannot account for is neither explained away nor ignored: the
run holds, every signalled end shows `stop`, and the block is named on
`tc49/dispatch/state/disputed` for a person to walk. That ADR rejects dropping
the reading in the words this rule generalizes — ignoring it is choosing the
picture over the railroad.

**Hardware checks stay out of `scripts/check.sh`, and the physical link is
verified at runtime.** The station's tests use a pty as the device, so the
gate is green on a laptop with nothing plugged in, and the actual link is one
command against the running mirror
([docs/station/README.md](../station/README.md), *Checking it against a real
station*; [#217](https://github.com/rails49/control/issues/217)). Both halves
are this rule. A gate that reached for the cable would report a hardware
failure as a software one; a gate that faked the cable and passed would report
nothing at all. The link is checked where it can be answered truthfully, by
the person who can also fix it.

## The alternative

**Keep going and stay quiet.** It is what both findings did, and it is the
obvious thing to write: swallow the exception, hold the bytes, let the client
keep its socket, and hope the cable comes back before anyone notices. It is
cheap, it needs no vocabulary, and on the day nothing breaks it is
indistinguishable from the rule adopted here.

It was rejected because it converts a five-minute repair into a silent
railroad nobody can diagnose. The cable goes back in the socket as soon as
somebody knows it is out. What the quiet version leaves instead is an operator
watching a normal-looking panel while nothing they press reaches the rails, a
log that says the app is fine, and — in the buffering case — a process that
dies of a symptom, memory, with nothing connecting it to its cause. Hiding the
failure does not avoid it; it moves the cost onto the person holding the
screwdriver, who now has to find it first.

It also spreads. Once one component covers for a peer, the next one
downstream is written against a peer that never fails, and there is no longer
a place where a failure is visible at all.

## What it rules on

- **Extends ADR-0030**, which carries a note saying so. ADR-0030 ranks the
  bindings; this says the same ranking governs what may be hidden. Nothing in
  ADR-0030 changes.
- **SYSTEM.md rule 4 stands as written.** An unreadable payload is still
  dropped and still never raises. This rule is about conditions, and it adds
  nothing to how a payload is read.
- **ADR-0048 stands** as this rule's instance inside the dispatcher, and its
  argument is now general rather than about detectors.
- **ADR-0049 stands.** "It stops no locomotive" is this rule, and stays out of
  scope for the same reason.
- **[GOALS.md](../GOALS.md) stands, reread.** "Hardware is assumed perfect" is
  a decision about which failures the software goes looking for — a set that
  is empty until there is a layout to learn from. This rule is about the
  failures it already sees, and the two do not meet: not hunting for a
  detector fault is allowed, and hiding an outage the software is holding in
  its hand is not.
- **It coins nothing.** *Report*, *drop* and *outage* already carry the rule,
  and [CONTEXT.md](../../CONTEXT.md) is unchanged: a name here would be a word
  for a decision rather than for anything on the railroad.
- **No code changes with it.** The two findings above are their own issues and
  land on their own; this records the rule they will be fixed against.
