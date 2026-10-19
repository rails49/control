# Power is on, draining or off, and replaces GO and HOLD

Part of [#813](https://github.com/rails49/control/issues/813). Supersedes
[ADR-0037](0037-the-run-is-held-or-running-and-held-blocks-commitment.md).
Amends [ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md),
[ADR-0048](0048-an-unexplained-reading-holds-the-run.md),
[ADR-0062](0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md),
[ADR-0074](0074-a-person-commands-track-power-and-it-is-cut-when-layout-goes-silent.md)
and [ADR-0076](0076-a-broken-lock-table-holds-the-run.md).

A person had two controls that meant nearly the same thing. The run was
`held`, `running` or `draining`, set with GO and HOLD on the dispatcher. Track
power was `on`, `stopped` or `off`, set on `layout`. Power not `on` held the
run, and power returning to `on` released nothing, so turning a railroad on
took two presses and turning it off took a drain, a wait and a cut.

## Decision

1. **Power is one switch: `on`, `draining` or `off`.** `layout` owns it,
   because it owns the track supply the switch controls. It answers
   `power_wanted` and publishes the state. `run_wanted` and `state/run` go.
   `moving` stays, on a topic of the dispatcher's.
2. **The railroad comes up `off`.**
3. **While `on` the dispatcher routes waiting requests as soon as it can.**
   While `draining` or `off` it routes nothing, and requests wait.
4. **A drain stops each moving train in the next block.** Nothing new starts.
   A train keeps its route and its locks. `layout` switches the supply off
   when nothing is moving. A person asking for `on` during a drain ends it.
5. **Emergency stop is `off` at once, without a drain.** It is a request of its
   own, and the guard that refuses to cut the supply under a moving train does
   not apply to it. `stopped`, with the track live and every speed zero, goes.
6. **`on` resumes.** After a stop or a drain every train carries on with what
   it was granted: a train left between blocks finishes its move, and the
   dispatcher routes the waiting requests.
7. **A fault drains the railroad.** An unexplained reading (ADR-0048) or a lock
   table that breaks a rule (ADR-0076) makes the dispatcher ask `layout` for a
   drain, as a person would. A person turning power on again acknowledges it,
   as GO did.

## Consequences

- One press turns the railroad on and one turns it off.
- A train is never left standing with a route it is not allowed to continue:
  `off` is the only state in which routing stops, and `on` always resumes it.
- A fault ends with the supply off. Under the hold a person could look at a
  fault with power on; now they look with power off. That is a guess about how
  rare faults are, to be revisited once the railroad has run.
- `stopped` leaves the contract. rails49/dccex reads `wanted/track` and is
  told by an issue there.

## Considered

- **Keep `stopped` beside the three values.** It keeps the track live for
  sound and lights, and a stopped train is stranded the same way under either.
  It is a fourth state for no gain in safety.
- **Drain to each train's destination,** as the old drain did. A long route
  makes the off press wait minutes.
- **The dispatcher owns power,** because it knows when a drain has finished.
  That splits the switch from the supply it controls, and `layout` already
  reads `moving`.
- **A fault stops the railroad at once.** The hold that ADR-0048 chose let
  granted moves finish, and a drain keeps that.
