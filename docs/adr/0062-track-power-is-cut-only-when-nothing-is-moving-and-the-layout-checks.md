# Track power is cut only when nothing is moving, and the layout checks

Resolves [#390](https://github.com/rails49/control/issues/390). Amends
[ADR-0051](0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md):
its "OFF is the drain trigger" section, and its claim that `layout` never
subscribes to the dispatcher.

ADR-0051 made OFF a two-step gesture: the panel asks the dispatcher to drain,
watches `tc49/dispatch/state/run` reach `held`, and only then publishes
`power_wanted: off`. The guarantee — that the supply is never removed under a
train in motion — lives in the one client that was written to honour it.
`layout` writes whatever `power_wanted` says straight through to
`wanted/track`, and the hardware acts on it at once.

Two things are wrong with that, one of them the issue's and one found
verifying it.

**A second publisher gets no guarantee.** A topic names the component that
answers it and never the one that sent the frame, so nothing about
`power_wanted` says the panel wrote it. A raw client, a test or a later UI
that publishes `off` cuts power under whatever is mid-transit, and strands it
where no sensor will ever say it stopped (CONTEXT.md, **Power off**). Every
other browser-writable gesture is re-validated against current state on
arrival; this one trusts the sender's sequencing.

**`held` does not mean nothing is moving.** A held run is a brake: the
dispatcher commits nothing further, and a move already granted runs to its
sensor (ADR-0037). The dispatcher writes `held` itself when a drain completes,
but a person's HOLD writes the same word with trains still rolling, and the
row carries nothing to tell the two apart. So the panel's wait is satisfied by
the wrong event: one panel drains, a second panel holds, the first cuts, and
a train strands. On one panel alone the wait is never cleared by a GO that
abandons the drain, so a HOLD hours later cuts the power out of a press the
person had moved on from.

The physical railroad has a switch, and nobody stops a second operator
throwing it. What the app can do that the switch cannot is know whether a
train is between blocks, because the dispatcher granted the move and the
sensors have not yet ended it. That knowledge is the dispatcher's, and it is
published so the check can be made where the command is answered.

## Decision

**1. `tc49/dispatch/state/run` carries `moving`.** A boolean beside `run`,
true while any train is **active** or **crossing** (CONTEXT.md) — the same
test the drain's completion already makes — and false otherwise. It is not a
fourth value of the run: the three stand, and `moving` is orthogonal to them.
A held run can be moving; a running run with nothing granted is not.

**2. `layout` applies a plain `off` only when the run is `held` and not
moving.** It subscribes to `state/run` for this. An `off` arriving while the
run is `running` or `draining`, or while `moving` is true, is dropped in
silence and to the trace, as every gesture an app cannot act on is
(ADR-0034). `stopped` and `on` are untouched: an emergency stop asks the rails
for less, and returning to `on` releases nothing (ADR-0041, ADR-0051).

`held` and not merely "not moving", because an `off` on a running run with
nothing granted would race the dispatcher's next grant by milliseconds. A
client that wants the supply removed from a running railroad has the panel's
two words: ask for a drain, and cut when it is done.

**3. No run state is no reason to refuse.** When `layout` holds no
`state/run` — no dispatcher up, or the retained row cleared by a reload
(ADR-0060) — `off` applies. The guard refuses on evidence that something
moves and on nothing else; with no dispatcher nothing has been granted, and a
railroad that could not be turned off would be worse than the race.
`layout` writing `off` at its own start is not a gesture and is not affected.

**4. The panel's OFF waits for `held` and not moving, and drops the wait when
the run is released.** OFF always asks for a drain, including from a held run
— it can be held and moving. The wait ends when `state/run` reads `held` with
`moving` false, and the panel then publishes `off` once. A run that reads
`running` while the wait stands is a drain somebody abandoned, and the wait
goes with it. ON, STOP and leaving the session clear it as before.

## What ADR-0051 keeps

The routing: the command goes to `layout`, which writes `wanted/track`, and
whatever supplies power acts on that. The row and its three words. The panel's
three buttons and STOP's one click with no confirm. The operator as the
backstop. What changes is where the drain-first guarantee is checked, and the
sentence "`layout` never subscribes to the dispatcher" is withdrawn: it was a
consequence of the routing rather than a rule, and `layout` has consumed the
dispatcher's `move`, `aspects`, `train_placed`, `train_removed` and
`facing` since well before this decision.

## Alternatives not taken

**The dispatcher owns the cut.** OFF as one gesture to the dispatcher, which
drains and then publishes `power_wanted: off` itself. It removes the wait from
the browser, but a bare `off` from any other publisher still cuts at once, so
the guarantee still lives in a sender.

**Keep it a panel courtesy.** A bare `off` is the breaker, as on every layout
ever built; fix the stale wait and document the rest. It is the cheapest and
leaves both faults above standing. The app knows something the switch does
not, and the issue's principle — nothing bad happens from an inconsistent
pair of messages — is the one the other seven gestures already meet.

**`held` as the precondition.** No contract change, and it leaves the
drain-then-hold case that strands a train.

## Consequences

**One field on an existing row.** SYSTEM.md's `state/run` entry and the
TypeScript binding gain `moving`. A reader that does not know the field
ignores it; a reader that needs it and does not find it treats the row as
unreadable and drops it, as for any other field it cannot read.

**`layout` gains a subscription and a guard**, and the trace gains a reason
for a refused `off`.

**The panel's OFF is the same three words to a person** and one wait shorter
in the cases that used to go wrong.

**The glossary gains Moving.** Of a run: some train is active or crossing.
Not a state of the run, and not what a throttle reads: a manual train on a
route it was granted is active, whether or not its wheels turn (#207).

**The simulator is untouched** (ADR-0030): what exercises this is a test
publishing the topics.
