# Dispatcher internals

How the dispatcher is built, one level beneath its footprint in
[SYSTEM.md](../SYSTEM.md#dispatcher). The dispatch model is
[DISPATCH.md](DISPATCH.md) and the avoidance layer [SAFETY.md](SAFETY.md);
terminology follows [CONTEXT.md](../../CONTEXT.md). The seam decisions are
[ADR-0004](../adr/0004-dispatcher-returns-commands.md) and
[ADR-0005](../adr/0005-seam-at-locking-strategy.md).

## State

Routing, queueing, locking and the safety check all sit behind the bus
footprint of [SYSTEM.md](../SYSTEM.md#dispatcher), and the dispatcher holds no
collaborators: it reads its layout and stock snapshot at startup and
thereafter only consumes and publishes events. Its state is the
pending-request queue, the lock table, the set of active routes, and the
sensor events buffered since the last grant boundary.

`Request`, `Route`, `Move` and friends are internal dataclasses, the in-memory
forms of what travels the bus as JSON. The wire vocabulary is the event
inventory; these types are private to the implementation and the tests, which
is why field-level schemas could be deferred.

## The locking seam

```python
class LockingStrategy(Protocol):
    def launch(self, req: Request, origin: str, depart: str, state: State) -> Launched | Refused | None: ...
    def grant(self, train: str, state: State) -> Move | Refused: ...
```

`launch` is handed the origin and the departure end to route from rather than
reading either off the request: which end a train leaves by is the
dispatcher's answer, not the strategy's (DISPATCH.md, requests).
`Launched` carries the committed route, `k_tried`, and the resources newly
locked; `Refused` carries the reason and one `{resource, holder}` obstacle
per blocked candidate, the payload of `grant_refused`. `None` from `launch`
means no candidate route exists (the request is rejected `unreachable`).
Strategies mutate `state.locks` and report what they locked, so the
dispatcher can publish the lock ledger.

Two adapters, both real from day one:

- **`FullRoute`** — the baseline. `launch` locks every block and transit of the
  route or returns `None`; `grant` walks the already-locked route with no check.
  Trivially deadlock-free, low throughput, and the yardstick for makespan.
- **`Incremental`** — `launch` tries up to `k` candidate routes and takes the
  first whose post-launch state is safe; `grant` gates the next
  transit-plus-block on the same check.

`LockingStrategy`, `FullRoute` and `Incremental` are the dispatcher's public
names alongside `Dispatcher` itself, because the strategy is chosen by
whoever assembles the run.

`safe()` is a plain function in `safety.py`, not a protocol. The polynomial
fallback of [SAFETY.md](SAFETY.md) would be a second function and a parameter
if anyone ever wants it. See
[ADR-0005](../adr/0005-seam-at-locking-strategy.md) for why the seam is here
and not there.
