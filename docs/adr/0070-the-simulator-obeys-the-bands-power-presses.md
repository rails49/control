# The simulator obeys the band's power presses

The contract is [#702](https://github.com/rails49/control/issues/702).
Reverses the "constant `on`" passages of
[ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md),
[ADR-0051](0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)
and
[ADR-0062](0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md),
and withdraws the 2026-09-05 amendment of
[ADR-0060](0060-the-railroad-is-chosen-while-the-apps-run-not-at-startup.md).

ADR-0041 had the simulator publish `state/power: on` once and never change
it, because a power cut is a physical act and simulating one would be the
field or the branch
[ADR-0030](0030-the-physical-railroad-is-the-normative-binding.md) keeps out
of every app. ADR-0051 and ADR-0062 repeated that. ADR-0051 also made OFF a
press on the band, sent on `tc49/layout/power_wanted`. That press is a
command to the layout interface, not a cut, and the reason does not cover it.

On a simulated box with a railroad loaded, the result was three dead
controls. OFF drained the run and then nothing happened. The railroad picker
and Restore wait for power `off`, so neither could be used. ADR-0060's
amendment let the simulator's binding load a railroad with the power on, but
the page still refused. Restore cannot leave the check to the binding: the
store writes the restored documents whether or not the rebuild is answered.

## Decision

1. **The simulator answers `power_wanted` as the layout interface does.** It
   publishes the commanded word on `state/power`, since it has no hardware to
   report it. `stopped` stands until `on`, as on the layout.
2. **It comes up `off`**, as the layout interface does. A person presses ON;
   the bench harness publishes `power_wanted: on` before a run.
3. **A plain `off` is applied only while the run is held and nothing moves**
   (ADR-0062). The check is one function in `tc49.lib`, used by both bindings.
4. **While the power is not `on`, no move starts and none advances.** A
   `move` is dropped, as the layout drops it. A transit under way at a STOP
   pauses: its sensor events wait and fire on ON with the time they had left,
   as a train under an emergency stop on steel goes on at its kept speed.
5. **Every binding waits for `off` before loading a railroad.** The
   2026-09-05 amendment of ADR-0060 is withdrawn, and `Answering` loses its
   exemption.

## Consequences

- The page does not change. Its rules for the picker and Restore were right
  for steel, and a simulated box can now reach `off`.
- A simulated box needs ON after it starts, as a real one does.
- The pinned batch trace gains the power lines and is regenerated.
- A train that fails to restart after a STOP is not simulated.
