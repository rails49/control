# Dispatcher publishes commands

*(As first recorded, the dispatcher **returned** commands from `advance()`;
the bus reshape amended the transport. The decision itself is unchanged.)*

The dispatcher has no collaborators. It publishes each granted move as an
event whose payload is the move itself — train, transit, destination block —
and whoever cares consumes it; in particular the driver translates it into
layout commands. The obvious alternative was ports-and-adapters — hand the
dispatcher a `Backend` and let it call `backend.move(...)` as it grants —
and we rejected it because independence from the layout's hardware is better
served by the move being **data** than by a protocol: there is nothing for a
physical-layout driver to implement and, more to the point, nothing for a
test to fake. The event stream is the test surface, and it takes no
arguments a test has to invent. Publishing is the new returning.

Sensor events are processed as a batch — buffered until the tick event, then
treated as a set. Grant order is fixed
([#4](https://github.com/iot49/tc49/issues/4)) as active trains by request
arrival tick and then pending launches oldest-first, and that must not
degrade into depending on the order sensors happened to arrive.

The old cost — each adapter writing out its own run loop — dissolved with
the loop itself: components react to events, and the tick's owner is fixed
by [ADR-0009](0009-layout-interface-owns-time.md). What remains is the same
promise, in its strongest form: the dispatcher never reads a clock, and now
never learns what tick it is. See [SYSTEM.md](../SYSTEM.md).
