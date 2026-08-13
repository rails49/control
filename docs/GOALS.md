# Control Model Railroads

A model railroad comprises **assets** (what it is made of) and **operations**
(what is done with them). Terminology follows the glossary in
[CONTEXT.md](../CONTEXT.md).

## Assets

### Tracks

The rails the railroad runs on, divided into blocks and the connections between
them.

**Blocks** are sections of track without turnouts where a train can park. Each
block is oriented with ends `A` and `B` and has a length. Sensors report the
presence of train(s) in a block — usually one, but cars decoupled from each
other appear as separate trains.

**Connections** join one end (`A` or `B`) of each of one or more blocks, and
are realized by zero or more turnouts. The ways a train can traverse a
connection are its **transits** — (end, end) pairs — and often only some of
the possible ones exist:

| Blocks joined | Typical realization | Transits |
| --- | --- | --- |
| 1 | Terminal station | — |
| 2 | Track segment, possibly of length zero | `a ↔ b` |
| 3 | Turnout | Only some, e.g. `a ↔ b` and `a ↔ c` but not `b ↔ c` |

When a transit from `a` to `b` exists, the reverse transit usually does too.
Each connection also declares which of its transits conflict; non-conflicting
transits (e.g. the two straight paths of a crossing) may be used by two trains
simultaneously.

> **Note** the resemblance to a graph, with connections as vertices and blocks
> as edges.

### Stock

The rolling stock traveling or parked on the tracks:

- Individual locomotives and cars, each with a length (and other properties).
- **Trains**: collections of cars and locomotives. A train's length is the sum
  of its parts. A train occupies exactly one block at a time (plus, while
  crossing, one transit); it must fit in every block of its route.

## Operations

Railroad operations divide into three distinct functions:

1. **Scheduling** — a request to deliver a train from end `A` or `B` of one
   block to another block, corresponding to shipping goods or passengers to
   their destinations. Requests arrive continually; a schedule may also be set
   up in advance.
2. **[Dispatching](DISPATCH.md)** — accepts requests by finding and allocating
   routes, deadlock-free and with high throughput.
3. **Driving** — takes the role of a locomotive engineer, performed by a human
   or automatically.

## Approach

The core is hardware-independent. A simulator is the first backend, behind an
interface a physical layout (eventually [DCC-EX](https://dcc-ex.com)) will
implement later; capabilities of DCC-EX-class hardware may be assumed.
