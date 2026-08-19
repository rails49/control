# The physical railroad is the normative binding

The layout interface has two bindings that coexist indefinitely, a physical
railroad and a simulator, and they are **ranked**. The physical railroad is
normative: where the two could differ, it decides, even at cost to the
simulator. The first question about any feature is how it behaves on the actual
railroad, and simulation is considered only once that has a satisfactory
answer.

The rank has a structural half. Simulation lives behind the layout interface,
in the `simulator` app, where it may grow as elaborate as its uses need:
travel times, speeds, whatever evaluating an unbuilt layout turns out to
require. What it may never do is put a field, a topic, or a branch into any
other app. That is the whole of the containment. It is a boundary rather than a
weight budget, so [ADR-0013](0013-apps-are-deployment-units.md) and
`tests/system/test_app_boundaries.py` already police most of it.

## The alternative

Simulator-first was a real option and the cheaper one. The simulator is the
only binding that exists, every test runs on it, and letting it shape the
contract buys determinism, byte-identical replay and a fast edit loop for
nothing. Building for hardware that is not there costs work now for a benefit
later.

It was rejected because the railroad is the product. A contract shaped by the
simulator is shaped by what was convenient to write, and each such convenience
becomes a defect to find once a physical layout is running. The rule spreads
that cost out instead of deferring it.

## What the rule looks like when followed

[SAFETY.md](../dispatcher/SAFETY.md) is the exemplar. On releasing a lock
mid-transit:

> Real trains straddle the boundary; the release rule handles that without the
> dispatcher knowing. In the simulator both events land in the same tick's
> buffered set, so the two behave identically.

The physical question is answered first, and the simulator is noted second as a
case that happens to collapse. The rule asks for that order every time.

## What it looks like when it is not

[ADR-0027](0027-the-tick-is-the-simulators-grant-boundary.md) reached the right
answer by the wrong argument. Per-sensor granting was rejected because
order-dependence "would leave the determinism property a simulator-only
guarantee and the tests exercising a code path hardware never takes", which is
a testing benefit deciding a hardware design. The hardware argument is stronger
and was not made: on a real railroad sensor arrival order is unspecified, so an
order-dependent grant makes the railroad's behaviour depend on wire timing.
That is a correctness defect on hardware and only an inconvenience in a
simulator. The decision stands, and is amended there rather than superseded.

## Consequences

This is a precedence rule, not a roadmap. Hardware stays a later effort and
[MILESTONE-1.md](../MILESTONE-1.md) is unchanged. What changes is which
argument wins when the two bindings pull apart. It is stated in
[GOALS.md](../GOALS.md#approach), in `CLAUDE.md` so an agent meets it before
designing anything, and as **layout binding** in
[CONTEXT.md](../../CONTEXT.md#contracts).
