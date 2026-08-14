# Layout and scenario files

The two document types of the asset store
([SYSTEM.md](SYSTEM.md#asset-store)), which validates both at `put` — schema
and cross-references — so components read them unchecked. Terminology follows
[CONTEXT.md](../CONTEXT.md); the semantics of what these files describe are in
[GOALS.md](GOALS.md) and [DISPATCH.md](DISPATCH.md).

A **layout** file is the durable railroad. A **scenario** file names a layout
and adds the stock standing on it and the fixed request list. The split is what
lets one railroad carry many benchmark runs, and it makes the benchmark CLI's
argument a single scenario path.

```
layouts/<layout>.layout.yaml
scenarios/<layout>/<scenario>.scenario.yaml     # e.g. gotthard/meet
```

Both are YAML. Layouts are hand-authored by someone drawing a railroad, so
comments do real work — `layouts/gotthard.layout.yaml` carries the reasoning for
each modelling call, and the crossover-yard file an ASCII track diagram of what
it describes. Connections nest two levels deep, which TOML expresses far less
readably. A Python DSL was rejected outright: it would stop layouts being data
that can be generated, diffed, or read by a future UI.

## Layout schema

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
```

- **Block ends** are written `<block>.A` / `<block>.B`. A block has exactly two
  ends, and each end belongs to **exactly one** connection. That is a real
  modelling constraint, not a notational one: it is why a siding cannot hang off
  the middle of a station track (its turnout is part of the connection at one
  *end* of that track), and why Airolo is a single junction rather than two
  throats.
- **Terminal blocks are derived, never declared** — a block is terminal iff only
  one of its ends appears in any connection.
- **Transits are always named**, mapping a name to an unordered end-pair. Names
  are mandatory even where nothing references them: they give the system a
  readable identity — `crossover.up_straight` in the event trace, in
  lock-granted logs, in test assertions and error messages — rather than an
  end-pair the reader must decode.
- **`concurrent` declares the exceptions.** Every pair of transits at a
  connection conflicts unless listed; see
  [ADR-0006](adr/0006-conflicts-declared-by-inversion.md) for why the
  declaration points this way.
- **Lengths** are load-bearing only for the admission fit check — does the train
  fit the blocks it may arrive in. Transit length is not modelled at all: every
  transit costs one tick ([DISPATCH.md](DISPATCH.md#time-model)).
- **There are no turnouts in the format.** A connection is abstract, "realized
  by zero or more turnouts" is a physical note, and turnout switching time is
  therefore not merely ignored but inexpressible until a later effort gives
  turnouts identity. Connection *length* is likewise absent — a connection can
  be metres of track, as the Gotthard return loop is, but a train transits it
  and can never stop in it.

## Scenario schema

```yaml
scenario: meet
layout: crossover-yard

trains:
  freight_1: { length: 1100, at: yard_w }

requests:
  - { train: freight_1, from: yard_w.B, to: [dn_e, up_e], at: 0 }
  - { train: freight_1, from: A,        to: [yard_w.B],   at: 12 }
```

- **`layout:` names the layout id**, not a path — the same string the layout
  file's own `layout:` key carries. The loader resolves it to
  `layouts/<id>.layout.yaml`, so a scenario can move between directories
  without rewriting.
- **Trains are flat** — id, length, starting block. The dispatcher only ever
  asks whether a train fits a block, so total length is the whole of what
  milestone 1 reads; [GOALS.md](GOALS.md)'s composed loco-and-car model arrives
  when something consumes it.
- **`to` is a list of arrival ends**, any one of which satisfies the request
  ([ADR-0007](adr/0007-requests-name-a-set-of-arrival-ends.md)). An element is
  either `<block>.<end>`, naming the end the train enters through, or a bare
  `<block>`, which expands at load time to both of its ends and is how a
  scenario says "either way round". So `to: [dn_e, up_e]` is four arrival ends
  and `to: [yard_w.B]` is one. The list is **unordered**: the entries are
  equally acceptable and route selection decides between them, so writing a
  preferred track first has no effect.
- **No facing is stored.** Routes are strict pass-throughs
  ([ADR-0001](adr/0001-no-reversal-within-a-route.md)) and both `from` and `to`
  name an end the train crosses, so orientation is a consequence of the route
  rather than a fact needing to be recorded. The one place this shows is the
  degenerate request — a train already standing in an arrival block completes
  at latency 0 whichever end that arrival names, because there is no final
  transit to constrain and nothing to check the end against
  ([DISPATCH.md](DISPATCH.md#requests)).
- **`from` requires the end and takes the block optionally.** `from: yard_w.B`
  states the working the way a reader wants to see it, and is checked by the
  dispatcher at admission against where the train actually stands — the
  scheduler is layout-blind, so every feasibility check is the dispatcher's
  ([SYSTEM.md](SYSTEM.md#scheduler)). But a
  chained working can no longer state it: where the previous request parked the
  train is a dispatcher choice among that request's arrival ends, unknown when
  the file is written. Those write `from: A`, and the block is whatever the
  train is standing in. Where the block *is* written, an authoring slip stays a
  loud error at a known tick rather than a silently different experiment.

## Reading a layout

Two structural facts fall out of the format and surprise people:

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
  wiring is an electrical concern of the layout and leaves no trace in the YAML.

## The encoded railroads

| File | Shape | Role |
| --- | --- | --- |
| [`layouts/gotthard.layout.yaml`](../layouts/gotthard.layout.yaml) | 14 blocks, 3 connections, 29 transits, 5 terminal blocks | the real railroad, headline benchmark |
| [`layouts/crossover-yard.layout.yaml`](../layouts/crossover-yard.layout.yaml) | 6 blocks, 3 connections, 8 transits | small, fast, the only one with a `concurrent` pair |

`facing-pair` and `single-track-meet` are property-test layouts and are
described in [ARCHITECTURE.md](ARCHITECTURE.md#tests); they are small enough to
write from those descriptions.

Gotthard's topology is checked against the owner's Rocrail netlist,
[`layouts/gotthard-rocrail.xml`](../layouts/gotthard-rocrail.xml) (rendered as
`gotthard-rocrail.png`), which is authoritative for what connects to what;
`Gotthard.pdf` remains the source for block lengths. Two cautions when reading
the netlist directly: its `<stlist>` routes are **stale** — they still name the
deleted block `c4` and call `bk1` by its old id `rw` — and the block list, not
the route list, is the current record. Block ids map 1:1 onto ours, and the
mapping is recorded at the top of `gotthard.layout.yaml`.

The remaining assumptions marked inline in that file are the block lengths,
which the netlist does not settle. Each is correctable in place.
