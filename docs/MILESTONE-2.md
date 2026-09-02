# Milestone 2

Trains run on a **physical layout** under dispatch. [GOALS.md](GOALS.md)
describes the whole system and [MILESTONE-1.md](MILESTONE-1.md) fixed the
boundary of its first slice, which was deliberately independent of any
hardware; this page fixes the boundary of the second, which is the hardware.

Any layout with a drawing and a roster. The one it is being tried on first is
an example and nothing here is specific to it
([ADR-0030](adr/0030-the-physical-railroad-is-the-normative-binding.md)).

**Not reached.** Everything under *Deliverable* is in the tree and green under
`scripts/check.sh`, and every decision the slice needed is made and written
down. What has not happened is the thing the milestone is named for: no
locomotive has yet crossed a transit on a `move_granted` over the physical
binding ([#211](https://github.com/rails49/control/issues/211)). Three of the
questions in *Settled by running* cannot be answered before it does, which is
why they are still open rather than deferred.

## Deliverable

The four things milestone 1 left out, plus a person being able to take a train
over by hand.

- **A physical binding of the layout interface.** `layout` is a core app,
  always running and hardware-independent: align before move, the sensor fold,
  the transit bound, `state/power`, and the signal standing at each block end
  ([layout/](layout/README.md),
  [ADR-0043](adr/0043-the-layout-interface-is-a-core-app-and-hardware-hangs-under-it-by-address.md)).
  Under it a **device vocabulary on the bus** — `state/wanted/…` is what
  `layout` wants the railroad to be, `state/device/…` is what the hardware
  says it is, both retained, the address as trailing levels and no ownership
  table anywhere.
- **Translators, thin and optional.** One per command station, named for the
  system it speaks to and hanging under `layout` by address; the one this
  railroad uses is `dccex`, with `dccex-usb` mirroring the station's USB port
  onto a TCP port so other software and hand-held throttles reach the same
  station ([dccex/](dccex/README.md)). A translator publishes its own link as
  observed state, which is where verifying a physical connection belongs — at
  runtime, not in a gate that would need a powered layout.
- **A driver that turns an aspect into a speed on a real locomotive.** `move`
  carries a magnitude in 0.0 … 1.0, `clear` full and `caution` a fraction; the
  driver stays a pure function of the aspect and `layout` supplies the sign,
  because direction is geometry composed with which way round a locomotive
  stands ([ADR-0052](adr/0052-layout-reads-facing-and-composes-the-sign-of-a-speed.md)).
  Decoder steps never leave a translator.
- **Stock a real railroad has.** A **model** is what a product is, a **car** is
  one the railroad owns — a model with zero or more fields overridden, plus its
  own bare traction address — and a **train** is an ordered list of cars
  ([ADR-0045](adr/0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)).
  The catalogue is shared between railroads because a product does not change
  on another layout; cars and trains belong to one.
- **A person taking a train over by hand.** The throttle is a view of this UI
  and its commands ride the bus, because a page that talked to a command
  station would be invisible to the system ([ui/THROTTLE.md](ui/THROTTLE.md)).
  *Manual* names only who turns the throttle: the dispatcher never hears of
  it, still holds the block and may still grant, and trusts a person to read
  the signal.
- **Power, commanded and drained.** The panel commands track power; on startup
  power is off and a person turns it on; the operator is the backstop and no
  hardware watchdog holds the rails up
  ([ADR-0051](adr/0051-the-panel-commands-track-power-and-the-operator-is-the-backstop.md)).
  `draining` is the third value of the run and gates launching rather than
  admission.
- **Signals that something can show.** `layout` publishes an aspect —
  `stop`, `caution` or `clear` — against an address a symbol carries, and
  whatever recognises the address makes something show it. No contract says
  how, so a command station, an operator tool, a board of pins or something
  not yet invented meet the same door.
- **An installation's own documents, and a copy of them.** The store roots
  outside the checkout, and backup drives git rather than owning it
  ([store/BACKUP.md](store/BACKUP.md),
  [ADR-0053](adr/0053-backup-drives-git-and-does-not-own-it.md)). A railroad
  drawn over months is on one disk otherwise.

**Time left the contract.** There is no beat and no boundary: the dispatcher
grants on the events that arrive, every grant is safety-checked so arrival
order cannot reach an unsafe state, and every command takes effect when it
arrives ([ADR-0047](adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
The fast clock has no carrier. A `move` does not expire; `layout` acts on one
only if the train is standing at the transit's near end, which is stronger
than a window and needs no clock.

## What being reached takes

One locomotive across one transit into a detected block, on a `move_granted`,
on the physical binding, on the layout server
([#211](https://github.com/rails49/control/issues/211)) — and an implementing
agent hitting no open decision on the rest, which is the same bar milestone 1
used.

For the first run **detection is hand-fed**: the camera and the broker come
after, so only this repository moves.

## Scope

Milestone 1's boundary still binds except where a row below crosses it. What
this slice changed about the earlier one:

- **The driver obeys the aspect**, which milestone 1 listed as out of scope.
  It carries a speed now, though what the fraction *costs* is still a question
  the simulator cannot answer, its delays being deaf to speed.
- **The scheduler is not a traffic generator.** Milestone 2 has two sources of
  requests and both already exist: a scenario, and a person dragging a train
  from its block to a vacant one
  ([#210](https://github.com/rails49/control/issues/210)). Keeping trains
  moving unattended is what those two do here; inventing continual arrivals
  from block roles is later work.
- **The bus is still in-process.** The contract is the MQTT-safe intersection
  and nothing relies on what MQTT cannot give, so bringing a broker up is a
  deployment step rather than a redesign. It is gated on the first train
  ([#173](https://github.com/rails49/control/issues/173)), because whether the
  translator wants its own process, and what latency turns out to matter, are
  things running experience answers and guesswork does not.

## Settled by running

Open on purpose. Each of these has a working answer and no decision, and the
decision is one a railroad in motion makes rather than one anybody reasons to
from here:

- **Braking distance, or speed signalling.** For now a train stops
  immediately, by being told speed 0, and that is the driver's concern alone
  ([GOALS.md](GOALS.md#driving)).
- **Which of the "hardware that lies" answers earn their cost.** The transit
  watchdog is answered, the dispute check half-answered. What is *expected* to
  lie: a detector reporting occupied for a locomotive somebody put on the
  track by hand, a turnout reporting thrown because the station fakes the
  reply, a power state reading `on` while a district has tripped. Everything
  else on the list is a guess until a train has run.
- **An unexpected sensor.** [SYSTEM.md](SYSTEM.md)'s unenforced assumption is
  that every sensor event explains a granted move, and a real layout fires a
  detector for a hand-placed locomotive.
  [ADR-0048](adr/0048-an-unexplained-reading-holds-the-run.md) holds the run
  on one; whether that is enough is what a running railroad answers.
- **What survives the in-process binding**
  ([#173](https://github.com/rails49/control/issues/173)), gated there for the
  same reason.

**No crash is planned for.** A driver can go through a stop signal exactly as
a car can run a red light, and in either case a crash can happen. The system
does not model rogue operation and grows no machinery to prevent it. This is
prototypical rather than a gap: an asleep driver who does not stop his train
causes an accident on a real railroad too.

## Out of scope

Each ruled out deliberately, and each binds unless its row says otherwise:

| Not in milestone 2 | Why |
| --- | --- |
| Sharing a model catalogue between railroaders | the catalogue is one local database for the installation, shared between one owner's railroads and no further; commercial online databases of model railroad products exist and copying that is a different effort ([#199](https://github.com/rails49/control/issues/199)) |
| Authored schedules — named operations run by hand, at a time, or at random | takes the rules for special cars (crane, camera, track cleaner) with it |
| A traffic generator inventing continual arrivals from block roles | two sources of requests already exist and suffice ([#210](https://github.com/rails49/control/issues/210)) |
| Splitting and merging trains on the layout | dropping cars in a siding mints a train from a train. **Milestone 3**, with the runtime writer of stock it needs ([#209](https://github.com/rails49/control/issues/209)); nothing in the stock document forecloses it |
| The patched command-station firmware — per-district trip currents and a way to flash it | a separate project against the station's own source. What this repository does is send a file of raw station commands when power comes on ([#205](https://github.com/rails49/control/issues/205)) |
| Linking a running instance from a public page | the UI is deployed and is not linkable: a private address, no authentication on purpose, and a store, a broker and a layout server needed beside it ([#231](https://github.com/rails49/control/issues/231)) |
| Decoder programming | DecoderPro reaches the station on 2560 and the app never knows |
| Containers for the apps | a compose file once MQTT lands ([#173](https://github.com/rails49/control/issues/173)) |
| A train standing across two blocks | real and common, and capacity the model declines rather than a way it is wrong: `no_fit` keeps a long train off a short track and the railroad runs without it. **Milestone 3**, and the version wanted is the dispatcher *routing to* such a stand ([#201](https://github.com/rails49/control/issues/201)) |
| A second binding of the layout interface, for a different command station | the same shape as the first, with every difference inside the binding, so the station this railroad has was built first. The other vendor's software coexists on the station's TCP port as an operator tool, which needs no code here ([#196](https://github.com/rails49/control/issues/196)) |
| Everything milestone 1 rules out and this milestone does not cross | mechanized proof, mid-route rerouting, an aging rule |
