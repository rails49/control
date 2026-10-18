# A person commands track power, and it is cut when `layout` goes silent

Resolves [#770](https://github.com/rails49/control/issues/770). Supersedes
[ADR-0051](0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md).
Applies the organisation's decision in
[rails49/.github#29](https://github.com/rails49/.github/issues/29).

ADR-0051 made track power a command a person gives, and dropped ADR-0040's
third leg: nothing cut the power when the software stopped, and the operator
was the backstop. rails49/.github#29 changed the second half. If the control
box crashes, hangs or loses power while the command station stays powered, the
station keeps refreshing each locomotive's last speed, and trains run with no
block protection. Nobody may be at the layout to pull the power. So something
that does not run on the box cuts track power when the box goes silent, and
`layout` says once a second that it is up
([#716](https://github.com/rails49/control/issues/716)).

This ADR restates what of ADR-0051 still holds, and records what control
decided in applying #29.

## Decision

1. **A person commands track power on `tc49/layout/power_wanted`.** It is an
   event with one field, `power`: `on`, `stopped` or `off`, the closed set of
   `state/power`
   ([ADR-0041](0041-the-layout-says-whether-a-train-may-move-and-the-run-holds-when-it-may-not.md)).
   Any client may publish it. The topic is `layout`'s, because `layout`
   answers it.
2. **The command goes to `layout`, which writes
   `tc49/layout/state/wanted/track`.** Whatever supplies power acts on that
   row. `layout` is the one writer of every desired row
   ([ADR-0043](0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)),
   so the command does not go round it to a translator. No app expects a
   particular kind of hardware, and `layout` does not check that the power
   went away ([#232](https://github.com/rails49/control/issues/232)).
3. **A command is applied when it arrives.** Nothing buffers it
   ([#243](https://github.com/rails49/control/issues/243)). A power command
   changes no lock and grants nothing.
4. **The railroad comes up with power off.** `layout` starts by writing
   `wanted/track: off`, and a person turns the power on. After that `layout`
   writes `off` only when asked
   ([ADR-0054](0054-the-railroad-comes-up-at-rest-and-points-replay.md) adds
   the throttles).
5. **The power controls.** Stop is one press with no confirm. On releases
   nothing, because power returning to `on` does not release the run
   (ADR-0041). Off drains first, and `layout` checks that nothing is moving
   ([ADR-0062](0062-track-power-is-cut-only-when-nothing-is-moving-and-the-layout-checks.md)).
   The controls are look's power toggle and stop sign
   ([ADR-0073](0073-the-chrome-comes-from-look.md)).
6. **`layout` says it is up on `tc49/layout/alive_confirmed`.** It is an
   event with payload `{}`, not retained, and not browser-writable. `layout`
   publishes it once a second by the monotonic clock, from its drain loop,
   while it is built on a railroad. The first goes out when `layout` is
   built, before a person can turn the power on. A `layout` that is standing
   or reloading publishes none. Loading needs the power off, so a cut then
   changes nothing. The simulator publishes none, because it drives no
   hardware.
7. **Something off the box cuts track power when the event stops.** Each
   translator that drives trains, or a device on the bus that switches the
   track supply, does it as its hardware allows. #29 says which, for each
   kind of station. The cut is power off, not an emergency stop. Control does
   no cutting of its own: `layout` still writes `off` only when asked
   (decision 4).
8. **A person stays the backstop for the rest.** The cut covers `layout`, the
   broker or the box stopping. It does not cover the command station hanging,
   the dispatcher or the driver hanging while `layout` runs, or any fault
   while `layout` is up.

## Consequences

- A train rolling when `layout` stops now loses its power within a few
  seconds, with nobody at the layout.
- One silence stands for three failures. A consumer cannot tell the box, the
  broker and `layout` apart, and each gets the same cut.
- Stopping or restarting `layout` on purpose also cuts the power. `layout`
  comes up with power off either way (decision 4), so a person turns it on
  again.
- The cut is checked on the physical layout, by stopping `layout` while the
  power is on. It needs hardware, so `scripts/check.sh` does not run it.

## Considered

- **Keep the operator as the only backstop (ADR-0051).** It assumes a person
  is at the layout whenever the box can fail. #29 is for the time nobody is.
- **`layout` cuts the power itself.** It cannot when the box, the broker or
  `layout` has stopped, and those are the failures this covers.
- **A last will on the broker.** The broker runs on the box, so it is gone
  when the box loses power.
