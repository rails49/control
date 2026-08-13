# Fixed route per request

A route is chosen when the train starts moving and never changed; only its
locks are acquired incrementally. Mid-journey rerouting would give the
dispatcher more throughput headroom and an escape hatch near congestion, but
safety arguments would then have to quantify over all possible futures. With
fixed routes the avoidance layer always knows every train's exact remaining
path — the information banker's-style safety checks and deadlock-freedom
proofs need. Rerouting may return later as an optimization, on top of a proven
core.
