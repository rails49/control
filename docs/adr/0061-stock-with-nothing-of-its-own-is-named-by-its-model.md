# Stock with nothing of its own is named by its model

Amends [ADR-0045](0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md).

ADR-0045 made a car "one the railroad owns: a model with zero or more fields
overridden, plus its own DCC address where it has a decoder", and added that
"zero overrides is the common case and still names its model, so a car has
exactly one shape".

That shape is right for a locomotive and wrong for ten identical hoppers. A car
with no address and no override carries exactly one thing: its name. For ten
hoppers that name records a distinction that does not exist — nobody can tell
the third from the seventh standing in a siding — so it is a fiction the
document then asks a person to maintain, and to maintain correctly through
every rake they make up.

ADR-0045's own test says as much. "Each holds facts with a different lifetime:
a model's outlive the railroad, a car's outlive the session, a train's are made
up this evening and unmade the next." An anonymous hopper has no fact of its
own, so it has no lifetime of its own, and nothing for an entry to hold.

## Decision

**A consist entry names either a car or a model.**

```yaml
cars:
  krokodil-a: { model: arnold-ce68, addr: "3" }
  krokodil-b: { model: arnold-ce68, addr: "4" }

trains:
  ore:
    cars:
      - { car: krokodil-a }
      - { model: hopper }
      - { model: hopper }
      - { model: hopper }
  shunt:
    cars:
      - { car: krokodil-b, orientation: reverse }
```

`cars` holds **identified stock**: an item with an address, or with a field
corrected on that item. Anything else is named by its model where it is used.
Orientation works on either kind of entry.

**Identity comes from having something to say about the item.** An address is
the physical identity — it is programmed into that decoder and no other. An
override is a correction true of that item and not of the product. An item with
neither is fully described by "one of these".

Two locomotives of one product keep their two addresses, written once. That is
what `cars` is for, and it is why a person does not restate an address every
time a rake is made up.

**A car entry with neither is still legal.** It is permitted for anything and
required only where there is something item-specific to say, so a person who
wants to name one weathered hopper may, and nothing migrates: the rosters under
`bench/` name a car per train and keep working as written.

## What is unchanged

`Train` is still an ordered list of `Coupled`, and `Coupled` still holds a
`Car`. The loader builds one from the model for an anonymous entry, so length,
kind and functions derive exactly as before and no consumer of the roster
changes. ADR-0045's three levels stand, as does its rejection of "a car that
states its own fields and names no model" — an anonymous entry names a model
and states nothing.

Kind still does not imply an address. `layout` takes "every car with an `addr`
... No `kind` is read: a powered van is a real thing"
(`layout/interface.py`), so what an item has is asked of the item and never
inferred from its product.

## What was rejected

**Auto-created names.** Generating `hopper-1`..`hopper-10` and keeping them out
of sight preserves one shape at the cost of writing down ten distinctions that
do not exist. Reordering a rake would produce a diff that means nothing, and
two hoppers physically swapped would leave the document wrong in a way nothing
can detect or correct.

**A count of what the railroad owns**, with the validator refusing a set of
trains needing twelve hoppers where ten are owned. It catches a real mistake,
and the count drifts the moment an item is bought or broken, with nothing able
to tell the software. A consist that overstates the stock gives a wrong length,
which is the class of error the operator is already the backstop for. It can be
added later as a field on `cars` without changing the consist shape.

**Keying a car by its address.** Unique and physical, but an item may be
identified by an override and carry no address at all, and CONTEXT.md keeps
*address* from serving as an id.

## Consequences

- CONTEXT.md's **Car** and **Roster** entries say what `cars` holds, and that an
  item with nothing of its own is named by its model.
- The store's roster validator accepts both entry shapes; `lib/roster.py` is
  untouched.
- The stock screen lists cars above models: cars are yours and are few, models
  are what anything is made of.
- #388 and #393 carry this shape.
- Nothing migrates.
