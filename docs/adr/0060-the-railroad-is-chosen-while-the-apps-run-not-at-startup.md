# The railroad is chosen while the apps run, not at startup

Amends decision 2 of
[ADR-0059](0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md).

ADR-0059 made one broker run one railroad, named to every app process when it
starts, and added a clause: "switching railroads is restarting the apps, and
the band's railroad picker goes with the bridge."
[#371](https://github.com/rails49/control/issues/371) states it flatly — "There
is no topic to choose a railroad."

That clause does not engage with
[ADR-0038](0038-the-ui-is-one-app-with-views-of-one-railroad.md), which had
considered restricting the picker and declined:

> The picker is not restricted on that account: a swapped railroad comes up
> **held** (ADR-0037), and what actually keeps wheels still is the track-power
> command, which is the hardware adapter's and not the browser's. Restricting
> the picker would buy nothing the hold does not already give, and would cost
> exploring drawn railroads in simulation, which is worth keeping.

## What removing the picker costs

The app holds one railroad and every view is a view of it (ADR-0038), so with
no picker the editor edits whatever railroad the apps were started on.
**Creating a railroad becomes impossible from the app**: starting the apps on a
name the store does not have leaves the layout interface with no drawing to
bind to, and the drawing cannot be made without the apps already running on it.
A person with a box in front of them and no terminal could not draw a second
railroad.

## Decision

**The railroad is chosen on the bus.** `tc49/layout/railroad_wanted` is an
event topic, browser-writable, one field `railroad`. The layout interface
answers it: it is the app bound to a railroad and already the publisher of
`tc49/layout/state/railroad` (#371). Every other app follows the **state** row
and never the wanted, as the scheduler follows `train_placed` and never
`placement_wanted`. One writing role
([ADR-0035](0035-a-topic-has-one-writing-role.md)) and one responder
([BUS.md](../BUS.md#event-inventory), rule 4).

The band's picker writes it, and stays.

Decision 2's first half is untouched: one broker runs one railroad, topics stay
flat, and a namespace level per railroad is still rejected for the reason given
there.

## Track power off is the precondition

**The picker is live only while `tc49/layout/state/power` reads `off`.** While
the track has power it is inert and says why.

This is a precondition, not a sequence. Turning the power off is a gesture a
person already has, and it is already two steps: the panel asks the run to
drain, waits for the dispatcher to write `held`, then commands power off
(ADR-0051, `ui/src/ui/tc-panel.ts`). Loading a railroad does not repeat any of
that. It reads one retained row.

A sequence run by the picker was rejected: it would duplicate the panel's
gesture and put a shutdown in a page that can be closed halfway, a risk the OFF
press already carries (`tc-panel.ts:94`) and that there is no reason to have in
a second place. The layout interface running one was rejected too, and is not
available in any case — that app "never writes `off` of its own accord: it
writes the word it was told to write" (`layout/interface.py`). The dispatcher
owns the drain; the layout owns the power state as an observation folded from
the hardware. Neither commands.

**Why power and not a held run.** ADR-0037 as amended by
[ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)
and [ADR-0049](0049-a-request-ends-by-cancellation-as-well-as-by-arrival.md)
blocks commitment, not motion: a train already under a committed route keeps
going, and on a physical railroad the locomotive keeps rolling whatever the
software forgets. With the power off nothing can move and "no turnout throws
until a person turns it on" (`layout/interface.py`).

The person who turns the power back on is the one confirming that the rails
match the drawing just loaded, which is ADR-0051's operator as the backstop.
That is what makes this safe on a railroad wired to steel and not only in
simulation: rebuilding a station and loading the matching plan is the ordinary
case, and no check the software can run would tell it whether the two agree.

### The precondition is about steel

*Amended 2026-09-05, after the picker landed dead on every simulated box.*

The precondition asks a person to confirm something no software can check:
that the rails in front of them match the drawing just loaded. **A binding
that drives no hardware has nothing to confirm.** Nothing rolls when its model
changes, no turnout throws, and there is no steel that could disagree with the
drawing.

**A binding that drives no hardware answers `railroad_wanted` whatever the
power row says.** The precondition binds the binding that drives hardware.

This is a correction, not a carve-out. "Why power and not a held run" above
argues entirely about physical consequence — a locomotive that keeps rolling
whatever the software forgets, a turnout that must not throw — and then states
the rule in terms of a row that a binding with no hardware writes as a
constant. Simulated track is always live and says so (`simulator/sim.py`,
[ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)), so the
rule as first written refuses the gesture for ever in exactly the place this
ADR's own motivation is strongest: a person with a box and no hardware, who
otherwise cannot create a railroad from the app at all.

The exemption is a property of the binding, not a name — not "the simulator" —
so a later binding that drives nothing inherits it without another amendment.
Nothing on the bus says which kind is running, since ADR-0030 keeps simulation
out of every other app's fields, topics and branches; it is expressed where the
app is built. The binding that drives hardware hands its answering the topic
its supply is on. One that drives none hands it nothing (`lib/loading.py`,
`Answering`).

## Loading a railroad is a cold start

The new railroad comes up at rest, which
[ADR-0054](0054-the-railroad-comes-up-at-rest-and-points-replay.md) already
requires. Nothing carries over.

**Each app clears the retained rows it owns, then rebuilds.** Dropping what an
app holds is not enough. The broker keeps retained values while it runs
(ADR-0059 decision 3), so the previous railroad's rows would still be delivered
to anything subscribing afterwards — desired speed per locomotive, desired
position per point, occupancy per block end — keyed to blocks and addresses the
new railroad may not have, and nothing republishes a row for a block that no
longer exists. One writing role means each app knows exactly which rows are its
own.

Clearing the observed rows leaves point and signal position **unknown**, which
is the true statement: a person may have moved them by hand. ADR-0054's replay
at power-on resolves it, as it does after a broker restart.

No trains are placed. A person puts them back through the stock view and drag
placement, the same path as a railroad opened for the first time.

## An app with no railroad stands

*Added 2026-09-22, after the first box ever booted against an empty store
([#564](https://github.com/rails49/control/issues/564)).*

A railroad named on a command line is where an app starts and not what binds
it. An app that **exited** because the store had no such railroad was treating
a starting point as a binding, which is the thing this page is about. On a box
whose store is empty — an ordinary state, nothing seeds a store
([docs/DEPLOY.md](../DEPLOY.md)) — four of the six containers exited 1 and were
restarted for ever, while the store beside them came up and answered.

**An app with no railroad stands.** It stays up, publishes nothing, watches
the row or the gesture it watches anyway, and is built on the first railroad
named that the store can give. It is the rule already written for a reload —
an app still running the railroad it had is worth more than one running none
([ADR-0050](0050-broken-hardware-is-reported-never-worked-around.md)) —
applied where there is nothing to fall back on.

**`TC49_RAILROAD` has no default.** A default that resolves on a box which has
done nothing but install does not exist: nothing seeds a store, and the
railroads in this repository are fixtures on nobody's box. So a box that has
named no railroad passes none, and its apps stand until one is named.

**The precondition binds a railroad that is loaded.** An app standing has
nothing bound to the steel: no turnout throws under it, it has published no
supply, and there is no drawing for the rails in front of a person to disagree
with, which is the whole of what the operator is being asked to confirm above.
Waiting for `off` there would refuse the first railroad a box ever loads and
leave a redeploy as the only way to name one, which is what this page says
choosing a railroad is not. The exemption is the absence of a **railroad** and
not the absence of hardware: they are separate, and the binding that drives
hardware waits for `off` again the moment it has one.

The broker is waited for **before** the documents, where the order used to be
the other way round (`lib/startup.py`): an app that cannot hear the row has no
way out of a railroad that was never drawn.

## What was rejected

**Restarting the containers from the UI.** The same operation on the person's
path under another name, and it would need the app to reach the container
runtime, which nothing else here does.

**A broadcast every app acts on independently.** One gesture with several
responders that can disagree about which railroad is loaded, which is what rule
4 prevents.

**One railroad per box.** What ADR-0059 assumed. Rails get rebuilt — a person
tries two track plans for a station on the same layout — so a box wired to
steel does load more than one railroad over its life. Allowing it only in
simulation would also make one railroad privileged over the others for no
reason a person would recognise.

**A last will on any row of ours.** ADR-0059 decision 7 permits one on
`device/link/<id>`. Our apps publish no link row; it is for hardware
participants (ADR-0050, ADR-0058). And after a shutdown the state worth knowing
is mostly not knowable: locomotives stand still, while turnouts and signals are
wherever somebody left them, including by hand. A will would assert a state
with a high chance of being wrong.

## Consequences

- #371 keeps its row and loses its last line.
- A communication issue carries `railroad_wanted`, landing after every app has
  its own process (#373–#378).
- #372's cold-start check covers a reload as well as a start, and asserts the
  previous railroad's retained rows are gone rather than only that new ones
  appeared.
- The picker is inert while the track has power, and says why.
- An app started on a railroad the store does not have stands, and
  `TC49_RAILROAD` carries no default (#564).
- **The band's picker cannot yet ask on a box that has never loaded one.** It
  is dead while `tc49/layout/state/power` reads nothing (`ui/src/ui/tc-header.ts`,
  "no railroad is running to ask"), and a standing binding publishes no supply,
  so the first railroad on a box is still named in `TC49_RAILROAD` and
  deployed. The apps answer the gesture; what cannot send it is the page.
