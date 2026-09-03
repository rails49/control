# The railroad owns cars, and a train is an ordered list of them

Resolves [#199](https://github.com/rails49/control/issues/199) of the
milestone-2 map.
[ADR-0039](0039-a-train-may-be-off-the-layout.md) left this open in as many
words: what a train carries beyond a name and a length — cars, kind,
addresses, priority — "is a separate design, and this decision takes none of
it". This is that design.

Nothing here is built beyond the read path and the fields `layout` consumes.
The map is a planning map, and the migration is
[#223](https://github.com/rails49/control/issues/223).

**Amended under
[ADR-0061](0061-stock-with-nothing-of-its-own-is-named-by-its-model.md):**
"zero overrides is the common case and still names its model, so a car has
exactly one shape" no longer holds. A consist entry names either a car or a
model, and `cars` holds identified stock — an item with an address or with a
field corrected on it. An item with neither carries only its name, which for
ten identical hoppers records a distinction that does not exist. A car entry
with neither is still legal, so nothing here migrates. The three levels below
stand, and so does the rejection of a car that states its own fields and names
no model.

## Three levels, because three different things are true

A **model** is what a product *is*: a length, a **kind**, and the meaning of
each DCC function — which number sounds the horn on that item. It is a fact
about the product and not about any railroad, so two railroads owning the
same item do not each write it down, and it is knowledge someone else may
already hold.

A **car** is one the railroad owns: **a model with zero or more fields
overridden**, plus its own **DCC address** where it has a decoder, unique
across the railroad. Zero overrides is the common case and still names its
model, so a car has exactly one shape. Scratch-built and kit-bashed stock
earns a model entry of its own rather than a second kind of car.

A **train** is an **ordered list of cars**, each recording which way round it
is coupled. A **locomotive is a car** whose model's kind says so; that is
what lets one list hold both, and it is why an address hangs on a car rather
than on a train.

The levels are not decoration. Each holds facts with a different lifetime: a
model's outlive the railroad, a car's outlive the session, a train's are made
up this evening and unmade the next.

## The roster changes referent, and the glossary gives

CONTEXT.md defined **roster** as "the trains a railroad owns" and ADR-0039
defined *known* as being in it. A railroad owns **cars**, not trains — a
train is something a person makes up out of cars and takes apart again — so
the roster becomes the cars, with trains beside them in the same per-railroad
document.

ADR-0039's split is not lost, it moves one level down: a **car** is *known*
by being on the roster, a **train** is *placed* by being in `block_of`, and
absence from `block_of` is still what off the layout means. Trains stay
**durable** — a railroad keeps rakes made up between sessions, and they go on
and off the layout as they do today — and are both authored and editable at
run time. That is what keeps every scenario file working in kind, and it is
what lets [#209](https://github.com/rails49/control/issues/209) be a ticket
about runtime *mechanics* rather than about a data model it would otherwise
have to invent.

## A car's address takes no system prefix

[ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)
made an address name its system as its first level, so a translator
subscribes only its own and no ownership table exists anywhere. **That rule
holds for points and not for traction**, and the reason is physical rather
than aesthetic.

Turnout wiring genuinely *can* be split across systems — some turnouts on
one, some on another — and two systems name the same turnout differently, so
the prefix is carrying real information. Traction cannot be split: one thing
powers the rails, and every locomotive on them answers to the number
programmed into its decoder, whoever sends the packet. That number is
programmed once and generally kept forever, because reprogramming it is
confusing rather than hard.

So a car carries a **bare address**, and a railroad changing command station
rewrites nothing. The consequence for
[#217](https://github.com/rails49/control/issues/217) is that the locomotive
device topic is keyed without a system level, and which translator drives
traction is railroad configuration — one setting, or simply which translator
is running. Still no ownership table, which is what ADR-0043 was protecting.

## Kind is the model's, and a train's is derived

Kind belongs to the **model**: an item is a locomotive, or passenger, or
freight, or special, whoever owns it.

A train's kind **derives from the cars it hauls, ignoring locomotives**.
Every hauled train has one, so counting them would make every train *mixed*
and the classification would say nothing. All-freight derives freight;
passenger and freight together derive mixed; nothing but locomotives is a
light engine, which is a real move rather than a degenerate case.

That answers half of [#200](https://github.com/rails49/control/issues/200)
before it is worked: **mixed is derived, not authored.** What survives there
is whether *special* is a filter or a wildcard, now a question about a
model's kind.

## Priority is strict, and gives up a bound it is worth giving up

Priority rides on the **train**, lowest number highest, read from the roster
as length already is.

It is **strict among simultaneously launchable requests**. Where a
higher-priority and a lower-priority request could both launch, the higher
one wins and the lower waits, *regardless of age*. Where the higher one
cannot launch and the lower one can, the lower one goes — which is the
existing greedy scan and needs nothing new, since a refused request is
skipped and the next is tried.

[ADR-0012](0012-the-pending-scan-ages-by-refusal-count.md) bounds starvation
by aging on refusal count, and this **keeps that bound within a priority
level and gives it up across levels**. That is a deliberate trade and not an
oversight: it is what real railroads do, and it is why freight often runs at
night, once higher-priority passenger traffic has subsided. The key stays
integer and dispatcher-derived, so it stays deterministic and replay is
unaffected.

## Orientation is a car's place in its train

Forward is a fixed direction of the physical locomotive — obvious on an
asymmetric one, found by trying on a symmetric one. Once it is on the rails,
forward corresponds to a direction on the track, and turning the locomotive
around flips it.

The system holds this as **each car's orientation within its train**,
composed with the train's **facing** to give a direction on the track. It
matches how the fact behaves: a locomotive's orientation is fixed while the
train is made up, and what changes when the train runs a reversing loop is
the train's facing, which is already tracked. It is also the only shape that
handles top-and-tail correctly, where a locomotive at each end must run
opposite.

**One thing is deliberately left open**: `layout` needs facing and has no
route to it. Facing is scheduler state
([ADR-0019](0019-facing-is-scheduler-state.md)) on
`tc49/schedule/state/facing`, and `train_placed` carries train and block
only. Either `layout` reads a scheduler topic, inverting the layering, or it
maintains its own orientation from the placement plus every `move` it
executes, routes being strict pass-throughs. It is hard to think through
without trying, so it waits on running experience and stays fog on the map.

**Settled under
[ADR-0052](0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md):**
`layout` subscribes to the retained state topic. The second option is rejected
as a second copy of a fact one component already holds, and reading a retained
state topic is not the inversion it looks like — facing is on a state topic
because views read it. Everything else here stands.

## `layout` reads the roster

`tc49/drive/move` names a train; ADR-0043 has `layout` writing desired speed
per locomotive address. **`layout` bridges those by reading the railroad's
roster**, as the dispatcher already does for lengths.

## Rejected

**Trains only, cars deferred to #209.** Defensible on the rule that a field
enters when something consumes it, and wrong on the ownership question: a
railroad owns cars, and a model that says otherwise puts the milestone's own
data model in the way of the first split.

**A car that states its own fields and names no model.** One rule for reading
a car and two for authoring one. A model with zero overrides costs nothing
and keeps the shape single.

**A train stating its own length, cars optional.** Two ways to know a length
in one document, and that is the field that rots — the roster's whole present
job is that a train's length is *one* fact.

**A system-qualified locomotive address.** Consistent with ADR-0043 and wrong
about the hardware, above. It would also make a change of command station a
rewrite of every car.

**Priority as a tie-break after refusal count**, and **priority aged by
refusals** (`priority − refusals`). Both preserve ADR-0012's bound across
levels, and both make priority mean almost nothing at the moment it is meant
to bite. The bound is the thing being traded, knowingly.

**Orientation as runtime state in `layout`**, seeded at placement and flipped
by a gesture, or calibrated afresh each session by driving and watching.
Neither represents top-and-tail, and the second makes the first move of every
evening a coin flip on live track.

**The address on `tc49/drive/move`**, so the driver reads the roster and
`layout` needs none. It puts a DCC address on the dispatch-side contract,
which is what ADR-0022, ADR-0025 and ADR-0030 have spent four decisions
keeping out of it.

**Copying JMRI's or Rocrail's stock format.** Both have solved this and both
have had a long time to accumulate history worth not inheriting. What they
are worth is two worked examples and, for JMRI, a possible import: DecoderPro
already holds the owner's locomotives with their addresses and function
labels, so an import would type every address once instead of twice.
[#222](https://github.com/rails49/control/issues/222) establishes that as
fact rather than prior.

**Building the CRUD implementation now.** Every act that writes stock — build
a train from cars, add a car to a train, merge two — is a UI gesture, and the
UI is a later app; writing it now means writing it against an imagined caller
and testing it against a synthetic one. The **contract is defined now**; the
implementation lands when something needs it.

## Consequences

**The glossary is rewritten around cars.** **Roster** and **Train** change,
**Placed** loses its claim that a placed train is on the roster, and
**Model**, **Car**, **Catalogue**, **Kind** and **Orientation** are new
entries. [GOALS.md](../GOALS.md) changes with them, since it is the end state
and stated the old ownership.

**The catalogue is one local database for the installation**, not per
railroad. Searchable, CRUD, ordinary. **Sharing a catalogue between
railroaders is out of scope** — online databases of model railroad products
exist commercially, and reaching one is a different effort.

**Functions are recorded and none is commanded.** A model carries the meaning
of each function; nothing in milestone 2 puts one on the bus, because no
automated driver touches a function to get a train across a layout. That is
also #217's answer, and a manual throttle
([#207](https://github.com/rails49/control/issues/207)) raises it if it wants
it.

**The five existing rosters are rewritten** as a handful of models by length
plus one car per synthetic train (#223). They are synthetic — `t1`–`t6` drive
the sweep — so none corresponds to a product anyone owns, and no benchmark
result may move.

**Milestone 2 builds the read path** and the fields `layout` consumes. Stock
stays hand-authored until the UI.
