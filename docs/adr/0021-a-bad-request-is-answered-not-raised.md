# A bad request is answered, not raised

A request may state the block it departs from, and the dispatcher checks that
against where the train stands
([DISPATCH.md](../dispatcher/DISPATCH.md#requests)). It used to raise on a
disagreement. That was right while an authored scenario file was the only
writer: the disagreement is a slip in a file somebody wrote, and a loud error
at a known tick is the cheapest way to see it.

The panel is a scheduler ([ADR-0016](0016-the-panel-is-a-scheduler.md)), so the
writer is now a browser, and a browser can be stale. The bridge relays the bus
and describes nothing ([SYSTEM.md](../SYSTEM.md#the-bus)), and a train's
placement lock is published before any page connects, so a panel joining a
running session seeds placement from the scenario and shows trains where they
started. A drag then states a block its train has left. Raising out of a bus
handler ends the run, so one such drag stops the railroad.

**The dispatcher answers instead.** A stated departure block the train is not
standing in is rejected at admission: `request_rejected` with reason
`wrong_origin`, alongside `no_fit`, `no_entry` and `unreachable`. The panel
spells that reason out at the request's endpoints as it spells the other three
out, so the operator learns the page is stale instead of watching the session
stop.

The reason is its own word rather than a reuse of `no_entry` because a person
reads it. The fault is in the departure, and "no arrival end is enterable"
would blame arrival ends that may be perfectly good. It also stays countable on
its own in the trace.

File scenarios lose little. An authoring slip is still visible at a known tick,
as a `request_rejected` line correlated by request id in the same trace that
records every other fate, rather than as a stack trace. That is deliberately a
weaker signal than a crash: the same disagreement now arrives from two writers,
and only one of them is a file that can be corrected.

The decision covers a request the dispatcher can read and must refuse. A
payload it cannot read at all, naming a train the session does not have or a
block the layout does not have, still raises and still ends the run. Whether
that belongs to the bridge or to admission is a separate question, with its own
contract change to make.

Two alternatives were rejected.

**Tell a joining panel where things stand**, by having the bridge describe the
run. [#67](https://github.com/rails49/control/issues/67) already refused that:
the bridge relays the bus and adds nothing, and a describing bridge is a second
authority on state the dispatcher owns.

**Submit a bare end letter** (`from: B`), which states no block and so skips the
check. That removes the question rather than answering it, and buys a silent
departure from wherever the train happens to be.

Facing is not checked. [ADR-0019](0019-facing-is-scheduler-state.md) stands: a
request may still depart a train through the end it is not facing, and the
dispatcher holds no facing to judge that with. `wrong_origin` is about the
block, which the dispatcher does hold.
