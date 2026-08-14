# The seam is at locking strategy

`LockingStrategy` is a protocol with two implementations, `FullRoute` and
`Incremental`; the safety check is a plain function that `Incremental` calls.
The tempting alternative was to make the *safety policy* the pluggable thing,
since [ADR-0003](0003-route-aware-bankers-safety-check.md) names a polynomial
fallback — but that fallback has exactly one hypothetical caller, while the
baseline/incremental split is real on day one and is the whole point of the
benchmark. A seam wants two implementations that actually exist; the other
direction would have demoted a genuine dual to a boolean flag and abstracted
something nobody has asked to vary.

If the polynomial policy is ever wanted it becomes a second function and a
parameter, which is a smaller change than the abstraction would have been.

Keeping the baseline behind the same protocol also keeps its trivial logic out
of the same body as the research core's subtle logic — the one place where
entanglement would be most expensive. See [ARCHITECTURE.md](../ARCHITECTURE.md).
