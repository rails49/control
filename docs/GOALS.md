# Control Model Railroads

A model railroad comprises **assets** (what it is made of) and **operations**
(what is done with them).

## Assets

### Tracks

The rails the railroad runs on, divided into blocks and the connections between
them.

**Blocks** are sections of track without turnouts where a train can park. Each
block is oriented with ends `A` and `B` and has a length. Sensors report the
presence of train(s) in a block — usually one, but cars decoupled from each
other appear as separate trains.

**Connections** join one end (`A` or `B`) of one or more blocks. A simple
connection links two blocks with no physical extent; more generally a connection
consists of one or more turnouts routing trains between the blocks it joins.
Often only some of the possible routes exist:

| Blocks joined | Typical realization | Routes |
| --- | --- | --- |
| 1 | Terminal station | — |
| 2 | Track segment, possibly of length zero | `a ↔ b` |
| 3 | Turnout | Only some, e.g. `a ↔ b` and `a ↔ c` but not `b ↔ c` |

When a route from `a` to `b` exists, the reverse route usually does too.

> **Note** the resemblance to a graph, with connections as vertices and blocks
> as edges.

### Stock

The rolling stock traveling or parked on the tracks:

- Individual locomotives and cars, each with a length (and other properties).
- **Trains**: collections of cars and locomotives. A train's length is the sum
  of its parts.

## Operations

Railroad operations divide into three distinct functions:

1. **Scheduling** — a request to deliver a train from end `A` or `B` of one
   block to another block, corresponding to shipping goods or passengers to
   their destinations. A schedule can be set up in advance or built up
   continually as requests come in.
2. **[Dispatching](DISPATCH.md)** — accepts scheduling requests by finding and
   allocating appropriate routes.
3. **Driving** — takes the role of a locomotive engineer, performed by a human
   or automatically.
