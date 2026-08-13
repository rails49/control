# Train Control

Dispatching trains on a model railroad: deadlock-free, high-throughput
allocation of track to scheduling requests. The core is hardware-independent;
DCC-EX is the eventual physical backend, a simulator the first one.

## Language

### Layout

**Block**:
A section of track without turnouts where a train can park, oriented with ends
`A` and `B` and having a length.
_Avoid_: section, segment, track

**Terminal block**:
A block with only one connected end. Can only be the start or end of a route,
never intermediate.
_Avoid_: dead end, siding

**Connection**:
The junction joining one end of each of one or more blocks, realized by zero or
more turnouts. Declares its transits and which of them conflict.
_Avoid_: connector, junction, node

**Transit**:
One traversable (end, end) pair through a connection. Two non-conflicting
transits may be in use simultaneously.
_Avoid_: route (reserved for the request-level path), path, crossing

### Stock

**Train**:
A collection of locomotives and cars moving or parked as a unit; its length is
the sum of its parts. A train occupies exactly one block at a time.
_Avoid_: consist

### Dispatch

**Request**:
An order to deliver a train from one end of a block to another block. Rejected
only if topologically unroutable; otherwise accepted and queued.
_Avoid_: order, job

**Route**:
A train's full path for a request: an alternating sequence of blocks and
transits, fixed when the train starts moving. Strictly pass-through — a train
enters each block at one end and exits at the other; reversal happens only
between requests, at rest.
_Avoid_: itinerary, journey, plan

**Lock**:
Exclusive claim on a block or transit by one train. Incremental locking claims
only the current and next resources of a route; full-route locking claims all
of them up front.
_Avoid_: reservation, allocation

**Tick**:
The discrete time unit of the simulator: each tick, a moving train completes
one transit. Travel time within blocks is ignored. The dispatcher itself is
event-driven and never reads a clock.
_Avoid_: step, cycle
