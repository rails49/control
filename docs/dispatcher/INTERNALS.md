# Dispatcher internals

How the dispatcher is built, one level beneath its footprint in
[SYSTEM.md](../SYSTEM.md#dispatcher). The dispatch model is
[DISPATCH.md](DISPATCH.md) and the avoidance layer [SAFETY.md](SAFETY.md);
terminology follows [GLOSSARY.md](../../GLOSSARY.md). The seam decisions are
[ADR-0004](../adr/0004-dispatcher-returns-commands.md) and
[ADR-0005](../adr/0005-seam-at-locking-strategy.md).

## State

Routing, queueing, locking and the safety check all sit behind the bus
footprint of [SYSTEM.md](../SYSTEM.md#dispatcher), and the dispatcher holds no
collaborators: it reads its layout and stock snapshot at startup and
thereafter only consumes and publishes events. Its state is the list of
waiting and started requests, and `State`: the roster, the lock table, which
holds the active routes too, and what it last read on `layout`'s state topics
(ADR-0047).

`Request`, `Route`, `Move` and friends are internal dataclasses, the in-memory
forms of what travels the bus as JSON. The wire vocabulary is the event
inventory; these types are private to the implementation and the tests, which
is why field-level schemas could be deferred.

## The lock table

`table.py` holds the lock table and every rule that changes it or answers a
question about it
([#1315](https://github.com/rails49/control/issues/1315)). It does no bus work,
holds no request, and imports `tc49.lib` and nothing else of the dispatcher.
The dispatcher holds the current table in `State.table`, turns each payload
into a call to one of the module's transitions, keeps the table it returns and
publishes the effects. It is the only caller of the transitions, so the module
is the only code that changes the table (#761).

### The table

`Table` is a frozen value. Its maps, lists and set cannot be changed in place,
and equal tables compare and hash equal; the layout it reads is left out of
both. It holds:

- `locks`: each locked block or transit, and the train that holds it;
- `block_of`: the block each placed train is recorded in;
- `occupied`: what each placed train occupies, tail to head. A lock on no
  list is held ahead;
- `crossing`: the transit each train is crossing, from its grant until its
  head is in;
- `active`: each train's committed route, how far along it the train is, its
  outstanding move, and the id of the request it runs, which the dispatcher
  keeps;
- `departure`: the end each train leaves by once the last route committed for
  it is done;
- `following`: each train's moves whose readings are still expected, oldest
  first;
- `readings`: each sensor's latest settled level, for the sensors a row has
  spoken for;
- `unknown_sensors`: the sensors `layout` lists as not reporting;
- `residue`: what a train taken off the layout still holds until it reads
  clear (ADR-0069);
- `without_sensors`: whether the railroad runs without sensors (#1314).

### Following a move

A grant adds a `Following` record for its move. For a move out of `X` through
`e`, over `T`, into `Y` through `f`, it names `X.e`, `Y.f` and the end of `Y`
opposite `f`, and notes whether `X.e` has read occupied, at the grant or
since (since only, where the train's list holds a move that entered `X` by
`e`: the train is going back out the way it came), whether the head is in,
and whether the head has reached the far sensor. A changed reading is taken
against every record that expects that sensor, oldest first, as the reading
table in
[GOALS.md](../GOALS.md#dispatching) says: `tc49.lib.following.follow` gives
what the reading makes true, and `table.py` acts on each fact. A record is
dropped once the whole train is in `Y`, or once a later move is granted after
the head reached the far sensor. The tail leaving `X` drops an older move into `X`, and a placement, a
removal, a withdrawn move and a change of `without_sensors` drop records too.

### Transitions

Each transition takes a table and an event and returns a new table and a list
of effects. It leaves the table it was given unchanged, and one that changes
nothing returns that table as given.

| Transition | Event |
| --- | --- |
| `reading` | a sensor's settled reading |
| `not_reporting` | the list of sensors not reporting |
| `opening` | asked after each reading and each change of that list: residue whose sensors read clear and report is released |
| `placing` | a train placed in a block, its requests already ended |
| `removing` | a train taken off the layout |
| `committing` | a route committed, with the locks the strategy said to take |
| `committing_whole` | a route committed while the railroad runs without sensors: the train occupies the whole route |
| `granting` | a move granted, with what it newly locks and what it locks ahead |
| `withdrawing` | `layout` took back the train's outstanding move (#1068) |
| `cancelling` | a person's cancel, taking effect at once |
| `retiring` | a run ended without arriving: everything held given up but what the train is on, or what the caller keeps |
| `completing` | a run ended at its route's last block |
| `arriving` | a person saying the train is in its route's last block, without sensors |
| `setting_without_sensors` | the setting changing, which ends every run (#1321) |
| `adopting` | a restart's kept allocation adopted |

`releasing` gives up everything a train holds but what is kept; `retiring`,
`placing`, `removing`, `arriving` and `setting_without_sensors` use it.

### Effects

Each effect is a fact, and the dispatcher acts on them in the order returned:

| Effect | The dispatcher |
| --- | --- |
| `Disputed` | publishes `state/disputed`; the first effect of a changed reading |
| `Granted` | publishes one `lock_granted` |
| `Released` | publishes one `lock_released` |
| `Opened` | publishes one `lock_released` for residue given up |
| `HeadIn` | publishes `state/aspects` and then `state/allocation`, before any grant that follows (#1025) |
| `MoveEnded` | decides what the train's request does: it completes, retires or goes on |
| `Placed` | publishes `train_placed`, and `state/unfit` again where it named the train |
| `Removed` | publishes `train_removed` |
| `RunsEnded` | cancels every request `revoked` |

### Questions

The questions read the table and write nothing:

- `Table.obstacle`: why a train cannot lock a block or transit, with its
  holder, or that it can;
- `Table.free`: whether a block is free of every claim, for a placement;
- `Table.out_of_use` and `Table.disputed_blocks`: the blocks out of use, and
  the blocks that read occupied with no train explaining it;
- `Table.reads_occupied`: whether either of a block's sensors last read
  occupied;
- `Table.standing_still`: the blocks no train is sent into until something
  changes, which the strategies hand `safe()` with the idle trains' blocks;
- `locked_ahead`: how many blocks a train holds ahead that it may enter;
- `Table.moving`: whether a power cut now would strand a train;
- `Table.kept`: what a removal of a train leaves held;
- `Table.newest`: a train's newest move whose readings are still expected;
- `broken`: which of the table's own rules are broken (ADR-0076).

`State` passes each read on to its table and so satisfies
`locking.ReadOnlyState`: the strategies read the table through it, and the
views they build for `safe()` come from these questions.

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
Strategies write nothing: they are handed a `ReadOnlyState`, which `State`
satisfies and through which `state.locks` cannot be written, and return what
to lock. The dispatcher hands that to `committing` or `granting` and
publishes the lock ledger from the effects, so `table.py` is the only code
that changes the table, and `broken` checks the table after every event
([ADR-0076](../adr/0076-a-broken-lock-table-holds-the-run.md)).

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
