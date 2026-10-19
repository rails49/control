# The waiting requests are a list a person orders

Part of [#813](https://github.com/rails49/control/issues/813). Supersedes
[ADR-0012](0012-the-pending-scan-ages-by-refusal-count.md). Amends the
priority section of
[ADR-0045](0045-the-railroad-owns-cars-and-a-train-is-an-ordered-list-of-them.md)
and [ADR-0039](0039-a-train-may-be-off-the-layout.md).

The queue was ordered by train priority and, within a priority, by how often a
request had been refused. A person could not see it, and could cancel only
every request of one train at once. A second drag of a train that had a
request departed from where the train stood, so it was refused or failed.

## Decision

1. **The waiting requests are a list, in the order the dispatcher serves
   them.** The panel shows it: train, from, to, waiting or underway.
2. **A new request goes in after every request of the same or a higher
   priority.** Priority does nothing else.
3. **An earlier request gets the first claim, and a later one still starts
   when an earlier one cannot.** Refusal counts no longer reorder the list.
4. **A person cancels or reorders any request that has not started**, one at
   a time. Cancelling a request that is underway stops the train in the next
   block.
5. **A train's later request starts where its earlier one ends.** Two drags
   send a train to a block by way of another. It stops there briefly until the
   driver can run through.
6. **A drag makes a request at any time,** whatever the power.
7. **A train is placed at any time, in a free block:** no train placed there,
   no lock on it, and on no active train's remaining route. A person drags it
   from the roster, then puts its cars there. With power on, a train put down
   before the drag is an unexplained reading.
8. **A restart loses the list.**

## Consequences

- What the panel shows is what the dispatcher does next.
- A request can wait forever while later requests keep taking the track it
  needs. The person ordering the list is the bound refusal counts were.

## Considered

- **Reordering only a train's own requests,** with priority ordering the rest.
  The list would then not show the dispatcher's order.
- **Moving a request sets its train's priority.** It changes every later
  request of that train as well.
- **A request names blocks to pass through.** It runs a train through without
  stopping, and changes the request now for what the driver will give later.
