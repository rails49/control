# A block's role and filter are advice to the generator

Resolves [#200](https://github.com/rails49/control/issues/200) of the
milestone-2 map. A generator that invents continual traffic has to pick a
destination, and the drawing says nothing today that would let it pick a
sensible one: a block declares a length and no more, so every block looks
alike and a goods train is as likely to be sent to the passenger platform as
to the yard.

Nothing here is built. The map is a planning map, and the fields land with
the generator, [#210](https://github.com/rails49/control/issues/210).

## Two fields, because two different things are being said

A block gains two optional keys on its **drawing symbol**, where the length
already is. A platform, a dead-end spur and a stretch of running line are
facts about the track, not about tonight's session, so they belong to the
drawing and reach every consumer through derivation
([ADR-0015](0015-drawing-is-the-source-of-truth.md)).

**`role`** — `station`, `siding` or `through` — says whether a request may
*end* in this block, and how long a train may then stand there. A **station**
is called at and left again. A **siding** holds a train as long as it likes:
minutes, days, or forever. A **through** block is never a destination.

**`admits`** — a set of train kinds — says which trains may be *sent* there.

They are orthogonal, and collapsing them into one enumeration would lose the
common case: a platform road that trains also run through is a `station` that
`admits` only what carries passengers, and neither half implies the other.

The word is **`through`** and not *transient*, which the first draft used.
**Transit** is a hard-worked term in this glossary — an (end, end) pair
through a connection — and two near-identical words for unrelated things in
one drawing is a bug waiting for a reader. **Siding** stays: CONTEXT.md
refuses it only as a synonym for *terminal block* and explicitly leaves it
available as the physical description, which is exactly what a role is.

## Neither is feasibility, and the dispatcher gains nothing

No check, no new member of `tc49.lib.rejection`.

The ticket assumed the opposite — the dispatcher is the single feasibility
authority, so a filtered block is a rejection reason — and that is wrong
about what these filters *are*. Every physical impossibility is already
**length**: a shed a locomotive will not fit in is `no_fit`, and a train must
fit in every block of its route. What is left over is **policy** — you do not
berth a goods train at the passenger platform, the coal spur takes coal — and
nothing on the steel prevents any of it. A dispatcher enforcing policy
answers a person's deliberate drag with `request_rejected`: the app telling
its owner no about something the layout permits.

[ADR-0028](0028-the-scheduler-knows-where-trains-stand.md) is intact. It
forbids the scheduler *judging feasibility*; a preference about which
destination to invent is the "knows enough to propose sensibly" it licenses.
There is still exactly one authority for what is **possible**, and now a
second, weaker thing for what is **sensible**, held by the only component
that invents traffic.

Rocrail arrives at the same place from the other side, which is worth
recording because it has the operating hours. It keeps two mechanisms:
**block type × train type** — eight block types against twelve train types —
is a *preference* table that sorts candidate destinations into preferred and
alternative and picks randomly among the preferred; **block permissions**
(include and exclude lists by id, class, engine type, era, length) are the
restriction. And even the restrictions carry the caveat that in automatic
mode with a defined destination, permissions are not respected for the
destination block or the route to it. An explicit destination overrides.

## Kind is the only filter dimension

Of the three the ticket listed:

**By length** is already the block's length and `no_fit`. A second spelling
would let one drawing say two contradictory things about the same berth.

**By name** — "only `ice_71` uses platform 1" — is a timetable, and authored
schedules are out of scope on this map. It is also the one filter that rots
when a train is split or renamed
([#209](https://github.com/rails49/control/issues/209)).

**By kind** is the only one that is a durable fact about the berth rather
than about tonight.

## `admits` is a set of train kinds, tested against the derived value

Set membership, as Rocrail does it: `admits: [passenger, mixed]` accepts a
mixed train and refuses a goods one.

Matching the *cars* one by one — admit a train when every hauled car's kind
is listed — was rejected, though it looks tidier. It can only produce
upward-closed sets, so it cannot say "mixed yes, pure freight no", and that
is the historically real case: a mixed train carried passengers and therefore
called where passengers were, while the goods train did not.

The consequence is that **coupling a passenger car to a goods train flips it
from refused to admitted**, its derived kind becoming `mixed`. That is not a
bug to be engineered away. A goods train with a passenger vehicle attached
*is* a mixed train — it is why the category has a name — and derivation is
what makes the platform notice it without anyone re-typing a label. Rocrail
never meets this because its train type is *authored*; ours is derived
([ADR-0045](0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).

**The two kind vocabularies are different lists**, which the glossary left
implicit and a filter makes load-bearing. A **model's** kind is one of
`locomotive`, `passenger`, `freight`, `special`. A **train's** derived kind is
one of `passenger`, `freight`, `special`, `mixed`, `light engine`.
`locomotive` is never a train kind, and `mixed` and `light engine` are never
model kinds. `admits` lists **train** kinds, so an engine shed writes
`admits: [light engine]` and never `[locomotive]`.

## Kind becomes a total function

A set filter forces it: every train must have exactly one kind for membership
to mean anything, and `special` with `freight` was undefined.

**Exactly one sort among the hauled cars gives that kind; more than one gives
`mixed`; none gives `light engine`** — locomotives ignored throughout, as
ADR-0045 already has it. So `mixed` means *more than one sort hauled*, not
specifically passenger-and-freight, and a crane in a goods train reads
`mixed`: coarse, never wrong.

That settles what ADR-0045 left of #200. **`mixed` is derived and never
authored** — it appears on no model, only in a filter. **`special` is an
ordinary kind and not a wildcard**: a crane is admitted where `special` is
listed and nowhere else. Giving it privileged behaviour would be writing the
rules for special cars, which left this map's scope with authored schedules.

## Destinations only, never origins

Both fields constrain where the generator **sends** a train, never where one
may **be**.

A person shunts a train into a `through` block by hand, and
[SAFETY.md](../dispatcher/SAFETY.md)'s scheduler obligation — that an
obstructing train eventually gets a request — means it must still be picked
up. A role that disqualified a block as an *origin* would starve a train by
reading a label off the drawing.

Placement is unchecked for the same reason the filter is advice: a person
puts stock where the steel allows
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)).

This makes `through` on a **terminal block** legal and useful rather than the
contradiction it first looks like — a block nothing can pass through and
nothing may be sent to is a **headshunt** or a fiddle track, shunted into by
hand and never chosen by the generator.

## Defaults keep every drawing working

Both fields are optional. **An absent `role` is `station`; an absent `admits`
is every kind.** All four drawn railroads declare a length and nothing else,
and they behave exactly as they do today.

The alternative default, `through`, would leave a generator with no
destinations at all on an unlabelled drawing — a silent failure rather than a
plain one. The honest cost of `station` is that an unlabelled Gotthard reads
as all-stations, and the fix is that the author labels it.

## Rejected

**The dispatcher enforcing the filter**, with a new rejection reason. Above:
it is policy, not feasibility, and it puts the app between a person and their
own railroad.

**The generator enforcing it and the dispatcher not knowing**, but with the
UI's drags filtered too. Same objection one layer up, and it would make the
panel and the bus disagree about what a request may say.

**A separate length or name filter.** The first duplicates `no_fit`; the
second is a timetable in the wrong document.

**Matching the cars rather than the train's kind.** Tidier, strictly less
expressive, and wrong about mixed trains.

**Adopting Rocrail's block-type × train-type taxonomy.** It answers something
`admits` cannot — a goods train may *legally* stand on the intercity main but
should *prefer* the yard — and it is still the wrong thing to buy here: an
eight-by-twelve compatibility table is how Rocrail substitutes for a
timetable, it is complex and it is *still* limited, and someone who wants
that much control over where traffic goes should author a schedule and get
more. Out of scope on the map, with the schedules it stands in for. If an
unweighted pick produces silly traffic, the upgrade is a weight rather than a
second taxonomy, and #210 can reach for the table then knowing what it costs.

**Roles as operations rather than layout** — beside a scenario, or on the
roster. A platform is where it is every evening; anything that varies session
to session is authored-schedule material.

## Consequences

**A block stops being a length.** The two fields ride derivation into the
derived layout beside `length`, so `Layout.blocks` becomes a record rather
than `dict[str, int]`, and the drawing's block symbol takes two more optional
keys — it already takes one.

**The glossary gains `Role` and `Admits` and rewrites `Kind`**, which now
carries both vocabularies and the total rule. GOALS.md's Tracks section gains
the same two sentences, since it is the end state.

**Nothing else reads them.** The dispatcher ignores both fields; the scheduler
is the only reader, and only its generator.

**No numbers here.** A role carries a name. How long a station dwell is, and
how the generator weights the destinations these two fields leave open, are
#210's — which keeps a per-railroad tuning knob out of the store's schema.
#210 starts with an unweighted pick, and whether it needs more is fog on the
map until there is run data.
