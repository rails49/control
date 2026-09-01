# The layout, the roster, and the scenario file

The layout is the durable railroad as the apps consume it: blocks, connections,
transits, and which transits are `concurrent`. It is **derived**, never
authored — the drawing is the source of truth
([DRAWING.md](DRAWING.md), [ADR-0015](../adr/0015-drawing-is-the-source-of-truth.md)),
and `get` derives the layout from it and runs the validator, so components read
it unchecked. A **roster** file names the trains the railroad owns, and with the drawing it
is the whole of what a run is built from
([#171](https://github.com/rails49/control/issues/171)). A **scenario** file
names a layout and adds where its trains stand and a fixed request list: it is
the **harness's** document, read off disk by `tc49 bench` and `tc49 live
--scenario` and served on no route. The split is what lets one railroad carry
many benchmark runs, and it makes the benchmark CLI's argument a single
scenario path.

Terminology follows [CONTEXT.md](../../CONTEXT.md); the semantics of what these
describe are in [GOALS.md](../GOALS.md) and
[DISPATCH.md](../dispatcher/DISPATCH.md).

```
layouts/<layout>.drawing.yaml                   # the railroad, drawn
layouts/<layout>.roster.yaml                    # the trains it owns
scenarios/<layout>/<scenario>.scenario.yaml     # e.g. gotthard/meet
```

To read a railroad's topology, print it:

```
uv run tc49 layout show crossover-yard
```

That is the review a committed layout file used to give in a diff: blocks with
their lengths, terminal blocks marked, and every connection's transits and
concurrent pairs.

Scenario files are YAML and hand-authored, so comments do real work there;
requests nest two levels deep, which TOML expresses far less readably. A Python
DSL was rejected outright: it would stop scenarios being data that can be
generated, diffed, or read by a future UI.

## The derived layout

What derivation produces, and what the validator checks — the shape every app
reads, shown as the document `Layout.from_document` takes:

```yaml
layout: crossover-yard
units: mm

blocks:
  up_w: { length: 3200 }

connections:
  crossover:
    transits:
      up_straight: [up_w.B, up_e.A]
      dn_straight: [dn_w.B, dn_e.A]
      up_to_dn:    [up_w.B, dn_e.A]
      dn_to_up:    [dn_w.B, up_e.A]
    concurrent:
      - [up_straight, dn_straight]
    points:                          # only where the drawing gives addresses
      up_to_dn:
        - { addr: "12", position: thrown }
```

- **Block ends** are written `<block>.A` / `<block>.B`. A block has exactly two
  ends, and each end belongs to **exactly one** connection. That is a real
  modelling constraint, not a notational one: it is why a siding cannot hang off
  the middle of a station track (its turnout is part of the connection at one
  *end* of that track), and why Airolo is a single connection rather than two
  throats.
- **Terminal blocks are derived, never declared** — a block is terminal iff only
  one of its ends appears in any connection.
- **Transits are always named**, mapping a name to an unordered end-pair. Names
  are mandatory even where nothing references them: they give the system a
  readable identity — `crossover.up_straight` in the event trace, in
  lock-granted logs, in test assertions and error messages — rather than an
  end-pair the reader must decode.
- **`concurrent` names the exceptions.** Every pair of transits at a connection
  conflicts unless listed; see
  [ADR-0006](../adr/0006-conflicts-declared-by-inversion.md) for why it points
  this way. In a drawn railroad nothing declares it: a pair is concurrent only
  where the two ways share no symbol, which is composition, not authoring.
- **Lengths** are load-bearing only for the admission fit check — does the train
  fit the blocks it may arrive in. Transit length is not modelled at all: every
  transit costs the same fixed delays, whatever it is and whatever crosses it
  ([DISPATCH.md](../dispatcher/DISPATCH.md#time-model)).
- **There are still no turnouts in the layout, but there are their addresses.**
  A connection is abstract; the turnouts it is realized by live in the drawing
  and are dropped by derivation, so turnout switching time is not merely
  ignored but inexpressible here. What derivation keeps is `points`: for each
  transit that needs any, the address of every point along its way and the
  position that way wants it in
  ([ADR-0031](../adr/0031-the-layout-carries-the-points-a-transit-needs.md)).
  That is what the dispatcher publishes on `align`, and it is the whole of the
  hardware the layout knows about — a point has an address and a position here,
  never a shape, a position on the canvas, or a switching time.
  Connection *length* is likewise absent — a connection can be metres of track,
  as the Gotthard return loop is, but a train transits it and can never stop in
  it.
- **`points` names transits, and only some of them.** Every key under it is a
  transit of the same connection, checked at load. A transit whose way crosses
  no point is absent rather than empty, as is the whole `points` key where a
  connection has none, the same way `concurrent` and `units` are absent when
  they have nothing to say. A point wearing no address is omitted too: the
  drawing is where an unaddressed point is reported, and the layout carries
  only what can be thrown.

## Roster schema

```yaml
roster: crossover-yard

trains:
  freight_1: { length: 1100 }
```

- **A roster belongs to the railroad**, not to a run: it sits beside the
  drawing as `layouts/<id>.roster.yaml` and every scenario over that railroad
  places trains from it. That is what makes a train's length one fact rather
  than one per scenario ([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)).
- **A train is a name and a length.** The dispatcher only ever asks whether a
  train fits a block, so total length is the whole of what milestone 1 reads;
  [GOALS.md](../GOALS.md)'s composed loco-and-car model, with types, addresses
  and priority, arrives when something consumes it.
- **Being on the roster is being *known*, which is not being *placed*.** A run
  built from a railroad has every train off the layout until a person puts one
  on it, and a railroad with no roster file owns nothing yet — a drawing made
  this morning, which is not a missing railroad.

## Scenario schema

```yaml
scenario: meet
layout: crossover-yard

trains:
  freight_1: { at: yard_w, facing: B }

requests:
  - { train: freight_1, from: yard_w.B, to: [dn_e, up_e] }
  - { train: freight_1, from: A,        to: [yard_w.B],   at: 12 }
```

- **`layout:` names the railroad id**, not a path — the same string the
  drawing's own `drawing:` key carries. The loader resolves it to
  `layouts/<id>.drawing.yaml`, so a scenario can move between directories
  without rewriting.
- **A scenario reaches a run two ways, and both are the harness's**:
  `tc49 bench` builds a batch run from it, and `tc49 live --scenario` replays
  it as the gestures a person would make — a placement per train, then the
  requests in the file's order
  ([#171](https://github.com/rails49/control/issues/171)). A gesture carries no
  departure end, so a replay cannot state `from` and a scenario whose `from`
  contradicts its facing replays by the facing.
- **A scenario places trains it does not own** — id, starting block, facing.
  The train itself is the railroad's roster's and so is its length, so a
  scenario naming a train the roster does not have is refused at load. A train
  the roster has and the scenario does not place starts **off the layout**,
  which is an ordinary state rather than a fault
  ([ADR-0039](../adr/0039-a-train-may-be-off-the-layout.md)).
- **`to` is a list of arrival ends**, any one of which satisfies the request
  ([ADR-0007](../adr/0007-requests-name-a-set-of-arrival-ends.md)). An element is
  either `<block>.<end>`, naming the end the train enters through, or a bare
  `<block>`, which expands at load time to both of its ends and is how a
  scenario says "either way round". So `to: [dn_e, up_e]` is four arrival ends
  and `to: [yard_w.B]` is one. The list is **unordered**: the entries are
  equally acceptable and route selection decides between them, so writing a
  preferred track first has no effect.
- **`facing` is declared, then derived.** It is the end of `at` the train
  would depart through nose-first ([CONTEXT.md](../../CONTEXT.md#stock)) —
  `A` or `B`, required at placement, and refused at load where no connection
  holds the end it names — a train facing a wall could never leave. Routes are
  strict pass-throughs
  ([ADR-0001](../adr/0001-no-reversal-within-a-route.md)), so after placement
  facing follows from the routes run and only a scheduler tracks it: the
  dispatcher never reads it, and a file scenario's `from` is free to
  contradict it ([ADR-0019](../adr/0019-facing-is-scheduler-state.md)). The
  dispatcher's blindness shows in the degenerate request — a train already
  standing in an arrival block completes at its first launch attempt without
  moving, whichever end that arrival names, because there is no final transit
  to constrain and the dispatcher holds nothing to check the end against
  ([DISPATCH.md](../dispatcher/DISPATCH.md#requests)).
- **Requests go in at the start of a run, in the file's order.** A scenario
  states no submission times: the queue does the staggering, and a timetable
  released against a clock is the scheduler's own milestone-2 work
  ([ADR-0047](../adr/0047-the-dispatcher-grants-on-events-and-the-boundary-leaves-the-contract.md)).
- **`from` requires the end and takes the block optionally.** `from: yard_w.B`
  states the working the way a reader wants to see it. A chained working may
  state the block only where the file fixes one: where the previous working's
  arrival ends all name a single block the train parks there, and where they
  name several, which one is a dispatcher choice unknown when the file is
  written. Those write `from: A`, and the block is whatever the train is
  standing in.

  **A stated block is checked at load**, against the block the file leaves the
  train in — the placement for a first working, the previous working's arrival
  block for a chained one — and a disagreement is refused there rather than
  running as a silently different experiment. It has to be caught here because
  nothing downstream catches it: at run time a stated block is not a routing
  input but a hint, and the dispatcher corrects it from the route it chose
  itself ([DISPATCH.md](../dispatcher/DISPATCH.md#requests)), which is the
  working a person dragging a moving train on the panel asked for. Only the
  block is judged. Which end the train leaves by stays the file's to state
  freely, facing being scheduler discipline rather than a fact the layout
  holds ([ADR-0019](../adr/0019-facing-is-scheduler-state.md)) — the run-time
  feasibility checks remain the dispatcher's, whatever the scheduler or a file
  happens to know
  ([ADR-0028](../adr/0028-the-scheduler-knows-where-trains-stand.md)).

## Reading a layout

Two structural facts fall out of the model and surprise people:

- **A throat ladder has no track-to-track transit.** Moving from station track 2
  to track 1 is a reversing shunt, not a pass-through, so it is correctly absent.
  What *is* possible is entering a station track at one end and leaving at the
  other — that is a pass-through, and it is how a train at Claro reaches the
  yellow line.
- **A reversing loop has a signature: a path from a block end back to that same
  end.** On Gotthard `line_yellow.A` reaches `airolo_2.A`, and leaving
  `airolo_2.B` returns to `line_yellow.A`. A train goes out, through the
  station, and comes back facing the other way without ever backing up. A single
  route still cannot use it — a route is a simple path, so the return leg would
  revisit `line_yellow` — so turning a train is two requests. That is consistent
  with ADR-0001 but for a subtler reason than the ADR contemplates: here it is
  the simple-path rule doing the work, not the no-reversal rule. Autoreverse
  wiring is an electrical concern of the railroad and leaves no trace in either
  document.

## The drawn railroads

| File | Shape | Role |
| --- | --- | --- |
| [`layouts/gotthard.drawing.yaml`](../../layouts/gotthard.drawing.yaml) | 15 blocks, 5 connections, 30 transits, 5 terminal blocks | the railroad on the bench, headline benchmark; drawn in the editor from the track itself, turnouts carrying their real decoder addresses |
| [`layouts/gotthard-v0.drawing.yaml`](../../layouts/gotthard-v0.drawing.yaml) | 14 blocks, 4 connections, 29 transits, 5 terminal blocks | **superseded**, frozen; wrong about Claro track 3 and the west throat, kept only so ADR-0006, ADR-0012 and ADR-0029 can be re-run (#161) |
| [`layouts/crossover-yard.drawing.yaml`](../../layouts/crossover-yard.drawing.yaml) | 6 blocks, 3 connections, 8 transits | small, fast, drawn from real symbols throughout |

`facing-pair` and `single-track-meet` are property-test railroads and are
described in [ARCHITECTURE.md](../ARCHITECTURE.md#tests); they are small enough to
read from those descriptions.

Gotthard is drawn from the track itself, in the editor, and that drawing is the
record — there is no second netlist it is checked against. `Gotthard.pdf`
(WinTrack) is the source for block lengths, which are measured rather than
assumed. Its turnouts carry the decoder addresses the hardware
answers to, and which of them are *identical* is the part that matters: an
address shared between two symbols means one decoder throws both, and the
derivation composes the concurrency from that.

The owner's Rocrail netlist was that second record until #161. It is deleted:
the drawing already carries the addresses, and Rocrail's ganging no longer
agrees with the railroad — it puts five switches on address 20 where the
drawing puts four on `'1'` — because the layout was rewired after that file was
written. Where the two disagree the track decides
([ADR-0030](../adr/0030-the-physical-railroad-is-the-normative-binding.md)),
and keeping a stale copy invites checking the wrong one.
