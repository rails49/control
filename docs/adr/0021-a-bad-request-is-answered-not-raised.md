# A bad request is answered, not raised

A request may state the block it departs from, and the dispatcher checks it
against where the train stands
([DISPATCH.md](../dispatcher/DISPATCH.md#requests)). It used to raise on a
disagreement. That was right while the only writer was an authored scenario
file, where a disagreement is a slip in a file somebody wrote and a loud error
at a known tick is the cheapest way to see it.

The panel is a scheduler ([ADR-0016](0016-the-panel-is-a-scheduler.md)), so the
writer is now a browser, and a browser can be stale. The bridge relays the bus
and describes nothing ([SYSTEM.md](../SYSTEM.md#the-bus)), and a train's
placement lock was published before the page connected, so a panel joining a
running session seeds placement from the scenario and shows trains where they
started. One drag then states a block its train has left. Raising out of a bus
handler ends the run: a stale page stops the railroad.

**The dispatcher answers instead.** A stated departure block the train is not
standing in is rejected at admission, `request_rejected` with reason
`wrong_origin`, alongside `no_fit`, `no_entry` and `unreachable`. Nothing a
submitter can put on the bus ends the run; every fate is an event, which is
what the dispatcher's boundary already promised
([SYSTEM.md](../SYSTEM.md#dispatcher)). The panel spells the reason out at the
request's endpoints exactly as it spells the other three out, so the staleness
becomes something the operator can see and act on — drag again once the train
has moved and the panel has watched it move.

The reason is its own word rather than a reuse of `no_entry`, because the
reasons are read by a human: the fault is in the departure, and saying "no
arrival end is enterable" would blame the arrival ends, which may be perfectly
good. It also keeps the rejection countable on its own in the trace.

Nothing is lost for file scenarios. An authoring slip is still visible at a
known tick — as a `request_rejected` line correlated by request id, in the same
trace that records every other fate — instead of as a stack trace. It is a
weaker signal than a crash and that is the point: the same disagreement now
arrives from two writers, and only one of them is a file that can be corrected.

Two alternatives were rejected.

**Tell a joining panel where things stand**, by having the bridge describe the
run. That was already refused in [#67](https://github.com/rails49/control/issues/67):
the bridge relays the bus and adds nothing, and a describing bridge is a second
authority on state that the dispatcher owns.

**Submit a bare end letter** (`from: B`), which states no block and so skips the
check entirely. It avoids the crash by removing the question, and buys a silent
departure from wherever the train happens to be — a wrong-way working that
completes rather than an answer that says why.

The check that is *not* added is facing.
[ADR-0019](0019-facing-is-scheduler-state.md) stands: a request is still free
to depart a train through the end it is not facing, and the dispatcher holds no
facing to judge that with. `wrong_origin` is about the block, which the
dispatcher does hold, and about it alone.
