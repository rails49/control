# Dispatcher returns commands

The dispatcher has no collaborators. `advance()` takes a tick's sensor events
and *returns* the granted moves; whoever called it applies them. The obvious
alternative was ports-and-adapters — hand the dispatcher a `Backend` and let it
call `backend.move(...)` as it grants — and we rejected it because hardware
independence is better served by the move being **data** than by a protocol:
there is nothing for a DCC-EX driver to implement and, more to the point,
nothing for a test to fake. The interface is the test surface, and it takes no
arguments a test has to invent.

Sensor events arrive as a batch rather than one at a time. Grant order is fixed
([#4](https://github.com/iot49/tc49/issues/4)) as active trains by request
arrival tick and then pending launches oldest-first, and that must not degrade
into depending on the order sensors happened to fire.

The cost is that each adapter owns its own run loop, so the simulator's
three-phase tick is written out rather than inherited. That is a few lines, and
it keeps the promise that the dispatcher never reads a clock.
See [ARCHITECTURE.md](../ARCHITECTURE.md).
