# Route-aware banker's safety check

Incremental locking is gated by a banker's-style safety check: a lock is
granted only if the resulting state is *safe* — there is an ordering of the
active trains in which each can traverse its exact remaining route, given
earlier trains parked at their destinations and later trains frozen in place.
Fixed routes ([ADR-0002](0002-fixed-route-per-request.md)) make the check exact
rather than max-claims conservative, which is what makes a banker's check
attractive here at all; no reversal
([ADR-0001](0001-no-reversal-within-a-route.md)) keeps a train's remaining
resource needs a simple walk down its route.

Because a finished train *parks* on its destination instead of releasing it,
the classical greedy safety check is incomplete, so the search runs as a
memoized search over subsets of completed trains — exponential in the number
of active trains, but a handful of trains means microseconds, and the
polynomial policies of Reveliotis et al. are the documented fallback if that
ever stops being true.

Cycle detection on the wait-for graph was the serious alternative and is far
cheaper, but it only refuses the step that closes a cycle and so misses the
states that make one inevitable; detection-and-recovery needs a preemption we
do not have. Siphon-based Petri-net prevention wants an offline synthesis that
does not fit routes created per request. The
[survey](../research/deadlock-avoidance-survey.md) has the full comparison and
[SAFETY.md](../SAFETY.md) the resulting check and its freedom argument.
