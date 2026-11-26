# Issue tracker

Issues are GitHub issues in [rails49/control](https://github.com/rails49/control). The `gh` commands and
the wayfinding operations are the organisation's
[issue-tracker.md](https://github.com/rails49/.github/blob/main/docs/agents/issue-tracker.md). This file holds what control adds.

## Issue scope: implementation or communication

Every issue is one of two kinds, declared in the title (#253). The components
are isolated on purpose — they meet only over the bus and the store's
contract — and an issue shaped any wider turns into a discussion of
everything at once.

- **Implementation** — work inside one component. Title `<component>: <what>`,
  e.g. `dispatcher: …`, `simulator: …`. The discussion stays inside that
  component; other components appear only as the contracts they expose
  (BUS.md, SYSTEM.md).
- **Communication** — one new or changed contract element: a bus topic or a
  REST route. Title `bus: <topic> — <what>` or `rest: <path> — <what>`. The
  body carries the draft contract element itself — topic, kind, publisher,
  full payload fields, and the consumers it obliges — so the issue is
  reviewable as the inventory entry it will become.

An issue that seems to need both is a communication issue: the contract
change is what makes it span components. Hardware protocols are
implementation detail of the translator apps and appear only in those apps'
implementation issues. No third kind and no new labels — the five triage
labels stay canonical, and a title prefix is greppable.

`/to-tickets` keeps this rule. Each ticket is one implementation or one
communication issue, and the spec is the issue that spans the components.
The skill's own default, one ticket through every layer, does not apply here.

## Wayfinding maps

### Live maps

None.

### Completed maps

- [UI map: how rails49's browser surfaces are organized](https://github.com/rails49/.github/issues/1)
  — in `rails49/.github`, not this repository. It decided whether a new thing
  is a UI of its own or a view of an existing one, what one system is binding
  on, where shared UI code lives, what serves each UI and how a person reaches
  it, and where the bus contract lives, which
  [ADR-0006 there](https://github.com/rails49/.github/blob/main/docs/adr/0006-the-bus-contract-is-controls-and-travels-when-something-reads-it.md)
  settled on this repository, as `docs/BUS.md`. Closed on 2026-09-21.

- [Model photos map: a photo on each catalogue model](https://github.com/rails49/control/issues/624)
  — the way to a person taking a model's photo from the stock view with a
  fixed camera. Reached on 2026-10-02 as three issues to build: the camera
  route ([#629](https://github.com/rails49/control/issues/629)), the store's
  photo route ([#630](https://github.com/rails49/control/issues/630)) and the
  stock view's thumbnail and dialog
  ([#631](https://github.com/rails49/control/issues/631)).
- [Milestone 2 map: connect hardware and run trains](https://github.com/rails49/control/issues/193)
  — the way to trains on a physical layout: a physical binding of the layout
  interface, a driver that turns an aspect into a speed, stock a real railroad
  has, a scheduler that runs trains unattended, and a person's throttle. Closed
  on 2026-09-03 to clear the tracker rather than at the end of the way.
- [System organization map](https://github.com/rails49/control/issues/13) — the way to `docs/SYSTEM.md`: component decomposition (asset store, scheduler, dispatcher, driver, layout interface) and the bus/CRUD contracts between them. Reached; the spec is `docs/SYSTEM.md` with ADRs 0008–0010.
- [Milestone 1 spec map](https://github.com/rails49/control/issues/1) — the way to a buildable spec for the simulator, dispatcher, and benchmark harness. Reached; the spec is `docs/`.
