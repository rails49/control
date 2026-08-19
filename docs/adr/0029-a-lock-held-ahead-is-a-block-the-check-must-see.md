# A lock held ahead is a block the check must see

Depth two ([ADR-0026](0026-two-blocks-ahead-is-full-speed.md)) is built here.
Building it takes two decisions: how the second increment is asked for, and
what the safety check has to be told about it. Asking for something the train
does not yet need is what makes a lock outlive the grant, and outliving the
grant is what the check has to model.

## The second increment is asked for, not required

A grant locks the next transit and block. That is the permission to move and
is still all-or-nothing. Having got it, the strategy asks for one increment
more. If either resource is held, or the resulting state is unsafe, the move
happens anyway and the request for more is dropped.

One increment of four resources, refused as a unit, was rejected because it
makes `approach` unreachable. A train that can only move while holding two
blocks ahead always holds two blocks ahead, so it always shows `clear`, and
the middle aspect appears only within two blocks of a destination where the
route runs out. That says "nearly there", not "be ready to stop". The amber
lamp is the report that the extra lock was not obtained
([ADR-0025](0025-a-signal-is-what-the-dispatcher-tells-the-driver.md)).

The extra is an ordinary grant, a transit with its far block, which is what
ADR-0026 already calls it. Locking the block without its transit was rejected:
`clear` would then be a promise the dispatcher cannot keep, because the train
must still win the transit on arrival and may have to stop at the end of the
block it was told to run through at speed.

Both grants are published as separate `lock_granted` events rather than one of
four resources. A grant is a transit with its far block, which is what Lemma 1
rests on, and the trace shows the extra as the same shape of grant made early.

## What the check was not being told

`safe()` modelled each active train as occupying one block, `cur(t)`, and
never saw the lock table. That was exact while every grant locked no further
than `cur(t)`. It stops being exact once a train holds a block it is not in:

```
X granted at b2, also holds b3.
the view reported   cur[X] = b2,  rem[X] = [b3, b4, ...]
safe() computed     frozen = { cur[u] }   -- b3 was not in it
```

Another train's route through `b3` would be judged feasible, though `b3` is
locked to `X` and it will be refused there. So `safe()` takes `held(t)` as
well, and a frozen train blocks every block it holds. A train's own held
blocks do not obstruct itself, as `cur` already did not.

`held(t)` is read off the lock table, not off the strategy's depth. The check
stays a description of the state it is handed rather than of who asked, so a
strategy reaching further ahead cannot make it optimistic by accident.

This corrects ADR-0026, which carries a banner. Its conclusion stands: target
two blocks ahead, never a third. Its reason for believing the safety core
untouched does not. "Depth is a property of the strategy asking, not of the
layer answering" held only because the answering layer could not see locks,
which is the same as saying it could not see depth.

In [SAFETY.md](../dispatcher/SAFETY.md) the Progress argument says every block
on `rem(t₁)` is free or held by `t₁` itself. That is now established by
`feasible(t₁, ∅)`; before, it was assumed.

## Lemma 1 survives, instantaneous admissibility does not

A train holding a transit still holds the block beyond it, so it can always
complete the crossing without waiting on anyone, and a waiting train still
waits holding only a block. No circular wait runs through a transit, and
transits stay out of `safe()`.

The sentence beneath Lemma 1 does change. A transit is now held while the
train sits in the block before it, so a conflicting transit at that connection
is refused for as long as the train takes to get there rather than for an
instant. This costs throughput, not safety: the refused train waits holding
only its block, and the holder moves on regardless.

## It costs throughput, and today it buys nothing back

Measured on the named scenarios when depth two landed:

| | depth 1 | depth 2 | `FullRoute` |
| --- | --- | --- | --- |
| `gotthard/saturation` makespan | 16 | 20 | 24 |
| `gotthard/saturation` mean latency | 9.27 | 12.73 | 13.93 |
| `gotthard/meet` makespan | 3 | 5 | 5 |

`gotthard/meet` stops splitting. Its routes are two blocks long, so an
increment plus the one asked for ahead of it is the whole route, and
`Incremental` becomes `FullRoute` there. The two part company again as soon as
a route is longer than the lookahead.

None of this is bought back yet. Every transit costs one tick
([ADR-0027](0027-the-tick-is-the-simulators-grant-boundary.md),
[MILESTONE-1.md](../MILESTONE-1.md)), so a train at `clear` and a train at
`approach` advance at the same rate. The benefit ADR-0026 claims, running
through a block at speed, cannot appear in a model without speed. Depth two is
recorded as a prerequisite: it is what makes the three aspects real, and its
cost reverses only when transits take time proportional to length and speed.

Reverting to depth one would restore the numbers and cost the `clear` aspect.
That trade was put to the owner with these measurements and taken.
