# The layout carries the points a transit needs

[ADR-0022](0022-a-symbol-carries-its-hardware-address.md) made `align` the
dispatcher's command, carrying the points a transit needs as address-and-
position pairs, and left one question open: how an address reaches the
dispatcher, which holds a layout, and a layout had no turnouts in it. It
guessed that `addr` would stay out of the layout document. That guess is
reversed here. Derivation stops dropping addresses, the layout document carries
the points each transit needs, and the dispatcher reads them off the `Layout`
it already holds.

## Where they sit

Beside the transits, inside the connection, rather than inside each transit:

```yaml
connections:
  crossover:
    transits:
      up_straight: [up_w.B, up_e.A]
      up_to_dn:    [up_w.B, dn_e.A]
    concurrent:
      - [up_straight, dn_straight]
    points:
      up_to_dn:
        - { addr: "12", position: thrown }
        - { addr: "13", position: closed }
```

A transit name is unique only within its connection, so a table keyed by bare
transit name has to live inside one. The alternative shapes both cost more. A
top-level `points` section would need qualified `crossover.up_to_dn` keys,
reintroducing a dotted string the document otherwise avoids. Folding the points
into the transit — making its value a mapping of `ends` and `points` rather
than an end pair — changes the shape every reader decodes, for a guarantee that
is cheaper as a check: `Layout.from_document` refuses a `points` entry naming a
transit the connection does not have.

The key is absent where a connection has nothing to say, which is how `units`
and `concurrent` already behave. A transit stays what it was — an unordered
pair of ends — so the model does not gain a second level of description. It
gains an appendix saying what a way costs in hardware.

## Why the layout, and not somewhere else

The dispatcher may not read the drawing: `Drawing` lives in the `store` app and
apps never import each other ([ADR-0013](0013-apps-are-deployment-units.md)).
So the address arrives either in an asset the store already serves, or in a new
one.

A third store read was the alternative — `points(name)` beside `drawing(name)`,
built from the same pass-2 walk, handed to the dispatcher as a second
constructor argument. It keeps the layout hardware-free, which was the stated
appeal, and it has precedent, `drawing()` and `/review` being store reads that
sit outside `get()`.

It was rejected because the layout is not hardware-free in any sense that
survives inspection. The drawing carries `addr` and the drawing is the source
of truth ([ADR-0015](0015-drawing-is-the-source-of-truth.md)), so a railroad is
already bound to the hardware it is wired to, one level up. Deriving the
binding down propagates a coupling that exists rather than creating one. What
the third read buys, then, is not purity but a second asset on the dispatcher,
a second thing to wire in `bench/runner.py` and in the live session, and a
second place for the two to disagree about which transits exist.

Moving `Drawing` into `lib` so every app could derive its own was the other
alternative, and it is worse: it relocates the store's whole reason for
existing into shared code to serve one field.

## An unaddressed point is not in the list

A motorised symbol wearing no address is omitted. It is not listed with an
empty `addr`, and it does not stop the layout deriving.

A drawing may be finished as topology and unfinished as wiring, and
[ADR-0022](0022-a-symbol-carries-its-hardware-address.md) says such a drawing
derives and cannot be driven. Derivation's rule is to drop what the layout
cannot act on, and a nameless address is exactly that. The complaint belongs
where it can be fixed, and it already is one: the editor marks an unaddressed
point on the canvas in the quiet weight (#96), computed from the open drawing
with no store round trip, in front of the person who knows what the address is.

The cost is real and worth naming. A transit crossing one addressed and one
unaddressed point derives a `points` list with a single entry, which is
indistinguishable from a transit that genuinely needs one point thrown. The
layout under-reports rather than visibly gapping, and the failure mode is a
route the dispatcher believes it set on a railroad where one point never moved.
That belongs to the class of failure [GOALS.md](../GOALS.md#hardware-that-lies)
assumes away until hardware runs, and the day that assumption is paid off this
is one of the places it will have to look.

## One address, two points

Two points may share an address and then move together, which is how a
crossover is wired and why a throat can have fewer usable ways than its
geometry suggests. So a way can name one address twice. The list is sorted by
address and identical pairs are collapsed: one accessory output commanded twice
the same way is noise, not a fact.

Sorted by address rather than in walk order, because `derive` is
canonically ordered throughout, walk order is geometry the layout otherwise
drops, and points are thrown as a set — nothing depends on the order they go
out in.

Where two points on one address want *opposite* positions the way cannot be
thrown at all, and both entries are emitted verbatim. `motor_faults()` already
reports this at the drawing, and dropping the transit instead would make
derivation's topology depend on addresses, which is a much deeper break than
this ADR is making: #94 established that the derived layout's shape is
unchanged by an address's presence, and that stands for everything except the
`points` key itself.

## Setting before moving

Splitting the two commands between two apps costs a guarantee that was never
written down. Today one component publishes `align` and `move` back to back;
after this, the dispatcher publishes one and the driver the other. The bus
contract refuses cross-topic ordering
([ADR-0008](0008-bus-contract-is-the-mqtt-safe-intersection.md)) precisely so
that nothing leans on it, and SYSTEM.md leaned on it in prose: "publishing
`align` for each so the route is set before anything moves."

Under the milestone binding the guarantee survives either publish order, since
the driver's `move` is enqueued while `move_granted` is being delivered and
joins the back of a queue `align` is already in. Under MQTT, two clients on two
topics promise nothing, and a hardware adapter can receive the `move` first
and start a train onto points that have not thrown.

So the duty is stated where it can be honoured: **the layout interface must not
act on a `move` before the `align` naming the same transit.** How it holds
that is its own business — the simulator gets it free by batching commands to
the tick, a hardware adapter pairs them — which is where binding-specific
behaviour belongs
([ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md)).

The alternative was to make it structural by folding the points into `move`,
leaving one command and no ordering question. That reverses #97: either the
dispatcher publishes the `move`, which is the driver's, or the driver
publishes the points, which is the arrangement being left behind.

## Consequences

[LAYOUT.md](../store/LAYOUT.md)'s "there are no turnouts in the layout" is no
longer true and is reworded: there are still no turnouts, but there are the
addresses of the points a transit needs thrown. `Connection` grows `points`,
and `Point` joins `lib/layout.py` as the pair of an address and a position.

The layout-to-drawing conversion would have lost them: it built one opaque
generic symbol per connection, which has no turnout detail and so nowhere to
put an address, and its round-trip test compared topology only. #121 answered
the question that raised — the conversion had had no caller since #45 and was
deleted rather than amended, so this decision pays nothing for it.

What is given up is unchanged from ADR-0022: commanded position is not measured
position, and a point that fails to throw looks correct.
