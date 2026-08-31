# The boundary period is real time, and the fast clock is out of the control path

*(Superseded by
[ADR-0047](0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md),
except one rule that stands: the fast clock never feeds dispatch and never
feeds safety. The boundary and its period go, the fast clock loses its
carrier, and `at` is deleted rather than rebound.)*

Resolves [#198](https://github.com/rails49/control/issues/198) of the
milestone-2 map. `layout` keeps **two** clocks and they are different things:
the grant boundary's period, which is real time, and the railroad's fast
clock, which is scaled. [ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)
blurred them in one parenthetical — "it keeps the beat … on the physical
railroad a tunable sped-up wall clock" — and that parenthetical is wrong.

## The boundary period is real time

On the physical railroad `layout` publishes `tc49/layout/boundary` on a
**fixed period of real time**: 500 ms by default, tunable per railroad, and
**never scaled by the fast clock's multiplier**.

Independence from the multiplier is the point.
[ADR-0040](0040-a-cross-expires-and-an-unfinished-one-stops-the-train.md)
makes the `move` expiry window two boundaries wide, so the period is part of
the failure budget: it has to be long enough that a slow message is still a
*live* one. Multiplying the railroad's clock by ten does not make the broker
ten times faster. A period derived from the multiplier would narrow that
window every time someone sped the railroad up, until an ordinary hiccup made
a legitimate grant look stale — dropped, train stopped, block wedged with no
automatic recovery. A knob turned for atmosphere must not reach into the
failure budget.

So the sizing rule rather than the number: **pick the period so that two
boundaries comfortably exceed worst-case cascade latency** — sensor,
boundary, grant, `move`, back to `layout` — and the expiry window is then
never what drops a live command. ADR-0040 is unchanged: the current boundary
or the one before, no wider. 500 ms is the default and the first train
([#211](https://github.com/rails49/control/issues/211)) confirms it.

The period is not a throughput limit. A transit takes tens of seconds and a
boundary comes twice a second, so what the period costs a train is a short
stand at the far detector it has stopped at anyway: 500 ms at worst, half
that on average.

## A boundary is a grant edge and a liveness pulse

[ADR-0027](0027-the-tick-is-the-simulators-grant-boundary.md) left open what a
boundary *is* once nothing advances per beat. It is two things and neither is
motion.

It is the **grant edge**: the moment the set of sensor events since the last
one is closed and handed to the grant phase. And it is a **liveness pulse**:
it is published whenever `layout` is running — a held run, dead rails, an hour
with nothing moving — and nothing pauses it. That is what makes its
*stopping* meaningful, and it is what ADR-0043 hands the translators when it
says one kicks ADR-0040's relay and stops when the beat stops. A boundary
that paused with the run would drop the relay on a perfectly healthy railroad
somebody had simply held.

A fixed period also keeps ADR-0027's pleasant consequence true: a boundary
count stays proportional to elapsed time, so makespan and latency measure
something real.

## The fast clock is the other clock, and the control path never reads it

The railroad's **fast clock** is wall clock × a configurable multiplier — 10×
puts an hour of railroad time in six minutes. It is what a departure is
written against and what would dim the lights for night.

- **`layout` mints it**, and it rides as a second field on
  `tc49/layout/boundary`: `clock`, fast seconds since the session's start.
  Same single writer, same event, twice a second — so nothing interpolates
  and no app ever reads a real clock, which is what
  [ADR-0009](0009-layout-interface-owns-time.md) exists to prevent. A panel
  joining late knows the time within one boundary.
- **It is free-running**: not coupled to run state, no pause. A person may set
  it. The multiplier and the session's start time are railroad configuration
  in the store; changing them mid-run is a gesture that arrives with the UI.
- **Nothing in the control path reads it.** It feeds scheduling and scenery,
  never dispatch and never safety. Trains wait on detectors: if a locomotive
  gives up the ghost the train is late, exactly as on the prototype, and no
  clock rescues it.

That last rule is what makes a settable, jumpable clock harmless. Move the
clock two hours and the worst that happens is that different departures come
due and the lights change; no train is commanded anywhere it was not already
going.

## `at` stops being a boundary count

A boundary count is what `at` binds to today, and
[SYSTEM.md](../SYSTEM.md#scheduler) already carries it as a milestone-1
expedient — a count means nothing to a person writing a departure.

On the wire `at` is a **fast-clock instant**: fast seconds since the session's
start, monotone, directly comparable, with no midnight wrap. In a document a
person authors it is a **time of day**, expanded by the scheduler at load —
the same mechanical expansion it already performs on arrival ends. Authored
schedules stay out of scope on the milestone-2 map; this fixes only what `at`
means.

## Rejected

**One clock, the period scaled by the multiplier** — the reading ADR-0043's
parenthetical invites. It puts an operator's knob inside ADR-0040's failure
budget, above.

**An activity-driven boundary**: fold a sensor event, wait a short coalescing
window, publish. It has the lowest latency and goes quiet on an idle
railroad. Rejected on three counts — a boundary count stops being
proportional to elapsed time and the metrics stop measuring anything, a
watchdog wants a regular rate, and a request arriving with nothing moving
would need a boundary minted for it.

**Widening the expiry window instead of slowing the period.** ADR-0040
argued "no wider" from the N+1 skew and that argument stands; the tension is
better resolved by a period long enough to make the window generous in
seconds.

**A retained fast-clock topic** carrying a time and a rate for consumers to
extrapolate between updates. Extrapolation needs a real clock in the
consumer, which is the thing ADR-0009 forbids.

**A session epoch on the boundary number.** `layout` restarting resets the
count, so a `move` redelivered from before the restart can carry a number
that looks current. The answer is not a field: everything comes back at rest
([#123](https://github.com/rails49/control/issues/123)), the run comes up held
and the rails come up dead, and `layout` acts on no `move` while
`state/power` is not `on`
([#204](https://github.com/rails49/control/issues/204) owns that rule).

**Pausing the fast clock with the run.** Tempting, so a hold does not run the
timetable on — but nothing in the control path reads the clock, so the
consequence of a jump is small, and a person who wants the clock stopped can
set it.

## Consequences

**The boundary payload gains a field**, and every binding mints it. The
**simulator therefore changes**, which ADR-0043's "the `simulator` is
unchanged" no longer covers: it has no wall clock to scale, so it advances
the fast clock by a **fixed increment per tick** — the nominal period times
the multiplier, five fast seconds — and byte-identical replay survives. A
benchmark run carries a plausible clock for free.

**`tick` keeps its meaning and gains nothing.** It is still the simulator's
word for its own beat.

**The glossary gains *fast clock*** and *grant boundary* gains what generates
it on the physical railroad. **Beat** stays a word to avoid, so the number
decided here is the **boundary period**.

**Carried to [#206](https://github.com/rails49/control/issues/206)**: 500 ms
is 10–15 cm of travel at N-scale top speed. Harmless while every transit ends
in a stop at the detector; a real overrun the day a train runs through a
block boundary without stopping, so the period and continuous running trade
against each other.

**Carried to [#204](https://github.com/rails49/control/issues/204)**: the
relay's kick is the boundary, and the power gate above.
