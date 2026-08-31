# The tick is the simulator's grant boundary

*(Amended under
[ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md): the
rejection below argues from testing, and the hardware argument is stronger. On
a real railroad sensor arrival order is unspecified, so an order-dependent
grant makes the railroad's behaviour depend on wire timing. That is a
correctness defect on hardware, and determinism in the tests is its consequence
rather than its reason. The decision itself is unchanged.)*

*(Amended for #198: "at whatever period suits it" is settled — on the
physical railroad the period is a fixed span of **real** time, 500 ms by
default, never scaled by the railroad's fast clock, and the boundary is a
liveness pulse as well as a grant edge
([ADR-0044](0044-the-boundary-period-is-real-time-and-the-fast-clock-is-out-of-the-control-path.md)).)*

*(Amended for #118: the event is `tc49/layout/boundary` carrying a field
`boundary`. It was first published as `tc49/layout/tick` carrying `tick`,
which put the subordinate binding's word on a contract every binding has to
speak — the containment rule's clearest violation. **Tick** keeps the meaning
this page gives it, and keeps it on the simulator alone.)*

The layout interface always publishes a **grant-boundary** event
(`tc49/layout/boundary`), and the dispatcher always runs its grant phase over
the sensor events buffered since the last one. What generates the boundary is
the binding. The simulator's is the **tick**: one transit per beat, published
when the bus is quiescent, and deterministic. A hardware adapter derives its
own from a real clock at whatever period suits it, with transit times varying
freely underneath: a long return loop takes longer than a station ladder, and
a train creeping under `caution` takes longer through a block than one
running `clear`.

`tick` therefore names the simulator's beat behind the boundary, not a unit of
time the model believes in.
[ADR-0009](0009-layout-interface-owns-time.md) stands unchanged: the layout
interface owns time, whatever time is made of behind it, and the dispatcher
never reads a clock.

## What the boundary is for

Not motion. Sensor events are buffered and the grant phase treats them as a
**set**, so grants are a pure function of that set and never of the order the
events happened to arrive. That is what makes byte-identical replay possible,
and it has nothing to do with how far a train moved.

Granting per sensor event on hardware was the obvious alternative and would
have been simpler and lower-latency. It was rejected because it makes grants
order-dependent, which would leave the determinism property a simulator-only
guarantee and the tests exercising a code path hardware never takes.

Having the layout interface stamp each event with a real time and letting the
dispatcher batch by window was rejected outright: it puts a clock inside the
dispatcher, which [ADR-0009](0009-layout-interface-owns-time.md) exists to
prevent.

## What stops being true

"Each tick, a moving train completes one transit" was stated as the model's
time unit and is a property of the milestone-1 simulator. So is ignoring
travel time within a block. Both survive as simulator behaviour, and neither
is a claim about a railroad.

A pleasant consequence: once the beat is decoupled from motion, a boundary
count is proportional to elapsed time, so makespan and latency measure
something real rather than counting transits.
